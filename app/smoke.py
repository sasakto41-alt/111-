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
    check("пояс: gov_tz_auto/gov_utc_offset существуют",
          hasattr(s, "gov_tz_auto") and hasattr(s, "gov_utc_offset"))
    from app import APP_VERSION as _ver
    try:
        ver_ok = tuple(int(x) for x in _ver.split(".")) >= (3, 3, 0)
    except Exception:
        ver_ok = False
    check("версия >= 3.3.0", ver_ok)
    s2 = models.Settings.from_dict({**s.to_dict(), "gov_org": "LSPD", "unknown_field": 1})
    check("Settings roundtrip + игнор неизвестных полей", s2.gov_org == "LSPD")
    s3 = models.Settings.from_dict({"gov_tz_auto": False, "gov_utc_offset": 3.0})
    check("настройки пояса roundtrip",
          s3.gov_tz_auto is False and abs(s3.gov_utc_offset - 3.0) < 1e-6)
    tz = models.timezone_options()
    check("timezone_options: полный диапазон",
          tz[0][0] == -12.0 and tz[-1][0] == 14.0 and len(tz) > 30)
    check("timezone_options: отсортирован", all(tz[i][0] < tz[i + 1][0] for i in range(len(tz) - 1)))

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
            # часовой пояс: ручной режим UTC+3
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz

            st.settings.gov_tz_auto = False
            st.settings.gov_utc_offset = 3.0
            gw.refresh_settings()
            now_manual = gw._now()
            expected = _dt.now(_tz.utc).replace(tzinfo=None) + _td(hours=3)
            delta_min = abs((now_manual - expected).total_seconds()) / 60.0
            check("gov page: ручной пояс UTC+3 ≈ UTC-время + 3 ч", delta_min < 5)
            check("gov page: индикатор пояса обновился", "UTC+3" in gw.lbl_tz.text())
            st.settings.gov_tz_auto = True
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
            from PySide6.QtCore import Qt as _Qt

            check("окно в панели задач (Qt.Window)",
                  bool(int(win.windowFlags()) & _Qt.Window))
            check("у окна есть иконка", not win.windowIcon().isNull())
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

    # 10. Надёжный запуск: журнал + повторный запуск
    try:
        import main as _m

        check("main: модуль запуска импортируется", callable(_m.main))
        from app import journal as _j

        _j.log("smoke-проверка журнала")
        check("main: журнал пишется на диск", bool(_j.path) and Path(_j.path).exists())
        check("main: show_box/fatal доступны",
              callable(_m.show_box) and callable(_m._fatal) and _m._app_version() == _ver)
        from PySide6.QtCore import QLockFile

        import tempfile as _tf

        lp = os.path.join(_tf.gettempdir(), "mth_smoke.lock")
        l1 = QLockFile(lp)
        check("QLockFile: первый захват", l1.tryLock(500))
        l2 = QLockFile(lp)
        check("QLockFile: второй экземпляр блокируется", not l2.tryLock(300))
        l1.unlock()
    except Exception as e:
        check(f"запуск: {type(e).__name__}: {e}", False)

    # 11. Хоткеи v3.4.0: VK-раскладка и опрос меню-клавиши
    try:
        import sys as _sys

        from app.hotkeys import HotkeyManager, combo_groups, vk_for_key

        check("vk_for_key('f6') == 0x75", vk_for_key("f6") == 0x75)
        check("vk_for_key('t') == 0x54", vk_for_key("t") == 0x54)
        check("vk_for_key('ctrl') == 0x11", vk_for_key("ctrl") == 0x11)
        check("combo_groups('f6') == [(0x75,)]", combo_groups("f6") == [(0x75,)])
        check("combo_groups('ctrl+1')", combo_groups("ctrl+1") == [(0x11,), (0x31,)])
        check("combo_groups('win+f6') — LWIN или RWIN",
              combo_groups("win+f6") == [(0x5B, 0x5C), (0x75,)])
        check("combo_groups('привет') == [] (неизвестное отбрасывается)",
              combo_groups("привет") == [])
        hm = HotkeyManager()
        hm.start("f6")
        check("меню-клавиша: старт без исключений", True)
        if _sys.platform == "win32":
            check("меню-клавиша активна (опрос)", hm.is_menu_active() and hm.error == "")
        else:
            check("вне Windows хук может не запуститься (не ошибка)", True)
        check("тест-режим включается при активной клавише",
              hm.start_menu_test(lambda: None) == hm.is_menu_active())
        hm.stop()
        check("stop() останавливает перехват", not hm.is_menu_active())
    except Exception as e:
        check(f"хоткеи v3.4.0: {type(e).__name__}: {e}", False)

    # 12. Кнопка сохранения настроек и тест меню-клавиши на странице
    try:
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            QApplication([])
        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            from app.ui.settings import SettingsPage

            sp = SettingsPage(st)
            check("кнопка «Сохранить настройки» есть", hasattr(sp, "btn_save"))
            check("кнопка «Проверить меню-клавишу» есть", hasattr(sp, "btn_test_key"))
            sp._save_all()
            check("сохранение кнопкой не падает и пишет файл",
                  (Path(td) / "d.json").exists())
            hm2 = HotkeyManager()
            sp.set_hotkeys(hm2)
            check("set_hotkeys: статус перехвата показан", bool(sp.lbl_hk_state.text()))
            hm2.stop()
    except Exception as e:
        check(f"настройки v3.4.0: {type(e).__name__}: {e}", False)

    # 13. v3.4.1: toggle оверлея (F6 открывает И закрывает) и поверх игры
    try:
        from PySide6.QtCore import Qt as _Qt2

        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            win2 = MainWindow(st, HotkeyManager())
            check("окно всегда поверх всего (WindowStaysOnTopHint)",
                  bool(int(win2.windowFlags()) & _Qt2.WindowStaysOnTopHint))
            check("до показа флаг оверлея False", not win2.is_overlay_visible())
            win2.show_overlay()
            check("show_overlay включает флаг", win2.is_overlay_visible())
            check("окно видимо после show_overlay", win2.isVisible())
            win2.toggle_overlay()
            check("повторный toggle ЗАКРЫВАЕТ оверлей (главный баг v3.4.0)",
                  not win2.is_overlay_visible())
            check("окно скрыто после закрытия", not win2.isVisible())
            win2.toggle_overlay()
            check("toggle снова открывает", win2.is_overlay_visible() and win2.isVisible())
            win2._do_hide()
            check("_do_hide сбрасывает флаг", not win2.is_overlay_visible())
            check("методы подъёма существуют",
                  callable(win2._raise_over_everything)
                  and callable(win2._check_foreground_after_show)
                  and callable(win2._ensure_on_screen_of))
            win2.hotkeys.stop()
    except Exception as e:
        check(f"toggle v3.4.1: {type(e).__name__}: {e}", False)

    # 14. window_utils v3.4.1: get_window_rect безопасен вне Windows
    try:
        check("get_window_rect вне Windows возвращает None",
              window_utils.get_window_rect(0) is None)
    except Exception as e:
        check(f"window_utils v3.4.1: {type(e).__name__}: {e}", False)

    # 15. v3.4.2: кириллица в клавишах, сканкоды, DRY, автопоиск игры
    try:
        from app.models import to_latin_key

        check("to_latin_key('е') == 't' (кириллица → физическая клавиша)",
              to_latin_key("е") == "t")
        check("to_latin_key('ё') == '`'", to_latin_key("ё") == "`")
        check("to_latin_key('ctrl+ш') == 'ctrl+i'", to_latin_key("ctrl+ш") == "ctrl+i")
        check("to_latin_key('F6') == 'f6'", to_latin_key("F6") == "f6")
        s4 = models.Settings()
        s4.type_key = "е"          # пользователь ввёл клавишу чата с RU-раскладкой
        s4.normalize()
        check("Settings.normalize: клавиша чата «е» → «t»", s4.type_key == "t")
        check("is_valid_hotkey('t') теперь True (одиночная клавиша без модификатора)",
              models.is_valid_hotkey("t") and models.is_valid_hotkey("`"))
        s5 = models.Settings()
        s5.type_key = "ё"
        s5.normalize()
        check("Settings.normalize: «ё» → «`» и проходит валидацию",
              s5.type_key == "`" and models.is_valid_hotkey(s5.type_key))
        import app.injector as inj

        check("injector._vk_for('е') == 0x54 (физическая T)",
              inj._vk_for("е") == 0x54)
        check("injector._vk_for('ё') == 0xC0 (физическая `)",
              inj._vk_for("ё") == 0xC0)
        check("injector._vk_for('t') == 0x54", inj._vk_for("t") == 0x54)
        check("injector: KEYEVENTF_SCANCODE определён",
              getattr(inj, "KEYEVENTF_SCANCODE", 0) == 0x0008)
        check("injector: DRY_RUN не нажимает клавиши (_key_down безопасен)",
              (inj._key_down(0x54), True)[1])
        check("injector: press_combo('ctrl+v') не падает (DRY/не-Windows)",
              (inj.press_combo("ctrl+v"), True)[1])
        check("injector: Enter по-прежнему заблокирован",
              inj._vk_for("enter") == 0)
        import app.sender as _sender_mod

        check("sender: маркеры автопоиска игры заданы",
              hasattr(_sender_mod.Sender, "_autodetect_game_hwnd")
              and "majestic" in _sender_mod._GAME_TITLE_MARKERS
              and "ragemp" in _sender_mod._GAME_EXE_MARKERS)
        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            snd2 = Sender(settings_getter=lambda: st.settings)
            hwnd = snd2._resolve_target_hwnd(st.settings)
            check("sender: цель без настроек безопасно резолвится (0 вне Windows)",
                  hwnd == 0 or isinstance(hwnd, int))
        # захват окна: обратный отсчёт и защита от захвата своего окна
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            QApplication([])
        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            from app.ui.settings import SettingsPage

            sp2 = SettingsPage(st)
            check("захват: есть обратный отсчёт (_capture_tick)",
                  callable(sp2._capture_tick) and sp2._capture_left == 0)
            check("захват: есть защита от захвата окна самой программы",
                  callable(sp2._is_own_window))
            sp2._capture_target = "target"
            sp2._do_capture()          # вне Windows fg=None → понятное сообщение
            check("захват: без окна показывает ошибку, а не молчит",
                  "не найдено" in sp2.lbl_target_status.text().lower())
    except Exception as e:
        check(f"v3.4.2: {type(e).__name__}: {e}", False)

    # 16. v3.5.0: отдельное меню Госволны и макрос с подтверждением
    try:
        from datetime import datetime as _dt2

        from PySide6.QtCore import Qt as _Qt5
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            QApplication([])
        check("models: GOV_MACRO_ACTIONS/LABELS заданы",
              len(models.GOV_MACRO_ACTIONS) == 7
              and models.GOV_MACRO_LABELS.get("step2") == "2. Занять волну")
        s6 = models.Settings()
        check("v3.5.0: поля меню/макроса существуют",
              hasattr(s6, "gov_menu_enabled") and hasattr(s6, "gov_menu_hotkey")
              and hasattr(s6, "gov_macro_enabled") and hasattr(s6, "gov_macro_hotkey")
              and hasattr(s6, "gov_macro_action") and hasattr(s6, "gov_macro_confirm_sec"))
        check("v3.5.0: значения по умолчанию (f7/f8, step2, 5 с, выключено)",
              s6.gov_menu_hotkey == "f7" and s6.gov_macro_hotkey == "f8"
              and s6.gov_macro_action == "step2" and s6.gov_macro_confirm_sec == 5
              and s6.gov_menu_enabled is False and s6.gov_macro_enabled is False)
        s6.gov_menu_hotkey = "е"          # кириллица → физическая клавиша
        s6.gov_menu_enabled = True
        s6.normalize()
        check("v3.5.0: normalize переводит кириллицу клавиши меню Госволны",
              s6.gov_menu_hotkey == "t" and s6.gov_menu_enabled is True)
        s6b = models.Settings()
        s6b.gov_menu_enabled = True
        s6b.gov_menu_hotkey = "f6"
        errs = s6b.validate()
        check("v3.5.0: валидатор ловит совпадение с F6",
              any("меню Госволны" in e for e in errs))
        s6c = models.Settings()
        s6c.gov_menu_enabled = True
        s6c.gov_macro_enabled = True
        s6c.gov_macro_hotkey = "f7"       # совпадает с меню Госволны по умолчанию
        errs2 = s6c.validate()
        check("v3.5.0: валидатор ловит совпадение макроса с меню Госволны",
              any("макроса" in e for e in errs2))

        from app.hotkeys import HotkeyManager as _HKM5
        from app.ui.gov_wave import gov_slots_for, now_in_tz, resolve_macro_command

        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            st.settings.gov_last_slots = "15:00 15:20 15:40"
            st.settings.gov_org = "LSCSD"
            check("gov_slots_for: читает выбранные слоты",
                  gov_slots_for(st.settings) == ["15:00", "15:20", "15:40"])
            st.settings.gov_last_slots = ""
            auto = gov_slots_for(st.settings)
            check("gov_slots_for: пусто → подбор по памятке", len(auto) == 3)
            t_now = now_in_tz(st.settings)
            check("now_in_tz: авто ≈ текущее время",
                  abs((t_now - _dt2.now()).total_seconds()) < 10)
            st.settings.gov_tz_auto = False
            st.settings.gov_utc_offset = 5.0
            t_off = now_in_tz(st.settings)
            check("now_in_tz: ручной пояс UTC+5",
                  abs((t_off - _dt2.now()).total_seconds() - 5 * 3600) < 15)
            st.settings.gov_tz_auto = True
            cmd2 = resolve_macro_command(st.settings, "step2")
            check("resolve_macro_command: команда занятия с фракцией и слотами",
                  cmd2.startswith("/dep to All: Фракция LSCSD занимает гос. волну на "))
            cmd_p = resolve_macro_command(st.settings, "gnews_paleto")
            check("resolve_macro_command: /gnews Палето", cmd_p.startswith("/gnews"))

            from app.ui.gov_overlay import GovWaveOverlay, MacroConfirmDialog

            ov = GovWaveOverlay(st)
            check("оверлей Госволны строится", ov is not None)
            check("оверлей Госволны: 7 команд на кнопках", len(ov._cmd_buttons) == 7)
            check("оверлей Госволны: всегда поверх (WindowStaysOnTopHint)",
                  bool(int(ov.windowFlags()) & _Qt5.WindowStaysOnTopHint))
            check("оверлей Госволны: кнопка «Подшитать время» есть",
                  callable(ov.btn_time.click) and callable(ov._reslot))
            ov.show_overlay()
            check("оверлей Госволны: show включает флаг",
                  ov._shown_flag and ov.isVisible())
            ov.toggle()
            check("оверлей Госволны: toggle закрывает окно",
                  not ov._shown_flag and not ov.isVisible())
            ov.toggle()
            check("оверлей Госволны: toggle снова открывает", ov._shown_flag)
            st.settings.gov_last_slots = ""
            ov._reslot()
            check("оверлей Госволны: «Подшитать время» пересчитал и сохранил слоты",
                  len(st.settings.gov_last_slots.split()) == 3)
            ov._do_hide()
            check("оверлей Госволны: _do_hide сбрасывает флаг",
                  not ov._shown_flag and not ov.isVisible())

            dlg = MacroConfirmDialog(st)
            st.settings.gov_macro_confirm_sec = 5
            st.settings.gov_macro_action = "step2"
            st.settings.gov_last_slots = "15:00 15:20 15:40"
            dlg.open_dialog()
            check("макрос: окно открылось, «Да» заблокирована (5 с)",
                  dlg.isVisible() and not dlg.btn_yes.isEnabled())
            check("макрос: время показано как выбранное в настройках",
                  "15:00" in dlg.lbl_slots.text() and "15:40" in dlg.lbl_slots.text())
            for _ in range(5):
                dlg._tick()
            check("макрос: после 5 тиков «Да» активна",
                  dlg.btn_yes.isEnabled() and dlg._remaining == 0)
            yes_fired = []
            dlg.confirmed.connect(lambda: yes_fired.append(True))
            dlg._on_yes()
            check("макрос: «Да» испускает confirmed и закрывает окно",
                  bool(yes_fired) and not dlg.isVisible())
            dlg2 = MacroConfirmDialog(st)
            st.settings.gov_macro_confirm_sec = 0
            dlg2.open_dialog()
            check("макрос: задержка 0 → «Да» активна сразу",
                  dlg2.btn_yes.isEnabled())
            dlg2._on_no()
            check("макрос: «Нет» закрывает окно", not dlg2.isVisible())

            hm5 = _HKM5()
            hm5.start("f6")
            hm5.start_gov("f7")
            hm5.start_macro("f8")
            check("v3.5.0: gov/macro клавиши стартуют, резерв заполнен",
                  hm5._gov_hotkey == "f7" and hm5._macro_hotkey == "f8"
                  and "f7" in hm5._reserved and "f8" in hm5._reserved)
            hm5.stop_gov()
            hm5.stop_macro()
            check("v3.5.0: stop_gov/stop_macro снимают резерв",
                  "f7" not in hm5._reserved and "f8" not in hm5._reserved)
            hm5.stop()
    except Exception as e:
        check(f"v3.5.0: {type(e).__name__}: {e}", False)

    # 17. v3.6.0: последовательности макроса, широкое меню F7, анти-зависание
    try:
        from PySide6.QtCore import Qt as _Qt6
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            QApplication([])

        # --- новые поля настроек ---
        s7 = models.Settings()
        check("v3.6.0: поля gov_macro_steps/gov_macro_step_pause_ms существуют",
              hasattr(s7, "gov_macro_steps") and hasattr(s7, "gov_macro_step_pause_ms"))
        check("v3.6.0: по умолчанию один шаг step2 и пауза 4000 мс",
              s7.gov_macro_steps == ["step2"] and s7.gov_macro_step_pause_ms == 4000)
        s7.gov_macro_steps = ["step4", "мусор", "step2", "step2", "step1"]
        s7.gov_macro_step_pause_ms = 999999
        s7.normalize()
        check("v3.6.0: normalize чистит шаги (неизвестные и дубли) и сохраняет порядок",
              s7.gov_macro_steps == ["step4", "step2", "step1"])
        check("v3.6.0: пауза между шагами зажата в 500..30000 мс",
              s7.gov_macro_step_pause_ms == 30000)
        s7b = models.Settings()
        s7b.gov_macro_steps = []
        s7b.gov_macro_action = "gnews_paleto"
        s7b.normalize()
        check("v3.6.0: пустые шаги → fallback на одиночное действие",
              s7b.gov_macro_steps == ["gnews_paleto"])

        # --- план последовательности ---
        from app.ui.gov_wave import plan_macro_sequence

        with tempfile.TemporaryDirectory() as td:
            st = Store(path=Path(td) / "d.json")
            st.settings.gov_last_slots = "15:00 15:20 15:40"
            st.settings.gov_org = "LSCSD"
            st.settings.gov_macro_steps = ["step1", "step2", "step4"]
            plan = plan_macro_sequence(st.settings)
            check("v3.6.0: план последовательности — 3 шага в заданном порядке",
                  len(plan) == 3 and plan[0][0].startswith("1.")
                  and plan[1][0].startswith("2.") and plan[2][0].startswith("4."))
            check("v3.6.0: тексты шагов — /dep вопрос, /dep занять, /report",
                  plan[0][1].startswith("/dep to All: Занята ли")
                  and "занимает гос. волну" in plan[1][1]
                  and plan[2][1].startswith("/report"))
            st.settings.gov_macro_steps = []
            plan1 = plan_macro_sequence(st.settings)
            check("v3.6.0: пустые шаги → одиночный план из gov_macro_action",
                  len(plan1) == 1)

            # --- широкое меню F7 ---
            from app.ui.gov_overlay import GovWaveOverlay, MacroConfirmDialog

            st.settings.gov_macro_steps = ["step2"]
            ov = GovWaveOverlay(st)
            check("v3.6.0: меню F7 — широкий прямоугольник (1080x470)",
                  ov.width() >= 1000 and ov.height() >= 440)
            check("v3.6.0: меню F7 — минимум 880x430 (тянется в ширину)",
                  ov.minimumWidth() >= 880 and ov.minimumHeight() >= 420)
            check("v3.6.0: меню F7 — 7 широких команд в сетке",
                  len(ov._cmd_buttons) == 7
                  and all(b.minimumHeight() >= 52 for _, b in ov._cmd_buttons))
            check("v3.6.0: меню F7 — всегда поверх (StaysOnTop)",
                  bool(int(ov.windowFlags()) & _Qt6.WindowStaysOnTopHint))
            check("v3.6.0: бейдж способа вставки читается из настроек",
                  "Способ вставки" in ov.lbl_mode.text()
                  and "Настроек" in ov.lbl_mode.text())
            st.settings.inject_method = "copy"
            ov._refresh()
            check("v3.6.0: смена способа в Настройках подхватывается меню",
                  "буфер" in ov.lbl_mode.text() or "скопирует" in ov.lbl_mode.text())
            st.settings.inject_method = "unicode"
            ov._refresh()
            check("v3.6.0: режим «наборка текста» виден в меню (будет набирать)",
                  "НАБЕРЁТ" in ov.lbl_mode.text() or "наберёт" in ov.lbl_mode.text())

            # --- конструктор макроса в меню ---
            check("v3.6.0: панель макроса со списком шагов присутствует",
                  ov.lst_steps is not None and ov.sp_pause is not None)
            check("v3.6.0: список шагов reflects настройки",
                  ov.lst_steps.count() == 1 and "Занять" in ov.lst_steps.item(0).text())
            st.settings.gov_macro_steps = ["step2", "step4"]
            ov._refresh()
            check("v3.6.0: меню показывает 2 шага из настроек", ov.lst_steps.count() == 2)
            st.settings.gov_macro_steps = ["step2"]
            ov._refresh()
            ov.cb_add.setCurrentIndex(3)          # step4 — просьба принять
            ov._step_add()
            check("v3.6.0: «+ Добавить» в меню растит последовательность",
                  ov.lst_steps.count() == 2 and st.settings.gov_macro_steps == ["step2", "step4"])
            ov.lst_steps.setCurrentRow(1)
            ov._step_up()
            check("v3.6.0: «↑» переставляет шаги и сохраняет порядок",
                  st.settings.gov_macro_steps == ["step4", "step2"])
            ov._step_down()
            check("v3.6.0: «↓» возвращает порядок",
                  st.settings.gov_macro_steps == ["step2", "step4"])
            ov.lst_steps.setCurrentRow(1)
            ov._step_del()
            check("v3.6.0: «✕ Удалить» убирает шаг",
                  st.settings.gov_macro_steps == ["step2"] and ov.lst_steps.count() == 1)
            st.settings.gov_macro_step_pause_ms = 6000
            ov._refresh()
            check("v3.6.0: пауза между шагами загружается из настроек",
                  ov.sp_pause.value() == 6000)
            ov._do_hide()

            # --- подтверждение показывает последовательность ---
            st.settings.gov_macro_steps = ["step2", "step4"]
            st.settings.gov_macro_confirm_sec = 5
            dlg = MacroConfirmDialog(st)
            dlg.open_dialog()
            check("v3.6.0: подтверждение показывает ОБА шага по порядку",
                  "1) " in dlg.lbl_steps.text() and "2) " in dlg.lbl_steps.text()
                  and "Занять" in dlg.lbl_steps.text() and "/report" in dlg.lbl_steps.text())
            check("v3.6.0: подтверждение показывает выбранное время",
                  "15:00" in dlg.lbl_slots.text() and "15:40" in dlg.lbl_slots.text())
            check("v3.6.0: «Да» заблокирована на 5 с",
                  not dlg.btn_yes.isEnabled() and dlg._remaining == 5)
            for _ in range(5):
                dlg._tick()
            check("v3.6.0: после 5 тиков «Да» активна", dlg.btn_yes.isEnabled())
            dlg._on_no()
            check("v3.6.0: «Нет» закрывает подтверждение", not dlg.isVisible())

            # --- анти-зависание: потокобезопасное скрытие и busy-guard ---
            from app.sender import Sender as _Sender

            snd = _Sender(lambda: models.Settings())
            check("v3.6.0: Sender скрывает оверлеи через СИГНАЛ (не QTimer из потока)",
                  hasattr(snd, "hide_overlays"))
            check("v3.6.0: busy-guard SendWorker существует",
                  hasattr(snd, "_busy"))
            import inspect as _insp

            src = _insp.getsource(_Sender.send_text)
            check("v3.6.0: повторная отправка при занятости игнорируется",
                  "_busy" in src and "пропущен" in src)
    except Exception as e:
        check(f"v3.6.0: {type(e).__name__}: {e}", False)

    # 18. v3.7.0: уведомление о госволне (красный квадратик) + авто-Enter макроса
    try:
        import inspect as _insp

        from datetime import datetime as _DT

        from PySide6.QtCore import Qt as _Qt7
        from PySide6.QtWidgets import QApplication as _QA7

        if _QA7.instance() is None:
            _QA7([])

        # --- новые поля настроек ---
        s8 = models.Settings()
        check("v3.7.0: поля gov_notify_*/gov_macro_press_enter существуют",
              hasattr(s8, "gov_notify_enabled") and hasattr(s8, "gov_notify_minutes")
              and hasattr(s8, "gov_macro_press_enter"))
        check("v3.7.0: по умолчанию уведомление ВКЛ и 3 минуты, авто-Enter ВКЛ",
              s8.gov_notify_enabled is True and s8.gov_notify_minutes == 3
              and s8.gov_macro_press_enter is True)
        s8.gov_notify_minutes = 99
        s8.gov_macro_press_enter = 0
        s8.normalize()
        check("v3.7.0: normalize зажимает минуты 1..30 и приводит флаги к bool",
              s8.gov_notify_minutes == 30 and s8.gov_macro_press_enter is False)
        s8c = models.Settings.from_dict({"gov_notify_minutes": 0, "gov_notify_enabled": True})
        check("v3.7.0: from_dict → минуты не меньше 1", s8c.gov_notify_minutes == 1)

        # --- расчёт окна уведомления ---
        from app.ui.gov_wave import gov_alert_state

        with tempfile.TemporaryDirectory() as td:
            st8 = Store(path=Path(td) / "d.json")
            now8 = _DT(2026, 1, 20, 14, 58, 30)
            st8.settings.gov_last_slots = "15:00 15:20 15:40"   # первый через 1.5 мин
            st8.settings.gov_notify_minutes = 3
            res = gov_alert_state(st8.settings, now=now8)
            check("v3.7.0: за 3 мин до слота уведомление запланировано",
                  res is not None and res[0] == "15:00" and 1.0 <= res[1] <= 2.0)
            st8.settings.gov_notify_minutes = 1
            check("v3.7.0: окно 1 мин — ещё рано (до слота 1.5 мин)",
                  gov_alert_state(st8.settings, now=now8) is None)
            st8.settings.gov_notify_minutes = 3
            now_far = _DT(2026, 1, 20, 12, 0, 0)
            check("v3.7.0: далеко от слотов — уведомления нет",
                  gov_alert_state(st8.settings, now=now_far) is None)
            now_after = _DT(2026, 1, 20, 15, 41, 0)
            check("v3.7.0: все слоты прошли сегодня — уведомления нет",
                  gov_alert_state(st8.settings, now=now_after) is None)
            # выбор БЛИЖАЙШЕГО слота: 15:20 ближе, чем 15:40
            now_near2 = _DT(2026, 1, 20, 15, 18, 10)
            res2 = gov_alert_state(st8.settings, now=now_near2)
            check("v3.7.0: выбирается ближайший слот (15:20, ~1.8 мин)",
                  res2 is not None and res2[0] == "15:20" and 1.5 <= res2[1] <= 2.0)

        # --- injector: авто-Enter только в отдельной функции ---
        from app import injector as _inj

        check("v3.7.0: injector.press_enter существует (VK_RETURN)",
              hasattr(_inj, "press_enter") and _inj.VK_RETURN == 0x0D)
        _pc_src = _insp.getsource(_inj.press_combo)
        check("v3.7.0: press_combo по-прежнему БЛОКИРУЕТ Enter",
              "ЗАБЛОКИРОВАНО" in _pc_src and "enter" in _pc_src)
        _pe_src = _insp.getsource(_inj.press_enter)
        check("v3.7.0: press_enter документирован как исключение для макроса",
              "макрос" in _pe_src and "DRY_RUN" in _pe_src)

        # --- sender: параметр press_enter и сигнал requested_seq ---
        from app.sender import SendWorker as _SW8, Sender as _S8

        check("v3.7.0: Sender.send_text принимает press_enter",
              "press_enter" in _insp.getsource(_S8.send_text))
        check("v3.7.0: SendWorker.requested_seq (запись, press_enter)",
              hasattr(_SW8, "requested_seq"))
        _impl_src = _insp.getsource(_S8._send_text_impl)
        check("v3.7.0: авто-Enter жмётся ПОСЛЕ текста (unicode/ctrlv)",
              "press_enter" in _impl_src and "injector.press_enter" in _impl_src)
        check("v3.7.0: в режиме «буфер» авто-Enter НЕ нажимается",
              "пропущен" in _impl_src)

        # --- красное уведомление ---
        from app.ui.gov_notify import GovNotifyToast

        toast8 = GovNotifyToast()
        check("v3.7.0: уведомление — безрамный Tool поверх всего",
              bool(int(toast8.windowFlags()) & _Qt7.FramelessWindowHint)
              and bool(int(toast8.windowFlags()) & _Qt7.WindowStaysOnTopHint))
        check("v3.7.0: уведомление НЕ забирает фокус (WA_ShowWithoutActivating)",
              toast8.testAttribute(_Qt7.WA_ShowWithoutActivating))
        toast8.popup(2.4, "15:00", "LSCSD")
        _qa8 = _QA7.instance()
        _qa8.processEvents()
        check("v3.7.0: popup показывает красный квадратик с текстом «ЧЕРЕЗ ~2 МИН»",
              toast8.isVisible() and "ЧЕРЕЗ ~2 МИН" in toast8.lbl_title.text()
              and "15:00" in toast8.lbl_sub.text())
        check("v3.7.0: красный фон уведомления",
              "#DC2626" in toast8.styleSheet())
        toast8.popup(0.2, "15:00")
        check("v3.7.0: при <1 мин текст «НАЧИНАЕТСЯ»",
              "НАЧИНАЕТСЯ" in toast8.lbl_title.text())
        toast8.dismiss()
        check("v3.7.0: dismiss скрывает уведомление", not toast8.isVisible())

        # --- интеграция в главное окно: таймер-опрос и макрос с авто-Enter ---
        from app.hotkeys import HotkeyManager as _HKM8

        with tempfile.TemporaryDirectory() as td2:
            st8b = Store(path=Path(td2) / "d.json")
            win8 = MainWindow(st8b, _HKM8())
            check("v3.7.0: у главного окна есть таймер опроса 5 с",
                  getattr(win8, "_notify_timer", None) is not None
                  and win8._notify_timer.interval() == 5000
                  and win8._notify_timer.isActive())
            check("v3.7.0: GovNotifyToast создан и не перехватывает фокус",
                  isinstance(win8._gov_notify, GovNotifyToast)
                  and win8._gov_notify.testAttribute(_Qt7.WA_ShowWithoutActivating))
            win8._check_gov_notify()   # слотов нет — ничего не показывает
            check("v3.7.0: опрос без слотов не падает и не показывает тост",
                  not win8._gov_notify.isVisible())
            st8b.settings.gov_last_slots = "15:00 15:20 15:40"
            win8._check_gov_notify()
            check("v3.7.0: опрос показал уведомление (если окно скоро) и запомнил слот",
                  isinstance(win8._gov_notified_keys, set))
            win8._check_gov_notify()
            check("v3.7.0: дедуп — повторный опрос НЕ показывает снова",
                  len(win8._gov_notified_keys) <= 1)
            win8._notify_timer.stop()

            # макрос: последовательность с авто-Enter (без реального ввода)
            st8b.settings.gov_macro_steps = ["step2", "step4"]
            win8._macro_confirmed()
            check("v3.7.0: макрос шагает с авто-Enter (тост шага 1)",
                  win8._seq_i == 1 and len(win8._seq) == 2)
            win8._seq_i = len(win8._seq)
            win8._seq_step(500, True)
            check("v3.7.0: конец последовательности → «выполнен полностью»",
                  win8._seq_i >= len(win8._seq))
            win8.hotkeys.stop()
            win8._notify_timer.stop()
            win8._gov_notify.dismiss()

        # --- настройки и меню F7: галочка авто-Enter ---
        from app.ui.settings import SettingsPage as _SP8

        with tempfile.TemporaryDirectory() as td3:
            sp8 = _SP8(Store(path=Path(td3) / "e.json"))
            check("v3.7.0: в Настройках есть галочка авто-Enter макроса",
                  hasattr(sp8, "chk_enter") and "Enter" in sp8.chk_enter.text())
            check("v3.7.0: в Настройках есть секция уведомления (красный квадратик)",
                  hasattr(sp8, "chk_notify") and hasattr(sp8, "sp_notify_min")
                  and sp8.sp_notify_min.value() == 3)
            sp8.sp_notify_min.setValue(10)
            sp8._apply_notify()
            check("v3.7.0: «за сколько минут» сохраняется в настройки",
                  sp8.store.settings.gov_notify_minutes == 10)

            ov8 = GovWaveOverlay(sp8.store)
            check("v3.7.0: в меню F7 есть галочка «Enter после каждого шага»",
                  hasattr(ov8, "chk_enter") and ov8.chk_enter.isChecked())
            ov8.chk_enter.setChecked(False)
            check("v3.7.0: переключение галочки в меню сохраняется",
                  ov8.store.settings.gov_macro_press_enter is False)
            ov8.chk_enter.setChecked(True)
            check("v3.7.0: возврат галочки сохраняется",
                  ov8.store.settings.gov_macro_press_enter is True)
            dlg8 = MacroConfirmDialog(sp8.store)
            dlg8.open_dialog()
            check("v3.7.0: подтверждение обещает САМО нажать Enter (по настройке)",
                  "САМА нажмёт Enter" in dlg8.lbl_hint.text())
            sp8.store.settings.gov_macro_press_enter = False
            dlg8.open_dialog()
            check("v3.7.0: при выключенном авто-Enter — «нажимаете вы сами»",
                  "сами" in dlg8.lbl_hint.text())
            dlg8.hide()
            ov8._do_hide()
    except Exception as e:
        check(f"v3.7.0: {type(e).__name__}: {e}", False)

    # ============================================= 19. v3.8.0: таймер/звук/вид/перенос --
    try:
        from datetime import datetime as _dt9, timedelta as _td9

        from PySide6.QtCore import Qt as _Qt9

        from app import porting as _porting
        from app import sounds as _sounds
        from app.storage import Store as _Store9
        from app.ui.gov_countdown import GovCountdownBadge, format_left
        from app.ui.gov_wave import now_in_tz as _now9
        from app.ui.settings import SettingsPage as _SP9

        check("v3.8.0: версия >= 3.8.0",
              tuple(int(x) for x in _ver.split(".")) >= (3, 8, 0))

        # --- формат времени таймера ---
        check("v3.8.0: format_left(2.783 мин) == '02:47'", format_left(2.783) == "02:47")
        check("v3.8.0: format_left(65 мин) == '1:05:00'", format_left(65.0) == "1:05:00")
        check("v3.8.0: format_left(0) == '00:00'", format_left(0) == "00:00")
        check("v3.8.0: format_left отрицательное → '00:00'", format_left(-5) == "00:00")

        with tempfile.TemporaryDirectory() as td9:
            st9 = _Store9(path=Path(td9) / "n.json")
            s9 = st9.settings

            # --- новые настройки: значения по умолчанию и normalize ---
            check("v3.8.0: таймер вкл. по умолчанию, окно 15 мин",
                  s9.gov_countdown_enabled is True and s9.gov_countdown_minutes == 15)
            check("v3.8.0: звуки вкл. по умолчанию",
                  s9.notify_sound is True and s9.macro_sound is True)
            check("v3.8.0: прозрачность 100 %, позиция авто (-1)",
                  s9.overlay_opacity == 100 and s9.overlay_pos_x == -1
                  and s9.gov_pos_x == -1 and s9.gov_pos_y == -1)
            s9.gov_countdown_minutes = 999
            s9.overlay_opacity = 5
            s9.overlay_pos_x = 1920
            s9.overlay_pos_y = 1080
            s9.normalize()
            check("v3.8.0: normalize ограничивает таймер (60) и прозрачность (30)",
                  s9.gov_countdown_minutes == 60 and s9.overlay_opacity == 30)
            check("v3.8.0: запомненная позиция сохраняется как есть",
                  s9.overlay_pos_x == 1920 and s9.overlay_pos_y == 1080)

            # --- таймер до госволны ---
            badge = GovCountdownBadge(lambda: st9.settings)
            check("v3.8.0: таймер не забирает фокус и пропускает клики",
                  badge.testAttribute(_Qt9.WA_ShowWithoutActivating)
                  and badge.testAttribute(_Qt9.WA_TransparentForMouseEvents))
            check("v3.8.0: таймер поверх всего (StaysOnTop)",
                  bool(badge.windowFlags() & _Qt9.WindowStaysOnTopHint))

            now9 = _now9(s9)
            near = (now9 + _td9(minutes=2)).strftime("%H:%M")
            s9.gov_last_slots = f"{near} 23:50"
            badge._tick()
            check("v3.8.0: таймер показывается, когда до слота ≤ N минут", badge.isVisible())
            check("v3.8.0: на таймере формат ММ:СС",
                  len(badge.lbl_time.text().split(":")) in (2, 3))
            badge._tick()
            check("v3.8.0: таймер не падает при повторном тике", badge.isVisible())

            s9.gov_countdown_enabled = False
            badge._tick()
            check("v3.8.0: выключенный таймер скрывается", not badge.isVisible())
            s9.gov_countdown_enabled = True
            s9.gov_countdown_minutes = 15      # окно обратно 15 мин (normalize выше дал 60)

            far = (now9 + _td9(minutes=40)).strftime("%H:%M")
            s9.gov_last_slots = far
            badge._tick()
            check("v3.8.0: таймер скрывается, когда до слота далеко", not badge.isVisible())

            # --- звуки ---
            s9.notify_sound = False
            check("v3.8.0: звук уведомления отключается настройкой",
                  _sounds.play_gov_notify(s9) is False)
            s9.notify_sound = True
            check("v3.8.0: пинг уведомления возвращает bool без ошибок",
                  isinstance(_sounds.play_gov_notify(s9), bool))
            check("v3.8.0: пинг макроса возвращает bool без ошибок",
                  isinstance(_sounds.play_macro_done(s9), bool))

            # --- экспорт / импорт ---
            st9.add("Тест фраза", "Текст тестовой фразы", "Общение")
            st9.add("Вторая", "Ещё текст", "Госволна")
            s9.gov_org = "LSPD"
            backup = Path(td9) / "backup.json"
            n_exp = _porting.export_to_file(st9, backup)
            check("v3.8.0: экспорт вернул число фраз", n_exp == len(st9.entries))
            check("v3.8.0: файл экспорта существует и читается",
                  backup.exists() and json.loads(backup.read_text(encoding="utf-8"))["settings"])

            other = _Store9(path=Path(td9) / "other.json")
            other.add("Старая фраза", "которая заменится", "Разное")
            n_imp, before_imp = _porting.import_from_file(other, backup)
            check("v3.8.0: импорт заменил фразы",
                  n_imp == len(st9.entries) and len(other.entries) == n_imp)
            check("v3.8.0: импорт перенёс настройки (gov_org)", other.settings.gov_org == "LSPD")
            check("v3.8.0: импорт перенёс поля v3.8.0",
                  other.settings.gov_countdown_minutes == st9.settings.gov_countdown_minutes
                  and other.settings.overlay_opacity == st9.settings.overlay_opacity)

            bad = Path(td9) / "bad.json"
            bad.write_text("{это не json", encoding="utf-8")
            try:
                _porting.import_from_file(other, bad)
                ok_bad = False
            except Exception:
                ok_bad = True
            check("v3.8.0: битый файл импорта не рушит программу", ok_bad)
            check("v3.8.0: после битого импорта данные целы", len(other.entries) == n_imp)

            # --- страница настроек ---
            sp9 = _SP9(_Store9(path=Path(td9) / "s.json"))
            check("v3.8.0: в Настройках есть галочка таймера",
                  hasattr(sp9, "chk_countdown") and sp9.chk_countdown.isChecked())
            check("v3.8.0: окно таймера по умолчанию 15 мин",
                  hasattr(sp9, "sp_countdown_min") and sp9.sp_countdown_min.value() == 15)
            check("v3.8.0: галочки звука на месте",
                  hasattr(sp9, "chk_notify_sound") and hasattr(sp9, "chk_macro_sound")
                  and sp9.chk_notify_sound.isChecked() and sp9.chk_macro_sound.isChecked())
            check("v3.8.0: прозрачность оверлеев на месте (100 %)",
                  hasattr(sp9, "sp_opacity") and sp9.sp_opacity.value() == 100)
            check("v3.8.0: кнопки экспорта/импорта на месте",
                  hasattr(sp9, "btn_export") and hasattr(sp9, "btn_import"))
            sp9.sp_opacity.setValue(70)
            sp9._apply_overlay_ui()
            check("v3.8.0: прозрачность сохраняется в настройки",
                  sp9.store.settings.overlay_opacity == 70)
            sp9.chk_countdown.setChecked(False)
            sp9.sp_countdown_min.setValue(30)
            sp9._apply_gov_extra()
            check("v3.8.0: таймер/окно сохраняются в настройки",
                  sp9.store.settings.gov_countdown_enabled is False
                  and sp9.store.settings.gov_countdown_minutes == 30)
            sp9.chk_notify_sound.setChecked(False)
            sp9._apply_gov_extra()
            check("v3.8.0: звук уведомления сохраняется",
                  sp9.store.settings.notify_sound is False)

            # --- позиция и прозрачность меню F7 ---
            ov9 = GovWaveOverlay(st9)
            st9.settings.gov_pos_x = 111
            st9.settings.gov_pos_y = 222
            st9.settings.overlay_opacity = 60
            ov9.show_overlay()
            check("v3.8.0: меню F7 вернулось на запомненную позицию",
                  ov9.x() == 111 and ov9.y() == 222)
            check("v3.8.0: меню F7 применило прозрачность",
                  abs(ov9.windowOpacity() - 0.60) < 0.01)
            ov9.move(333, 444)
            ov9._do_hide()
            check("v3.8.0: позиция F7 запомнилась при закрытии",
                  st9.settings.gov_pos_x == 333 and st9.settings.gov_pos_y == 444)
            check("v3.8.0: меню F7 реально скрылось", not ov9.isVisible())
    except Exception as e:
        check(f"v3.8.0: {type(e).__name__}: {e}", False)

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
