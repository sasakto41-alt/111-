"""Ввод через SendInput (Unicode-посимвольно) и нажатие комбинаций.

ВАЖНО: Enter никогда не отправляется — пользователь подтверждает чат сам.
MTH_DRYRUN=1 — режим отладки: ввод только логируется.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

DRY_RUN = os.getenv("MTH_DRYRUN") == "1"

_is_windows = sys.platform == "win32"
if _is_windows:
    _user32 = ctypes.windll.user32

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_ubyte * 32)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTUNION)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_EXTENDEDKEY = 0x0001


def _log(msg: str) -> None:
    if DRY_RUN:
        print(f"[injector:DRY] {msg}", flush=True)


# ------------------------------------------------------------------ unicode --
def _send_unicode_char(ch: str) -> bool:
    extra = ctypes.POINTER(ctypes.c_ulong)()
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTUNION(ki=KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, extra)),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTUNION(
            ki=KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, extra)
        ),
    )
    arr = (INPUT * 2)(down, up)
    sent = _user32.SendInput(2, arr, ctypes.sizeof(INPUT))
    return sent == 2


def type_text_unicode(text: str, char_delay_ms: int = 4) -> None:
    """Печатает текст посимвольно. Переводы строк пропускаются (Enter не нажимается)."""
    if not text:
        return
    if not _is_windows:
        _log(f"type_text_unicode({text!r})")
        return
    for ch in text:
        if ch in ("\n", "\r"):
            _log("пропущен перевод строки (Enter не отправляется)")
            continue
        _send_unicode_char(ch)
        time.sleep(max(0.0, char_delay_ms) / 1000.0)
    _log(f"напечатано {len(text)} символов")


# ------------------------------------------------------------------ combo --
_VK_MAP = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "tab": 0x09, "space": 0x20, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}


def _vk_for(key: str) -> int:
    key = (key or "").strip().lower()
    if not key:
        return 0
    if key in ("enter", "return"):
        return 0
    if key in _VK_MAP:
        return _VK_MAP[key]
    if len(key) == 1 and key.isalpha():
        return 0x41 + (ord(key) - ord("a"))
    if len(key) == 1 and key.isdigit():
        return 0x30 + int(key)
    if key.startswith("f") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1
    return 0


def _press_key(vk: int, extended: bool = False) -> None:
    extra = ctypes.POINTER(ctypes.c_ulong)()
    flags_down = KEYEVENTF_EXTENDEDKEY if extended else 0
    flags_up = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    down = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(vk, 0, flags_down, 0, extra)))
    up = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=KEYBDINPUT(vk, 0, flags_up, 0, extra)))
    arr = (INPUT * 2)(down, up)
    _user32.SendInput(2, arr, ctypes.sizeof(INPUT))


def press_combo(combo: str) -> None:
    """Нажимает комбинацию вида 't', 'f6', 'ctrl+v'. Enter заблокирован намеренно."""
    combo = (combo or "").strip().lower()
    if not combo:
        return
    parts = [p for p in combo.split("+") if p]
    if not parts:
        return
    if parts[-1] in ("enter", "return"):
        _log("ЗАБЛОКИРОВАНО: Enter не отправляется по дизайну")
        return
    if not _is_windows:
        _log(f"press_combo({combo!r})")
        return
    mods = [p for p in parts[:-1] if p in ("ctrl", "alt", "shift", "win")]
    key = parts[-1]
    vk = _vk_for(key)
    if not vk:
        _log(f"неизвестная клавиша: {key!r}")
        return
    for m in mods:
        _press_key(_VK_MAP[m])
        time.sleep(0.02)
    _press_key(vk)
    time.sleep(0.02)
    for m in reversed(mods):
        # отпускаем модификаторы
        extra = ctypes.POINTER(ctypes.c_ulong)()
        up = INPUT(
            type=INPUT_KEYBOARD,
            union=_INPUTUNION(ki=KEYBDINPUT(_VK_MAP[m], 0, KEYEVENTF_KEYUP, 0, extra)),
        )
        _user32.SendInput(1, (INPUT * 1)(up), ctypes.sizeof(INPUT))
    _log(f"press_combo({combo!r})")


def press_ctrl_v() -> None:
    press_combo("ctrl+v")
