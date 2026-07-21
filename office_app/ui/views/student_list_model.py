"""Virtualized model and painter for the student list."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QWidget
from office_app.ui.theme import theme_color


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
        name = f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
        if role == Qt.ItemDataRole.DisplayRole:
            return name
        if role in (
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.AccessibleDescriptionRole,
        ):
            completion = student.get("_completion", 0)
            budget = student.get("_budget_status") or {}
            budget_text = (
                f"Budget {budget.get('title')}, {budget.get('detail')}"
                if budget.get("allocated")
                else "No budget allocated"
            )
            return (
                f"Open student profile. {completion}% complete. "
                f"{budget_text}."
            )
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return name or "Unnamed student"
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
        base = theme_color("border_subtle")
        base.setAlpha(120 + int(70 * wave))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base)
        width = max(260, self.width() - 16)
        for row in range(min(6, max(1, self.height() // 104))):
            top = 7 + row * 104
            painter.drawRoundedRect(QRectF(8, top, width, 94), 8, 8)
            painter.setBrush(theme_color("surface_subtle"))
            painter.drawRoundedRect(QRectF(28, top + 16, width * 0.28, 13), 6, 6)
            painter.drawRoundedRect(QRectF(28, top + 39, width * 0.42, 10), 5, 5)
            painter.drawRoundedRect(QRectF(28, top + 64, width * 0.18, 22), 7, 7)
            painter.setBrush(base)


class StudentCardDelegate(QStyledItemDelegate):
    """Paint the compact table rows defined by the Figma directory frame."""

    CARD_HEIGHT = 86

    def sizeHint(self, option, index):
        # Let QListView own the row width. Returning a cached viewport width
        # here leaves a horizontal scrollbar after the main window narrows.
        return QSize(1, self.CARD_HEIGHT)

    @staticmethod
    def _font(base: QFont, pixels: int, *, bold=False):
        font = QFont(base)
        if font.pointSize() <= 0:
            font.setPointSize(10)
        font.setPixelSize(pixels)
        font.setBold(bold)
        return font

    @staticmethod
    def _utility_font(base: QFont, pixels: int, *, bold=True):
        font = StudentCardDelegate._font(base, pixels, bold=bold)
        font.setFamilies(["Cascadia Mono", "Consolas", "Segoe UI"])
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.35)
        return font

    @staticmethod
    def _text(painter, rect, text, color, font, flags):
        painter.setPen(color)
        painter.setFont(font)
        painter.drawText(rect, flags, str(text))

    @staticmethod
    def _elided_text(painter, rect, text, color, font):
        painter.setPen(color)
        painter.setFont(font)
        elided = painter.fontMetrics().elidedText(
            str(text), Qt.TextElideMode.ElideRight, int(rect.width())
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

    @staticmethod
    def _budget_color(state):
        return {
            "danger": theme_color("danger"),
            "warning": theme_color("warning"),
            "success": theme_color("success"),
        }.get(state, theme_color("text_disabled"))

    @staticmethod
    def _pill(
        painter,
        x,
        y,
        text,
        foreground,
        background,
        border,
        *,
        max_width=112,
    ):
        metrics = painter.fontMetrics()
        width = min(max_width, max(46, metrics.horizontalAdvance(str(text)) + 16))
        rect = QRectF(x, y, width, 24)
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(foreground)
        pill_text = metrics.elidedText(
            str(text),
            Qt.TextElideMode.ElideRight,
            max(1, int(rect.width()) - 12),
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, pill_text)
        return width

    def paint(self, painter: QPainter, option, index):
        student = index.data(StudentListModel.StudentRole) or {}
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        row = QRectF(option.rect.adjusted(0, 0, 0, -1))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        if selected or hovered:
            painter.fillRect(
                row,
                theme_color("primary_selected") if selected else theme_color("primary_soft"),
            )
        painter.setPen(QPen(
            theme_color("primary") if focused else theme_color("border_subtle"),
            2 if focused else 1,
        ))
        painter.drawLine(row.bottomLeft(), row.bottomRight())

        full_status = student.get("_full_status", "Active")
        status_text = student.get("_status_text", full_status)
        status_color = {
            "Active": theme_color("success"),
            "Graduated": theme_color("graduated"),
        }.get(full_status, theme_color("danger"))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(status_color)
        painter.drawRoundedRect(
            QRectF(row.left() + 1, row.top() + 8, 3, row.height() - 16), 1.5, 1.5,
        )

        left = row.left() + 14
        top = row.top() + 10
        available = max(500.0, row.width() - 28)
        student_w = available * 0.32
        status_w = available * 0.15
        profile_w = available * 0.16
        budget_w = available * 0.23
        student_x = left
        status_x = student_x + student_w
        profile_x = status_x + status_w
        budget_x = profile_x + profile_w
        updated_x = budget_x + budget_w

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(status_color)
        painter.drawEllipse(QRectF(student_x, top + 3, 8, 8))

        gender = str(student.get("gender") or "").strip().upper()
        name = f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
        if gender:
            name += f" ({gender})"
        self._elided_text(
            painter,
            QRectF(student_x + 16, top - 2, student_w - 24, 20),
            name or "Unnamed student",
            theme_color("text_primary"),
            self._font(option.font, 13, bold=True),
        )

        meta = (
            f"{student.get('area') or 'Area not set'}"
            f"  /  {student.get('sponsor') or 'Sponsor not set'}"
        )
        self._elided_text(
            painter,
            QRectF(student_x + 16, top + 22, student_w - 24, 18),
            meta,
            theme_color("text_secondary"),
            self._font(option.font, 11),
        )

        painter.setFont(self._font(option.font, 11, bold=True))
        status_background = {
            "Active": theme_color("success_soft"),
            "Graduated": theme_color("graduated_soft"),
        }.get(full_status, theme_color("danger_soft"))
        self._pill(
            painter,
            status_x,
            top - 2,
            status_text,
            status_color,
            status_background,
            status_background,
            max_width=max(60, int(status_w - 12)),
        )

        completion = max(0, min(100, int(student.get("_completion", 0))))
        progress_color = (
            theme_color("success") if completion == 100 else
            theme_color("primary") if completion >= 75 else
            theme_color("warning") if completion >= 50 else theme_color("danger")
        )
        self._text(
            painter, QRectF(profile_x, top - 2, profile_w - 14, 18),
            f"{completion}%", theme_color("text_primary"),
            self._font(option.font, 12, bold=True),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        profile_bar = QRectF(profile_x, top + 24, max(40, profile_w - 24), 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme_color("border_subtle"))
        painter.drawRoundedRect(profile_bar, 3, 3)
        if completion:
            painter.setBrush(progress_color)
            painter.drawRoundedRect(
                QRectF(profile_bar.left(), profile_bar.top(), profile_bar.width() * completion / 100, profile_bar.height()),
                3, 3,
            )
        self._text(
            painter, QRectF(profile_x, top + 36, profile_w - 14, 14),
            "PROFILE", theme_color("text_disabled"),
            self._utility_font(option.font, 8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        budget = student.get("_budget_status") or {}
        allocated = bool(budget.get("allocated"))
        percent = max(0, min(100, int(budget.get("percent") or 0)))
        detail = budget.get("detail") or "No budget allocated"
        state_color = self._budget_color(budget.get("state"))
        label_color = theme_color("text_primary") if allocated else theme_color("text_disabled")
        self._elided_text(
            painter, QRectF(budget_x, top - 2, budget_w - 18, 18),
            detail, label_color, self._font(option.font, 11, bold=allocated),
        )
        budget_bar = QRectF(budget_x, top + 24, max(48, budget_w - 26), 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme_color("border_subtle"))
        painter.drawRoundedRect(budget_bar, 3, 3)
        if allocated and percent:
            painter.setBrush(state_color)
            painter.drawRoundedRect(
                QRectF(budget_bar.left(), budget_bar.top(), budget_bar.width() * percent / 100, budget_bar.height()),
                3, 3,
            )
        budget_caption = f"{percent}% used" if allocated else ""
        self._text(
            painter, QRectF(budget_x, top + 36, budget_w - 18, 14),
            budget_caption, state_color if allocated else theme_color("text_disabled"),
            self._utility_font(option.font, 8),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        updated = str(student.get("sheet_synced_at") or "").strip()
        if updated:
            try:
                parsed = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                updated = parsed.strftime("%b %d").replace(" 0", " ")
            except ValueError:
                updated = updated[:10]
        else:
            updated = "Current"
        self._text(
            painter, QRectF(updated_x, top + 5, max(30, available * 0.10 - 18), 20),
            updated, theme_color("text_secondary"), self._font(option.font, 10),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._text(
            painter, QRectF(row.right() - 18, top + 4, 12, 20),
            "›", theme_color("text_secondary"), self._font(option.font, 18),
            Qt.AlignmentFlag.AlignCenter,
        )

        painter.restore()
