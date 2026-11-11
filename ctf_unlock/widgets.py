"""Disposition de commandes qui s'adapte à la largeur et aux polices système."""
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self):
        super().__init__()
        self.items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        return self.items.pop(index) if 0 <= index < len(self.items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.arrange(QRect(0, 0, width, 0), True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self.items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        return size

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.arrange(rect, False)

    def arrange(self, rect, measure):
        rows, row, used = [], [], 0
        for item in self.items:
            if item.isEmpty():
                continue
            size = item.sizeHint().expandedTo(item.minimumSize())
            width = min(size.width(), rect.width())
            if row and used + self.spacing() + width > rect.width():
                rows.append(row); row, used = [], 0
            row.append((item, width, size.height()))
            used += width + (self.spacing() if len(row) > 1 else 0)
        if row:
            rows.append(row)
        y = rect.y()
        for row in rows:
            height = max(entry[2] for entry in row)
            expanding = [entry for entry in row if entry[0].expandingDirections() & Qt.Orientation.Horizontal]
            extra = max(0, rect.width() - sum(entry[1] for entry in row) - self.spacing()*(len(row)-1))
            x = rect.x()
            for item, width, _ in row:
                if item.expandingDirections() & Qt.Orientation.Horizontal:
                    width += extra // max(len(expanding), 1)
                if not measure:
                    item.setGeometry(QRect(x, y, width, height))
                x += width + self.spacing()
            y += height + self.spacing()
        return y - rect.y() - (self.spacing() if rows else 0)
