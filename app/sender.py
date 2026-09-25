"""Отправка текста в игру.

Режимы вставки (Settings.inject_method):
  unicode — открыть чат (T) и печатать посимвольно;
  ctrlv   — открыть чат (T), скопировать текст, нажать Ctrl+V;
  copy    — v3.2: никаких клавиш, только скопировать в буфер и переключить
            в окно игры (пользователь сам жмёт T и вставляет Ctrl+V).

Целевое окно игры (Settings.target_title/target_exe, v3.2): если задано,
программа сама находит окно игры через EnumWindows и переключается на него
перед нажатием T / после копирования. Fallback — окно, активное до оверлея.

v3.6.0 (починка «нажимаю кнопку — всё зависает»):
  • скрытие оверлеев больше НЕ вызывается из рабочего потока через
    QTimer.singleShot — вместо этого сигнал hide_overlays, который Qt сам
    маршалирует в GUI-поток (очередное соединение). Раньше _do_hide
    выполнялся в рабочем потоке: фокус/AttachThreadInput из чужого потока
    могли взаимно блокироваться с GUI-потоком — окна «зависали»;
  • защита от наложения отправок (busy-guard): пока предыдущая отправка
    не завершилась, новая игнорируется — раньше несколько нажатий
    складывались в очередь и печатали каскадом;
  • каждый этап отправки пишется в журнал с длительностью — если на
    какой-то машине всё ещё «подвисает», в error.log видно этап.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, Slot

from . import injector, window_utils
from .journal import log
from .models import Settings, TextEntry

# Маркеры окна игры для автопоиска, если в настройках цель НЕ задана (v3.4.2)
_GAME_TITLE_MARKERS = ("majestic", "rage", "gta", "grand theft auto")
_GAME_EXE_MARKERS = ("majestic", "ragemp", "rage_mp", "rageplugin", "gta5", "gta")


class Sender(QObject):
    copy_requested = Signal(str)   # положить текст в буфер (выполняется в GUI-потоке)
    hide_overlays = Signal()       # v3.6.0: скрыть оверлеи (маршалируется в GUI-поток)
    status = Signal(str)           # сообщение пользователю
    used = Signal(str)             # id использованной фразы (статистика)

    def __init__(self, settings_getter: Callable[[], Settings],
                 get_prev_foreground: Callable[[], int] = lambda: 0,
                 is_overlay_visible: Callable[[], bool] = lambda: False,
                 hide_overlay: Optional[Callable[[], None]] = None,
                 parent=None):
        super().__init__(parent)
        self._settings_getter = settings_getter
        self._get_prev_foreground = get_prev_foreground
        self._is_overlay_visible = is_overlay_visible
        # параметр hide_overlay оставлен для совместимости, но НЕ используется:
        # скрытие идёт через сигнал hide_overlays (потокобезопасно)
        self._busy = False

    # ----------------------------------------------------- целевое окно игры --
    def _autodetect_game_hwnd(self) -> int:
        """Автопоиск окна игры по известным маркерам (когда цель не задана)."""
        try:
            for marker in _GAME_TITLE_MARKERS:
                hwnd = window_utils.find_target_window(marker, "")
                if hwnd:
                    log(f"автопоиск: окно игры найдено по заголовку «{marker}» (hwnd={hwnd})")
                    return hwnd
            for marker in _GAME_EXE_MARKERS:
                hwnd = window_utils.find_target_window("", marker)
                if hwnd:
                    log(f"автопоиск: окно игры найдено по процессу «{marker}» (hwnd={hwnd})")
                    return hwnd
        except Exception:
            pass
        return 0

    def _resolve_target_hwnd(self, settings: Settings) -> int:
        title = (getattr(settings, "target_title", "") or "").strip()
        exe = (getattr(settings, "target_exe", "") or "").strip()
        if title or exe:
            try:
                return window_utils.find_target_window(title, exe)
            except Exception:
                return 0
        # цель не задана — пробуем найти игру сами (v3.4.2: перенос в игру
        # после копирования работал только при ручной настройке окна)
        return self._autodetect_game_hwnd()

    def _focus_game(self, settings: Settings, prev_hwnd: int) -> int:
        """Фокус на окно игры (по настройке) или на прежнее окно. Возвращает hwnd."""
        t0 = time.monotonic()
        target = self._resolve_target_hwnd(settings)
        if target:
            if window_utils.get_foreground_hwnd() != target:
                if window_utils.focus_window(target):
                    time.sleep(0.25)
                    log(f"фокус: игра (hwnd={target}) за {time.monotonic() - t0:.2f} с")
                    return target
            else:
                return target
        if prev_hwnd:
            try:
                if window_utils.focus_window(prev_hwnd):
                    time.sleep(0.2)
                    log(f"фокус: прежнее окно (hwnd={prev_hwnd})")
                    return prev_hwnd
            except Exception:
                pass
        log(f"фокус: окно игры НЕ найдено ({time.monotonic() - t0:.2f} с)")
        return 0

    # ----------------------------------------------------------------- send --
    def send_text(self, entry: TextEntry) -> None:
        """Точка входа из рабочего потока. С защитой от наложения отправок."""
        if self._busy:
            log("отправка: предыдущая ещё выполняется — запрос пропущен")
            return
        self._busy = True
        t0 = time.monotonic()
        try:
            self._send_text_impl(entry)
        finally:
            self._busy = False
            log(f"отправка завершена за {time.monotonic() - t0:.2f} с")

    def _send_text_impl(self, entry: TextEntry) -> None:
        settings = self._settings_getter()
        method = getattr(settings, "inject_method", "unicode") or "unicode"
        log(f"отправка «{entry.title or entry.text[:24]}»: способ={method}")

        prev_hwnd = 0
        try:
            if self._is_overlay_visible():
                prev_hwnd = int(self._get_prev_foreground() or 0)
                # v3.6.0: сигнал — Qt сам выполнит скрытие в GUI-потоке
                self.hide_overlays.emit()
                time.sleep(0.25)
        except Exception:
            pass

        # --- v3.2: режим «Копировать в буфер» — никаких клавиш вообще ---
        if method == "copy":
            self.copy_requested.emit(entry.text)
            time.sleep(0.3)                   # даём GUI-потоку положить в буфер
            focused = self._focus_game(settings, prev_hwnd)
            if focused:
                self.status.emit(
                    f"Скопировано: {entry.title or 'фраза'} — вы в игре. "
                    "Жмите T и вставляйте Ctrl+V (Enter сами)"
                )
            else:
                self.status.emit(
                    f"Скопировано: {entry.title or 'фраза'}. Окно игры НЕ найдено — "
                    "переключитесь сами или укажите его в Настройки → «Окно игры»"
                )
            self.used.emit(entry.id)
            return

        # --- обычные режимы: сфокусировать игру и открыть чат ---
        focused = self._focus_game(settings, prev_hwnd)
        if not focused and (getattr(settings, "target_title", "") or "").strip():
            self.status.emit("Окно игры не найдено — проверьте «Настройки → Окно игры»")

        log(f"ввод: клавиша чата «{settings.type_key or 't'}», пауза {settings.pre_delay_ms} мс")
        injector.press_combo(settings.type_key or "t")
        time.sleep(max(0.05, (settings.pre_delay_ms or 1000) / 1000.0))

        if method == "ctrlv":
            self.copy_requested.emit(entry.text)
            time.sleep(0.25)
            injector.press_ctrl_v()
        else:
            t1 = time.monotonic()
            injector.type_text_unicode(entry.text)
            log(f"ввод: напечатано посимвольно за {time.monotonic() - t1:.2f} с")

        self.status.emit(f"Отправлено: {entry.title or entry.text[:32]}")
        self.used.emit(entry.id)


class SendWorker(QObject):
    """Мост: отправка выполняется в рабочем потоке, UI не блокируется."""

    requested = Signal(object)

    def __init__(self, sender: Sender, parent=None):
        super().__init__(parent)
        self.sender = sender
        self.requested.connect(self.send)

    @Slot(object)
    def send(self, entry: TextEntry) -> None:
        try:
            self.sender.send_text(entry)
        except Exception as e:
            try:
                self.sender.status.emit(f"Ошибка отправки: {e}")
            except Exception:
                pass
