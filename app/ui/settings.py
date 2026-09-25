"""Страница настроек: хоткеи, способ вставки, окно игры, трей, белый список."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .. import window_utils
from ..models import INJECT_HINTS, INJECT_LABELS, INJECT_METHODS, timezone_options
from .theme import DANGER, MUTED, OK
from .widgets import SectionFrame


class SettingsPage(QWidget):
    settings_changed = Signal()   # после любого изменения
    key_test_hit = Signal()       # нажатие меню-клавиши в режиме теста (из фонового потока)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._capture_target: str | None = None
        self._hotkeys = None

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

        # -------------------------------------------- сохранение настроек --
        sec_save = SectionFrame("Сохранение настроек")
        h_save = QHBoxLayout()
        self.btn_save = QPushButton("💾 Сохранить настройки")
        self.btn_save.setObjectName("primary")
        self.btn_save.setToolTip(
            "Применяет ВСЕ поля этой страницы и записывает в data/data.json"
        )
        self.btn_save.clicked.connect(self._save_all)
        h_save.addWidget(self.btn_save)
        self.lbl_save = QLabel(
            "Изменения применяются сразу, а кнопка принудительно сохраняет всё "
            "и проверяет корректность — нажмите её после правки хоткеев."
        )
        self.lbl_save.setObjectName("hint")
        self.lbl_save.setWordWrap(True)
        h_save.addWidget(self.lbl_save, 1)
        sec_save.body_layout().addLayout(h_save)
        v.addWidget(sec_save)

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
        self.lbl_keys_hint = QLabel(
            "Пауза даёт игре время открыть чат. Enter никогда не нажимается. "
            "В Majestic RP чат открывает латинская T: если в поле была русская "
            "буква — программа сама заменит её на ту же физическую клавишу "
            "(е→T, ё→` и т.д.), но лучше введите «t» при раскладке EN."
        )
        self.lbl_keys_hint.setObjectName("hint")
        self.lbl_keys_hint.setWordWrap(True)
        sec_keys.body_layout().addWidget(self.lbl_keys_hint)
        self.lbl_hk_state = QLabel("Перехват клавиш: ещё не запущен (нажмите «Сохранить настройки»)")
        self.lbl_hk_state.setObjectName("hint")
        self.lbl_hk_state.setWordWrap(True)
        sec_keys.body_layout().addWidget(self.lbl_hk_state)
        h_test = QHBoxLayout()
        self.btn_test_key = QPushButton("Проверить меню-клавишу (10 с)")
        self.btn_test_key.setToolTip(
            "Нажмите клавишу меню (например F6) в любом окне — программа покажет, доходит ли нажатие"
        )
        self.btn_test_key.clicked.connect(self._start_key_test)
        h_test.addWidget(self.btn_test_key)
        h_test.addStretch(1)
        sec_keys.body_layout().addLayout(h_test)
        self.lbl_key_test = QLabel("")
        self.lbl_key_test.setWordWrap(True)
        sec_keys.body_layout().addWidget(self.lbl_key_test)
        self._test_timer = QTimer(self)
        self._test_timer.setSingleShot(True)
        self._test_timer.timeout.connect(self._key_test_timeout)
        self.key_test_hit.connect(self._do_key_test_hit)
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
        self._capture_timer.timeout.connect(self._capture_tick)
        self._capture_left = 0

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
        # показать в полях то, что реально сохранилось (кириллица → латиница)
        if self.ed_menu.text() != s.menu_hotkey.upper():
            self.ed_menu.setText(s.menu_hotkey.upper())
        if self.ed_type.text() != s.type_key:
            self.ed_type.setText(s.type_key)
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

    # --------------------------------------------------- сохранение кнопкой --
    def _save_all(self) -> None:
        """Кнопка «Сохранить настройки»: применить все поля и записать файл."""
        try:
            self._apply_keys()
            self._apply_delay(self.sp_delay.value())
            self._apply_inject()
            self._apply_target()
            self._apply_tz()
            self._apply_tray(self.chk_tray.isChecked())
            self._apply_wl(self.chk_wl.isChecked())
            self._apply_wl_text()
            self.store.save()
            errs = self.store.settings.validate()
            if errs:
                self.lbl_save.setStyleSheet(f"color: {DANGER};")
                self.lbl_save.setText("⚠ Сохранено с предупреждениями: " + "; ".join(errs))
            else:
                from datetime import datetime as _dt

                self.lbl_save.setStyleSheet(f"color: {OK};")
                self.lbl_save.setText(
                    f"✓ Настройки сохранены ({_dt.now():%H:%M:%S}) — хоткеи перезапущены"
                )
            self.settings_changed.emit()
        except Exception as e:
            self.lbl_save.setStyleSheet(f"color: {DANGER};")
            self.lbl_save.setText(f"Ошибка сохранения: {e}")

    # --------------------------------------------- хоткеи: статус и тест --
    def set_hotkeys(self, hk) -> None:
        """Подключить HotkeyManager (вызывается из главного окна)."""
        self._hotkeys = hk
        if hk is not None:
            hk.state_changed.connect(self._on_hk_state)

    def _on_hk_state(self, _state: str) -> None:
        hk = self._hotkeys
        if hk is None:
            return
        if hk.error:
            self.lbl_hk_state.setStyleSheet(f"color: {DANGER};")
            self.lbl_hk_state.setText(f"Перехват клавиш: ОШИБКА — {hk.error}")
        else:
            self.lbl_hk_state.setStyleSheet(f"color: {OK};")
            self.lbl_hk_state.setText(
                "Перехват клавиш активен (опрос клавиатуры — работает и в игре, "
                "и при игре от администратора, без системных хуков)."
            )

    def _show_key_test(self, text: str, color: str) -> None:
        self.lbl_key_test.setStyleSheet(f"color: {color};")
        self.lbl_key_test.setText(text)

    def _start_key_test(self) -> None:
        hk = self._hotkeys
        if hk is None:
            self._show_key_test(
                "Хоткеи ещё не запущены — сначала нажмите «Сохранить настройки».", DANGER
            )
            return
        if not hk.start_menu_test(self._on_key_test_hit):
            self._show_key_test(
                "Меню-клавиша не активна (ошибка регистрации). Проверьте клавишу "
                "и нажмите «Сохранить настройки».", DANGER,
            )
            return
        key = (self.ed_menu.text().strip() or "F6").upper()
        self.btn_test_key.setEnabled(False)
        self._show_key_test(
            f"Ожидание нажатия {key}… нажмите её в любом окне (10 секунд).", MUTED
        )
        self._test_timer.start(10000)

    def _on_key_test_hit(self) -> None:
        """Вызывается из фонового потока опроса — маршируем в GUI-поток."""
        self.key_test_hit.emit()

    def _do_key_test_hit(self) -> None:
        if self._hotkeys is not None:
            self._hotkeys.stop_menu_test()
        self._test_timer.stop()
        self.btn_test_key.setEnabled(True)
        self._show_key_test(
            "✓ Клавиша дошла до программы! Перехват работает — F6 будет открывать меню.",
            OK,
        )

    def _key_test_timeout(self) -> None:
        if self._hotkeys is not None:
            self._hotkeys.stop_menu_test()
        self.btn_test_key.setEnabled(True)
        self._show_key_test(
            "✗ За 10 секунд нажатие не пришло. Возможные причины: эту клавишу заняла "
            "другая программа; вы нажали не ту клавишу, что указана в поле «Меню»; "
            "игра в полноэкранном эксклюзивном режиме — переключите её в «окно без рамки».",
            DANGER,
        )

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
        self._capture_left = 10
        self._capture_timer.start(1000)      # тик раз в секунду — обратный отсчёт
        msg = "Захват окна: переключитесь в ИГРУ в течение 10 с…"
        if which == "target":
            self.lbl_target_status.setStyleSheet(f"color: {MUTED};")
            self.lbl_target_status.setText(msg)
        else:
            self.lbl_wl_hint.setStyleSheet(f"color: {MUTED};")
            self.lbl_wl_hint.setText(msg)

    def _capture_tick(self) -> None:
        self._capture_left -= 1
        if self._capture_left > 0:
            msg = f"Захват окна: переключитесь в игру… {self._capture_left} с"
            if self._capture_target == "target":
                self.lbl_target_status.setStyleSheet(f"color: {MUTED};")
                self.lbl_target_status.setText(msg)
            else:
                self.lbl_wl_hint.setStyleSheet(f"color: {MUTED};")
                self.lbl_wl_hint.setText(msg)
            return
        self._capture_timer.stop()
        self._do_capture()

    def _is_own_window(self, fg: dict) -> bool:
        """Захватили не игру, а окно самой программы? (частая ошибка ранее)"""
        try:
            own_hwnd = int(self.window().winId()) if sys.platform == "win32" else 0
        except Exception:
            own_hwnd = 0
        if own_hwnd and fg.get("hwnd") == own_hwnd:
            return True
        exe_name = (fg.get("exe") or "").rsplit("\\", 1)[-1].lower()
        own_exe = os.path.basename(sys.executable).lower()
        return bool(exe_name) and exe_name == own_exe

    def _do_capture(self) -> None:
        which, self._capture_target = self._capture_target, None
        fg = window_utils.get_foreground_window()
        if not fg:
            if which == "target":
                self.lbl_target_status.setStyleSheet(f"color: {DANGER};")
                self.lbl_target_status.setText(
                    "✗ Окно не найдено. Нажмите кнопку и ПЕРЕКЛЮЧИТЕСЬ в игру за 10 секунд."
                )
            else:
                self.lbl_wl_hint.setStyleSheet(f"color: {DANGER};")
                self.lbl_wl_hint.setText("✗ Окно не найдено — попробуйте ещё раз.")
            return
        if self._is_own_window(fg):
            msg = ("✗ Это окно САМОЙ программы, а не игры. Нажмите кнопку и "
                   "переключитесь в игру за 10 секунд.")
            if which == "target":
                self.lbl_target_status.setStyleSheet(f"color: {DANGER};")
                self.lbl_target_status.setText(msg)
            else:
                self.lbl_wl_hint.setStyleSheet(f"color: {DANGER};")
                self.lbl_wl_hint.setText(msg)
            return
        title = fg.get("title") or ""
        exe = (fg.get("exe") or "").rsplit("\\", 1)[-1]
        if which == "target":
            self.ed_target_title.setText(title)
            self.ed_target_exe.setText(exe)
            self._apply_target()
            self.lbl_target_status.setStyleSheet(f"color: {OK};")
            self.lbl_target_status.setText(
                f"✓ Захвачено: «{title[:60]}» ({exe}) — нажмите «💾 Сохранить настройки»"
            )
        elif which == "whitelist":
            cur_exe = self.txt_wl_exe.toPlainText().splitlines()
            cur_title = self.txt_wl_title.toPlainText().splitlines()
            if exe and exe not in cur_exe:
                cur_exe.append(exe)
            if title and title not in cur_title:
                cur_title.append(title)
            self.txt_wl_exe.setPlainText("\n".join(x for x in cur_exe if x))
            self.txt_wl_title.setPlainText("\n".join(x for x in cur_title if x))
            self._apply_wl_text()
            self.lbl_wl_hint.setStyleSheet(f"color: {OK};")
            self.lbl_wl_hint.setText(f"✓ Добавлено в белый список: {exe or title[:40]}")

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
