"""Главное окно: библиотека фраз, раздел «Госволна», настройки, оверлей F6."""
from __future__ import annotations

import ctypes
import sys
import threading

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import window_utils
from ..config import APP_NAME
from ..models import CATEGORIES, TextEntry
from ..sender import SendWorker, Sender
from .. import APP_VERSION
from .card import MIME_ENTRY, PhraseCard
from .editor import TextEditorDialog
from .flow_layout import FlowLayout
from .gov_wave import GovWavePage
from .settings import SettingsPage
from .theme import build_qss
from .widgets import SectionFrame, Toast

PAGE_LIBRARY, PAGE_GOV, PAGE_SETTINGS = 0, 1, 2


class MainWindow(QWidget):
    def __init__(self, store, hotkeys, parent=None):
        super().__init__(parent)
        self.store = store
        self.hotkeys = hotkeys

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.resize(920, 580)

        self._prev_hwnd = 0
        self._shown_flag = False
        self._shown_lock = threading.Lock()
        self._tray_notify = None
        self._filter_cat = "Все"
        self._search = ""
        self._drag_pos = None

        self._build_ui()
        self.setStyleSheet(build_qss())
        self._build_sender()
        self._refresh_cards()

    # ------------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- титул-бар ---
        bar = QFrame()
        bar.setObjectName("titleBar")
        bar.setFixedHeight(46)
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 6, 10, 6)
        h.setSpacing(8)
        icon_lbl = QLabel("M")
        icon_lbl.setStyleSheet(
            "background:#3B82F6;color:white;border-radius:8px;"
            "font-weight:800;padding:4px 9px;font-size:15px;"
        )
        h.addWidget(icon_lbl)
        title = QLabel(f"{APP_NAME}")
        title.setObjectName("appTitle")
        h.addWidget(title)
        sub = QLabel(f"v{APP_VERSION}  •  Enter не нажимается")
        sub.setObjectName("appSub")
        h.addWidget(sub)
        h.addStretch(1)

        self.nav_lib = QPushButton("Библиотека")
        self.nav_lib.setObjectName("navBtn")
        self.nav_lib.setCheckable(True)
        self.nav_lib.clicked.connect(lambda: self.switch_page(PAGE_LIBRARY))
        self.nav_gov = QPushButton("Госволна")
        self.nav_gov.setObjectName("navBtn")
        self.nav_gov.setCheckable(True)
        self.nav_gov.clicked.connect(lambda: self.switch_page(PAGE_GOV))
        self.nav_set = QPushButton("Настройки")
        self.nav_set.setObjectName("navBtn")
        self.nav_set.setCheckable(True)
        self.nav_set.clicked.connect(lambda: self.switch_page(PAGE_SETTINGS))
        for b in (self.nav_lib, self.nav_gov, self.nav_set):
            h.addWidget(b)

        btn_min = QPushButton("—")
        btn_min.setObjectName("tbBtn")
        btn_min.clicked.connect(self.showMinimized)
        h.addWidget(btn_min)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("tbBtn")
        btn_close.clicked.connect(self._do_hide)
        h.addWidget(btn_close)
        root.addWidget(bar)
        self._titlebar = bar
        bar.installEventFilter(self)

        # --- страницы ---
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_library_page())
        self._gov_page = GovWavePage(self.store)
        self._gov_page.toast.connect(self.show_toast)
        self._gov_page.library_changed.connect(self._on_library_changed)
        self.stack.addWidget(self._gov_page)
        self._settings_page = SettingsPage(self.store)
        self._settings_page.settings_changed.connect(self._on_settings_changed)
        self.stack.addWidget(self._settings_page)
        self.switch_page(PAGE_LIBRARY)

        self.toast = Toast(self)

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(18, 14, 18, 12)
        v.setSpacing(10)

        top = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Поиск по названию и тексту…")
        self.ed_search.textChanged.connect(self._on_search)
        top.addWidget(self.ed_search, 1)
        btn_add = QPushButton("+ Новая фраза")
        btn_add.setObjectName("primary")
        btn_add.clicked.connect(self._new_entry)
        top.addWidget(btn_add)
        v.addLayout(top)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chip_buttons: list[QPushButton] = []
        for name in ["Все", "★"] + CATEGORIES:
            b = QPushButton(name)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(name == self._filter_cat)
            b.clicked.connect(lambda _=False, n=name: self._on_chip(n))
            chips.addWidget(b)
            self._chip_buttons.append(b)
        chips.addStretch(1)
        v.addLayout(chips)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        self.flow = FlowLayout(content, margin=2, spacing=10)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)
        return page

    # ---------------------------------------------------------------- sender --
    def _build_sender(self) -> None:
        self.sender = Sender(
            settings_getter=lambda: self.store.settings,
            get_prev_foreground=lambda: self._prev_hwnd,
            is_overlay_visible=lambda: self._shown_flag,
            hide_overlay=self.hide_overlay_from_sender,
        )
        self._thread = QThread(self)
        self._worker = SendWorker(self.sender)
        self._worker.moveToThread(self._thread)
        self._thread.start()
        self.sender.copy_requested.connect(self._on_copy_requested)
        self.sender.status.connect(self.show_toast)
        self.sender.used.connect(self._on_used)

    # ----------------------------------------------------- library фильтры --
    def _on_search(self, text: str) -> None:
        self._search = text
        self._refresh_cards()

    def _on_chip(self, name: str) -> None:
        self._filter_cat = name
        for b in self._chip_buttons:
            b.setChecked(b.text() == name)
        self._refresh_cards()

    def _filtered_entries(self) -> list[TextEntry]:
        entries = self.store.search(self._search)
        if self._filter_cat == "★":
            entries = [e for e in entries if e.favorite]
        elif self._filter_cat != "Все":
            entries = [e for e in entries if e.category == self._filter_cat]
        return entries

    def _refresh_cards(self) -> None:
        while self.flow.count():
            it = self.flow.takeAt(0)
            w = it.widget() if it else None
            if w:
                w.setParent(None)
                w.deleteLater()
        for e in self._filtered_entries():
            card = PhraseCard(e, overlay_mode=False)
            card.edit_requested.connect(self._edit_entry)
            card.trigger_requested.connect(self.trigger_entry)
            card.favorite_requested.connect(self._toggle_favorite)
            self.flow.addWidget(card)

    # ------------------------------------------------------------ карточки --
    def _new_entry(self) -> None:
        entry = TextEntry(title="", text="", category=self._filter_cat
                          if self._filter_cat in CATEGORIES else "Разное")
        self._open_editor(entry, is_new=True)

    def _edit_entry(self, entry_id: str) -> None:
        e = self.store.get(entry_id)
        if e:
            self._open_editor(e, is_new=False)

    def _open_editor(self, entry: TextEntry, is_new: bool) -> None:
        dlg = TextEditorDialog(self.store, entry, self)
        if dlg.exec():
            data = dlg.result_entry()
            if is_new:
                self.store.add(data["title"], data["text"], data["category"], data["hotkey"])
            else:
                self.store.update(entry.id, **data)
            self._after_store_changed()

    def _toggle_favorite(self, entry_id: str) -> None:
        self.store.toggle_favorite(entry_id)
        self._refresh_cards()

    def _after_store_changed(self) -> None:
        self.store.save()
        self._refresh_cards()
        self.hotkeys.set_entries(self.store.entries)

    def _on_library_changed(self) -> None:
        self._refresh_cards()
        self.hotkeys.set_entries(self.store.entries)

    # -------------------------------------------------------------- overlay --
    def switch_page(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self.nav_lib.setChecked(idx == PAGE_LIBRARY)
        self.nav_gov.setChecked(idx == PAGE_GOV)
        self.nav_set.setChecked(idx == PAGE_SETTINGS)

    def is_overlay_visible(self) -> bool:
        return self._shown_flag

    @property
    def prev_foreground_hwnd(self) -> int:
        return self._prev_hwnd

    def toggle_overlay(self) -> None:
        if self._shown_flag:
            self._do_hide()
        else:
            self.show_overlay()

    def show_overlay(self) -> None:
        self._prev_hwnd = window_utils.get_foreground_hwnd()
        self.switch_page(PAGE_LIBRARY)
        self.show()
        self.raise_()
        self.activateWindow()
        self._force_topmost()

    def _force_topmost(self) -> None:
        try:
            hwnd = int(self.winId()) if sys.platform == "win32" else 0
            if hwnd:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, window_utils.HWND_TOPMOST, 0, 0, 0, 0,
                    window_utils.SWP_NOMOVE | window_utils.SWP_NOSIZE
                    | window_utils.SWP_SHOWWINDOW,
                )
        except Exception:
            pass

    def _do_hide(self) -> None:
        self.hide()
        self._restore_previous_focus()

    def _restore_previous_focus(self) -> None:
        if self._prev_hwnd and sys.platform == "win32":
            try:
                window_utils.focus_window(self._prev_hwnd)
            except Exception:
                pass

    def hide_overlay_from_sender(self) -> None:
        """Вызывается из рабочего потока — маршируем в GUI-поток."""
        QTimer.singleShot(0, self._do_hide)

    # ------------------------------------------------------------- действия --
    def trigger_entry(self, entry_id: str) -> None:
        e = self.store.get(entry_id)
        if e:
            self._worker.requested.emit(e)

    def on_text_hotkey(self, entry_id: str) -> None:
        self.trigger_entry(entry_id)

    def test_inject(self) -> None:
        self._worker.requested.emit(
            TextEntry(title="Тест", text="Majestic Text Helper: тест вставки OK", category="Разное")
        )

    @Slot(str)
    def _on_copy_requested(self, text: str) -> None:
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    @Slot(str)
    def _on_used(self, entry_id: str) -> None:
        if self.store.get(entry_id):
            self.store.inc_usage(entry_id)

    def show_toast(self, text: str) -> None:
        if self._shown_flag:
            self.toast.popup(text)
        elif self._tray_notify:
            try:
                self._tray_notify(APP_NAME, text)
            except Exception:
                pass

    def set_tray_notify(self, fn) -> None:
        self._tray_notify = fn

    def _on_settings_changed(self) -> None:
        s = self.store.settings
        self.hotkeys.start(s.menu_hotkey)
        self.hotkeys.set_entries(self.store.entries)
        try:
            self._gov_page.refresh_settings()
        except Exception:
            pass

    # ---------------------------------------------------------------- misc --
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

    # -------------------------------------------------------------- трей --
    def toggle_from_tray(self) -> None:
        QTimer.singleShot(0, self.toggle_overlay)

    def quit_from_tray(self) -> None:
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        QApplication.quit()

    def closeEvent(self, ev) -> None:  # noqa: N802
        ev.ignore()
        self._do_hide()
