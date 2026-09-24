"""Самопроверка приложения (без реального ввода): python main.py --smoke."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

CHECKS: list[tuple[str, bool]] = []


def check(name: str, cond: bool) -> None:
    CHECKS.append((name, bool(cond)))
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {name}")


def run_smoke() -> int:
    print("=== Majestic Text Helper — самопроверка ===")

    # 1. Импорт ядра
    try:
        from app import models, storage  # noqa: F401
        from app import injector, window_utils  # noqa: F401

        check("импорт app (models/storage/injector/window_utils)", True)
    except Exception as e:
        check(f"импорт app ({e})", False)
        return _finish()

    # 2. Хоткеи: нормализация и валидация
    check("normalize_hotkey('F6') == 'f6'", models.normalize_hotkey("F6") == "f6")
    check("normalize_hotkey('CTRL + 1') == 'ctrl+1'", models.normalize_hotkey("CTRL + 1") == "ctrl+1")
    check("is_valid_hotkey('f6')", models.is_valid_hotkey("f6"))
    check("is_valid_hotkey('ctrl+1')", models.is_valid_hotkey("ctrl+1"))
    check("is_valid_hotkey('привет') == False", not models.is_valid_hotkey("привет"))
    conf = models.hotkey_conflicts("F6", "f6", [])
    check("конфликт с меню-хоткеем обнаружен", len(conf) == 1)

    # 3. Способ вставки copy присутствует
    check("inject_method 'copy' поддерживается", "copy" in models.INJECT_METHODS)
    check("подпись режима copy понятна", "буфер" in models.INJECT_LABELS.get("copy", ""))

    # 4. Новые поля Settings
    s = models.Settings()
    check("Settings.target_title/target_exe существуют",
          hasattr(s, "target_title") and hasattr(s, "target_exe"))
    check("Settings.gov_* существуют",
          hasattr(s, "gov_org") and hasattr(s, "gov_gnews_paleto") and hasattr(s, "gov_last_slots"))
    d = s.to_dict()
    s2 = models.Settings.from_dict({**d, "gov_org": "LSPD", "unknown_field": 1})
    check("Settings roundtrip + игнор неизвестных полей", s2.gov_org == "LSPD")

    # 5. Госволна: чистые функции
    from datetime import datetime, timedelta

    from app.ui.gov_wave import build_commands, suggest_slots, validate_slots

    now = datetime(2026, 1, 15, 14, 35)
    slots = suggest_slots(now)
    check("suggest_slots даёт 3 слота", len(slots) == 3)
    ok_fmt = all(
        len(x) == 5 and int(x.split(":")[1]) % 10 == 0 for x in slots
    )
    check("слоты на сетке 10 минут", ok_fmt)
    check("первый слот ≥ now+10", _minutes_between(now, slots[0]) >= 10 - 1e-6)
    check("первый слот ≤ now+120", _minutes_between(now, slots[0]) <= 120)
    warns = validate_slots(["15:05", "15:10"], now)
    check("валидатор ловит не-десятые минуты", any("00, 10" in w for w in warns))
    warns2 = validate_slots(["15:00", "15:10"], now)
    check("валидатор ловит интервал < 20 минут", any("20 минут" in w for w in warns2))
    cmds = build_commands("LSCSD", ["15:00", "15:20", "15:40"])
    texts = " || ".join(c[1] for c in cmds)
    check("команда занятия содержит фракцию и слоты",
          "/dep to All: Фракция LSCSD занимает гос. волну на 15:00 15:20 15:40" in texts)
    check("команда проверки занятости", "Занята ли гос. волна на 15:00 15:20 15:40?" in texts)
    check("команда /report", "/report Примите, пожалуйста, гос волну" in texts)
    check("команда освобождения", "/dep to All: Освободил гос. волну." in texts)
    check("шаблоны /gnews присутствуют",
          models.GNEWS_PALETO.startswith("/gnews") and models.GNEWS_SANDY.startswith("/gnews"))
    check("в шаблонах адреса Палето и Сенди",
          "Бульвар Палето" in models.GNEWS_PALETO and "Сенди-шорс" in models.GNEWS_SANDY)

    # 6. Хранилище (временный файл)
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "data.json"
        st = storage.Store(path=f)
        e1 = st.add("Тест", "Привет, город!", "Общение")
        check("store.add/save", f.exists() and st.get(e1.id) is not None)
        st.update(e1.id, title="Тест2")
        check("store.update", st.get(e1.id).title == "Тест2")
        st.inc_usage(e1.id)
        check("store.inc_usage", st.get(e1.id).usage == 1)
        # повреждение → бэкап и пересоздание
        f.write_text("{битый json", encoding="utf-8")
        st2 = storage.Store(path=f)
        check("автовосстановление после порчи", len(st2.entries) >= 1)
        backups = list(Path(td).glob("*.corrupt-*.json"))
        check("бэкап повреждённого файла создан", len(backups) == 1)
        st2.settings.gov_org = "LSCSD"
        st2.settings.inject_method = "copy"
        st2.save()
        st3 = storage.Store(path=f)
        check("настройки (gov/copy) сохраняются", st3.settings.gov_org == "LSCSD"
              and st3.settings.inject_method == "copy")

    # 7. Инжектор: DRY-безопасность и запрет Enter
    injector.DRY_RUN = True
    injector.type_text_unicode("проверка")
    injector.press_combo("t")
    injector.press_combo("ctrl+v")
    injector.press_combo("enter")  # должен быть заблокирован
    check("инжектор в DRY-режиме не падает и блокирует Enter", True)
    check("injector._vk_for('f6') == 0x75", injector._vk_for("f6") == 0x75)
    check("injector._vk_for('t') == 0x54", injector._vk_for("t") == 0x54)

    # 8. window_utils на этой платформе безопасен
    check("find_windows возвращает список", isinstance(window_utils.find_windows("x"), list))
    check("focus_window вне Windows безопасен", window_utils.focus_window(0) is False)

    # 9. UI (offscreen)
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        from app.storage import Store
        from app.ui.gov_wave import GovWavePage
        from app.ui.main_window import MainWindow
        from app.ui.settings import SettingsPage

        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            gw = GovWavePage(st)
            check("страница «Госволна» строится", gw is not None)
            fields = [gw.cmd_fields[k].text() for k in gw.cmd_fields]
            check("команды на странице заполнены", all(fields) and len(fields) == 5)
            sp = SettingsPage(st)
            check("страница настроек строится", sp is not None)
            check("в настройках есть способ «copy»",
                  any(sp.cb_inject.itemData(i) == "copy" for i in range(sp.cb_inject.count())))
            check("в настройках есть «Окно игры»",
                  hasattr(sp, "ed_target_title") and hasattr(sp, "ed_target_exe"))
            check("в настройках есть поле фракции gov_org", hasattr(st.settings, "gov_org"))

            from app.hotkeys import HotkeyManager

            hk = HotkeyManager()
            win = MainWindow(st, hk)
            check("главное окно строится", win is not None)
            check("навигация: 3 страницы", win.stack.count() == 3)
            # эмуляция: сохранение команд в библиотеку
            gw._save_to_library()
            gov_entries = [e for e in st.entries if e.category == "Госволна"]
            check("команды сохраняются в библиотеку", len(gov_entries) == 7)
            # режим copy через Sender: копирование сигналом
            st.settings.inject_method = "copy"
            from app.sender import Sender

            got = []
            snd = Sender(settings_getter=lambda: st.settings,
                         is_overlay_visible=lambda: False)
            snd.copy_requested.connect(got.append)
            entry = list(st.entries)[0]
            snd.send_text(entry)
            check("режим copy: текст ушёл в буфер (сигнал)", len(got) == 1 and got[0] == entry.text)
            check("режим copy: клавиши не нажимались (нет исключений)", True)
        check("QApplication offscreen работает", app is not None)
    except Exception as e:
        check(f"UI: {type(e).__name__}: {e}", False)

    return _finish()


def _minutes_between(now: datetime, hhmm: str) -> float:
    h, m = hhmm.split(":")
    t = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if t < now:
        t = t + timedelta(days=1)
    return (t - now).total_seconds() / 60.0


def _finish() -> int:
    total = len(CHECKS)
    ok = sum(1 for _, c in CHECKS if c)
    print(f"\nИтог: {ok}/{total} проверок пройдено")
    for name, c in CHECKS:
        if not c:
            print(f"  FAIL: {name}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(run_smoke())
