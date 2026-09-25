"""Иконка приложения: assets/icon.ico|icon.png с программным фолбэком."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from .config import get_assets_dir


def _fallback_pixmap() -> QPixmap:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#22D3EE"), 2))
    p.setBrush(QColor("#3B82F6"))
    p.drawRoundedRect(QRectF(4, 4, 56, 56), 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(32)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "M")
    p.end()
    return pm


def app_icon() -> QIcon:
    base = get_assets_dir()
    for name in ("icon.ico", "icon.png"):
        path = base / name
        if path.exists():
            try:
                ic = QIcon(str(path))
                if not ic.isNull():
                    return ic
            except Exception:
                pass
    return QIcon(_fallback_pixmap())
