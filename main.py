"""Majestic Text Helper — точка входа.

Режимы:
  python main.py            — обычный запуск
  python main.py --hidden   — запуск свёрнутым (только трей)
  python main.py --smoke    — самопроверка без GUI-цикла
  python main.py --version  — версия
Переменные окружения:
  MTH_DRYRUN=1              — ввод только логируется (безопасный тест)
  QT_QPA_PLATFORM=offscreen — без экрана (для CI/тестов)

При любой ошибке запуска отчёт пишется в data/error.log и показывается окно.
"""
from __future__ import annotations

import os
import sys

if "--smoke" in sys.argv and not os.getenv("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"


def _write_error_log(err: str) -> str:
    try:
        from app.config import get_data_dir

        log = get_data_dir() / "error.log"
        log.write_text(err, encoding="utf-8")
        return str(log)
    except Exception:
        return ""


def main() -> int:
    if "--version" in sys.argv or "-v" in sys.argv:
        from app import APP_VERSION

        print(f"Majestic Text Helper v{APP_VERSION}")
        return 0

    if "--smoke" in sys.argv:
        from app.smoke import run_smoke

        return run_smoke()

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

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
    except SystemExit:
        raise
    except BaseException:
        import traceback

        err = traceback.format_exc()
        log_path = _write_error_log(err)
        print(err, file=sys.stderr)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            qa = QApplication.instance() or QApplication(sys.argv)
            tail = "\n".join(err.strip().splitlines()[-6:])
            QMessageBox.critical(
                None,
                "Majestic Text Helper — ошибка запуска",
                "Программа не смогла запуститься.\n"
                + (f"Отчёт сохранён:\n{log_path}\n\n" if log_path else "")
                + tail,
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
