"""F9-цикл «госволна → одобрение → скриншот → Discord» (v3.10.0): UI.

DiscordConfirmDialog — окно подтверждения запуска (как у макроса F8):
  • время госволны + список шагов;
  • НОМЕР ГОСВОЛНЫ «N/13» — подставляется следующий после отправленного
    (локальный счётчик), НО можно исправить руками прямо в окне —
    это выбранный пользователем способ определения номера;
  • «Да» блокируется на 5 секунд (защита от случайного нажатия).

DiscordWaitToast — маленькая панель «ЖДУ ОДОБРЕНИЕ» поверх игры:
  • НЕ забирает фокус и НЕ перехватывает мышь (клики проходят в игру);
  • показывает обратный отсчёт до таймаута и подсказку «F10 — отмена»;
  • живёт, пока программа ищет уведомление об одобрении (OCR).
"""
from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from .. import window_utils
from ..journal import log
from ..models import format_discord_message
from .gov_overlay import _overlay_flags, move_to_screen_of, raise_topmost
from .gov_wave import gov_slots_for, plan_macro_sequence_keys
from .theme import build_qss

_DIALOG_QSS = """
#dcDialog { background: #0B1220; border: 2px solid #3B82F6; border-radius: 14px; }
#dcPreview { color: #22D3EE; font-size: 16px; font-weight: 800; background: transparent; }
"""

_WAIT_QSS = """
#dcWaitRoot {
    background: #1E3A8A;
    border: 2px solid #22D3EE;
    border-radius: 14px;
}
#dcWaitTitle { color: #FFFFFF; font-size: 18px; font-weight: 800; background: transparent; }
#dcWaitSub { color: #BAE6FD; font-size: 12px; background: transparent; }
"""


class DiscordConfirmDialog(QWidget):
    """Окно подтверждения F9-цикла: время + шаги + номер с правкой."""

    confirmed = Signal(int)   # выбранный номер госволны
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._remaining = 0
        self._prev_hwnd = 0
        _overlay_flags(self)
        self.setObjectName("dcDialog")
        self.setWindowTitle("Запуск госволны + Discord")
        self.setStyleSheet(build_qss() + _DIALOG_QSS)
        self.setFixedSize(680, 500)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        self.lbl_action = QLabel("")
        f = self.lbl_action.font()
        f.setBold(True)
        f.setPointSize(11)
        self.lbl_action.setFont(f)
        self.lbl_action.setWordWrap(True)
        root.addWidget(self.lbl_action)

        self.lbl_slots = QLabel("")
        sf = self.lbl_slots.font()
        sf.setPointSize(13)
        sf.setBold(True)
        self.lbl_slots.setFont(sf)
        root.addWidget(self.lbl_slots)

        self.lbl_steps = QLabel("")
        self.lbl_steps.setObjectName("hint")
        self.lbl_steps.setWordWrap(True)
        root.addWidget(self.lbl_steps, 1)

        h_num = QHBoxLayout()
        lbl_num = QLabel("Номер госволны:")
        lbl_num.setStyleSheet("background: transparent;")
        h_num.addWidget(lbl_num)
        self.sp_number = QSpinBox()
        self.sp_number.setRange(1, 999)
        self.sp_number.setMinimumWidth(90)
        self.sp_number.valueChanged.connect(self._update_preview)
        h_num.addWidget(self.sp_number)
        h_num.addStretch(1)
        root.addLayout(h_num)

        self.lbl_preview = QLabel("")
        self.lbl_preview.setObjectName("dcPreview")
        root.addWidget(self.lbl_preview)

        h = QHBoxLayout()
        self.btn_yes = QPushButton("Да — начать")
        self.btn_yes.setObjectName("primary")
        self.btn_yes.setEnabled(False)
        self.btn_yes.clicked.connect(self._on_yes)
        h.addWidget(self.btn_yes, 1)
        self.btn_no = QPushButton("Нет")
        self.btn_no.setObjectName("ghost")
        self.btn_no.clicked.connect(self._on_no)
        h.addWidget(self.btn_no, 1)
        root.addLayout(h)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("hint")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ показ --
    def open_dialog(self) -> None:
        s = self.store.settings
        plan = plan_macro_sequence_keys(s)
        self._plan = plan
        n = len(plan)
        self.lbl_action.setText(
            f"F9-цикл: {n} " + ("шаг" if n == 1 else "шага" if 2 <= n % 10 <= 4
                                and (n % 100 < 10 or n % 100 > 20) else "шагов")
            + " → одобрение → скриншот → Discord"
        )
        slots = gov_slots_for(s)
        self.lbl_slots.setText("Время: " + " ".join(slots))

        # где ждём одобрения: после ПОСЛЕДНЕГО шага «/report» (или в конце)
        wait_idx = n - 1
        for i, (key, _label, _text) in enumerate(plan):
            if key == "step4":
                wait_idx = i
        self._wait_idx = wait_idx

        lines = []
        for i, (key, label, cmd) in enumerate(plan):
            short = cmd if len(cmd) <= 90 else cmd[:90] + "…"
            mark = "   ← после этого ждём одобрение" if i == wait_idx else ""
            lines.append(f"{i + 1}) {label}{mark}\n     {short}")
        self.lbl_steps.setText("\n".join(lines) or "(пусто — соберите шаги в меню Госволны)")

        # номер: следующий за последним ОТПРАВЛЕННЫМ (можно исправить руками)
        try:
            counter = int(getattr(s, "discord_wave_counter", 0) or 0)
        except Exception:
            counter = 0
        self.sp_number.setValue(counter + 1)
        self._update_preview(self.sp_number.value())

        try:
            sec = int(getattr(s, "gov_macro_confirm_sec", 5))
        except Exception:
            sec = 5
        self._remaining = max(0, sec)
        self._update_yes_button()

        try:
            tmo = int(getattr(s, "discord_timeout_min", 5))
        except Exception:
            tmo = 5
        try:
            cancel_hk = (getattr(s, "discord_cancel_hotkey", "f10") or "f10").upper()
        except Exception:
            cancel_hk = "F10"
        self.lbl_hint.setText(
            f"«Да» станет активной через {self._remaining} с. После шага «/report» "
            f"программа будет ждать одобрение объявления (распознавание экрана, "
            f"до {tmo} мин; {cancel_hk} — отмена). Когда одобрение появится — "
            f"скриншот всего экрана уйдёт в Discord (текущий канал). Esc — «Нет»."
        )

        self._prev_hwnd = window_utils.get_foreground_hwnd()
        move_to_screen_of(self, self._prev_hwnd)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        raise_topmost(self)
        log(f"F9-цикл: окно подтверждения показано ({n} шагов, ожидание после "
            f"шага {wait_idx + 1}; номер {self.sp_number.value()})")
        if self._remaining > 0:
            self._timer.start()

    def _update_preview(self, *args) -> None:
        self.lbl_preview.setText(
            f"Будет отправлено в Discord: «{format_discord_message(self.store.settings, self.sp_number.value())}»"
        )

    def _update_yes_button(self) -> None:
        if self._remaining > 0:
            self.btn_yes.setText(f"Да ({self._remaining} с)")
            self.btn_yes.setEnabled(False)
        else:
            self.btn_yes.setText("Да — начать")
            self.btn_yes.setEnabled(True)

    def _tick(self) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            self._update_yes_button()
        if self._remaining <= 0:
            self._timer.stop()

    # ---------------------------------------------------------------- Да/Нет --
    def _on_yes(self) -> None:
        self._timer.stop()
        number = int(self.sp_number.value())
        log(f"F9-цикл: подтверждён, номер {number}")
        self.hide()
        self.confirmed.emit(number)
        self.closed.emit()

    def _on_no(self) -> None:
        self._timer.stop()
        log("F9-цикл: отменено («Нет»)")
        self._restore_focus()
        self.hide()
        self.closed.emit()

    def _restore_focus(self) -> None:
        if self._prev_hwnd and sys.platform == "win32":
            try:
                window_utils.focus_window(self._prev_hwnd)
            except Exception:
                pass

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:
            self._on_no()
        super().keyPressEvent(ev)


