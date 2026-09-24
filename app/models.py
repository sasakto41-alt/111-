"""Модели данных: фразы, настройки, валидация хоткеев, шаблоны госволны."""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional

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
_MOD_KEY_RE = re.compile(r"^((ctrl|alt|shift|win)\+)+([a-z0-9])$")


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

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Settings":
        known = {f.name for f in fields(Settings)}
        s = Settings(**{k: v for k, v in (d or {}).items() if k in known})
        s.normalize()
        return s

    def normalize(self) -> None:
        self.menu_hotkey = normalize_hotkey(self.menu_hotkey) or "f6"
        self.type_key = normalize_hotkey(self.type_key) or "t"
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

    def validate(self) -> List[str]:
        errs: List[str] = []
        if not is_valid_hotkey(self.menu_hotkey):
            errs.append("горячая клавиша меню некорректна (F1–F24 или ctrl/alt/shift+клавиша)")
        if not self.type_key or not is_valid_hotkey(self.type_key):
            errs.append("клавиша чата некорректна (одна буква/цифра или F-клавиша)")
        if self.inject_method not in INJECT_METHODS:
            errs.append("неизвестный способ вставки")
        return errs
