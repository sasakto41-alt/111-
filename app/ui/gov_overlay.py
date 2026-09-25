"""Отдельное окно-оверлей «Госволна» и окно подтверждения макроса (v3.5.0).

GovWaveOverlay — ВТОРОЕ меню программы (включается в Настройках, у него своя
клавиша открытия/закрытия). Внутри:
  • кнопка «🕐 Подшитать время» — пересчитывает слоты по правилам памятки
    от текущего времени (с учётом выбранного часового пояса) и обновляет
    все команды;
  • текущее время вещания;
  • команды госволны одним кликом — отправляются тем же способом, что
    задан в «Способе вставки» (обычно: скопировать в буфер и переключить
    в окно игры).

MacroConfirmDialog — окно подтверждения макроса: по своей комбинации
клавиш показывает выбранное время и команду; кнопка «Да» активируется
через N секунд (защита от случайного нажатия), «Нет» закрывает окно.

Оба окна поднимаются поверх безрамочной игры тем же способом, что и
главный оверлей (v3.4.1): TOPMOST + BringWindowToTop + фокус.
"""
from __future__ import annotations

import ctypes
import sys
from typing import List, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from .. import window_utils
from ..journal import log
from ..models import GOV_MACRO_ACTIONS, GOV_MACRO_LABELS, GNEWS_PALETO, GNEWS_SANDY
from .gov_wave import build_commands, gov_slots_for, now_in_tz, resolve_macro_command, suggest_slots
from .theme import OK, build_qss


# ------------------------------------------------------------------ helpers --
def _overlay_flags(widget: QWidget) -> None:
    """Флаги окна-оверлея: своё окно, без рамки, поверх всего."""
    widget.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)


def raise_topmost(widget: QWidget) -> None:
    """Поднять окно ПОВЕРХ всего (включая безрамочную игру) и забрать фокус."""
    try:
        if sys.platform == "win32":
            hwnd = int(widget.winId())
            if hwnd:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, window_utils.HWND_TOPMOST, 0, 0, 0, 0,
                    window_utils.SWP_NOMOVE | window_utils.SWP_NOSIZE
                    | window_utils.SWP_SHOWWINDOW,
                )
                ctypes.windll.user32.BringWindowToTop(hwnd)
                window_utils.focus_window(hwnd)
        else:
            widget.raise_()
            widget.activateWindow()
    except Exception as e:
        log(f"подъём окна: ошибка {e}")


def move_to_screen_of(widget: QWidget, hwnd: int) -> None:
    """Если окно не видно на мониторе, где окно игры — перенести его туда."""
    try:
        if sys.platform != "win32" or not hwnd:
            return
        rect = window_utils.get_window_rect(hwnd)
        if not rect:
            return
        from PySide6.QtCore import QRect

        l, t, r, b = rect
        game_screen = None
        for sc in QApplication.screens():
            if sc.geometry().intersects(QRect(l, t, max(1, r - l), max(1, b - t))):
                game_screen = sc
                break
        if game_screen is None:
            return
        if widget.frameGeometry().intersects(game_screen.geometry()):
            return          # уже видно на этом мониторе — не трогаем
        gg = game_screen.geometry()
        widget.move(
            gg.center().x() - widget.width() // 2,
            gg.center().y() - widget.height() // 2,
        )
        log(f"окно перемещено на монитор игры ({gg.x()},{gg.y()} {gg.width()}x{gg.height()})")
    except Exception as e:
        log(f"перемещение на монитор игры: ошибка {e}")


