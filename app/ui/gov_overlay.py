"""Отдельное окно-оверлей «Госволна» и окно подтверждения макроса.

v3.6.0 — РЕДИЗАЙН: окно — широкий горизонтальный прямоугольник (~1080×460).
Слева — команды госволны крупными широкими кнопками (сетка 2 колонки),
сверху часы и кнопка «Подшитать время», бейдж способа вставки, который
КАЖДЫЙ раз читается из Настроек главного окна («наборка текста» → меню
само откроет чат и наберёт; Ctrl+V → вставит; буфер → скопирует).
Справа — КОНСТРУКТОР МАКРОСА прямо в меню: пользователь набирает
последовательность шагов (добавить/удалить/вверх/вниз), задаёт паузу
между шагами и сохраняет. По клавише макроса открывается подтверждение
с временем и списком шагов; «Да» отправляет шаги по порядку.

GovWaveOverlay — ВТОРОЕ меню программы (включается в Настройках, у него
своя клавиша открытия/закрытия). MacroConfirmDialog — окно подтверждения:
«Да» активируется через N секунд (защита от случайного нажатия).

Оба окна поднимаются поверх безрамочной игры тем же способом, что и
главный оверлей (v3.4.1): TOPMOST + BringWindowToTop + фокус.
"""
from __future__ import annotations

