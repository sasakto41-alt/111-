"""Глобальные горячие клавиши.

МЕНЮ-КЛАВИША (F6 по умолчанию) — v3.4.0: опрос GetAsyncKeyState в
фоновом потоке, БЕЗ системных хуков. Причина: низкоуровневые хуки
(WH_KEYBOARD_LL) в играх часто перестают доставать события — Windows
отключает «медленный» хук по таймауту, античиты мешают установке, а
если игра запущена от администратора, хук непривилегированного процесса
вовсе не видит клавиши. Опрос читает состояние клавиатуры напрямую и
от всего этого не зависит.

ХОТКЕИ ФРАЗ — через библиотеку keyboard (хук): срабатывают в том числе
внутри открытого оверлея, где фокус у нашего окна и хук работает.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Iterable, Optional

from PySide6.QtCore import QObject, Signal

from .journal import log
from .models import TextEntry, normalize_hotkey, to_latin_key

try:
    import keyboard
except Exception:            # клавиатурная библиотека недоступна —
    keyboard = None          # хоткеи фраз отключатся, меню останется

_POLL_SEC = 0.035            # период опроса клавиши меню
_DEBOUNCE = 0.35             # защита от дребезга/двойных срабатываний

_VK_SIMPLE = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10}


def vk_for_key(key: str) -> Optional[int]:
    """Виртуальный код клавиши (VK) для имени из хоткея (кириллица тоже)."""
    k = to_latin_key((key or "").strip().lower())
    if not k:
        return None
    if k in _VK_SIMPLE:
        return _VK_SIMPLE[k]
    if k == "win":
        return 0x5B          # VK_LWIN (в комбинациях проверяем и 0x5C)
    if len(k) == 2 and k[0] == "f" and k[1:].isdigit():
        n = int(k[1:])
        if 1 <= n <= 24:
            return 0x70 + (n - 1)          # VK_F1..VK_F24
    if len(k) == 1 and k.isalnum():
        return ord(k.upper())              # буквы и цифры
    return None


def combo_groups(hotkey: str) -> list[tuple[int, ...]]:
    """Хоткей → список групп VK. Клавиша нажата, если в КАЖДОЙ группе
    нажата хотя бы одна из её VK (win = LWIN или RWIN).
    Пустой список = комбинация не распознана."""
    hk = normalize_hotkey(hotkey or "")
    if not hk:
        return []
    groups: list[tuple[int, ...]] = []
    for part in hk.split("+"):
        part = part.strip().lower()
        if not part:
            continue
        if part == "win":
            groups.append((0x5B, 0x5C))
        else:
            vk = vk_for_key(part)
            if vk is None:
                return []
            groups.append((vk,))
    return groups


def _combo_pressed(groups: list[tuple[int, ...]]) -> bool:
    """Все группы нажаты прямо сейчас (GetAsyncKeyState, только Windows)."""
    if not groups:
        return False
    try:
        user32 = ctypes_windll()
        for grp in groups:
            if not any(user32.GetAsyncKeyState(v) & 0x8000 for v in grp):
                return False
        return True
    except Exception:
        return False


def ctypes_windll():
    import ctypes

    return ctypes.windll.user32


class _ComboPollThread(threading.Thread):
    """Фоновый опрос одной комбинации клавиш (GetAsyncKeyState, Windows).

    Используется для меню-клавиши, клавиши меню Госволны и макроса (v3.5.0):
    опрос работает и в игре, и при запуске от администратора — в отличие от
    низкоуровневых хуков.
    """

    def __init__(self, groups: list[tuple[int, ...]], on_fire: Callable[[], None],
                 name: str = "MTH-combo"):
        super().__init__(name=name, daemon=True)
        self._groups = groups
        self._on_fire = on_fire
        self._stop_evt = threading.Event()
        self._was = False
        self._last = 0.0

    def run(self) -> None:
        while not self._stop_evt.wait(_POLL_SEC):
            pressed = _combo_pressed(self._groups)
            if not pressed:
                self._was = False
                continue
            if self._was:
                continue                       # удержание — уже сработали
            self._was = True
            if time.monotonic() - self._last < _DEBOUNCE:
                continue
            self._last = time.monotonic()
            try:
                self._on_fire()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop_evt.set()


class HotkeyManager(QObject):
    menu_toggled = Signal()
    gov_toggled = Signal()         # v3.5.0: клавиша отдельного меню Госволны
    macro_triggered = Signal()     # v3.5.0: клавиша макроса с подтверждением
    text_triggered = Signal(str)   # id фразы
    state_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._menu_hotkey = ""
        self._groups: list[tuple[int, ...]] = []
        self._menu_hook = None               # только вне Windows
        self._entry_hooks: list = []
        self._lock = threading.Lock()
        self.error = ""
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._was_pressed = False
        self._last_fire = 0.0
        self._test_cb: Optional[Callable[[], None]] = None
        # v3.5.0: клавиши меню Госволны и макроса (опрос как у меню)
        self._gov_hotkey = ""
        self._gov_thread: Optional[_ComboPollThread] = None
        self._gov_hook = None
        self._macro_hotkey = ""
        self._macro_thread: Optional[_ComboPollThread] = None
        self._macro_hook = None
        self._reserved: set[str] = set()

    # ------------------------------------------------------------------ api --
    def start(self, menu_hotkey: str) -> None:
        """(Пере)запустить перехват меню-клавиши."""
        self._stop_menu()
        self.error = ""
        self._menu_hotkey = normalize_hotkey(menu_hotkey or "")
        if not self._menu_hotkey:
            self.error = "пустая горячая клавиша меню"
            self.state_changed.emit("ошибка")
            return
        self._groups = combo_groups(self._menu_hotkey)
        if not self._groups:
            self.error = f"непонятная клавиша меню: «{self._menu_hotkey}»"
            log(f"ошибка меню-клавиши: {self.error}")
            self.state_changed.emit("ошибка")
            return
        if sys.platform == "win32":
            # опрос GetAsyncKeyState — без хуков, надёжно в играх
            self._stop.clear()
            self._thread = _ComboPollThread(
                self._groups, self._on_menu, name="MTH-menu-key"
            )
            self._thread.start()
            self._rebuild_reserved()
            log(
                f"меню-клавиша {self._menu_hotkey.upper()}: запущен опрос "
                f"GetAsyncKeyState (период {_POLL_SEC * 1000:.0f} мс)"
            )
            self.state_changed.emit(f"меню: {self._menu_hotkey.upper()} (опрос активен)")
        else:
            if keyboard is None:
                self.error = "библиотека keyboard недоступна"
                self.state_changed.emit("ошибка")
                return
            try:
                self._menu_hook = keyboard.add_hotkey(
                    self._menu_hotkey, self._on_menu,
                    suppress=False, trigger_on_release=True,
                )
                log(f"меню-клавиша {self._menu_hotkey.upper()}: хук keyboard")
                self.state_changed.emit(f"меню: {self._menu_hotkey.upper()}")
            except Exception as e:
                self.error = f"Не удалось зарегистрировать {self._menu_hotkey.upper()}: {e}"
                log(f"ошибка регистрации меню-клавиши: {e}")
                self.state_changed.emit("ошибка")
            self._rebuild_reserved()

    # --------------------------------------------- меню Госволны и макрос --
    def start_gov(self, hotkey: str) -> None:
        """(Пере)запустить опрос клавиши отдельного меню Госволны (v3.5.0)."""
        self.stop_gov()
        hk = normalize_hotkey(to_latin_key(hotkey or ""))
        if not hk:
            return
        self._gov_hotkey = hk
        self._rebuild_reserved()
        groups = combo_groups(hk)
        if not groups:
            log(f"меню Госволны: непонятная клавиша «{hk}» — перехват не запущен")
            return
        if sys.platform == "win32":
            self._gov_thread = _ComboPollThread(
                groups, lambda: self._fire_extra(self.gov_toggled, hk),
                name="MTH-gov-key",
            )
            self._gov_thread.start()
            log(f"меню Госволны {hk.upper()}: запущен опрос GetAsyncKeyState")
        elif keyboard is not None:
            try:
                self._gov_hook = keyboard.add_hotkey(
                    hk, lambda: self._fire_extra(self.gov_toggled, hk),
                    suppress=False, trigger_on_release=True,
                )
                log(f"меню Госволны {hk.upper()}: хук keyboard")
            except Exception as e:
                log(f"меню Госволны: ошибка регистрации: {e}")
        self.state_changed.emit(f"госволна: {hk.upper()}")

    def stop_gov(self) -> None:
        t, self._gov_thread = self._gov_thread, None
        if t is not None:
            t.stop()
            if t.is_alive():
                t.join(timeout=0.8)
        if self._gov_hook is not None:
            try:
                keyboard.remove_hotkey(self._gov_hook)
            except Exception:
                pass
            self._gov_hook = None
        if self._gov_hotkey:
            self._gov_hotkey = ""
            self._rebuild_reserved()

    def start_macro(self, hotkey: str) -> None:
        """(Пере)запустить опрос комбинации макроса (v3.5.0)."""
        self.stop_macro()
        hk = normalize_hotkey(to_latin_key(hotkey or ""))
        if not hk:
            return
        self._macro_hotkey = hk
        self._rebuild_reserved()
        groups = combo_groups(hk)
        if not groups:
            log(f"макрос: непонятная комбинация «{hk}» — перехват не запущен")
            return
        if sys.platform == "win32":
            self._macro_thread = _ComboPollThread(
                groups, lambda: self._fire_extra(self.macro_triggered, hk),
                name="MTH-macro-key",
            )
            self._macro_thread.start()
            log(f"макрос {hk.upper()}: запущен опрос GetAsyncKeyState")
        elif keyboard is not None:
            try:
                self._macro_hook = keyboard.add_hotkey(
                    hk, lambda: self._fire_extra(self.macro_triggered, hk),
                    suppress=False, trigger_on_release=True,
                )
                log(f"макрос {hk.upper()}: хук keyboard")
            except Exception as e:
                log(f"макрос: ошибка регистрации: {e}")
        self.state_changed.emit(f"макрос: {hk.upper()}")

    def stop_macro(self) -> None:
        t, self._macro_thread = self._macro_thread, None
        if t is not None:
            t.stop()
            if t.is_alive():
                t.join(timeout=0.8)
        if self._macro_hook is not None:
            try:
                keyboard.remove_hotkey(self._macro_hook)
            except Exception:
                pass
            self._macro_hook = None
        if self._macro_hotkey:
            self._macro_hotkey = ""
            self._rebuild_reserved()

    def _fire_extra(self, sig, hk: str) -> None:
        log(f"доп. клавиша: нажатие зафиксировано ({hk.upper()})")
        try:
            sig.emit()
        except Exception as e:
            log(f"доп. клавиша: ошибка сигнала: {e}")

    def _rebuild_reserved(self) -> None:
        """Клавиши, занятые меню/госволной/макросом — хоткеи фраз их не берут."""
        r: set[str] = set()
        if self._menu_hotkey:
            r.add(self._menu_hotkey)
        if self._gov_hotkey:
            r.add(self._gov_hotkey)
        if self._macro_hotkey:
            r.add(self._macro_hotkey)
        self._reserved = r

    def set_entries(self, entries: Iterable[TextEntry]) -> None:
        """Перерегистрировать хоткеи фраз (пропускает занятые клавиши и дубли)."""
        with self._lock:
            for h in self._entry_hooks:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self._entry_hooks = []
            taken: set[str] = set()
            if keyboard is not None:
                for e in entries or []:
                    hk = normalize_hotkey(e.hotkey)
                    if not hk or hk in self._reserved or hk in taken:
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
            else:
                log("hotkeys: keyboard недоступна — хоткеи фраз отключены")
            self.state_changed.emit(f"фраз с хоткеями: {len(taken)}")

    def stop(self) -> None:
        with self._lock:
            self._stop_menu()
            self.stop_gov()
            self.stop_macro()
            for h in self._entry_hooks:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
            self._entry_hooks = []
            self._test_cb = None

    def is_menu_active(self) -> bool:
        """Меню-клавиша реально перехватывается прямо сейчас?"""
        if sys.platform == "win32":
            return self._thread is not None and self._thread.is_alive()
        return self._menu_hook is not None

    # ------------------------------------------------------------- тест клавиши --
    def start_menu_test(self, cb: Callable[[], None]) -> bool:
        """Режим проверки: следующее нажатие меню-клавиши вызовет cb
        (из фонового потока!) вместо переключения меню."""
        if not self.is_menu_active():
            return False
        self._test_cb = cb
        return True

    def stop_menu_test(self) -> None:
        self._test_cb = None

    # ----------------------------------------------------------------- threads --
    def _stop_menu(self) -> None:
        t = self._thread
        if t is not None:
            t.stop()
            if t.is_alive():
                t.join(timeout=0.8)
        self._thread = None
        if self._menu_hook is not None:
            try:
                keyboard.remove_hotkey(self._menu_hook)
            except Exception:
                pass
            self._menu_hook = None

    # ---------------------------------------------------------------- internal --
    def _on_menu(self) -> None:
        # каждый факт нажатия — в журнал: если пользователь скажет «F6 не
        # работает в игре», по error.log будет видно, дошло ли нажатие
        log(f"меню-клавиша: нажатие зафиксировано ({self._menu_hotkey.upper()})")
        cb = self._test_cb
        if cb is not None:
            try:
                cb()
            except Exception:
                pass
            return
        try:
            self.menu_toggled.emit()
        except Exception as e:
            log(f"меню-клавиша: ошибка сигнала toggle: {e}")
