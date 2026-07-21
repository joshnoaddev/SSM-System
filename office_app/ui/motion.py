"""Purposeful, reduced-motion-aware animation helpers for the desktop UI."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QTimer,
    Qt,
    QVariantAnimation,
)
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
    QWidget,
)

from .fluent import CardWidget
from .theme import theme_color


MotionEnabled = Callable[[], bool]


class MotionCard(CardWidget):
    """Card surface with an orchestrated reveal and restrained hover depth."""

    def __init__(
        self,
        parent=None,
        *,
        motion_enabled: MotionEnabled | None = None,
        hover_depth: bool = True,
    ):
        super().__init__(parent)
        self._motion_enabled = motion_enabled or (lambda: True)
        self._hover_depth = bool(hover_depth)
        self._shadow_effect = None
        self._hover_progress = 0.0
        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.setDuration(180)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.valueChanged.connect(
            self._apply_hover_progress
        )
        self._reveal_animation = None
        if self._hover_depth:
            self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.installEventFilter(self)
            self._install_shadow()

    def eventFilter(self, watched, event):
        if watched is self and self._hover_depth and self._motion_enabled():
            if event.type() == QEvent.Type.Enter:
                self._animate_hover_to(1.0)
            elif event.type() == QEvent.Type.Leave:
                self._animate_hover_to(0.0)
        return super().eventFilter(watched, event)

    def reveal(self, delay_ms: int = 0) -> None:
        """Fade the card in once, then restore its interactive shadow."""
        if not self._motion_enabled():
            self._finish_reveal()
            return

        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.01)
        self.setGraphicsEffect(effect)
        self._shadow_effect = None

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(210)
        animation.setStartValue(0.01)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self._finish_reveal)
        self._reveal_animation = animation

        QTimer.singleShot(max(0, delay_ms), animation.start)

    def _finish_reveal(self) -> None:
        if self._hover_depth:
            self._install_shadow()
        else:
            self.setGraphicsEffect(None)
            self._shadow_effect = None

    def _animate_hover_to(self, target: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def _apply_hover_progress(self, value) -> None:
        self._hover_progress = float(value)
        effect = self._shadow_effect
        if effect is None:
            return
        effect.setBlurRadius(12 + (10 * self._hover_progress))
        effect.setOffset(0, 2 + (3 * self._hover_progress))
        effect.setColor(
            theme_color("shadow", int(18 + (18 * self._hover_progress)))
        )

    def _install_shadow(self) -> None:
        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(12 + (10 * self._hover_progress))
        effect.setOffset(0, 2 + (3 * self._hover_progress))
        effect.setColor(
            theme_color("shadow", int(18 + (18 * self._hover_progress)))
        )
        self.setGraphicsEffect(effect)
        self._shadow_effect = effect


class PressFeedbackController(QObject):
    """Mouse-only button feedback; keyboard activation remains instant."""

    def __init__(
        self,
        button: QPushButton,
        motion_enabled: MotionEnabled,
    ):
        super().__init__(button)
        self.button = button
        self.motion_enabled = motion_enabled
        self.effect = QGraphicsOpacityEffect(button)
        self.effect.setOpacity(1.0)
        button.setGraphicsEffect(self.effect)
        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        button.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            watched is self.button
            and self.motion_enabled()
            and self.button.isEnabled()
        ):
            if event.type() == QEvent.Type.MouseButtonPress:
                self._animate_to(0.78, 80)
            elif event.type() in (
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.Leave,
            ):
                self._animate_to(1.0, 140)
        return super().eventFilter(watched, event)

    def _animate_to(self, opacity: float, duration_ms: int) -> None:
        self.animation.stop()
        self.animation.setDuration(duration_ms)
        self.animation.setStartValue(self.effect.opacity())
        self.animation.setEndValue(opacity)
        self.animation.start()


class PulseController(QObject):
    """Gentle progress pulse for a compact status indicator."""

    def __init__(
        self,
        widget: QWidget,
        motion_enabled: MotionEnabled,
    ):
        super().__init__(widget)
        self.widget = widget
        self.motion_enabled = motion_enabled
        self.effect = None
        self.animation = None

    def start(self) -> None:
        self.stop()
        if not self.motion_enabled():
            return
        effect = QGraphicsOpacityEffect(self.widget)
        effect.setOpacity(1.0)
        self.widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(760)
        animation.setKeyValueAt(0.0, 0.58)
        animation.setKeyValueAt(0.5, 1.0)
        animation.setKeyValueAt(1.0, 0.58)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.setLoopCount(-1)
        self.effect = effect
        self.animation = animation
        animation.start()

    def stop(self) -> None:
        if self.animation is not None:
            self.animation.stop()
        self.animation = None
        self.effect = None
        self.widget.setGraphicsEffect(None)


def attach_press_feedback(
    button: QPushButton,
    motion_enabled: MotionEnabled,
) -> PressFeedbackController:
    controller = getattr(button, "_press_feedback_controller", None)
    if controller is None:
        controller = PressFeedbackController(button, motion_enabled)
        button._press_feedback_controller = controller
    return controller


def animate_count(
    label,
    target: int,
    *,
    motion_enabled: bool,
    duration_ms: int = 240,
) -> None:
    """Animate a dashboard integer without delaying the underlying data."""
    target = max(0, int(target))
    previous = getattr(label, "_count_animation", None)
    if previous is not None:
        previous.stop()

    if not motion_enabled:
        label.setText(str(target))
        return

    current_text = label.text().replace(",", "").strip()
    start = int(current_text) if current_text.isdigit() else 0
    if start == target:
        label.setText(str(target))
        return

    animation = QVariantAnimation(label)
    animation.setDuration(min(280, max(120, duration_ms)))
    animation.setStartValue(start)
    animation.setEndValue(target)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(
        lambda value: label.setText(f"{round(float(value)):,}")
    )
    animation.finished.connect(lambda: label.setText(f"{target:,}"))
    label._count_animation = animation
    animation.start()


def fade_in(
    widget: QWidget,
    *,
    motion_enabled: bool,
    duration_ms: int = 180,
    delay_ms: int = 0,
) -> None:
    """Short attention transition for a newly updated non-card element."""
    if not motion_enabled:
        widget.setGraphicsEffect(None)
        return

    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.25)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(min(280, max(100, duration_ms)))
    animation.setStartValue(0.25)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_in_animation = animation
    QTimer.singleShot(max(0, delay_ms), animation.start)