class DiscordWaitToast(QWidget):
    """Панель «ЖДУ ОДОБРЕНИЕ ОБЪЯВЛЕНИЯ» с обратным отсчётом (не крадёт фокус)."""

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setObjectName("dcWaitRoot")
        self.setStyleSheet(_WAIT_QSS)
        self.setFixedSize(460, 96)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(3)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("dcWaitTitle")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl_title)
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("dcWaitSub")
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        v.addWidget(self.lbl_sub)

        self._deadline = 0.0
        self._phase = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start_wait(self, timeout_min: int, cancel_hk: str = "F10") -> None:
        self._deadline = time.monotonic() + max(1, int(timeout_min)) * 60
        self._phase = "ОДОБРЕНИЕ ОБЪЯВЛЕНИЯ"
        self.lbl_title.setText("⏳ ЖДУ ОДОБРЕНИЕ ОБЪЯВЛЕНИЯ")
        self._place_game_screen()
        self.show()
        self.raise_()

        # как уведомление о госволне: не активироваться, не мешать игре
        if sys.platform == "win32":
            try:
                GWL_EXSTYLE = -20
                WS_EX_TRANSPARENT = 0x00000020
                WS_EX_NOACTIVATE = 0x08000000
                WS_EX_TOOLWINDOW = 0x00000080
                user32 = ctypes.windll.user32
                hwnd = int(self.winId())
                if hwnd:
                    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    user32.SetWindowLongW(
                        hwnd, GWL_EXSTYLE,
                        style | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                    )
            except Exception as e:
                log(f"F9-ожидание: ex-style не применён ({e})")
        self._cancel_hk = cancel_hk
        self._timer.start()
        self._tick()
        log(f"F9-ожидание: панель показана (таймаут {timeout_min} мин, отмена {cancel_hk})")

    def set_phase(self, text: str) -> None:
        """Сменить заголовок фазы («делаю скриншот…», «отправляю в Discord…»)."""
        self._phase = text
        self.lbl_title.setText(text)

    def stop_wait(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        left = max(0, int(self._deadline - time.monotonic()))
        mm, ss = divmod(left, 60)
        self.lbl_sub.setText(
            f"осталось {mm}:{ss:02d} · F10 — отмена · одобрение ищется на экране"
        )
        if left <= 0:
            self._timer.stop()

    def _place_game_screen(self) -> None:
        """Левый верхний угол монитора игры (уведомление игры появляется там)."""
        scr = None
        try:
            hwnd = window_utils.find_game_window()
            rect = window_utils.get_window_rect(hwnd) if hwnd else None
            if rect:
                l, t, r, b = rect
                from PySide6.QtCore import QRect

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
        self.move(gg.x() + 24, gg.y() + 84)
