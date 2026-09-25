"""Работа с окнами Windows: активное окно, фокус, поиск целевого окна игры.

Все WinAPI-вызовы безопасно отключаются на других платформах (smoke-тесты).
"""
from __future__ import annotations

import ctypes
import os
import sys
from typing import List, Optional

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SW_RESTORE = 9

_is_windows = sys.platform == "win32"
if _is_windows:
    try:
        import ctypes.wintypes as wt

        _user32 = ctypes.windll.user32
        _kernel32 = ctypes.windll.kernel32
        _ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    except Exception:  # pragma: no cover
        _is_windows = False


# ------------------------------------------------------------------ helpers --
def _process_exe(hwnd) -> str:
    """Путь к exe процесса-владельца окна."""
    if not _is_windows:
        return ""
    try:
        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h:
            return ""
        try:
            size = ctypes.wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            _kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def get_window_title(hwnd) -> str:
    if not _is_windows or not hwnd:
        return ""
    try:
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def get_window_rect(hwnd: int) -> Optional[tuple]:
    """(left, top, right, bottom) окна или None (вне Windows/ошибка)."""
    if not _is_windows or not hwnd:
        return None
    try:
        import ctypes.wintypes as wt

        rc = wt.RECT()
        if _user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return (int(rc.left), int(rc.top), int(rc.right), int(rc.bottom))
    except Exception:
        pass
    return None


# ------------------------------------------------------------- foreground --
def get_foreground_hwnd() -> int:
    if not _is_windows:
        return 0
    try:
        return int(_user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def get_foreground_window() -> Optional[dict]:
    hwnd = get_foreground_hwnd()
    if not hwnd:
        return None
    return {"hwnd": hwnd, "title": get_window_title(hwnd), "exe": _process_exe(hwnd)}


# -------------------------------------------------------- поиск целевого окна --
def find_windows(title_contains: str = "", exe_contains: str = "") -> List[dict]:
    """Перечисляет видимые окна (EnumWindows) и фильтрует по подстрокам.

    Возвращает список {"hwnd": int, "title": str, "exe": str}.
    """
    result: List[dict] = []
    if not _is_windows:
        return result
    t = (title_contains or "").strip().lower()
    e = (exe_contains or "").strip().lower()
    try:

        def _cb(hwnd, _lparam):
            try:
                if not _user32.IsWindowVisible(hwnd):
                    return True
                title = get_window_title(hwnd)
                if not title:
                    return True
                exe = _process_exe(hwnd)
                if t and t not in title.lower():
                    return True
                if e and e not in (exe or "").lower():
                    return True
                result.append({"hwnd": int(hwnd), "title": title, "exe": exe})
            except Exception:
                pass
            return True

        _user32.EnumWindows(_ENUMPROC(_cb), 0)
    except Exception:
        pass
    return result


def find_target_window(title_contains: str = "", exe_contains: str = "") -> int:
    """hwnd первого окна, подходящего под критерии целевого окна игры, или 0."""
    wins = find_windows(title_contains, exe_contains)
    return wins[0]["hwnd"] if wins else 0


# ------------------------------------------------ окно игры (общие маркеры) --
# Используются уведомлением о госволне, таймером до госволны и автопереходом
# после копирования (v3.8.0: единая точка автопоиска вместо трёх копий).
GAME_TITLE_MARKERS = ("majestic", "rage", "gta", "grand theft auto")
GAME_EXE_MARKERS = ("majestic", "ragemp", "rage_mp", "rageplugin", "gta5", "gta")


def find_game_window(target_title: str = "", target_exe: str = "") -> int:
    """Найти окно игры: сначала по настройке «Окно игры», затем по маркерам."""
    try:
        t = (target_title or "").strip()
        e = (target_exe or "").strip()
        if t or e:
            hwnd = find_target_window(t, e)
            if hwnd:
                return hwnd
        for marker in GAME_TITLE_MARKERS:
            hwnd = find_target_window(marker, "")
            if hwnd:
                return hwnd
        for marker in GAME_EXE_MARKERS:
            hwnd = find_target_window("", marker)
            if hwnd:
                return hwnd
    except Exception:
        pass
    return 0


# ----------------------------------------------------------------- фокус --
def _window_pid(hwnd) -> int:
    """PID процесса-владельца окна (0 при ошибке/не Windows)."""
    if not _is_windows or not hwnd:
        return 0
    try:
        import ctypes.wintypes as wt

        pid = wt.DWORD(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def focus_window(hwnd: int) -> bool:
    """Принудительно поднимает и фокусирует окно (AttachThreadInput + топмост).

    v3.6.0 (починка «всё зависает»): к потокам СОБСТВЕННОГО процесса
    AttachThreadInput больше не применяется. Раньше рабочий поток отправки
    мог прикрепить свой ввод к GUI-потоку программы (когда активным было
    наше окно-оверлей) — взаимные блокировки этих потоков подвешивали
    интерфейс. Если активное окно — наше, достаточно простого
    SetForegroundWindow: разрешение на смену фокуса есть у самого процесса.
    """
    if not _is_windows or not hwnd:
        return False
    try:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        fg = _user32.GetForegroundWindow()
        cur_tid = _kernel32.GetCurrentThreadId()
        my_pid = os.getpid()
        fg_tid = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
        target_tid = _user32.GetWindowThreadProcessId(hwnd, None)
        fg_own = bool(fg) and _window_pid(fg) == my_pid
        tgt_own = _window_pid(hwnd) == my_pid
        attached_fg = attached_target = False
        try:
            if fg and fg_tid and fg_tid != cur_tid and not fg_own:
                attached_fg = bool(_user32.AttachThreadInput(cur_tid, fg_tid, True))
            if target_tid and target_tid != cur_tid and not tgt_own:
                attached_target = bool(_user32.AttachThreadInput(cur_tid, target_tid, True))
            ok = bool(_user32.SetForegroundWindow(hwnd))
        finally:
            if attached_fg:
                _user32.AttachThreadInput(cur_tid, fg_tid, False)
            if attached_target:
                _user32.AttachThreadInput(cur_tid, target_tid, False)
        if not ok:
            _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            _user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            ok = bool(_user32.SetForegroundWindow(hwnd))
        return ok
    except Exception:
        return False


# --------------------------------------------------------- белый список --
def is_window_allowed(whitelist_enabled: bool, exes: List[str], titles: List[str],
                      fg: Optional[dict] = None) -> bool:
    if not whitelist_enabled:
        return True
    fg = fg or get_foreground_window()
    if not fg:
        return False
    exe_l = (fg.get("exe") or "").lower()
    title_l = (fg.get("title") or "").lower()
    for exe in exes or []:
        if exe and exe.strip().lower() in exe_l:
            return True
    for t in titles or []:
        if t and t.strip().lower() in title_l:
            return True
    return False
