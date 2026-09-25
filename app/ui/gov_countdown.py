"""Живой таймер «До Госволны: ММ:СС» поверх игры (v3.8.0).

Маленькая панель в углу экрана игры: сколько осталось до ближайшего
БУДУЩЕГО слота, который подобрало приложение («Подшитать время» /
«Подобрать время»). Обновляется каждую секунду. Показывается, когда до
слота осталось меньше N минут (настройка «Таймер до госволны»).

Свойства — те же, что у красного уведомления (v3.7.0):
  • НЕ забирает фокус (WA_ShowWithoutActivating + WS_EX_NOACTIVATE) —
    игра не сворачивается и не дёргается;
  • НЕ перехватывает мышь (WS_EX_TRANSPARENT) — клики проходят в игру;
  • TOPMOST поверх безрамочной игры, монитор выбирается по окну игры
    (настройка «Окно игры» → автопоиск Majestic/RAGE/GTA);
  • исчезает, когда слот закончился (наступило время) или выключен
    в настройках.

Тик таймера — свой QTimer раз в секунду (лёгкий: разбор нескольких
слотов без обращения к Windows API, подъём окна — одно обращение).
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .. import window_utils
from ..journal import log
from .gov_wave import gov_alert_state, now_in_tz

_COUNTDOWN_QSS = """
#govCountdownRoot {
    background: #0B1220;
    border: 2px solid #22D3EE;
    border-radius: 12px;
}
#govCountdownCap {
    color: #8FA3C4;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
}
#govCountdownTime {
    color: #22D3EE;
    font-size: 22px;
    font-weight: 800;
    background: transparent;
}
"""


def format_left(minutes: float) -> str:
    """Минуты (float) → «02:47» или «1:05:00», если больше часа."""
    total = max(0, int(round(float(minutes) * 60)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class GovCountdownBadge(QWidget):
    """Автономная панель-таймер (top-level, без родителя, не мешает игре)."""

    def __init__(self, settings_getter, parent=None):
        super().__init__(None)
        self._settings_getter = settings_getter
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        # таймер не должен становиться активным окном и красть фокус
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setObjectName("govCountdownRoot")
        self.setStyleSheet(_COUNTDOWN_QSS)
        self.setFixedSize(250, 66)

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(0)
        self.lbl_cap = QLabel("⏳ ДО ГОСВОЛНЫ")
        self.lbl_cap.setObjectName("govCountdownCap")
        self.lbl_cap.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl_cap)
        self.lbl_time = QLabel("00:00")
        self.lbl_time.setObjectName("govCountdownTime")
        self.lbl_time.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl_time, 1)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()
        self.hide()

    # ----------------------------------------------------------------- тик --
    def _tick(self) -> None:
        """Раз в секунду: пересчитать остаток и решить — показывать или нет."""
        try:
            s = self._settings_getter() if self._settings_getter else None
            if s is None or not getattr(s, "gov_countdown_enabled", True):
                self._hide_now()
                return
            try:
                window_min = int(getattr(s, "gov_countdown_minutes", 15))
            except Exception:
                window_min = 15
            st = gov_alert_state(s, minutes_before=max(5, min(60, window_min)))
            if not st:
                self._hide_now()
                return
            slot, left = st
            self.lbl_time.setText(format_left(left))
            if not self.isVisible():
                self._place(s)
                self.show()
                self._apply_noactivate_clickthrough()
                log(f"таймер: показан — до слота {slot} осталось {format_left(left)}")
            else:
                # игра может пере-поднять своё окно — держим таймер поверх
                self._stay_on_top()
        except Exception as e:
            log(f"таймер до госволны: ошибка {e}")

    def _hide_now(self) -> None:
        if self.isVisible():
            log("таймер: скрыт (слот далеко/прошёл либо выключен)")
        self.hide()

    # ------------------------------------------------------------- позиция --
    def _place(self, settings) -> None:
        """Появиться в ПРАВОМ верхнем углу монитора окна игры."""
        scr = None
        try:
            hwnd = window_utils.find_game_window(
                (getattr(settings, "target_title", "") or ""),
                (getattr(settings, "target_exe", "") or ""),
            )
            rect = window_utils.get_window_rect(hwnd) if hwnd else None
            if rect:
                l, t, r, b = rect
                g = QRect(l, t, max(1, r - l), max(1, b - t))
                for sc in QApplication.screens():
                    if sc.geometry().intersects(g):
                        scr = sc
                        break
        except Exception:
            scr = None
        if scr is None:
            scr = QApplication.primaryScreen()
        if scr is None:
            return
        gg = scr.availableGeometry()
        self.move(
            gg.x() + gg.width() - self.width() - 28,
            gg.y() + 84,
        )

    # ------------------------------------------------- не активироваться --
    def _stay_on_top(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            if hwnd:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, window_utils.HWND_TOPMOST, 0, 0, 0, 0,
                    window_utils.SWP_NOMOVE | window_utils.SWP_NOSIZE
                    | window_utils.SWP_SHOWWINDOW,
                )
        except Exception:
            pass

    def _apply_noactivate_clickthrough(self) -> None:
        """Windows: таймер никогда не получает фокус и пропускает клики."""
        if sys.platform != "win32":
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if not hwnd:
                return
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
        except Exception as e:
            log(f"таймер: ex-style не применён ({e})")

    def dismiss(self) -> None:
        self._hide_now()
