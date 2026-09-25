"""Системный трей: иконка, меню, уведомления (фидбек, когда окно скрыто)."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .icons import app_icon


class TrayController:
    def __init__(self, window):
        self.window = window
        self.tray: QSystemTrayIcon | None = None

    def setup(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.tray = QSystemTrayIcon(app_icon())
        menu = QMenu()

        act_toggle = QAction("Показать / скрыть меню", menu)
        act_toggle.triggered.connect(self.toggle)
        menu.addAction(act_toggle)

        act_test = QAction("Тест вставки (в активное окно)", menu)
        act_test.triggered.connect(self.test)
        menu.addAction(act_test)

        menu.addSeparator()
        act_quit = QAction("Выход", menu)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Majestic Text Helper")
        self.tray.activated.connect(self._on_activated)
        self.tray.show()
        return True

    def _on_activated(self, reason) -> None:
        try:
            if reason == QSystemTrayIcon.Trigger:
                self.toggle()
        except Exception:
            pass

    def toggle(self) -> None:
        try:
            self.window.toggle_from_tray()
        except Exception:
            pass

    def test(self) -> None:
        try:
            self.window.test_inject()
        except Exception:
            pass

    def show_message(self, title: str, text: str) -> None:
        if self.tray:
            try:
                self.tray.showMessage(title, text, QSystemTrayIcon.Information, 3000)
            except Exception:
                pass

    def quit(self) -> None:
        try:
            self.window.quit_from_tray()
        except Exception:
            pass
