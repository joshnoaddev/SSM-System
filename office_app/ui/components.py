"""Small, reusable widgets that encode the application's visual structure."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import Spacing, theme_color


def refresh_style(widget: QWidget) -> None:
    """Re-evaluate QSS selectors after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class Card(QFrame):
    """Standard surface container with consistent role, spacing, and depth."""

    def __init__(
        self,
        parent=None,
        *,
        layout=None,
        tone: str | None = None,
        margins=(Spacing.M, Spacing.M, Spacing.M, Spacing.M),
        spacing=Spacing.XS,
        shadow=True,
    ):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setProperty("tone", tone or "default")
        self.setProperty("ownsShadow", shadow)

        if layout is not None:
            self.setLayout(layout)
            layout.setContentsMargins(*margins)
            layout.setSpacing(spacing)

        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(24)
            effect.setOffset(0, 4)
            effect.setColor(theme_color("shadow", 28))
            self.setGraphicsEffect(effect)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        refresh_style(self)


class ActionButton(QPushButton):
    """Button whose visual variant is selected through QSS properties."""

    def __init__(self, text="", parent=None, *, variant="primary"):
        super().__init__(text, parent)
        # Set the property before the widget is polished so QSS variant rules
        # are in effect from the very first paint, not just after a re-polish.
        self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_style(self)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        refresh_style(self)


class StatusBadge(QLabel):
    """Compact semantic label controlled by a dynamic ``state`` property."""

    def __init__(self, text="", parent=None, *, state="neutral", role="StatusBadge"):
        super().__init__(text, parent)
        self.setObjectName(role)
        self.setProperty("state", state)
        # Trigger polish so QSS state-property rules apply before first paint.
        refresh_style(self)

    def set_state(self, state: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("state", state)
        refresh_style(self)


class EmptyState(Card):
    """Reusable centered empty state with optional description and action."""

    def __init__(self, title, description="", action=None, parent=None, *, shadow=True):
        layout = QVBoxLayout()
        super().__init__(
            parent,
            layout=layout,
            margins=(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL),
            spacing=Spacing.S,
            shadow=shadow,
        )
        self.setProperty("component", "emptyState")

        layout.addStretch()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("EmptyStateTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setObjectName("EmptyStateDescription")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setVisible(bool(description))
        layout.addWidget(self.description_label)

        if action is not None:
            layout.addWidget(action, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
