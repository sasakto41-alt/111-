"""Хранилище: атомарная запись data.json, автобэкап при повреждении, CRUD фраз."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Optional

from .models import CATEGORIES, Settings, TextEntry


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.file = Path(path) if path else self._default_file()
        self.entries: List[TextEntry] = []
        self.settings: Settings = Settings()
        self.load()

    # ---------------------------------------------------------------- paths --
    @staticmethod
    def _default_file():
        from .config import get_data_file

        return get_data_file()

    # ---------------------------------------------------------- load / save --
    def load(self) -> None:
        self.entries, self.settings = [], Settings()
        f = self.file
        if not f.exists():
            self._seed_defaults()
            self.save()
            return
        try:
            raw = f.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
            self.entries = [TextEntry.from_dict(e) for e in data.get("entries", [])]
            self.settings = Settings.from_dict(data.get("settings", {}))
        except Exception:
            self._backup_corrupted()
            self._seed_defaults()
            self.save()

    def save(self) -> None:
        data = {
            "version": 2,
            "entries": [e.to_dict() for e in self.entries],
            "settings": self.settings.to_dict(),
        }
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.file)
        except Exception:
            pass

    def _backup_corrupted(self) -> None:
        try:
            if self.file.exists():
                stamp = time.strftime("%Y%m%d-%H%M%S")
                self.file.replace(self.file.with_name(f"{self.file.stem}.corrupt-{stamp}.json"))
        except Exception:
            pass

    def _seed_defaults(self) -> None:
        self.settings = Settings()
        self.entries = [
            TextEntry(title="Приветствие", text="Доброго времени суток!", category="Общение", order=0),
            TextEntry(
                title="Прощание",
                text="Всего доброго, удачного дня!",
                category="Общение",
                order=1,
            ),
        ]

    # ----------------------------------------------------------------- CRUD --
    def add(self, title: str, text: str, category: str = "Разное", hotkey: str = "",
            favorite: bool = False) -> TextEntry:
        e = TextEntry(
            title=title, text=text,
            category=category if category in CATEGORIES else "Разное",
            hotkey=hotkey, favorite=favorite, order=len(self.entries),
        )
        self.entries.append(e)
        self.save()
        return e

    def get(self, entry_id: str) -> Optional[TextEntry]:
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None

    def update(self, entry_id: str, **kw) -> Optional[TextEntry]:
        e = self.get(entry_id)
        if not e:
            return None
        for k, v in kw.items():
            if hasattr(e, k):
                setattr(e, k, v)
        e.updated_at = time.time()
        self.save()
        return e

    def delete(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) != before:
            self.save()
            return True
        return False

    def reorder(self, ordered_ids: List[str]) -> None:
        pos = {eid: i for i, eid in enumerate(ordered_ids)}
        self.entries.sort(key=lambda e: pos.get(e.id, e.order))
        for i, e in enumerate(self.entries):
            e.order = i
        self.save()

    def toggle_favorite(self, entry_id: str) -> Optional[TextEntry]:
        e = self.get(entry_id)
        if e:
            e.favorite = not e.favorite
            self.save()
        return e

    def inc_usage(self, entry_id: str) -> None:
        e = self.get(entry_id)
        if e:
            e.usage += 1
            self.save()

    def search(self, query: str) -> List[TextEntry]:
        q = (query or "").strip().lower()
        if not q:
            return list(self.entries)
        return [e for e in self.entries if q in e.title.lower() or q in e.text.lower()]

    def find_by_title(self, title: str) -> Optional[TextEntry]:
        for e in self.entries:
            if e.title == title:
                return e
        return None

    # ------------------------------------------------------------ settings --
    def update_settings(self, **kw) -> None:
        for k, v in kw.items():
            if hasattr(self.settings, k):
                setattr(self.settings, k, v)
        self.settings.normalize()
        self.save()
