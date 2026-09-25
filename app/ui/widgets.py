"""Переиспользуемые виджеты: секция-панель и всплывающий тост."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SectionFrame(QFrame):
    """Панель с заголовком внутри страницы."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(14, 12, 14, 14)
        self._lay.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("sectionTitle")
            self._lay.addWidget(t)
            self._title_label = t
        else:
            self._title_label = None

    def body_layout(self) -> QVBoxLayout:
        return self._lay


class Toast(QLabel):
    """Небольшое всплывающее уведомление внутри окна (2.5 с)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("QToast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def popup(self, text: str, ms: int = 2500) -> None:
        if not self.parentWidget():
            return
        self.setText(text)
        self.adjustSize()
        pw, ph = self.parentWidget().width(), self.parentWidget().height()
        w = min(max(self.width(), 260), pw - 40)
        self.setFixedWidth(w)
        self.adjustSize()
        self.move((pw - self.width()) // 2, ph - self.height() - 28)
        self.show()
        self.raise_()
        self._timer.start(ms)

    @staticmethod
    def show_message(parent: QWidget, text: str, ms: int = 2500) -> None:
        existing = parent.findChild(Toast)
        if not existing:
            existing = Toast(parent)
        existing.popup(text, ms)
