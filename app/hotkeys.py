"""Глобальные горячие клавиши через библиотеку keyboard (системный хук)."""
from __future__ import annotations

import threading
from typing import Iterable

import keyboard
from PySide6.QtCore import QObject, Signal

from .models import TextEntry, normalize_hotkey


class HotkeyManager(QObject):
    menu_toggled = Signal()
    text_triggered = Signal(str)   # id фразы
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menu_hotkey = ""
        self._menu_hook = None
        self._entry_hooks = []
        self._lock = threading.Lock()
        self.error = ""

    # ------------------------------------------------------------------ api --
    def start(self, menu_hotkey: str) -> None:
        self.stop()
        self.error = ""
        self._menu_hotkey = normalize_hotkey(menu_hotkey)
        if not self._menu_hotkey:
            self.error = "пустая горячая клавиша меню"
            self.state_changed.emit("ошибка")
            return
        try:
            self._menu_hook = keyboard.add_hotkey(
                self._menu_hotkey, self._on_menu, suppress=False, trigger_on_release=True
            )
            self.state_changed.emit(f"меню: {self._menu_hotkey.upper()}")
        except Exception as e:
            self.error = f"Не удалось зарегистрировать {self._menu_hotkey.upper()}: {e}"
            self._menu_hook = None
            self.state_changed.emit("ошибка")

    def set_entries(self, entries: Iterable[TextEntry]) -> None:
        """Перерегистрировать хоткеи фраз (пропускает конфликты с меню и дубли)."""
        with self._lock:
            for h in self._entry_hooks:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self._entry_hooks = []
            taken = set()
            for e in entries or []:
                hk = normalize_hotkey(e.hotkey)
                if not hk or hk == self._menu_hotkey or hk in taken:
                    continue
                try:
                    hook = keyboard.add_hotkey(
                        hk, lambda eid=e.id: self.text_triggered.emit(eid),
                        suppress=False, trigger_on_release=True,
                    )
                    self._entry_hooks.append(hook)
                    taken.add(hk)
                except Exception:
                    continue
            self.state_changed.emit(f"фраз с хоткеями: {len(taken)}")

    def stop(self) -> None:
        with self._lock:
            if self._menu_hook is not None:
                try:
                    keyboard.remove_hotkey(self._menu_hook)
                except Exception:
                    pass
                self._menu_hook = None
            for h in self._entry_hooks:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self._entry_hooks = []

    # -------------------------------------------------------------- internal --
    def _on_menu(self) -> None:
        try:
            self.menu_toggled.emit()
        except Exception:
            pass