import ctypes
import sys
from typing import List, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import window_utils
from ..journal import log
from ..models import (
    GOV_MACRO_ACTIONS, GOV_MACRO_LABELS, GNEWS_PALETO, GNEWS_SANDY,
    INJECT_LABELS,
)
from .gov_wave import build_commands, gov_slots_for, now_in_tz, plan_macro_sequence, suggest_slots
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
    """Второе меню: широкий прямоугольник с командами и конструктором макроса."""

    closed = Signal()
    slots_updated = Signal()               # время пересчитано — страница перечитает
    trigger_command = Signal(str, str)     # (title, text) — отправить команду
    macro_changed = Signal()               # v3.6.0: шаги макроса изменены в меню

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._prev_hwnd = 0
        self._shown_flag = False
        self._drag_pos = None
        self._cmd_buttons: List[Tuple[str, QPushButton]] = []
        self._loading_macro = False
        _overlay_flags(self)
        self.setWindowTitle("Госволна")
        # v3.6.0: широкий горизонтальный прямоугольник
        self.resize(1080, 470)
        self.setMinimumSize(880, 430)
        self._build_ui()
        self.setStyleSheet(build_qss())
        self._refresh()

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- титул-бар (перетаскивается) ---
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(44)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 5, 8, 5)
        h.setSpacing(10)
        icon_lbl = QLabel("ГВ")
        icon_lbl.setStyleSheet(
            "background:#22D3EE;color:#0B1220;border-radius:8px;"
            "font-weight:800;padding:3px 8px;font-size:13px;"
        )
        h.addWidget(icon_lbl)
        title = QLabel("Госволна — команды и макрос")
        title.setObjectName("appTitle")
        h.addWidget(title)
        self.lbl_clock = QLabel("")
        self.lbl_clock.setObjectName("appSub")
        h.addWidget(self.lbl_clock)
        h.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("tbBtn")
        btn_close.clicked.connect(self._do_hide)
        h.addWidget(btn_close)
        root.addWidget(bar)
        self._titlebar = bar
        bar.installEventFilter(self)

        body = QWidget()
        hb = QHBoxLayout(body)
        hb.setContentsMargins(12, 10, 12, 8)
        hb.setSpacing(12)

        # ============================================ ЛЕВО: команды ===
        left = QVBoxLayout()
        left.setSpacing(8)

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
        left.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        holder = QWidget()
        self.grid_cmds = QGridLayout(holder)
        self.grid_cmds.setContentsMargins(0, 0, 0, 0)
        self.grid_cmds.setHorizontalSpacing(8)
        self.grid_cmds.setVerticalSpacing(8)
        self.scroll.setWidget(holder)
        left.addWidget(self.scroll, 1)

        self.lbl_mode = QLabel("")
        self.lbl_mode.setObjectName("hint")
        self.lbl_mode.setWordWrap(True)
        left.addWidget(self.lbl_mode)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("hint")
        self.lbl_status.setWordWrap(True)
        left.addWidget(self.lbl_status)

        leftw = QWidget()
        leftw.setLayout(left)
        hb.addWidget(leftw, 3)

        # ============================================ ПРАВО: макрос ===
        right = QVBoxLayout()
        right.setSpacing(7)

        cap = QLabel("МАКРОС — последовательность шагов")
        cap.setObjectName("sectionTitle")
        right.addWidget(cap)

        self.lst_steps = QListWidget()
        self.lst_steps.setToolTip(
            "Шаги отправляются по порядку после подтверждения. "
            "Между шагами пауза — вы жмёте Enter в игре сами."
        )
        right.addWidget(self.lst_steps, 1)

        row_e = QHBoxLayout()
        btn_up = QPushButton("↑")
        btn_up.setFixedWidth(36)
        btn_up.setToolTip("Поднять шаг")
        btn_up.clicked.connect(self._step_up)
        row_e.addWidget(btn_up)
        btn_dn = QPushButton("↓")
        btn_dn.setFixedWidth(36)
        btn_dn.setToolTip("Опустить шаг")
        btn_dn.clicked.connect(self._step_down)
        row_e.addWidget(btn_dn)
        btn_del = QPushButton("✕ Удалить шаг")
        btn_del.setObjectName("danger")
        btn_del.clicked.connect(self._step_del)
        row_e.addWidget(btn_del, 1)
        right.addLayout(row_e)

        row_a = QHBoxLayout()
        self.cb_add = QComboBox()
        for _a in GOV_MACRO_ACTIONS:
            self.cb_add.addItem(GOV_MACRO_LABELS.get(_a, _a), _a)
        row_a.addWidget(self.cb_add, 1)
        btn_add = QPushButton("+ Добавить")
        btn_add.setObjectName("primary")
        btn_add.clicked.connect(self._step_add)
        row_a.addWidget(btn_add)
        right.addLayout(row_a)

        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("Пауза между шагами:"))
        self.sp_pause = QSpinBox()
        self.sp_pause.setRange(500, 30000)
        self.sp_pause.setSingleStep(500)
        self.sp_pause.setSuffix(" мс")
        self.sp_pause.setToolTip(
            "Пауза после каждого шага, чтобы вы успели нажать Enter в игре. "
            "Enter программой не нажимается никогда."
        )
        row_p.addWidget(self.sp_pause, 1)
        right.addLayout(row_p)

        self.lbl_macro_hk = QLabel("")
        self.lbl_macro_hk.setObjectName("hint")
        self.lbl_macro_hk.setWordWrap(True)
        right.addWidget(self.lbl_macro_hk)

        row_s = QHBoxLayout()
        self.btn_save_macro = QPushButton("💾 Сохранить макрос")
        self.btn_save_macro.setObjectName("primary")
        self.btn_save_macro.clicked.connect(self._persist_macro_clicked)
        row_s.addWidget(self.btn_save_macro)
        self.lbl_macro_status = QLabel("")
        self.lbl_macro_status.setObjectName("hint")
        row_s.addWidget(self.lbl_macro_status, 1)
        right.addLayout(row_s)

        rightw = QWidget()
        rightw.setMinimumWidth(330)
        rightw.setLayout(right)
        hb.addWidget(rightw, 2)

        root.addWidget(body, 1)

        self.lbl_hint = QLabel(
            "Клик по команде — отправить способом из Настроек (если выбрана «наборка "
            "текста» — меню само откроет чат и напечатает). Esc — закрыть, окно "
            "таскается за верхнюю полосу."
        )
        self.lbl_hint.setObjectName("hint")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setContentsMargins(12, 0, 12, 8)
        root.addWidget(self.lbl_hint)

    # ------------------------------------------------------------ содержимое --
    def _current_slots(self) -> List[str]:
        return gov_slots_for(self.store.settings)

    def _refresh(self) -> None:
        """Перечитать настройки из главного окна и перестроить всё."""
        s = self.store.settings
        slots = self._current_slots()
        self.lbl_slots.setText("Время: " + " ".join(slots))

        # бейдж способа вставки — читается из настроек КАЖДЫЙ раз
        method = getattr(s, "inject_method", "unicode") or "unicode"
        m_label = INJECT_LABELS.get(method, method)
        m_tail = {
            "unicode": "меню само откроет чат и НАБЕРЁТ текст посимвольно",
            "ctrlv": "меню само откроет чат и вставит через Ctrl+V",
            "copy": "меню скопирует в буфер и переключит вас в игру",
        }.get(method, "")
        self.lbl_mode.setText(f"Способ вставки (из Настроек): {m_label} — {m_tail}.")

        # команды — широкие кнопки в сетке 2 колонки
        while self.grid_cmds.count():
            it = self.grid_cmds.takeAt(0)
            w = it.widget() if it else None
            if w:
                w.setParent(None)
                w.deleteLater()
        for r in range(self.grid_cmds.rowCount()):
            self.grid_cmds.setRowStretch(r, 0)
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
        for i, (key, label, cmd) in enumerate(rows):
            if not cmd:
                continue
            short = cmd if len(cmd) <= 64 else cmd[:64] + "…"
            b = QPushButton(f"{label}\n{short}")
            b.setToolTip(cmd)
            b.setCursor(Qt.PointingHandCursor)
            b.setObjectName("govCmd")
            b.setMinimumHeight(52)
            b.clicked.connect(
                lambda _=False, t=label, c=cmd: self.trigger_command.emit(t, c)
            )
            self.grid_cmds.addWidget(b, i // 2, i % 2)
            self._cmd_buttons.append((key, b))
        self.grid_cmds.setRowStretch(len(rows) // 2 + 1, 1)

        # конструктор макроса — перечитать из настроек (без циклов автосохранения)
        self._loading_macro = True
        try:
            self._reload_macro_list()
            try:
                self.sp_pause.setValue(int(getattr(s, "gov_macro_step_pause_ms", 4000)))
            except Exception:
                self.sp_pause.setValue(4000)
            hk = (getattr(s, "gov_macro_hotkey", "f8") or "f8").upper()
            sec = getattr(s, "gov_macro_confirm_sec", 5)
            on = "включён" if getattr(s, "gov_macro_enabled", False) else "ВЫКЛЮЧЕН (Настройки)"
            self.lbl_macro_hk.setText(
                f"Клавиша макроса: {hk} ({on}) · задержка «Да»: {sec} с. "
                "Клавиша и вкл/выкл меняются в Настройках."
            )
        finally:
            self._loading_macro = False

    def _reload_macro_list(self) -> None:
        steps = list(getattr(self.store.settings, "gov_macro_steps", []) or [])
        self.lst_steps.clear()
        for i, st in enumerate(steps):
            self.lst_steps.addItem(f"{i + 1}.  {GOV_MACRO_LABELS.get(st, st)}")

    def _tick_clock(self) -> None:
        if not self.isVisible():
            return
        try:
            s = self.store.settings
            now = now_in_tz(s)
            if getattr(s, "gov_tz_auto", True):
                self.lbl_clock.setText(f"🕒 {now:%H:%M:%S} (время компьютера)")
            else:
                off = float(getattr(s, "gov_utc_offset", 0.0) or 0.0)
                self.lbl_clock.setText(f"🕒 {now:%H:%M:%S} (UTC{off:+g})")
        except Exception:
            pass

    # ----------------------------------------------------- конструктор макроса --
    def _steps_now(self) -> List[str]:
        out: List[str] = []
        for i in range(self.lst_steps.count()):
            txt = self.lst_steps.item(i).text()
            # «3.  Подпись» → подпись → ключ
            label = txt.split(".", 1)[1].strip() if "." in txt else txt
            for k, v in GOV_MACRO_LABELS.items():
                if v == label:
                    out.append(k)
                    break
        return out

    def _after_macro_edit(self) -> None:
        if self._loading_macro:
            return
        self._persist_macro()

    def _step_add(self) -> None:
        key = self.cb_add.currentData()
        if not key:
            return
        cur = self._steps_now()
        if key in cur:
            self.lbl_macro_status.setText("Такой шаг уже есть в макросе")
            return
        if len(cur) >= len(GOV_MACRO_ACTIONS):
            self.lbl_macro_status.setText("Максимум шагов — все команды уже добавлены")
            return
        self.lst_steps.addItem(f"{len(cur) + 1}.  {GOV_MACRO_LABELS.get(key, key)}")
        self._after_macro_edit()

    def _step_del(self) -> None:
        row = self.lst_steps.currentRow()
        if row < 0:
            return
        self.lst_steps.takeItem(row)
        self._renumber()
        self._after_macro_edit()

    def _step_up(self) -> None:
        row = self.lst_steps.currentRow()
        if row <= 0:
            return
        it = self.lst_steps.takeItem(row)
        self.lst_steps.insertItem(row - 1, it)
        self.lst_steps.setCurrentRow(row - 1)
        self._renumber()
        self._after_macro_edit()

    def _step_down(self) -> None:
        row = self.lst_steps.currentRow()
        if row < 0 or row >= self.lst_steps.count() - 1:
            return
        it = self.lst_steps.takeItem(row)
        self.lst_steps.insertItem(row + 1, it)
        self.lst_steps.setCurrentRow(row + 1)
        self._renumber()
        self._after_macro_edit()

    def _renumber(self) -> None:
        for i in range(self.lst_steps.count()):
            txt = self.lst_steps.item(i).text()
            label = txt.split(".", 1)[1].strip() if "." in txt else txt
            self.lst_steps.item(i).setText(f"{i + 1}.  {label}")

    def _persist_macro(self) -> None:
        try:
            s = self.store.settings
            s.gov_macro_steps = self._steps_now() or [getattr(s, "gov_macro_action", "step2")]
            s.gov_macro_step_pause_ms = int(self.sp_pause.value())
            self.store.save()
            self.lbl_macro_status.setText("✓ сохранено")
            log(f"макрос: шаги = {' → '.join(s.gov_macro_steps)}; "
                f"пауза {s.gov_macro_step_pause_ms} мс")
            self.macro_changed.emit()
        except Exception as e:
            self.lbl_macro_status.setText(f"ошибка: {e}")
            log(f"макрос: ошибка сохранения: {e}")

    def _persist_macro_clicked(self) -> None:
        self._persist_macro()
        from datetime import datetime

        self.lbl_macro_status.setText(
            f"✓ макрос сохранён ({datetime.now():%H:%M:%S}) — "
            f"{self.lst_steps.count()} шагов"
        )

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
        self._refresh()          # каждый раз читаем настройки главного окна
        self._tick_clock()
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
        """Совместимость: скрытие из рабочего потока идёт через сигнал Sender."""
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
    """Окно подтверждения макроса: время + шаги + «Да» (с задержкой) / «Нет»."""

    confirmed = Signal()
    closed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._remaining = 0
        self._prev_hwnd = 0
        _overlay_flags(self)
        self.setWindowTitle("Подтверждение макроса")
        self.setFixedSize(640, 380)
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

        self.lbl_steps = QLabel("")
        self.lbl_steps.setObjectName("hint")
        self.lbl_steps.setWordWrap(True)
        root.addWidget(self.lbl_steps, 1)

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

    # совместимость со старыми тестами/кодом
    @property
    def lbl_cmd(self) -> QLabel:  # noqa: N802
        return self.lbl_steps

    # ------------------------------------------------------------------ показ --
    def open_dialog(self) -> None:
        s = self.store.settings
        plan = plan_macro_sequence(s)
        if not plan:
            from .gov_wave import resolve_macro_command

            fallback = resolve_macro_command(s, getattr(s, "gov_macro_action", "step2"))
            plan = [(GOV_MACRO_LABELS.get(getattr(s, "gov_macro_action", "step2"),
                                          "Шаг"), fallback)] if fallback else []
        slots = gov_slots_for(s)
        n = len(plan)
        self.lbl_action.setText(
            f"Макрос: {n} " + ("шаг" if n == 1 else "шага" if 2 <= n % 10 <= 4
                               and (n % 100 < 10 or n % 100 > 20) else "шагов")
        )
        self.lbl_slots.setText("Время: " + " ".join(slots))
        lines = []
        for i, (label, cmd) in enumerate(plan):
            short = cmd if len(cmd) <= 96 else cmd[:96] + "…"
            lines.append(f"{i + 1}) {label}\n     {short}")
        self.lbl_steps.setText("\n".join(lines) or "(пусто — соберите шаги в меню Госволны)")
        try:
            sec = int(getattr(s, "gov_macro_confirm_sec", 5))
        except Exception:
            sec = 5
        self._remaining = max(0, sec)
        self._update_yes_button()
        self.lbl_hint.setText(
            "Кнопка «Да» станет активной через "
            + (f"{self._remaining} с" if self._remaining > 0 else "0 с")
            + " — защита от случайного нажатия. Шаги отправятся по порядку, "
              "Enter в игре вы нажимаете сами. Esc — «Нет»."
        )
        self._prev_hwnd = window_utils.get_foreground_hwnd()
        move_to_screen_of(self, self._prev_hwnd)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        raise_topmost(self)
        log(f"макрос: окно подтверждения показано ({n} шагов; задержка {self._remaining} с)")
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
