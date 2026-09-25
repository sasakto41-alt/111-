"""Страница настроек: хоткеи, способ вставки, окно игры, трей, белый список."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import window_utils
from ..models import INJECT_HINTS, INJECT_LABELS, INJECT_METHODS, timezone_options
from .theme import MUTED, OK
from .widgets import SectionFrame


class SettingsPage(QWidget):
    settings_changed = Signal()   # после любого изменения

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._capture_target: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        root = QWidget()
        scroll.setWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 18, 18)
        v.setSpacing(12)

        # ---------------------------------------------------------- хоткеи --
        sec_keys = SectionFrame("Горячие клавиши")
        form = QFormLayout()
        form.setSpacing(8)
        self.ed_menu = QLineEdit()
        self.ed_menu.setPlaceholderText("F6")
        form.addRow("Меню (показать/скрыть):", self.ed_menu)
        self.ed_type = QLineEdit()
        self.ed_type.setPlaceholderText("t")
        form.addRow("Клавиша чата:", self.ed_type)
        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(100, 10000)
        self.sp_delay.setSingleStep(100)
        self.sp_delay.setSuffix(" мс")
        form.addRow("Пауза после чата:", self.sp_delay)
        sec_keys.body_layout().addLayout(form)
        self.lbl_keys_hint = QLabel("Пауза даёт игре время открыть чат. Enter никогда не нажимается.")
        self.lbl_keys_hint.setObjectName("hint")
        self.lbl_keys_hint.setWordWrap(True)
        sec_keys.body_layout().addWidget(self.lbl_keys_hint)
        v.addWidget(sec_keys)

        # -------------------------------------------------- способ вставки --
        sec_inject = SectionFrame("Способ вставки")
        self.cb_inject = QComboBox()
        for m in INJECT_METHODS:
            self.cb_inject.addItem(INJECT_LABELS.get(m, m), m)
        sec_inject.body_layout().addWidget(self.cb_inject)
        self.lbl_inject_hint = QLabel("")
        self.lbl_inject_hint.setObjectName("hint")
        self.lbl_inject_hint.setWordWrap(True)
        sec_inject.body_layout().addWidget(self.lbl_inject_hint)
        v.addWidget(sec_inject)

        # ------------------------------------------------------- окно игры --
        sec_target = SectionFrame("Окно игры (куда переключаться)")
        form_t = QFormLayout()
        form_t.setSpacing(8)
        self.ed_target_title = QLineEdit()
        self.ed_target_title.setPlaceholderText("часть заголовка окна игры, напр. Majestic")
        form_t.addRow("Заголовок содержит:", self.ed_target_title)
        self.ed_target_exe = QLineEdit()
        self.ed_target_exe.setPlaceholderText("часть имени exe, напр. majestic (можно пусто)")
        form_t.addRow("Процесс содержит:", self.ed_target_exe)
        sec_target.body_layout().addLayout(form_t)

        h_t = QHBoxLayout()
        btn_capture = QPushButton("Захватить активное окно (10 с)")
        btn_capture.clicked.connect(lambda: self._start_capture("target"))
        h_t.addWidget(btn_capture)
        btn_check = QPushButton("Проверить")
        btn_check.clicked.connect(self._check_target)
        h_t.addWidget(btn_check)
        h_t.addStretch(1)
        sec_target.body_layout().addLayout(h_t)
        self.lbl_target_status = QLabel(
            "Если указано — программа сама найдёт это окно, переключится на него, "
            "нажмёт T (или скопирует в буфер и переключит вас). Оставьте пустым, "
            "если не нужно."
        )
        self.lbl_target_status.setObjectName("hint")
        self.lbl_target_status.setWordWrap(True)
        sec_target.body_layout().addWidget(self.lbl_target_status)
        v.addWidget(sec_target)

        # ---------------------------------------------------- часовой пояс --
        sec_tz = SectionFrame("Часовой пояс госволны")
        h_tz = QHBoxLayout()
        h_tz.addWidget(QLabel("Подбор времени:"))
        self.cb_tz = QComboBox()
        self.cb_tz.addItem("Как на компьютере (местное время)", "auto")
        for _off, _label in timezone_options():
            self.cb_tz.addItem(_label, _off)
        h_tz.addWidget(self.cb_tz, 1)
        sec_tz.body_layout().addLayout(h_tz)
        lbl_tz_hint = QLabel(
            "Влияет на кнопку «Подобрать время» и проверку правил в разделе «Госволна». "
            "Если сервер живёт по другому времени — выберите его пояс, например UTC+0."
        )
        lbl_tz_hint.setObjectName("hint")
        lbl_tz_hint.setWordWrap(True)
        sec_tz.body_layout().addWidget(lbl_tz_hint)
        v.addWidget(sec_tz)

        # ------------------------------------------------------------ трей --
        sec_tray = SectionFrame("Трей")
        self.chk_tray = QCheckBox("Иконка в трее и уведомления (когда окно скрыто)")
        sec_tray.body_layout().addWidget(self.chk_tray)
        v.addWidget(sec_tray)

        # ------------------------------------------------------ белый список --
        sec_wl = SectionFrame("Ограничение по окнам (белый список)")
        self.chk_wl = QCheckBox("Работать только в выбранных окнах")
        sec_wl.body_layout().addWidget(self.chk_wl)
        self.txt_wl_exe = QPlainTextEdit()
        self.txt_wl_exe.setPlaceholderText("по одному exe в строке, напр.:\nmajestic.exe")
        self.txt_wl_exe.setFixedHeight(64)
        sec_wl.body_layout().addWidget(QLabel("Процессы (exe):"))
        sec_wl.body_layout().addWidget(self.txt_wl_exe)
        self.txt_wl_title = QPlainTextEdit()
        self.txt_wl_title.setPlaceholderText("по одной части заголовка в строке, напр.:\nMajestic RP")
        self.txt_wl_title.setFixedHeight(64)
        sec_wl.body_layout().addWidget(QLabel("Заголовки окон:"))
        sec_wl.body_layout().addWidget(self.txt_wl_title)
        h_wl = QHBoxLayout()
        btn_cap_wl = QPushButton("Захватить активное окно (10 с)")
        btn_cap_wl.clicked.connect(lambda: self._start_capture("whitelist"))
        h_wl.addWidget(btn_cap_wl)
        h_wl.addStretch(1)
        sec_wl.body_layout().addLayout(h_wl)
        self.lbl_wl_hint = QLabel("Подсказка: если игра запущена от администратора — запускайте программу тоже от администратора.")
        self.lbl_wl_hint.setObjectName("hint")
        self.lbl_wl_hint.setWordWrap(True)
        sec_wl.body_layout().addWidget(self.lbl_wl_hint)
        v.addWidget(sec_wl)

        v.addStretch(1)

        # ------------------------------------------------------------- wire --
        self.ed_menu.editingFinished.connect(self._apply_keys)
        self.ed_type.editingFinished.connect(self._apply_keys)
        self.sp_delay.valueChanged.connect(self._apply_delay)
        self.cb_inject.currentIndexChanged.connect(self._apply_inject)
        self.chk_tray.toggled.connect(self._apply_tray)
        self.chk_wl.toggled.connect(self._apply_wl)
        self.txt_wl_exe.textChanged.connect(self._apply_wl_text)
        self.txt_wl_title.textChanged.connect(self._apply_wl_text)
        self.ed_target_title.editingFinished.connect(self._apply_target)
        self.ed_target_exe.editingFinished.connect(self._apply_target)
        self.cb_tz.currentIndexChanged.connect(self._apply_tz)

        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._do_capture)

        self._load()

    # ----------------------------------------------------------------- load --
    def _load(self) -> None:
        s = self.store.settings
        self.ed_menu.setText(s.menu_hotkey.upper())
        self.ed_type.setText(s.type_key)
        self.sp_delay.setValue(s.pre_delay_ms)
        idx = INJECT_METHODS.index(s.inject_method) if s.inject_method in INJECT_METHODS else 0
        self.cb_inject.setCurrentIndex(idx)
        self._update_inject_hint()
        self.chk_tray.setChecked(s.tray_enabled)
        self.chk_wl.setChecked(s.whitelist_enabled)
        self.txt_wl_exe.setPlainText("\n".join(s.whitelist_exes))
        self.txt_wl_title.setPlainText("\n".join(s.whitelist_titles))
        self.ed_target_title.setText(s.target_title)
        self.ed_target_exe.setText(s.target_exe)
        self._load_tz()

    # ---------------------------------------------------------------- apply --
    def _apply_keys(self) -> None:
        s = self.store.settings
        s.menu_hotkey = self.ed_menu.text().strip().lower() or "f6"
        s.type_key = self.ed_type.text().strip().lower() or "t"
        s.normalize()
        self.store.save()
        self.settings_changed.emit()

    def _apply_delay(self, val: int) -> None:
        self.store.settings.pre_delay_ms = int(val)
        self.store.save()

    def _apply_inject(self) -> None:
        m = self.cb_inject.currentData() or "unicode"
        self.store.settings.inject_method = m
        self.store.save()
        self._update_inject_hint()
        self.settings_changed.emit()

    def _apply_tray(self, on: bool) -> None:
        self.store.settings.tray_enabled = bool(on)
        self.store.save()
        self.settings_changed.emit()

    def _apply_wl(self, on: bool) -> None:
        self.store.settings.whitelist_enabled = bool(on)
        self.store.save()

    def _apply_wl_text(self) -> None:
        s = self.store.settings
        s.whitelist_exes = [x.strip() for x in self.txt_wl_exe.toPlainText().splitlines() if x.strip()]
        s.whitelist_titles = [t.strip() for t in self.txt_wl_title.toPlainText().splitlines() if t.strip()]
        self.store.save()

    def _apply_target(self) -> None:
        s = self.store.settings
        s.target_title = self.ed_target_title.text().strip()
        s.target_exe = self.ed_target_exe.text().strip()
        self.store.save()
        if s.target_title:
            n = len(window_utils.find_windows(s.target_title, s.target_exe))
            self.lbl_target_status.setStyleSheet(f"color: {OK};")
            self.lbl_target_status.setText(f"Сохранено. Окон по запросу найдено: {n}")
        else:
            self.lbl_target_status.setStyleSheet(f"color: {MUTED};")
            self.lbl_target_status.setText("Целевое окно не задано — используется окно, активное до оверлея.")

    def _update_inject_hint(self) -> None:
        m = self.cb_inject.currentData() or "unicode"
        self.lbl_inject_hint.setText(INJECT_HINTS.get(m, ""))

    # ------------------------------------------------------- часовой пояс --
    def _load_tz(self) -> None:
        s = self.store.settings
        if getattr(s, "gov_tz_auto", True):
            self.cb_tz.setCurrentIndex(0)
        else:
            try:
                off = float(s.gov_utc_offset or 0.0)
            except Exception:
                off = 0.0
            idx = self.cb_tz.findData(off)
            self.cb_tz.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply_tz(self) -> None:
        data = self.cb_tz.currentData()
        s = self.store.settings
        if data == "auto" or data is None:
            s.gov_tz_auto = True
        else:
            s.gov_tz_auto = False
            try:
                s.gov_utc_offset = float(data)
            except Exception:
                s.gov_utc_offset = 0.0
        self.store.save()

    # -------------------------------------------------------------- capture --
    def _start_capture(self, which: str) -> None:
        self._capture_target = which
        self._capture_timer.start(10000)

    def _do_capture(self) -> None:
        which, self._capture_target = self._capture_target, None
        fg = window_utils.get_foreground_window()
        if not fg:
            return
        if which == "target":
            self.ed_target_title.setText(fg.get("title") or "")
            exe = (fg.get("exe") or "").rsplit("\\", 1)[-1]
            self.ed_target_exe.setText(exe)
            self._apply_target()
        elif which == "whitelist":
            cur_exe = self.txt_wl_exe.toPlainText().splitlines()
            cur_title = self.txt_wl_title.toPlainText().splitlines()
            exe = (fg.get("exe") or "")
            title = (fg.get("title") or "")
            if exe and exe not in cur_exe:
                cur_exe.append(exe)
            if title and title not in cur_title:
                cur_title.append(title)
            self.txt_wl_exe.setPlainText("\n".join(x for x in cur_exe if x))
            self.txt_wl_title.setPlainText("\n".join(x for x in cur_title if x))
            self._apply_wl_text()

    def _check_target(self) -> None:
        title = self.ed_target_title.text().strip()
        exe = self.ed_target_exe.text().strip()
        if not title and not exe:
            self.lbl_target_status.setStyleSheet(f"color: {MUTED};")
            self.lbl_target_status.setText("Сначала укажите заголовок или процесс.")
            return
        wins = window_utils.find_windows(title, exe)
        if wins:
            self.lbl_target_status.setStyleSheet(f"color: {OK};")
            self.lbl_target_status.setText(f"Найдено окон: {len(wins)}. Пример: «{wins[0]['title'][:60]}»")
        else:
            self.lbl_target_status.setStyleSheet(f"color: {MUTED};")
            self.lbl_target_status.setText("Окон не найдено — проверьте подстроку заголовка/процесса.")
