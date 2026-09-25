"""Модели данных: фразы, настройки, валидация хоткеев, шаблоны госволны."""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional, Tuple

CATEGORIES: List[str] = ["Общение", "РП-отыгровки", "Команды", "Госволна", "Разное"]

INJECT_METHODS: List[str] = ["unicode", "ctrlv", "copy"]
INJECT_LABELS = {
    "unicode": "Печатать посимвольно (Unicode)",
    "ctrlv": "Вставить через Ctrl+V",
    "copy": "Копировать в буфер — вставите сами (T → Ctrl+V)",
}
INJECT_HINTS = {
    "unicode": "Программа сама откроет чат (T), подождёт и напечатает текст посимвольно. Enter не нажимается.",
    "ctrlv": "Программа сама откроет чат (T), скопирует текст в буфер и нажмёт Ctrl+V. Enter не нажимается.",
    "copy": "Никаких клавиш: текст просто копируется в буфер обмена, программа переключит вас в окно игры. Вы сами нажимаете T и вставляете Ctrl+V. Самый надёжный способ, если игра блокирует ввод.",
}

MODIFIERS = {"ctrl", "alt", "shift", "win"}
_FKEY_RE = re.compile(r"^f([1-9]|[12][0-9])$")
# одиночная клавиша (с модификаторами или без): буква/цифра или знак (` - = [ ] ; ' , . / \)
# v3.4.2: модификатор теперь НЕ обязателен — раньше «t» считалась ошибкой
_MOD_KEY_RE = re.compile(r"^((ctrl|alt|shift|win)\+)*([a-z0-9`=\[\];',./\\-])$")

# ЙЦУКЕН → латиница (та же ФИЗИЧЕСКАЯ клавиша). Если пользователь вводил
# клавишу чата с русской раскладкой («е» вместо «t», «ё» вместо «`»),
# программа сама превратит её в правильную физическую клавишу (v3.4.2).
_CYR_TO_LATIN = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y",
    "г": "u", "ш": "i", "щ": "o", "з": "p",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h",
    "о": "j", "л": "k", "д": "l",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n", "ь": "m",
    "ё": "`", "б": ",", "ю": ".", "ж": ";", "э": "'", "х": "]", "ъ": "\\",
}


def to_latin_key(key: str) -> str:
    """Кириллица → латиница по физическим клавишам («е»→«t», «ё»→«`»)."""
    s = (key or "").strip().lower()
    return "".join(_CYR_TO_LATIN.get(ch, ch) for ch in s)


def normalize_hotkey(hotkey: str) -> str:
    hotkey = (hotkey or "").strip().lower().replace(" ", "")
    if not hotkey:
        return ""
    parts = [p for p in hotkey.split("+") if p]
    mods = [p for p in parts if p in MODIFIERS]
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        return "+".join(parts)
    return "+".join(sorted(set(mods)) + keys)


def is_valid_hotkey(hotkey: str) -> bool:
    hotkey = normalize_hotkey(hotkey)
    if not hotkey:
        return False
    if _FKEY_RE.match(hotkey):
        return True
    return bool(_MOD_KEY_RE.match(hotkey))


