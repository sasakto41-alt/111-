"""Majestic Text Helper — точка входа.

Режимы:
  python main.py            — обычный запуск
  python main.py --hidden   — запуск свёрнутым (только трей)
  python main.py --smoke    — самопроверка без GUI-цикла
  python main.py --version  — версия
  python main.py --diag     — диагностика окружения (окно + лог, для отчёта)
Переменные окружения:
  MTH_DRYRUN=1              — ввод только логируется (безопасный тест)
  QT_QPA_PLATFORM=offscreen — без экрана (для CI/тестов)

Гарантии запуска (v3.3.0):
  • журнал пишется ДО любых импортов приложения (error.log рядом с exe,
    иначе data/error.log, иначе %APPDATA%/MajesticTextHelper/error.log);
  • faulthandler пишет в тот же журнал даже нативные падения Qt;
  • при любой ошибке — окно с текстом (WinAPI, работает без Qt);
  • повторный запуск не плодит второй экземпляр, а показывает подсказку.
"""
from __future__ import annotations

import datetime
import faulthandler
import os
import sys

if "--smoke" in sys.argv and not os.getenv("QT_QPA_PLATFORM"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

_LOG_FH = None
LOG_PATH = ""


def _log_candidates():
    out = []
    try:
        if getattr(sys, "frozen", False):
            out.append(os.path.join(os.path.dirname(sys.executable), "error.log"))
        root = os.path.dirname(os.path.abspath(__file__))
        out.append(os.path.join(root, "data", "error.log"))
    except Exception:
        pass
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    out.append(os.path.join(appdata, "MajesticTextHelper", "error.log"))
    return out


def log(msg: str) -> None:
    """Аварийное журналирование: работает даже если Qt/приложение сломаны."""
    global _LOG_FH, LOG_PATH
    try:
        if _LOG_FH is None:
            for p in _log_candidates():
                try:
                    d = os.path.dirname(p)
                    if d:
                        os.makedirs(d, exist_ok=True)
                    fh = open(p, "a", encoding="utf-8", errors="replace")
                except Exception:
                    continue
                _LOG_FH, LOG_PATH = fh, p
                fh.write(
                    f"\n=== Запуск {datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                    f"(Python {sys.version.split()[0]}, "
                    f"frozen={getattr(sys, 'frozen', False)}) ===\n"
                )
                break
        if _LOG_FH is not None:
            _LOG_FH.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
            _LOG_FH.flush()
    except Exception:
        pass


def _app_version() -> str:
    try:
        from app import APP_VERSION

        return APP_VERSION
    except Exception:
        return "?"


def show_box(text: str, error: bool = True) -> None:
    """Окно с сообщением через WinAPI — показывается, даже если Qt сломан."""
    try:
        import ctypes

        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, "Majestic Text Helper", flags)
    except Exception:
        pass


def _fatal(where: str, err: str) -> None:
    log(f"FATAL ({where}):\n{err}")
    tail = "\n".join(err.strip().splitlines()[-8:])
    show_box(
        "Программа не смогла запуститься.\n\n"
        f"Этап: {where}\n\n{tail}\n\n"
        f"Полный отчёт: {LOG_PATH or 'error.log (рядом с программой)'}\n"
        "Пришлите этот файл разработчику."
    )


def _excepthook(tp, val, tb):
    import traceback

    _fatal("необработанная ошибка", "".join(traceback.format_exception(tp, val, tb)))


sys.excepthook = _excepthook


def _diag() -> int:
    """--diag: собрать сведения об окружении и показать их."""
    import platform

    lines = [
        f"Версия: Majestic Text Helper v{_app_version()}",
        f"Python: {sys.version.split()[0]}",
        f"Система: {platform.platform()}",
        f"exe: {sys.executable}",
        f"frozen: {getattr(sys, 'frozen', False)}",
    ]
    try:
        import PySide6

        lines.append(f"PySide6: {PySide6.__version__} — импорт OK")
    except Exception as e:
        lines.append(f"PySide6: ОШИБКА ИМПОРТА — {e}")
    try:
        import keyboard  # noqa: F401

        lines.append("keyboard: импорт OK")
    except Exception as e:
        lines.append(f"keyboard: ОШИБКА ИМПОРТА — {e}")
    try:
        from app.config import get_data_dir

        lines.append(f"Папка данных: {get_data_dir()}")
    except Exception as e:
        lines.append(f"Папка данных: ошибка — {e}")
    log("диагностика (--diag):\n" + "\n".join(lines))
    text = "\n".join(lines) + f"\n\nЖурнал: {LOG_PATH or 'error.log'}"
    print(text)
    show_box(text, error=False)
    return 0


def main() -> int:
    args = sys.argv[1:]
    log(f"старт; argv={args!r}; exe={sys.executable}")

    if "--version" in args or "-v" in args:
        print(f"Majestic Text Helper v{_app_version()}")
        return 0
    if "--smoke" in args:
        from app.smoke import run_smoke

        return run_smoke()
    if "--diag" in args:
        return _diag()

    # faulthandler — как можно раньше, в тот же журнал
    try:
        if _LOG_FH is None:
            log("инициализация журнала")
        if _LOG_FH is not None:
            faulthandler.enable(_LOG_FH)
    except Exception:
        pass

    try:
        log("шаг 1/7: импорт PySide6…")
        from PySide6.QtCore import QLockFile, QTimer
        from PySide6.QtWidgets import QApplication

        log("шаг 1/7: OK")

        from app.config import APP_NAME
        from app.hotkeys import HotkeyManager
        from app.storage import Store
        from app.tray import TrayController
        from app.ui.main_window import MainWindow

        log("шаг 2/7: импорт приложения OK")

        if os.getenv("MTH_DRYRUN") == "1":
            import app.injector as _inj

            _inj.DRY_RUN = True
            log("MTH_DRYRUN=1 — ввод только логируется")

        log("шаг 3/7: проверка повторного запуска…")
        tmp = os.getenv("TEMP") or os.getenv("TMP") or os.path.expanduser("~")
        lock = QLockFile(os.path.join(tmp, "MajesticTextHelper.lock"))
        if not lock.tryLock(200):
            log("второй экземпляр: программа уже запущена")
            show_box(
                "Majestic Text Helper уже запущена.\n\n"
                "Ищите иконку «M» в трее возле часов:\n"
                "• двойной клик по иконке — открыть окно;\n"
                "• правый клик → «Выход» — закрыть совсем.",
                error=False,
            )
            return 0
        log("шаг 3/7: OK (первый экземпляр)")

        log("шаг 4/7: создание QApplication…")
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setQuitOnLastWindowClosed(False)
        log("шаг 4/7: OK")

        log("шаг 5/7: загрузка данных и окна…")
        store = Store()
        hotkeys = HotkeyManager()
        win = MainWindow(store, hotkeys)
        log("шаг 5/7: OK")

        tray = TrayController(win)
        tray_ok = False
        if store.settings.tray_enabled:
            tray_ok = tray.setup()
        if tray_ok:
            win.set_tray_notify(tray.show_message)
        log(f"шаг 6/7: трей — {'OK' if tray_ok else 'выключен или недоступен'}")

        hotkeys.menu_toggled.connect(win.toggle_overlay)
        hotkeys.text_triggered.connect(win.on_text_hotkey)
        hotkeys.start(store.settings.menu_hotkey)
        hotkeys.set_entries(store.entries)
        log("шаг 7/7: хоткеи зарегистрированы")

        if "--hidden" not in args:
            win.show()
            win.raise_()
            win.activateWindow()
            log("окно показано")
        elif tray_ok:
            log("запуск скрытым (трей)")
        else:
            win.show()
            log("трей недоступен — показал окно даже при --hidden")

        QTimer.singleShot(
            3000, lambda: log("приложение работает (прошло 3 с) — запуск успешен")
        )
        code = app.exec()
        log(f"событийный цикл завершён, код {code}")
        try:
            hotkeys.stop()
        except Exception:
            pass
        try:
            lock.unlock()
        except Exception:
            pass
        return code
    except SystemExit:
        raise
    except BaseException:
        import traceback

        _fatal("запуск", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
