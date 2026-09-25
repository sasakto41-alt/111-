"""Раздел «Госволна» — помощник подачи государственных волн (по памятке LSCSD).

Правила памятки, зашитые в логику:
  • занимать волну разрешено за 10–120 минут до начала вещания;
  • интервал между объявлениями одной организации — не менее 20 минут;
  • общий интервал между объявлениями — не менее 10 минут;
  • за час — не более трёх волн;
  • время подачи — только десятые интервалы: XX:00/10/20/30/40/50;
  • порядок: проверить → занять → «занял» → объявление → /report → освободить.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QTime, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QTimeEdit, QVBoxLayout, QWidget,
)

from ..models import (
    DISCORD_ANNOUNCE_URL, GOV_MACRO_ACTIONS, GOV_MACRO_LABELS,
    GNEWS_PALETO, GNEWS_SANDY,
)
from .theme import DANGER, MUTED, OK
from .widgets import SectionFrame

VALID_MINUTES = (0, 10, 20, 30, 40, 50)

MEMO_TEXT = (
    "⏰ Занимать волну: за 10–120 минут до вещания.  •  Интервал между объявлениями "
    "вашей организации: ≥ 20 минут.  •  Общий интервал: ≥ 10 минут.  •  Не более 3 волн в час.\n"
    "📌 Время подачи — только десятые интервалы: XX:00, XX:10, XX:20, XX:30, XX:40, XX:50. "
    "Повторное занятие — только после публикации объявления на последнее время.\n"
    "📡 Порядок: 1) узнать занятость (/dep вопрос) → 2) если тишина 5 минут — занять (/dep) → "
    "3) подтвердить (/dep «Занял гос.волну») → 4) отправить объявление в Discord-канал → "
    "5) попросить администрацию принять (/report) → 6) после публикации освободить (/dep)."
)


# --------------------------------------------------------- чистые функции --
def _parse_hhmm(s: str) -> Optional[Tuple[int, int]]:
    try:
        h, m = s.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:
        pass
    return None


def now_in_tz(settings) -> datetime:
    """Текущее время в поясе, выбранном для госволны (settings.gov_tz_*)."""
    if getattr(settings, "gov_tz_auto", True):
        return datetime.now()
    try:
        off = float(getattr(settings, "gov_utc_offset", 0.0) or 0.0)
    except Exception:
        off = 0.0
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=off)


def suggest_slots(now: Optional[datetime] = None, count: int = 3) -> List[str]:
    """Ближайшие допустимые слоты: за 10–120 минут, шаг сетки 10 мин,
    между своими объявлениями ≥ 20 минут (как в примере 15:00 15:20 15:40)."""
    now = now or datetime.now()
    base = now.replace(second=0, microsecond=0) + timedelta(minutes=10)
    if base.minute % 10:
        base += timedelta(minutes=10 - base.minute % 10)
    latest = now + timedelta(minutes=120)
    slots: List[str] = []
    t = base
    while len(slots) < count and t <= latest:
        slots.append(t.strftime("%H:%M"))
        t += timedelta(minutes=20)
    return slots


def validate_slots(slots: List[str], now: Optional[datetime] = None) -> List[str]:
    """Список предупреждений по правилам памятки (пустой список = всё хорошо)."""
    now = now or datetime.now()
    warns: List[str] = []
    parsed: List[Tuple[str, int, int]] = []
    for s in slots:
        pm = _parse_hhmm(s)
        if pm is None:
            warns.append(f"«{s}» — не похоже на время ЧЧ:ММ")
        else:
            parsed.append((s, pm[0], pm[1]))
    for s, _h, m in parsed:
        if m % 10 != 0:
            warns.append(f"{s}: минуты должны быть 00, 10, 20, 30, 40 или 50")
    for (a, ah, am), (b, bh, bm) in zip(parsed, parsed[1:]):
        if (bh * 60 + bm) - (ah * 60 + am) < 20:
            warns.append(f"{a} → {b}: между объявлениями одной организации ≥ 20 минут")
    for s, h, m in parsed:
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t < now:
            t += timedelta(days=1)
        delta = (t - now).total_seconds() / 60.0
        if delta < 10 - 1e-6:
            warns.append(f"{s}: до вещания меньше 10 минут — ещё рано занимать")
        elif delta > 120 + 1e-6:
            warns.append(f"{s}: до вещания больше 120 минут — слишком рано занимать")
    if len(parsed) > 3:
        warns.append("За час можно занять не более трёх волн")
    if not parsed and not warns:
        warns.append("Укажите хотя бы один слот времени")
    return warns


def build_commands(org: str, slots: List[str]) -> List[Tuple[str, str]]:
    """Команды подачи госволны в порядке памятки."""
    s = " ".join(slots)
    org = (org or "").strip() or "LSCSD"
    return [
        ("1. Узнать занятость", f"/dep to All: Занята ли гос. волна на {s}?"),
        ("2. Занять волну", f"/dep to All: Фракция {org} занимает гос. волну на {s}"),
        ("3. Подтвердить занятие", "/dep to all: Занял гос.волну"),
        ("4. Просьба принять волну", "/report Примите, пожалуйста, гос волну"),
        ("5. Освободить волну", "/dep to All: Освободил гос. волну."),
    ]


# ------------------------------------------- helpers для меню и макроса --
def gov_slots_for(settings) -> List[str]:
    """Слоты времени, выбранные пользователем (settings.gov_last_slots).

    Если в сохранённом значении нет трёх корректных времён — подбираются
    ближайшие допустимые по памятке (от времени в выбранном поясе).
    """
    raw = (getattr(settings, "gov_last_slots", "") or "").split()
    slots = [x for x in raw if _parse_hhmm(x)]
    if len(slots) != 3:
        slots = suggest_slots(now_in_tz(settings))
    return slots[:3]


# ключи макроса → названия шагов из build_commands (v3.5.0)
_MACRO_STEP_KEYS = {
    "step1": "1. Узнать занятость",
    "step2": "2. Занять волну",
    "step3": "3. Подтвердить занятие",
    "step4": "4. Просьба принять волну",
    "step5": "5. Освободить волну",
}


def resolve_macro_command(settings, action: str) -> str:
    """Текст команды для макроса по ключу действия (GOV_MACRO_ACTIONS)."""
    org = (getattr(settings, "gov_org", "") or "LSCSD").strip() or "LSCSD"
    slots = gov_slots_for(settings)
    cmds = dict(build_commands(org, slots))
    if action == "gnews_paleto":
        return getattr(settings, "gov_gnews_paleto", "") or GNEWS_PALETO
    if action == "gnews_sandy":
        return getattr(settings, "gov_gnews_sandy", "") or GNEWS_SANDY
    key = _MACRO_STEP_KEYS.get(action)
    if key is None:
        key = action if action in cmds else "2. Занять волну"
    return cmds.get(key, "")


def plan_macro_sequence(settings) -> List[Tuple[str, str]]:
    """Последовательность шагов макроса: [(подпись, команда), …] (v3.6.0).

    Порядок задает settings.gov_macro_steps (собирается в меню F7).
    Если список пуст или все шаги неизвестны — берётся одиночный шаг
    settings.gov_macro_action (поведение v3.5.0). Пустые команды
    (например, не заполнен шаблон /gnews) пропускаются.
    """
    steps = list(getattr(settings, "gov_macro_steps", []) or [])
    if not any(st in GOV_MACRO_ACTIONS for st in steps):
        steps = [getattr(settings, "gov_macro_action", "step2")]
    out: List[Tuple[str, str]] = []
    for st in steps:
        if st not in GOV_MACRO_ACTIONS:
            continue
        text = resolve_macro_command(settings, st)
        if text:
            out.append((GOV_MACRO_LABELS.get(st, st), text))
    return out


# ------------------------------------------------------------------- UI --
class GovWavePage(QWidget):
    toast = Signal(str)            # сообщение в главное окно
    library_changed = Signal()     # после сохранения команд в библиотеку

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        root = QWidget()
        scroll.setWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 18, 18)
        v.setSpacing(12)

        # описание
        desc = QLabel(
            "Помощник подачи государственной волны: подберёт допустимое время по памятке "
            "и соберёт готовые команды. Скопируйте кнопку «Копировать» и вставьте в игру "
            "(T → Ctrl+V) или сохраните команды в библиотеку, чтобы вставлять по хоткею."
        )
        desc.setObjectName("hint")
        desc.setWordWrap(True)
        v.addWidget(desc)

        # ------------------------------------------------ время вещания --
        sec_time = SectionFrame("Время вещания")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Организация/фракция:"), 0, 0)
        self.ed_org = QLineEdit()
        self.ed_org.setPlaceholderText("LSCSD")
        grid.addWidget(self.ed_org, 0, 1, 1, 3)

        self.time_edits: list[QTimeEdit] = []
        for i in range(3):
            te = QTimeEdit()
            te.setDisplayFormat("HH:mm")
            te.setFixedWidth(92)
            self.time_edits.append(te)
            grid.addWidget(QLabel(f"Слот {i + 1}:"), 1, i * 2)
            grid.addWidget(te, 1, i * 2 + 1)
        btn_auto = QPushButton("Подобрать время")
        btn_auto.setObjectName("accent")
        btn_auto.setToolTip("Ближайшие допустимые слоты по правилам памятки")
        btn_auto.clicked.connect(self._auto_slots)
        grid.addWidget(btn_auto, 1, 6)

        sec_time.body_layout().addLayout(grid)
        self.lbl_validation = QLabel("")
        self.lbl_validation.setWordWrap(True)
        sec_time.body_layout().addWidget(self.lbl_validation)
        self.lbl_tz = QLabel("")
        self.lbl_tz.setObjectName("hint")
        sec_time.body_layout().addWidget(self.lbl_tz)
        v.addWidget(sec_time)

        # -------------------------------------------------------- команды --
        sec_cmd = SectionFrame("Команды (в порядке памятки)")
        grid_cmd = QGridLayout()
        grid_cmd.setHorizontalSpacing(8)
        grid_cmd.setVerticalSpacing(8)
        self.cmd_fields: dict[str, QLineEdit] = {}
        for row, (name, _tpl) in enumerate(self._command_templates()):
            grid_cmd.addWidget(QLabel(name), row, 0)
            fld = QLineEdit()
            fld.setReadOnly(True)
            self.cmd_fields[name] = fld
            grid_cmd.addWidget(fld, row, 1)
            btn = QPushButton("Копировать")
            btn.clicked.connect(lambda _=False, n=name: self._copy_cmd(n))
            grid_cmd.addWidget(btn, row, 2)
        sec_cmd.body_layout().addLayout(grid_cmd)

        h_discord = QHBoxLayout()
        btn_open = QPushButton("Открыть канал объявления (Discord)")
        btn_open.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(DISCORD_ANNOUNCE_URL))
        )
        h_discord.addWidget(btn_open)
        btn_copy_url = QPushButton("Скопировать ссылку")
        btn_copy_url.clicked.connect(
            lambda: self._copy_text(DISCORD_ANNOUNCE_URL, "Ссылка скопирована")
        )
        h_discord.addWidget(btn_copy_url)
        h_discord.addStretch(1)
        sec_cmd.body_layout().addLayout(h_discord)

        h_save = QHBoxLayout()
        btn_save = QPushButton("Сохранить команды в библиотеку")
        btn_save.setObjectName("primary")
        btn_save.setToolTip("Создаст фразы категории «Госволна» — можно назначить хоткеи")
        btn_save.clicked.connect(self._save_to_library)
        h_save.addWidget(btn_save)
        h_save.addStretch(1)
        sec_cmd.body_layout().addLayout(h_save)
        v.addWidget(sec_cmd)

        # ---------------------------------------------------------- gnews --
        sec_news = SectionFrame("Объявление /gnews (шаблоны LSCSD)")
        self.txt_paleto = QPlainTextEdit()
        self.txt_paleto.setFixedHeight(96)
        self.txt_paleto.setPlaceholderText("Шаблон для Палето-Бэй…")
        sec_news.body_layout().addWidget(QLabel("Палето-Бэй:"))
        sec_news.body_layout().addWidget(self.txt_paleto)
        h_p = QHBoxLayout()
        btn_cp = QPushButton("Копировать")
        btn_cp.clicked.connect(
            lambda: self._copy_text(self.txt_paleto.toPlainText().strip(), "Объявление Палето скопировано")
        )
        h_p.addWidget(btn_cp)
        btn_rs = QPushButton("Сбросить шаблон")
        btn_rs.setObjectName("ghost")
        btn_rs.clicked.connect(lambda: self._reset_gnews("paleto"))
        h_p.addWidget(btn_rs)
        h_p.addStretch(1)
        sec_news.body_layout().addLayout(h_p)

        self.txt_sandy = QPlainTextEdit()
        self.txt_sandy.setFixedHeight(96)
        self.txt_sandy.setPlaceholderText("Шаблон для Сенди-Шорс…")
        sec_news.body_layout().addWidget(QLabel("Сенди-Шорс:"))
        sec_news.body_layout().addWidget(self.txt_sandy)
        h_s = QHBoxLayout()
        btn_cs = QPushButton("Копировать")
        btn_cs.clicked.connect(
            lambda: self._copy_text(self.txt_sandy.toPlainText().strip(), "Объявление Сенди скопировано")
        )
        h_s.addWidget(btn_cs)
        btn_rs2 = QPushButton("Сбросить шаблон")
        btn_rs2.setObjectName("ghost")
        btn_rs2.clicked.connect(lambda: self._reset_gnews("sandy"))
        h_s.addWidget(btn_rs2)
        h_s.addStretch(1)
        sec_news.body_layout().addLayout(h_s)
        v.addWidget(sec_news)

        # -------------------------------------------------------- памятка --
        sec_memo = SectionFrame("Памятка")
        lbl_memo = QLabel(MEMO_TEXT)
        lbl_memo.setObjectName("hint")
        lbl_memo.setWordWrap(True)
        sec_memo.body_layout().addWidget(lbl_memo)
        v.addWidget(sec_memo)

        v.addStretch(1)

        # ----------------------------------------------------------- wire --
        self.ed_org.editingFinished.connect(self._persist_org)
        self._slots_timer = QTimer(self)
        self._slots_timer.setSingleShot(True)
        self._slots_timer.setInterval(400)
        self._slots_timer.timeout.connect(self._on_slots_changed)
        for te in self.time_edits:
            te.timeChanged.connect(lambda *_: self._slots_timer.start())
        self._gnews_timer = QTimer(self)
        self._gnews_timer.setSingleShot(True)
        self._gnews_timer.setInterval(800)
        self._gnews_timer.timeout.connect(self._persist_gnews)
        self.txt_paleto.textChanged.connect(lambda: self._gnews_timer.start())
        self.txt_sandy.textChanged.connect(lambda: self._gnews_timer.start())

        self._load_settings()
        self._regen()

    # ------------------------------------------------------------ settings --
    # ----------------------------------------------------------------- время --
    def _now(self) -> datetime:
        """Текущее время в выбранном поясе (или время компьютера)."""
        return now_in_tz(self.store.settings)

    def _load_settings(self) -> None:
        s = self.store.settings
        self.ed_org.setText(s.gov_org or "LSCSD")
        slots = [x for x in (s.gov_last_slots or "").split() if _parse_hhmm(x)]
        if len(slots) != 3:
            slots = suggest_slots(self._now())
        for te, val in zip(self.time_edits, slots[:3]):
            pm = _parse_hhmm(val)
            if pm:
                te.setTime(QTime(pm[0], pm[1]))
        if s.gov_gnews_paleto:
            self.txt_paleto.setPlainText(s.gov_gnews_paleto)
        else:
            self.txt_paleto.setPlainText(GNEWS_PALETO)
        if s.gov_gnews_sandy:
            self.txt_sandy.setPlainText(s.gov_gnews_sandy)
        else:
            self.txt_sandy.setPlainText(GNEWS_SANDY)

    def _persist_org(self) -> None:
        self.store.settings.gov_org = self.ed_org.text().strip() or "LSCSD"
        self.store.save()

    def _persist_slots(self) -> None:
        self.store.settings.gov_last_slots = " ".join(self._current_slots())
        self.store.save()

    def _persist_gnews(self) -> None:
        self.store.settings.gov_gnews_paleto = self.txt_paleto.toPlainText().strip()
        self.store.settings.gov_gnews_sandy = self.txt_sandy.toPlainText().strip()
        self.store.save()

    # --------------------------------------------------------------- slots --
    def _current_slots(self) -> List[str]:
        out = []
        for te in self.time_edits:
            t = te.time()
            out.append(f"{t.hour():02d}:{t.minute():02d}")
        return out

    def _auto_slots(self) -> None:
        slots = suggest_slots(self._now())
        for te, val in zip(self.time_edits, slots):
            pm = _parse_hhmm(val)
            if pm:
                te.setTime(QTime(pm[0], pm[1]))
        self._persist_slots()
        self._regen()
        self.toast.emit(f"Подобрано время: {' '.join(slots)}")

    def _on_slots_changed(self) -> None:
        self._persist_slots()
        self._regen()

    # ------------------------------------------------------------ commands --
    def _command_templates(self) -> List[Tuple[str, str]]:
        return build_commands(self.ed_org.text(), self._current_slots())

    def _regen(self) -> None:
        slots = self._current_slots()
        warns = validate_slots(slots, self._now())
        s = self.store.settings
        if getattr(s, "gov_tz_auto", True):
            self.lbl_tz.setText(
                f"Используется время компьютера: {datetime.now():%H:%M} — "
                "пояс сервера можно сменить в Настройках"
            )
        else:
            try:
                off = float(s.gov_utc_offset or 0.0)
            except Exception:
                off = 0.0
            self.lbl_tz.setText(
                f"Выбран пояс UTC{off:+g}: сейчас {self._now():%H:%M} по нему — "
                "слоты подбираются по этому времени"
            )
        if warns:
            self.lbl_validation.setStyleSheet(f"color: {DANGER};")
            self.lbl_validation.setText("⚠ " + "  •  ".join(warns))
        else:
            self.lbl_validation.setStyleSheet(f"color: {OK};")
            self.lbl_validation.setText(
                "✓ Слоты соответствуют памятке (за 10–120 мин, шаг 10 мин, интервал ≥ 20 мин)"
            )
        for name, cmd in self._command_templates():
            fld = self.cmd_fields.get(name)
            if fld is not None:
                fld.setText(cmd)

    # ---------------------------------------------------------------- copy --
    def _copy_text(self, text: str, message: str) -> None:
        if not text:
            self.toast.emit("Нечего копировать")
            return
        QApplication.clipboard().setText(text)
        self.toast.emit(message)

    def _copy_cmd(self, name: str) -> None:
        fld = self.cmd_fields.get(name)
        if fld is None:
            return
        QApplication.clipboard().setText(fld.text())
        self.toast.emit(f"Скопировано: {name}")

    # -------------------------------------------------------------- library --
    def _save_to_library(self) -> None:
        org = self.ed_org.text().strip() or "LSCSD"
        pairs = [
            ("[ГВ] 1. Проверить занятость", self.cmd_fields["1. Узнать занятость"].text()),
            ("[ГВ] 2. Занять волну", self.cmd_fields["2. Занять волну"].text()),
            ("[ГВ] 3. Занял гос.волну", self.cmd_fields["3. Подтвердить занятие"].text()),
            ("[ГВ] 4. Просьба принять (/report)", self.cmd_fields["4. Просьба принять волну"].text()),
            ("[ГВ] 5. Освободить волну", self.cmd_fields["5. Освободить волну"].text()),
            ("[ГВ] Объявление: Палето-Бэй", self.txt_paleto.toPlainText().strip()),
            ("[ГВ] Объявление: Сенди-Шорс", self.txt_sandy.toPlainText().strip()),
        ]
        n_new = n_upd = 0
        for title, text in pairs:
            if not text:
                continue
            existing = self.store.find_by_title(title)
            if existing:
                existing.text = text
                existing.updated_at = time.time()
                n_upd += 1
            else:
                self.store.add(title, text, "Госволна")
                n_new += 1
        self.store.save()
        self.toast.emit(f"Библиотека: добавлено {n_new}, обновлено {n_upd} (категория «Госволна»)")
        self.library_changed.emit()

    # ---------------------------------------------------------------- reset --
    def _reset_gnews(self, which: str) -> None:
        if which == "paleto":
            self.txt_paleto.setPlainText(GNEWS_PALETO)
        else:
            self.txt_sandy.setPlainText(GNEWS_SANDY)
        self._persist_gnews()
        self.toast.emit("Шаблон восстановлен")

    def refresh_settings(self) -> None:
        """Перечитать настройки (после внешних изменений)."""
        self._load_settings()
        self._regen()
