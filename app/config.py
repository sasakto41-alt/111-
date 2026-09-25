"""Пути и базовые константы приложения (portable-режим).

Порядок поиска папки данных:
1)  data/ рядом с exe (или проектом) — если доступна для записи;
2)  %APPDATA%/MajesticTextHelper — fallback.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Majestic Text Helper"
APP_FOLDER = "MajesticTextHelper"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_base_dir() -> Path:
    """Папка, рядом с которой лежат данные (для exe — папка самого exe)."""
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            return _project_root()
    return _project_root()


def get_assets_dir() -> Path:
    """Папка ресурсов (в onefile-сборке ресурсы распакованы в _MEIPASS)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass and (Path(meipass) / "assets").exists():
            return Path(meipass) / "assets"
        base = get_base_dir()
        if (base / "assets").exists():
            return base / "assets"
    return _project_root() / "assets"


def get_data_dir() -> Path:
    local = get_base_dir() / "data"
    try:
        local.mkdir(parents=True, exist_ok=True)
        probe = local / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return local
    except Exception:
        pass
    appdata = os.getenv("APPDATA") or str(Path.home())
    fallback = Path(appdata) / APP_FOLDER
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_data_file() -> Path:
    return get_data_dir() / "data.json"
