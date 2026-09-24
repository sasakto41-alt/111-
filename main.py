"""Majestic Text Helper — точка входа.

Режимы:
  python main.py            — обычный запуск
  python main.py --hidden   — запуск свёрнутым (только трей)
  python main.py --smoke    — самопроверка без GUI-цикла
Переменные окружения:
  MTH_DRYRUN=1              — ввод только логируется (безопасный тест)
  QT_QPA_PLATFORM=offscreen — без экрана (для CI/тестов)
"""
from __future__ import annotations

import os
import sys

if "--smoke" in sys.argv and not os.getenv("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main() -> int:
    if "--smoke" in sys.argv:
        from app.smoke import run_smoke

        return run_smoke()

    from PySide6.QtWidgets import QApplication

    from app.config import APP_NAME
    from app.hotkeys import HotkeyManager
    from app.storage import Store
    from app.tray import TrayController
    from app.ui.main_window import MainWindow

    if os.getenv("MTH_DRYRUN") == "1":
        import app.injector as _inj

        _inj.DRY_RUN = True

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    store = Store()
    hotkeys = HotkeyManager()
    win = MainWindow(store, hotkeys)

    tray = TrayController(win)
    tray_ok = False
    if store.settings.tray_enabled:
        tray_ok = tray.setup()
    if tray_ok:
        win.set_tray_notify(tray.show_message)

    hotkeys.menu_toggled.connect(win.toggle_overlay)
    hotkeys.text_triggered.connect(win.on_text_hotkey)
    hotkeys.start(store.settings.menu_hotkey)
    hotkeys.set_entries(store.entries)

    if "--hidden" not in sys.argv:
        win.show()

    code = app.exec()

    try:
        hotkeys.stop()
    except Exception:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
