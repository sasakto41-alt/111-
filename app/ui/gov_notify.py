"""Красное уведомление «скоро госволна» (v3.7.0).

За N минут (по умолчанию 3) до времени, которое подобрало приложение
(settings.gov_last_slots / «Подшитать время»), поверх всего вылетает
КРАСНЫЙ КВАДРАТИК с обратным отсчётом. Свойства уведомления:

  • НЕ забирает фокус (WA_ShowWithoutActivating + WS_EX_NOACTIVATE) —
    игра не сворачивается и не дёргается;
  • НЕ перехватывает мышь (WS_EX_TRANSPARENT) — клики проходят в игру;
  • поднимается TOPMOST поверх безрамочной игры и появляется на мониторе
    окна игры (по настройке «Окно игры» или автопоиску Majestic/RAGE/GTA);
  • исчезает само через 30 секунд (или когда время волны наступает).

Опросом времени занимается MainWindow (QTimer каждые 5 секунд) —
«опроси меня» выполнено: приложение само следит за часами.
"""
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .. import window_utils
from ..journal import log

# маркеры автопоиска окна игры (как в sender.py — если «Окно игры» не задана)
_GAME_TITLE_MARKERS = ("majestic", "rage", "gta", "grand theft auto")
_GAME_EXE_MARKERS = ("majestic", "ragemp", "rage_mp", "gta5", "gta")

_NOTIFY_QSS = """
#govNotifyRoot {
    background: #DC2626;
    border: 2px solid #FCA5A5;
    border-radius: 14px;
}
#govNotifyTitle {
    color: #FFFFFF;
    font-size: 21px;
    font-weight: 800;
    background: transparent;
}
#govNotifySub {
    color: #FEE2E2;
    font-size: 13px;
    background: transparent;
}
"""


class GovNotifyToast(QWidget):
    """Автономное красное уведомление (top-level, без родителя)."""

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        # уведомление НЕ должно становиться активным окном и красть фокус
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setObjectName("govNotifyRoot")
        self.setStyleSheet(_NOTIFY_QSS)
        self.setFixedSize(440, 116)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 18, 12)
        v.setSpacing(4)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("govNotifyTitle")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl_title)
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("govNotifySub")
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        self.lbl_sub.setWordWrap(True)
        v.addWidget(self.lbl_sub, 1)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self.hide()

    # ---------------------------------------------------------------- показ --
    def popup(self, minutes_left: float, slot: str, org: str = "",
              target_title: str = "", target_exe: str = "",
              ms: int = 30000) -> None:
        """Показать уведомление: слот времени и сколько минут осталось."""
        try:
            left = max(0, float(minutes_left))
        except Exception:
            left = 0.0
        if left >= 0.5:
            n = max(1, int(round(left)))    # 2.4 мин → «~2 МИН», 1.6 → «~2 МИН»
            self.lbl_title.setText(f"⚡ ГОСВОЛНА ЧЕРЕЗ ~{n} МИН")
        else:
            self.lbl_title.setText("⚡ ГОСВОЛНА НАЧИНАЕТСЯ")
        org_part = f" · {org}" if (org or "").strip() else ""
        self.lbl_sub.setText(
            f"Ваше время: {slot}{org_part} — готовьте команду «Занять волну»"
        )
        self._place(target_title, target_exe)
        self.show()
        self.raise_()
        self._apply_noactivate_clickthrough()
        self._hide_timer.start(max(5000, int(ms)))
        log(f"уведомление: госволна скоро — слот {slot}, осталось ~{left:.1f} мин")

    # ------------------------------------------------------------- позиция --
    def _place(self, target_title: str = "", target_exe: str = "") -> None:
        """Появиться на мониторе окна игры (или на основном экране)."""
        scr = None
        try:
            hwnd = self._game_hwnd(target_title, target_exe)
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
            gg.x() + (gg.width() - self.width()) // 2,
            gg.y() + 84,
        )

    def _game_hwnd(self, target_title: str, target_exe: str) -> int:
        try:
            if (target_title or "").strip() or (target_exe or "").strip():
                hwnd = window_utils.find_target_window(
                    (target_title or "").strip(), (target_exe or "").strip()
                )
                if hwnd:
                    return hwnd
            for marker in _GAME_TITLE_MARKERS:
                hwnd = window_utils.find_target_window(marker, "")
                if hwnd:
                    return hwnd
            for marker in _GAME_EXE_MARKERS:
                hwnd = window_utils.find_target_window("", marker)
                if hwnd:
                    return hwnd
        except Exception:
            pass
        return 0

    # ------------------------------------------- не активироваться/не мешать --
    def _apply_noactivate_clickthrough(self) -> None:
        """Windows: уведомление никогда не получает фокус и пропускает клики."""
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
            log(f"уведомление: ex-style не применён ({e})")

    def dismiss(self) -> None:
        self._hide_timer.stop()
        self.hide()
