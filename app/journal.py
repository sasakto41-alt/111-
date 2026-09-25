"""Общий журнал диагностики (только стандартная библиотека).

Пишется ДО любых импортов приложения, поэтому работает даже если
PySide6/приложение сломаны. Файл: error.log рядом с exe (portable),
иначе data/error.log проекта, иначе %APPDATA%/MajesticTextHelper.
"""
from __future__ import annotations

import datetime
import os
import sys

_fh = None
path = ""


def _candidates():
    out = []
    try:
        if getattr(sys, "frozen", False):
            out.append(os.path.join(os.path.dirname(sys.executable), "error.log"))
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out.append(os.path.join(root, "data", "error.log"))
    except Exception:
        pass
    appdata = os.getenv("APPDATA") or os.path.expanduser("~")
    out.append(os.path.join(appdata, "MajesticTextHelper", "error.log"))
    return out


def log(msg: str) -> None:
    """Аварийное журналирование: никогда не бросает исключений."""
    global _fh, path
    try:
        if _fh is None:
            for p in _candidates():
                try:
                    d = os.path.dirname(p)
                    if d:
                        os.makedirs(d, exist_ok=True)
                    fh = open(p, "a", encoding="utf-8", errors="replace")
                except Exception:
                    continue
                _fh, path = fh, p
                fh.write(
                    f"\n=== Запуск {datetime.datetime.now():%Y-%m-%d %H:%M:%S} "
                    f"(Python {sys.version.split()[0]}, "
                    f"frozen={getattr(sys, 'frozen', False)}) ===\n"
                )
                break
        if _fh is not None:
            _fh.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
            _fh.flush()
    except Exception:
        pass


def enable_faulthandler() -> None:
    """Нативные падения (Qt и пр.) тоже попадают в журнал."""
    try:
        import faulthandler

        log("инициализация журнала")
        if _fh is not None:
            faulthandler.enable(_fh)
    except Exception:
        pass


def show_box(text: str, error: bool = True) -> None:
    """Окно с сообщением через WinAPI — показывается, даже если Qt сломан."""
    try:
        import ctypes

        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, "Majestic Text Helper", flags)
    except Exception:
        try:
            print(text, file=sys.stderr)
        except Exception:
            pass