# ------------------------------------------------------------- меню Госволны --
class GovWaveOverlay(QWidget):
    """Второе меню: команды госволны + кнопка «Подшитать время» (v3.5.0)."""

    closed = Signal()
    slots_updated = Signal()               # время пересчитано — страница перечитает
    trigger_command = Signal(str, str)     # (title, text) — отправить команду

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._prev_hwnd = 0
        self._shown_flag = False
        self._drag_pos = None
        self._cmd_buttons: List[Tuple[str, QPushButton]] = []
        _overlay_flags(self)
        self.setWindowTitle("Госволна")
        self.resize(620, 470)
        self._build_ui()
        self.setStyleSheet(build_qss())
        self._refresh()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- титул-бар (перетаскивается) ---
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(42)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 5, 8, 5)
        h.setSpacing(8)
        icon_lbl = QLabel("ГВ")
        icon_lbl.setStyleSheet(
            "background:#22D3EE;color:#0B1220;border-radius:8px;"
            "font-weight:800;padding:3px 8px;font-size:13px;"
        )
        h.addWidget(icon_lbl)
        title = QLabel("Госволна — команды")
        title.setObjectName("appTitle")
        h.addWidget(title)
        h.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("tbBtn")
        btn_close.clicked.connect(self._do_hide)
        h.addWidget(btn_close)
        root.addWidget(bar)
        self._titlebar = bar
        bar.installEventFilter(self)

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(8)

        # --- верх: кнопка «Подшитать время» + текущее время ---
        top = QHBoxLayout()
        self.btn_time = QPushButton("🕐 Подшитать время")
        self.btn_time.setObjectName("accent")
        self.btn_time.setToolTip(
            "Пересчитать слоты по правилам памятки от текущего времени "
            "(с учётом выбранного пояса) и обновить все команды"
        )
        self.btn_time.clicked.connect(self._reslot)
        top.addWidget(self.btn_time)
        self.lbl_slots = QLabel("")
        self.lbl_slots.setObjectName("appSub")
        top.addWidget(self.lbl_slots, 1)
        v.addLayout(top)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("hint")
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)

        # --- команды ---
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        holder = QWidget()
        self.v_cmds = QVBoxLayout(holder)
        self.v_cmds.setContentsMargins(0, 0, 0, 0)
        self.v_cmds.setSpacing(6)
        self.scroll.setWidget(holder)
        v.addWidget(self.scroll, 1)

        self.lbl_hint = QLabel(
            "Клик по команде — отправить (способ из «Способа вставки»: обычно "
            "скопировать в буфер и переключить в игру). Esc — закрыть."
        )
        self.lbl_hint.setObjectName("hint")
        self.lbl_hint.setWordWrap(True)
        v.addWidget(self.lbl_hint)

        root.addWidget(body, 1)

    # ------------------------------------------------------------ содержимое --
    def _current_slots(self) -> List[str]:
        return gov_slots_for(self.store.settings)

    def _refresh(self) -> None:
        """Перечитать настройки и перестроить кнопки команд."""
        s = self.store.settings
        slots = self._current_slots()
        self.lbl_slots.setText("Время: " + " ".join(slots))
        while self.v_cmds.count():
            it = self.v_cmds.takeAt(0)
            w = it.widget() if it else None
            if w:
                w.setParent(None)
                w.deleteLater()
        self._cmd_buttons = []
        org = (getattr(s, "gov_org", "") or "LSCSD").strip() or "LSCSD"
        rows: List[Tuple[str, str, str]] = []
        for name, cmd in build_commands(org, slots):
            rows.append((name, name, cmd))
        rows.append((
            "gnews_paleto", GOV_MACRO_LABELS["gnews_paleto"],
            getattr(s, "gov_gnews_paleto", "") or GNEWS_PALETO,
        ))
        rows.append((
            "gnews_sandy", GOV_MACRO_LABELS["gnews_sandy"],
            getattr(s, "gov_gnews_sandy", "") or GNEWS_SANDY,
        ))
        for key, label, cmd in rows:
            if not cmd:
                continue
            preview = cmd if len(cmd) <= 58 else cmd[:58] + "…"
            b = QPushButton(f"{label}  —  {preview}")
            b.setToolTip(cmd)
            b.setCursor(Qt.PointingHandCursor)
            b.setObjectName("govCmd")
            b.clicked.connect(
                lambda _=False, t=label, c=cmd: self.trigger_command.emit(t, c)
            )
            self.v_cmds.addWidget(b)
            self._cmd_buttons.append((key, b))
        self.v_cmds.addStretch(1)

    # --------------------------------------------------------- подшить время --
    def _reslot(self) -> None:
        """Кнопка «Подшитать время»: пересчитать слоты от текущего момента."""
        from datetime import datetime

        s = self.store.settings
        slots = suggest_slots(now_in_tz(s))
        s.gov_last_slots = " ".join(slots)
        self.store.save()
        self._refresh()
        self.lbl_status.setStyleSheet(f"color: {OK};")
        self.lbl_status.setText(
            f"✓ Время подшито ({datetime.now():%H:%M:%S}): {' '.join(slots)} — "
            "команды обновлены"
        )
        log(f"госволна: время подшито — {' '.join(slots)}")
        self.slots_updated.emit()

    # ------------------------------------------------------------- показ/скрытие --
    def is_overlay_visible(self) -> bool:
        return self._shown_flag

    def toggle(self) -> None:
        if self._shown_flag or self.isVisible():
            self._do_hide()
        else:
            self.show_overlay()

    def show_overlay(self) -> None:
        self._prev_hwnd = window_utils.get_foreground_hwnd()
        self._refresh()
        move_to_screen_of(self, self._prev_hwnd)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        raise_topmost(self)
        self._shown_flag = True
        log(f"Госволна: оверлей показан (прежнее окно hwnd={self._prev_hwnd})")
        # некоторые игры пере-поднимают своё окно — повторяем подъём (v3.4.1)
        QTimer.singleShot(150, lambda: raise_topmost(self))
        QTimer.singleShot(500, self._check_foreground)

    def _check_foreground(self) -> None:
        try:
            if not self.isVisible() or not self._shown_flag:
                return
            if sys.platform != "win32":
                return
            fg = window_utils.get_foreground_hwnd()
            me = int(self.winId())
            if fg == me:
                log("Госволна: подтверждено — окно в фокусе, поверх игры")
            else:
                log(f"Госволна: фокус у другого окна (hwnd={fg}), повторный подъём")
                raise_topmost(self)
        except Exception:
            pass

    def _do_hide(self) -> None:
        self._shown_flag = False
        self.hide()
        if self._prev_hwnd and sys.platform == "win32":
            try:
                window_utils.focus_window(self._prev_hwnd)
            except Exception:
                pass
        self.closed.emit()
        log("Госволна: оверлей скрыт")

    def hide_overlay_from_sender(self) -> None:
        """Вызывается из рабочего потока — маршируем в GUI-поток."""
        QTimer.singleShot(0, self._do_hide)

    # ---------------------------------------------------------------- прочее --
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._titlebar:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if (event.type() == QEvent.MouseMove and self._drag_pos is not None
                    and (event.buttons() & Qt.LeftButton)):
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_pos = None
        return super().eventFilter(obj, event)

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:
            self._do_hide()
        super().keyPressEvent(ev)