def hotkey_conflicts(hotkey: str, menu_hotkey: str, others: List[str]) -> List[str]:
    """Список конфликтов хоткея фразы (текстом)."""
    h = normalize_hotkey(hotkey)
    res: List[str] = []
    if not h:
        return res
    if menu_hotkey and h == normalize_hotkey(menu_hotkey):
        res.append("совпадает с горячей клавишей меню")
    for o in others or []:
        if o and h == normalize_hotkey(o):
            res.append("уже занята другой фразой")
            break
    return res


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class TextEntry:
    id: str = field(default_factory=_new_id)
    title: str = ""
    text: str = ""
    category: str = "Разное"
    hotkey: str = ""
    favorite: bool = False
    usage: int = 0
    order: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TextEntry":
        known = {f.name for f in fields(TextEntry)}
        return TextEntry(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------- ГОСТВОЛНА --
# Памятка: занимать волну за 10–120 минут до вещания; интервал между
# объявлениями одной организации ≥ 20 минут; общий интервал ≥ 10 минут;
# не более трёх волн в час; слоты только XX:00/10/20/30/40/50.

DISCORD_ANNOUNCE_URL = (
    "https://discord.com/channels/905216724712976394/"
    "1529212572098760865/1529561075295584457"
)

GNEWS_PALETO = (
    "/gnews Доброго времени суток, уважаемые жители штата! Sheriff Department "
    "объявляет набор новобранцев в свои ряды. Для вступления необходимо: военный "
    "билет, действующие медицинские справки, отсутствие судимостей и лицензия на "
    "оружие. Также мы выдаем лицензию на оружие, для оформления необходимо: "
    "действующая медицинская справка, проживание в штате не менее двух лет и "
    "оплата установленной государственной пошлины. Ждем всех желающих по адресу "
    "Бульвар Палето, на GPS отмечены Красным щитом. С уважением, отдел Internal "
    "Affairs Division."
)

GNEWS_SANDY = (
    "/gnews Доброго времени суток, уважаемые жители штата! Sheriff Department "
    "объявляет набор новобранцев в свои ряды. Для вступления необходимо: военный "
    "билет, действующие медицинские справки, отсутствие судимостей и лицензия на "
    "оружие. Также мы выдаем лицензию на оружие, для оформления необходимо: "
    "действующая медицинская справка, проживание в штате не менее двух лет и "
    "оплата установленной государственной пошлины. Ждем всех желающих по адресу "
    "Переулок Сенди-шорс, на GPS отмечены Красным щитом. Также мы выдаем лицензии "
    "на оружие. С уважением, отдел Internal Affairs Division."
)


# ------------------------------------------------------------------- ЧАСОВОЙ ПОЯС --
_TZ_EXTRA = {
    -3.5: "UTC-3:30", 3.5: "UTC+3:30", 4.5: "UTC+4:30", 5.5: "UTC+5:30",
    5.75: "UTC+5:45", 6.5: "UTC+6:30", 9.5: "UTC+9:30", 10.5: "UTC+10:30",
    12.75: "UTC+12:45",
}


def timezone_options() -> List[Tuple[float, str]]:
    """Список (offset_часов, подпись) для выбора пояса госволны."""
    opts = [(float(h), "UTC+0" if h == 0 else f"UTC{h:+d}") for h in range(-12, 15)]
    opts.extend(_TZ_EXTRA.items())
    opts.sort(key=lambda p: p[0])
    return opts


# --- ключи действий макроса госволны (v3.5.0) ---
GOV_MACRO_ACTIONS = (
    "step1", "step2", "step3", "step4", "step5", "gnews_paleto", "gnews_sandy",
)
GOV_MACRO_LABELS = {
    "step1": "1. Узнать занятость",
    "step2": "2. Занять волну",
    "step3": "3. Занял гос.волну (подтвердить)",
    "step4": "4. Просьба принять (/report)",
    "step5": "5. Освободить волну",
    "gnews_paleto": "Объявление /gnews: Палето-Бэй",
    "gnews_sandy": "Объявление /gnews: Сенди-Шорс",
}


@dataclass
class Settings:
    menu_hotkey: str = "f6"
    type_key: str = "t"
    pre_delay_ms: int = 1000
    inject_method: str = "unicode"
    tray_enabled: bool = True
    whitelist_enabled: bool = False
    whitelist_exes: List[str] = field(default_factory=list)
    whitelist_titles: List[str] = field(default_factory=list)
    # --- целевое окно игры (v3.2): программа сама знает, куда переключаться ---
    target_title: str = ""
    target_exe: str = ""
    # --- раздел «Госволна» (v3.2) ---
    gov_org: str = "LSCSD"
    gov_last_slots: str = ""      # "15:00 15:20 15:40"
    gov_gnews_paleto: str = ""    # "" → шаблон по умолчанию
    gov_gnews_sandy: str = ""
    gov_tz_auto: bool = True      # True — время компьютера; False — ручной пояс
    gov_utc_offset: float = 0.0   # UTC±X, когда gov_tz_auto=False
    # --- отдельное меню Госволны и макрос (v3.5.0) ---
    gov_menu_enabled: bool = False     # отдельное окно с командами госволны
    gov_menu_hotkey: str = "f7"        # его клавиша открыть/закрыть
    gov_macro_enabled: bool = False    # макрос с окном подтверждения
    gov_macro_hotkey: str = "f8"       # комбинация клавиш макроса
    gov_macro_action: str = "step2"    # одиночная команда (начальный шаг)
    gov_macro_confirm_sec: int = 5     # задержка кнопки «Да»
    # v3.6.0: макрос как ПОСЛЕДОВАТЕЛЬНОСТЬ шагов (собирается в меню F7)
    gov_macro_steps: List[str] = field(default_factory=lambda: ["step2"])
    gov_macro_step_pause_ms: int = 4000  # пауза между шагами
    # v3.7.0: авто-Enter после каждого шага макроса + уведомление о госволне
    gov_macro_press_enter: bool = True  # после шага макрос само жмёт Enter
    gov_notify_enabled: bool = True     # красное уведомление «скоро госволна»
    gov_notify_minutes: int = 3         # за сколько минут до слота предупреждать
    # v3.8.0: живой таймер до госволны, звуки, вид оверлеев, перенос данных
    gov_countdown_enabled: bool = True  # таймер «До Госволны: ММ:СС» поверх игры
    gov_countdown_minutes: int = 15     # показывать таймер, когда до слота ≤ N минут
    notify_sound: bool = True           # звук красного уведомления о госволне
    macro_sound: bool = True            # звук, когда макрос выполнен полностью
    overlay_opacity: int = 100          # непрозрачность оверлеев, 30..100 %
    overlay_pos_x: int = -1             # запомненная позиция окна F6 (-1 = авто)
    overlay_pos_y: int = -1
    gov_pos_x: int = -1                 # запомненная позиция меню Госволны (F7)
    gov_pos_y: int = -1

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        known = {f.name for f in fields(Settings)}
        s = Settings(**{k: v for k, v in (d or {}).items() if k in known})
        s.normalize()
        return s

    def normalize(self) -> None:
        # кириллица → физическая латинская клавиша (v3.4.2: «нажимает ё»)
        self.menu_hotkey = normalize_hotkey(to_latin_key(self.menu_hotkey)) or "f6"
        self.type_key = normalize_hotkey(to_latin_key(self.type_key)) or "t"
        try:
            self.pre_delay_ms = int(self.pre_delay_ms)
        except Exception:
            self.pre_delay_ms = 1000
        self.pre_delay_ms = max(100, min(10000, self.pre_delay_ms))
        if self.inject_method not in INJECT_METHODS:
            self.inject_method = "unicode"
        if self.gov_org is None:
            self.gov_org = "LSCSD"
        if not isinstance(self.whitelist_exes, list):
            self.whitelist_exes = []
        if not isinstance(self.whitelist_titles, list):
            self.whitelist_titles = []
        try:
            self.gov_utc_offset = float(self.gov_utc_offset)
        except Exception:
            self.gov_utc_offset = 0.0
        self.gov_utc_offset = max(-12.0, min(14.0, self.gov_utc_offset))
        self.gov_tz_auto = bool(self.gov_tz_auto)
        # v3.5.0: отдельное меню Госволны и макрос
        self.gov_menu_enabled = bool(self.gov_menu_enabled)
        self.gov_macro_enabled = bool(self.gov_macro_enabled)
        self.gov_menu_hotkey = normalize_hotkey(to_latin_key(self.gov_menu_hotkey)) or "f7"
        self.gov_macro_hotkey = normalize_hotkey(to_latin_key(self.gov_macro_hotkey)) or "f8"
        if self.gov_macro_action not in GOV_MACRO_ACTIONS:
            self.gov_macro_action = "step2"
        try:
            self.gov_macro_confirm_sec = int(self.gov_macro_confirm_sec)
        except Exception:
            self.gov_macro_confirm_sec = 5
        self.gov_macro_confirm_sec = max(0, min(30, self.gov_macro_confirm_sec))
        # v3.6.0: последовательность шагов макроса (только известные, без дублей)
        if not isinstance(self.gov_macro_steps, list):
            self.gov_macro_steps = []
        clean: List[str] = []
        for st in self.gov_macro_steps:
            st = str(st).strip()
            if st in GOV_MACRO_ACTIONS and st not in clean:
                clean.append(st)
        if not clean:
            clean = [self.gov_macro_action]
        self.gov_macro_steps = clean[: len(GOV_MACRO_ACTIONS)]
        try:
            self.gov_macro_step_pause_ms = int(self.gov_macro_step_pause_ms)
        except Exception:
            self.gov_macro_step_pause_ms = 4000
        self.gov_macro_step_pause_ms = max(500, min(30000, self.gov_macro_step_pause_ms))
        # v3.7.0: авто-Enter макроса и уведомление о госволне
        self.gov_macro_press_enter = bool(self.gov_macro_press_enter)
        self.gov_notify_enabled = bool(self.gov_notify_enabled)
        try:
            self.gov_notify_minutes = int(self.gov_notify_minutes)
        except Exception:
            self.gov_notify_minutes = 3
        self.gov_notify_minutes = max(1, min(30, self.gov_notify_minutes))
        # v3.8.0: таймер до госволны, звуки, прозрачность, позиции оверлеев
        self.gov_countdown_enabled = bool(self.gov_countdown_enabled)
        try:
            self.gov_countdown_minutes = int(self.gov_countdown_minutes)
        except Exception:
            self.gov_countdown_minutes = 15
        self.gov_countdown_minutes = max(5, min(60, self.gov_countdown_minutes))
        self.notify_sound = bool(self.notify_sound)
        self.macro_sound = bool(self.macro_sound)
        try:
            self.overlay_opacity = int(self.overlay_opacity)
        except Exception:
            self.overlay_opacity = 100
        self.overlay_opacity = max(30, min(100, self.overlay_opacity))
        for _attr in ("overlay_pos_x", "overlay_pos_y", "gov_pos_x", "gov_pos_y"):
            try:
                _v = int(getattr(self, _attr))
            except Exception:
                _v = -1
            # -1 = авто-позиция; остальное — запомненные координаты
            # (не ограничиваем: у вторых мониторов бывают отрицательные X/Y)
            setattr(self, _attr, _v)

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not is_valid_hotkey(self.menu_hotkey):
            errs.append("горячая клавиша меню некорректна (F1–F24 или ctrl/alt/shift+клавиша)")
        if not self.type_key or not is_valid_hotkey(self.type_key):
            errs.append("клавиша чата некорректна (одна буква/цифра или F-клавиша)")
        if self.inject_method not in INJECT_METHODS:
            errs.append("неизвестный способ вставки")
        # v3.5.0: клавиши отдельного меню Госволны и макроса не должны конфликтовать
        if self.gov_menu_enabled:
            if not is_valid_hotkey(self.gov_menu_hotkey):
                errs.append("клавиша меню Госволны некорректна (F1–F24 или ctrl/alt/shift+клавиша)")
            elif normalize_hotkey(self.gov_menu_hotkey) == normalize_hotkey(self.menu_hotkey):
                errs.append("клавиша меню Госволны совпадает с клавишей основного меню")
        if self.gov_macro_enabled:
            if not is_valid_hotkey(self.gov_macro_hotkey):
                errs.append("клавиша макроса некорректна (F1–F24 или ctrl/alt/shift+клавиша)")
            else:
                _mk = normalize_hotkey(self.gov_macro_hotkey)
                if _mk == normalize_hotkey(self.menu_hotkey):
                    errs.append("клавиша макроса совпадает с клавишей основного меню")
                elif self.gov_menu_enabled and _mk == normalize_hotkey(self.gov_menu_hotkey):
                    errs.append("клавиша макроса совпадает с клавишей меню Госволны")
        return errs
