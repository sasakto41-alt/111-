"""Экспорт и импорт всех данных программы в один JSON-файл (v3.8.0).

Перенос на другой ПК одним файлом: ВСЕ фразы библиотеки и ВСЕ настройки
(хоткеи, способ вставки, окно игры, госволна, макрос, уведомления,
таймер, звуки, вид оверлеев). Экспорт — полный снимок; импорт — замена
текущих данных данными из файла с очисткой и нормализацией моделей
(битые фразы пропускаются, настройки проходят Settings.normalize()).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from . import APP_VERSION
from .journal import log
from .models import CATEGORIES, Settings, TextEntry

FORMAT = 1


def export_payload(store) -> dict:
    """Собрать полный снимок данных хранилища."""
    return {
        "app": "Majestic Text Helper",
        "app_version": APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "format": FORMAT,
        "settings": store.settings.to_dict(),
        "entries": [e.to_dict() for e in store.entries],
    }


def export_to_file(store, path) -> int:
    """Сохранить всё в JSON-файл. Возвращает число фраз в файле."""
    p = Path(path)
    payload = export_payload(store)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(p)
    log(f"экспорт: {len(store.entries)} фраз и настройки → {p}")
    return len(store.entries)


def import_payload(payload: dict) -> Tuple[List[TextEntry], Settings]:
    """Разобрать снимок → (фразы, настройки) с очисткой и валидацией."""
    data = payload if isinstance(payload, dict) else {}
    entries: List[TextEntry] = []
    for d in (data.get("entries") or []):
        try:
            e = TextEntry.from_dict(d if isinstance(d, dict) else {})
            if not isinstance(e.title, str) or not isinstance(e.text, str):
                continue
            if e.category not in CATEGORIES:
                e.category = "Разное"
            entries.append(e)
        except Exception:
            continue                      # битую фразу пропускаем
    s = Settings.from_dict(data.get("settings") or {})
    return entries, s


def import_from_file(store, path) -> Tuple[int, int]:
    """Заменить данные хранилища данными из файла.

    Возвращает (загружено_фраз, было_фраз). Битый JSON или файл без единой
    корректной фразы вызывает исключение — библиотека НЕ стирается молча.
    """
    p = Path(path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    entries, s = import_payload(payload)
    before = len(store.entries)
    if not entries and before:
        raise ValueError("в файле нет ни одной корректной фразы — импорт отменён")
    store.entries = entries
    store.settings = s
    store.save()
    log(f"импорт: {len(entries)} фраз (было {before}), настройки заменены")
    return len(entries), before