# ------------------------------------------------- подтверждение макроса --
class MacroConfirmDialog(QWidget):
    """Окно подтверждения макроса: время + «Да» (с задержкой) / «Нет» (v3.5.0)."""

    confirmed = Signal()
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._remaining = 0
        self._prev_hwnd = 0
        _overlay_flags(self)
        self.setWindowTitle("Подтверждение макроса")
        self.setFixedSize(560, 260)
        self.setStyleSheet(build_qss())

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
        self.lbl_slots.setWordWrap(True)
        root.addWidget(self.lbl_slots)

        self.lbl_cmd = QLabel("")
        self.lbl_cmd.setObjectName("hint")
        self.lbl_cmd.setWordWrap(True)
        root.addWidget(self.lbl_cmd, 1)

        h = QHBoxLayout()
        self.btn_yes = QPushButton("Да")
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
        action = getattr(s, "gov_macro_action", "step2")
        if action not in GOV_MACRO_ACTIONS:
            action = "step2"
        label = GOV_MACRO_LABELS.get(action, action)
        slots = gov_slots_for(s)
        cmd = resolve_macro_command(s, action)
        self.lbl_action.setText(f"Макрос: {label}")
        self.lbl_slots.setText("Время: " + " ".join(slots))
        preview = cmd if len(cmd) <= 220 else cmd[:220] + "…"
        self.lbl_cmd.setText(preview)
        try:
            sec = int(getattr(s, "gov_macro_confirm_sec", 5))
        except Exception:
            sec = 5
        self._remaining = max(0, sec)
        self._update_yes_button()
        self.lbl_hint.setText(
            "Кнопка «Да» станет активной через "
            + (f"{self._remaining} с" if self._remaining > 0 else "0 с")
            + " — защита от случайного нажатия. Esc — «Нет»."
        )
        self._prev_hwnd = window_utils.get_foreground_hwnd()
        move_to_screen_of(self, self._prev_hwnd)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        raise_topmost(self)
        log(f"макрос: окно подтверждения показано ({label}; задержка {self._remaining} с)")
        if self._remaining > 0:
            self._timer.start()

    def _update_yes_button(self) -> None:
        if self._remaining > 0:
            self.btn_yes.setText(f"Да ({self._remaining} с)")
            self.btn_yes.setEnabled(False)
        else:
            self.btn_yes.setText("Да — отправить")
            self.btn_yes.setEnabled(True)

    def _tick(self) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            self._update_yes_button()
        if self._remaining <= 0:
            self._timer.stop()

    # ------------------------------------------------------------------ Да/Нет --
    def _on_yes(self) -> None:
        self._timer.stop()
        log("макрос: подтверждено («Да»)")
        self.hide()
        self.confirmed.emit()
        self.closed.emit()

    def _on_no(self) -> None:
        self._timer.stop()
        log("макрос: отменено («Нет»)")
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
