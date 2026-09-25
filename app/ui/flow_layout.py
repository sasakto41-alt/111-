"""FlowLayout — перенос виджетов по строкам (карточки фраз)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidgetItem


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, spacing: int = 10):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items: list = []

    # ---------------------------------------------------------------- bookkeeping --
    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        if 0 <= i < len(self._items):
            return self._items[i]
        return None

    def takeAt(self, i):  # noqa: N802
        if 0 <= i < len(self._items):
            return self._items.pop(i)
        return None

    def insertWidget(self, index: int, widget):  # noqa: N802
        self.addChildWidget(widget)
        item = QWidgetItem(widget)
        if index is None or index < 0 or index >= len(self._items):
            self._items.append(item)
        else:
            self._items.insert(index, item)
        self.update()

    def removeAll(self) -> None:
        while self._items:
            it = self._items.pop()
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, v: int) -> None:  # noqa: N802
        self._spacing = v
        self.update()

    # ------------------------------------------------------------------ geometry --
    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_h = 0
        right = rect.right() - m.right()
        spacing = self._spacing
        for it in self._items:
            hint = it.sizeHint()
            w, h = hint.width(), hint.height()
            if w > right - x and line_h > 0:
                x = rect.x() + m.left()
                y += line_h + spacing
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), QSize(max(w, 0), max(h, 0))))
            x += w + spacing
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()
