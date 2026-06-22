"""Virtualized model and painter for the student list."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QWidget

from office_app.ui import DESIGN_TOKENS


class StudentListModel(QAbstractListModel):
    """Small in-memory window over a lazily fetched student result set."""

    StudentRole = Qt.ItemDataRole.UserRole + 1
    fetch_more_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._has_more = False
        self._loading = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        student = self._rows[index.row()]
        if role == self.StudentRole:
            return student
        if role == Qt.ItemDataRole.UserRole:
            return student.get("id")
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
        if role == Qt.ItemDataRole.ToolTipRole:
            completion = student.get("_completion", 0)
            return f"Open student profile - {completion}% complete"
        return None

    def reset_rows(self, rows: Sequence[Mapping], *, has_more=False):
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self._has_more = has_more
        self._loading = False
        self.endResetModel()

    def append_rows(self, rows: Sequence[Mapping], *, has_more=False):
        additions = [dict(row) for row in rows]
        if additions:
            start = len(self._rows)
            self.beginInsertRows(QModelIndex(), start, start + len(additions) - 1)
            self._rows.extend(additions)
            self.endInsertRows()
        self._has_more = has_more
        self._loading = False

    def set_loading(self, loading: bool):
        self._loading = loading

    def canFetchMore(self, parent):
        return not parent.isValid() and self._has_more and not self._loading

    def fetchMore(self, parent):
        if self.canFetchMore(parent):
            self._loading = True
            self.fetch_more_requested.emit()

    def student_at(self, index):
        return self.data(index, self.StudentRole)

    @property
    def has_more(self):
        return self._has_more


class StudentSkeleton(QWidget):
    """Lightweight pulsing placeholders shown while the first page loads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self):
        self._phase = (self._phase + 1) % 20
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        wave = abs(10 - self._phase) / 10
        base = QColor(DESIGN_TOKENS["border_subtle"])
        base.setAlpha(120 + int(70 * wave))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        width = max(260, self.width() - 16)
        for row in range(min(5, max(1, self.height() // 126))):
            top = 8 + row * 126
            painter.drawRoundedRect(QRectF(8, top, width, 112), 8, 8)
            painter.setBrush(QColor(DESIGN_TOKENS["surface_subtle"]))
            painter.drawRoundedRect(QRectF(28, top + 20, width * 0.30, 13), 6, 6)
            painter.drawRoundedRect(QRectF(28, top + 47, width * 0.45, 10), 5, 5)
            painter.drawRoundedRect(QRectF(28, top + 76, width * 0.18, 22), 11, 11)
            painter.setBrush(base)


class StudentCardDelegate(QStyledItemDelegate):
    """Paint student cards without creating one QWidget tree per row."""

    CARD_HEIGHT = 132

    def sizeHint(self, option, index):
        return QSize(max(option.rect.width(), 320), self.CARD_HEIGHT)

    @staticmethod
    def _font(base: QFont, pixels: int, *, bold=False):
        font = QFont(base)
        font.setPixelSize(pixels)
        font.setBold(bold)
        return font

    @staticmethod
    def _text(painter, rect, text, color, font, flags):
        painter.setPen(QColor(color))
        painter.setFont(font)
        painter.drawText(rect, flags, str(text))

    @staticmethod
    def _pill(painter, x, y, text, foreground, background, border):
        metrics = painter.fontMetrics()
        width = max(48, metrics.horizontalAdvance(str(text)) + 18)
        rect = QRectF(x, y, width, 26)
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 13, 13)
        painter.setPen(QColor(foreground))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(text))
        return width

    def paint(self, painter: QPainter, option, index):
        student = index.data(StudentListModel.StudentRole) or {}
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card = QRectF(option.rect.adjusted(6, 4, -6, -4))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        background = DESIGN_TOKENS["primary_selected"] if selected else (
            DESIGN_TOKENS["primary_soft"] if hovered else DESIGN_TOKENS["surface"]
        )
        painter.setPen(QPen(QColor(DESIGN_TOKENS["border_subtle"]), 1))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(card, 8, 8)

        full_status = student.get("_full_status", "Active")
        status_text = student.get("_status_text", full_status)
        status_color = {
            "Active": DESIGN_TOKENS["success"],
            "Graduated": DESIGN_TOKENS["graduated"],
        }.get(full_status, DESIGN_TOKENS["danger"])

        left = card.left() + 16
        top = card.top() + 13
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(status_color))
        painter.drawEllipse(QRectF(left, top + 3, 11, 11))

        gender = str(student.get("gender") or "").strip().upper()
        name = f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
        if gender:
            name += f" ({gender})"
        name_rect = QRectF(left + 19, top, card.width() * 0.46, 24)
        self._text(
            painter, name_rect, name or "Unnamed student", DESIGN_TOKENS["text_primary"],
            self._font(option.font, 15, bold=True),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        meta = f"Sponsor: {student.get('sponsor') or '--'}    Area: {student.get('area') or '--'}"
        self._text(
            painter, QRectF(left, top + 28, card.width() * 0.52, 20), meta,
            DESIGN_TOKENS["text_secondary"], self._font(option.font, 12),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        painter.setFont(self._font(option.font, 12, bold=True))
        pill_y = top + 58
        grade_width = self._pill(
            painter, left, pill_y, student.get("grade") or "--",
            DESIGN_TOKENS["primary"], DESIGN_TOKENS["primary_soft"], DESIGN_TOKENS["primary_selected"],
        )
        self._pill(
            painter, left + grade_width + 8, pill_y, status_text,
            status_color, DESIGN_TOKENS["surface_subtle"], DESIGN_TOKENS["border"],
        )

        completion = int(student.get("_completion", 0))
        ring_size = 42
        ring = QRectF(left + 210, pill_y - 8, ring_size, ring_size)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(DESIGN_TOKENS["border_subtle"]), 4))
        painter.drawEllipse(ring)
        progress_color = (
            DESIGN_TOKENS["success"] if completion == 100 else
            DESIGN_TOKENS["primary"] if completion >= 75 else
            DESIGN_TOKENS["warning"] if completion >= 50 else DESIGN_TOKENS["danger"]
        )
        progress_pen = QPen(QColor(progress_color), 4)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(ring, 90 * 16, -int(completion / 100 * 360 * 16))
        self._text(
            painter, ring, f"{completion}%", DESIGN_TOKENS["text_primary"],
            self._font(option.font, 9, bold=True), Qt.AlignmentFlag.AlignCenter,
        )

        if card.width() >= 620:
            remarks_left = card.left() + card.width() * 0.60
            remarks_rect = QRectF(remarks_left, top, card.right() - remarks_left - 14, 94)
            painter.setPen(QPen(QColor(DESIGN_TOKENS["border_subtle"]), 1))
            painter.setBrush(QColor(DESIGN_TOKENS["surface_subtle"]))
            painter.drawRoundedRect(remarks_rect, 8, 8)
            self._text(
                painter, remarks_rect.adjusted(12, 7, -12, -66), "Remarks",
                DESIGN_TOKENS["text_disabled"], self._font(option.font, 11, bold=True),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            remarks = " ".join(str(student.get("remarks") or "").split()) or "No remarks"
            color = DESIGN_TOKENS["text_secondary"] if student.get("remarks") else DESIGN_TOKENS["text_disabled"]
            self._text(
                painter, remarks_rect.adjusted(12, 29, -12, -8), remarks, color,
                self._font(option.font, 12),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            )

        painter.restore()
