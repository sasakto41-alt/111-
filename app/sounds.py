"""Звуковые сигналы (v3.8.0): пинг уведомления о госволне и макроса.

Без внешних файлов: на Windows — системный звук «Внимание»
(winsound.MessageBeep, играется асинхронно и НЕ блокирует GUI-поток),
на других платформах и при любой ошибке — тихий фолбэк QApplication.beep().
Звук выключается в Настройках: «Звук уведомления» (notify_sound) и
«Звук макроса» (macro_sound).
"""
from __future__ import annotations

from .journal import log


def _sound_enabled(settings, attr: str, default: bool = True) -> bool:
    """Прочитать галочку звука из настроек (безопасно для любых объектов)."""
    if settings is None:
        return default
    try:
        return bool(getattr(settings, attr, default))
    except Exception:
        return default


def _ping() -> bool:
    """Сыграть короткий системный сигнал. True — сигнал отправлен."""
    # Windows: системный звук без внешних файлов
    try:
        import winsound  # доступен только на Windows

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return True
    except Exception:
        pass
    # фолбэк Qt (работает и в песочнице без звуковой карты)
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.beep()
            return True
    except Exception as e:
        log(f"звук: не удалось воспроизвести ({e})")
    return False


def play_gov_notify(settings=None) -> bool:
    """Пинг красного уведомления «скоро госволна» (v3.8.0)."""
    if not _sound_enabled(settings, "notify_sound"):
        return False
    return _ping()


def play_macro_done(settings=None) -> bool:
    """Пинг «макрос выполнен полностью» (v3.8.0)."""
    if not _sound_enabled(settings, "macro_sound"):
        return False
    return _ping()
