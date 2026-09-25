"""Карточка фразы: компактная, с drag&drop сортировкой и быстрой отправкой."""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

MIME_ENTRY = "application/x-mth-entry-id"


class PhraseCard(QFrame):
    edit_requested = Signal(str)      # id (открыть редактор)
    trigger_requested = Signal(str)   # id (вставить/скопировать сейчас)
    favorite_requested = Signal(str)
    move_requested = Signal(str, int)  # id, сдвиг (fallback без DnD)

    def __init__(self, entry, overlay_mode: bool = False, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.overlay_mode = overlay_mode
        self.setObjectName("phraseCard")
        self.setFixedWidth(280)
        self.setCursor(Qt.PointingHandCursor)
        self._drag_start = None

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl_title = QLabel(entry.title or "(без названия)")
        self.lbl_title.setObjectName("cardTitle")
        self.lbl_title.setWordWrap(False)
        top.addWidget(self.lbl_title, 1)
        self.lbl_hotkey = QLabel(entry.hotkey.upper() if entry.hotkey else "")
        self.lbl_hotkey.setObjectName("hint")
        top.addWidget(self.lbl_hotkey)
        v.addLayout(top)

        text = (entry.text or "").replace("\n", " ")
        self.lbl_text = QLabel(text if len(text) <= 90 else text[:90] + "…")
        self.lbl_text.setObjectName("cardText")
        self.lbl_text.setWordWrap(True)
        v.addWidget(self.lbl_text)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.lbl_cat = QLabel(entry.category or "")
        self.lbl_cat.setObjectName("hint")
        bottom.addWidget(self.lbl_cat)
        bottom.addStretch(1)
        self.lbl_usage = QLabel(f"×{entry.usage}" if entry.usage else "")
        self.lbl_usage.setObjectName("hint")
        bottom.addWidget(self.lbl_usage)
        if entry.favorite:
            star = QLabel("★")
            star.setStyleSheet("color: #FBBF24; font-size: 14px;")
            bottom.addWidget(star)
        btn_send = QPushButton("▶")
        btn_send.setToolTip("Вставить/скопировать сейчас")
        btn_send.setFixedWidth(34)
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.clicked.connect(lambda: self.trigger_requested.emit(self.entry.id))
        bottom.addWidget(btn_send)
        v.addLayout(bottom)

    # ------------------------------------------------------------- события --
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._drag_start = ev.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self.overlay_mode or self._drag_start is None:
            super().mouseMoveEvent(ev)
            return
        if not (ev.buttons() & Qt.LeftButton):
            return
        if (ev.pos() - self._drag_start).manhattanLength() < 12:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_ENTRY, self.entry.id.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        self._drag_start = None
        if ev.button() == Qt.LeftButton:
            if self.overlay_mode:
                self.trigger_requested.emit(self.entry.id)
            else:
                self.edit_requested.emit(self.entry.id)
        super().mouseReleaseEvent(ev)

    def refresh(self, entry) -> None:
        self.entry = entry
        self.lbl_title.setText(entry.title or "(без названия)")
        text = (entry.text or "").replace("\n", " ")
        self.lbl_text.setText(text if len(text) <= 90 else text[:90] + "…")
        self.lbl_cat.setText(entry.category or "")
        self.lbl_hotkey.setText(entry.hotkey.upper() if entry.hotkey else "")
        self.lbl_usage.setText(f"×{entry.usage}" if entry.usage else "")
