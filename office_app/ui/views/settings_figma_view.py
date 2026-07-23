"""Figma-aligned application settings screen."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSettings, QSize, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractButton, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from office_app.app_config import (
    clear_sheet_sync_token, get_sheet_sync_token, get_supabase_config,
    save_sheet_sync_token,
)
from office_app.ui import theme_color
from office_app.ui.components import ActionButton, StatusBadge, set_content_hugging_button
from office_app.ui.fluent import CaptionLabel, ComboBox, LineEdit, MessageBox, StrongBodyLabel
from office_app.ui.theme import THEMES


class ToggleSwitch(QAbstractButton):
    """Accessible animated 42x24 switch matching the Figma control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0.0
        self._motion_enabled = True
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_toggle)

    def sizeHint(self):
        return QSize(42, 24)

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = pyqtProperty(float, _get_position, _set_position)

    def set_motion_enabled(self, enabled):
        self._motion_enabled = bool(enabled)

    def _animate_toggle(self, checked):
        target = 1.0 if checked else 0.0
        if not self._motion_enabled:
            self.position = target
            return
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QColor(
            theme_color("primary") if self.isChecked() else theme_color("border")
        )
        if not self.isEnabled():
            track.setAlpha(120)
        painter.setBrush(track)
        painter.drawRoundedRect(0, 0, 42, 24, 12, 12)
        painter.setBrush(QColor(theme_color("surface")))
        painter.drawEllipse(int(round(3 + 18 * self._position)), 3, 18, 18)


class TokenDialog(QDialog):
    remove_requested = pyqtSignal()

    def __init__(self, configured, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Replace synchronization token")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = StrongBodyLabel("Private synchronization token")
        title.setObjectName("CardHeading")
        copy = CaptionLabel(
            "Enter the protected commit token. It is encrypted for this Windows user."
        )
        copy.setWordWrap(True)
        self.token_input = LineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("Paste a new private sync token")
        self.token_input.setAccessibleName("Private sheet sync token")
        layout.addWidget(title)
        layout.addWidget(copy)
        layout.addWidget(self.token_input)
        buttons = QDialogButtonBox()
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        save = buttons.addButton("Save token", QDialogButtonBox.ButtonRole.AcceptRole)
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        for button in (cancel, save):
            set_content_hugging_button(button)
        if configured:
            remove = buttons.addButton(
                "Remove saved token", QDialogButtonBox.ButtonRole.DestructiveRole
            )
            set_content_hugging_button(remove)
            remove.clicked.connect(self._remove)
        layout.addWidget(buttons)

    def _remove(self):
        self.remove_requested.emit()
        self.done(2)


class SettingsView(QWidget):
    theme_changed = pyqtSignal(str)
    connection_settings_requested = pyqtSignal()
    test_connection_requested = pyqtSignal()
    sync_now_requested = pyqtSignal()
    preferences_changed = pyqtSignal()
    sync_token_changed = pyqtSignal(bool)

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._loading_preferences = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(20)
        top = QGridLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setHorizontalSpacing(20)
        top.setColumnStretch(0, 1)
        top.setColumnStretch(1, 1)
        self.appearance_card = self._appearance_card()
        self.connection_card = self._connection_card()
        top.addWidget(self.appearance_card, 0, 0)
        top.addWidget(self.connection_card, 0, 1)
        outer.addLayout(top)
        self.sync_card = self._sync_card()
        outer.addWidget(self.sync_card)
        outer.addStretch(1)

        # Compatibility attributes used by established app callbacks.
        self.workbook_path_input = LineEdit(self)
        self.workbook_path_input.hide()
        self.sync_token_input = LineEdit(self)
        self.sync_token_input.hide()
        self.load_settings()

    @staticmethod
    def _card(title_text, copy_text):
        card = QFrame()
        card.setObjectName("SettingsCard")
        card.setFixedHeight(290)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)
        title = StrongBodyLabel(title_text)
        title.setObjectName("CardHeading")
        copy = CaptionLabel(copy_text)
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(copy)
        return card, layout

    def _appearance_card(self):
        card, layout = self._card(
            "Appearance and accessibility",
            "Local preferences apply to this computer.",
        )
        layout.setContentsMargins(20, 18, 20, 12)
        layout.addSpacing(13)
        self.theme_combo = ComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.hide()
        self.dark_theme_checkbox = ToggleSwitch()
        self.large_text_checkbox = ToggleSwitch()
        self.reduce_motion_checkbox = ToggleSwitch()
        rows = (
            ("Dark theme", "Use the darker office palette.", self.dark_theme_checkbox),
            ("Larger text", "Increase interface type for readability.", self.large_text_checkbox),
            ("Reduce motion", "Keep feedback but skip fades and count animations.", self.reduce_motion_checkbox),
        )
        for title, copy, toggle in rows:
            toggle.setAccessibleName(title)
            layout.addWidget(self._preference_row(title, copy, toggle))
            toggle.toggled.connect(self._save_preferences)
        self.dark_theme_checkbox.toggled.connect(
            lambda enabled: self.theme_combo.setCurrentText("Dark" if enabled else "Light")
        )
        return card

    @staticmethod
    def _preference_row(title_text, copy_text, toggle):
        row = QFrame()
        row.setObjectName("SettingsPreferenceRow")
        row.setFixedHeight(68)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 8, 8)
        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel(title_text)
        title.setObjectName("SettingsPreferenceTitle")
        copy = QLabel(copy_text)
        copy.setObjectName("SettingsPreferenceCopy")
        text.addWidget(title)
        text.addWidget(copy)
        layout.addLayout(text, 1)
        layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignVCenter)
        return row

    def _connection_card(self):
        card, layout = self._card(
            "Database connection", "Changes require an application restart."
        )
        layout.addSpacing(18)
        status = QHBoxLayout()
        status.setSpacing(12)
        status_label = QLabel("STATUS")
        status_label.setObjectName("UtilityLabel")
        self.database_badge = StatusBadge(
            "Connected", state="success", role="SettingsDatabaseBadge"
        )
        self.database_badge.setFixedHeight(24)
        status.addWidget(status_label)
        status.addWidget(self.database_badge)
        status.addStretch()
        layout.addLayout(status)
        layout.addSpacing(16)
        project = QLabel("PROJECT")
        project.setObjectName("UtilityLabel")
        self.project_value_label = QLabel(self._project_id())
        self.project_value_label.setObjectName("SettingsProjectValue")
        self.connection_checked_label = QLabel("Waiting for connection check")
        self.connection_checked_label.setObjectName("Caption")
        layout.addWidget(project)
        layout.addSpacing(6)
        layout.addWidget(self.project_value_label)
        layout.addSpacing(14)
        layout.addWidget(self.connection_checked_label)
        layout.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(0)
        self.connection_button = ActionButton("Edit connection", variant="secondary")
        self.test_connection_button = ActionButton("Test connection")
        for button in (self.connection_button, self.test_connection_button):
            button.setProperty("density", "compact")
            set_content_hugging_button(button, height=38)
            actions.addWidget(button)
        actions.addStretch()
        self.connection_button.clicked.connect(self.connection_settings_requested.emit)
        self.test_connection_button.clicked.connect(self.test_connection_requested.emit)
        layout.addLayout(actions)
        return card

    def _sync_card(self):
        card = QFrame()
        card.setObjectName("SyncSettingsCard")
        card.setFixedHeight(298)
        shell = QHBoxLayout(card)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        accent = QFrame()
        accent.setObjectName("SettingsSyncAccent")
        accent.setFixedWidth(4)
        shell.addWidget(accent)
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 20, 18)
        layout.setSpacing(0)
        title = StrongBodyLabel("Google Sheet synchronization")
        title.setObjectName("CardHeading")
        copy = CaptionLabel(
            "Import the latest student masterlist using a protected commit token."
        )
        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(copy)
        layout.addSpacing(16)
        panel = QFrame()
        panel.setObjectName("SettingsTokenPanel")
        panel.setFixedHeight(58)
        token_row = QHBoxLayout(panel)
        token_row.setContentsMargins(16, 8, 16, 8)
        token_text = QVBoxLayout()
        token_text.setSpacing(2)
        caption = QLabel("Token status")
        caption.setObjectName("SettingsMetaLabel")
        self.token_state_label = QLabel("Not configured on this computer")
        self.token_state_label.setObjectName("SettingsMetaValue")
        token_text.addWidget(caption)
        token_text.addWidget(self.token_state_label)
        token_row.addLayout(token_text)
        token_row.addStretch()
        self.sync_token_badge = StatusBadge(
            "Token needed", state="warning", role="SyncTokenBadge"
        )
        self.sync_token_badge.setFixedHeight(25)
        token_row.addWidget(self.sync_token_badge)
        layout.addWidget(panel)
        layout.addSpacing(18)
        meta = QHBoxLayout()
        meta.setSpacing(20)
        self.sync_last_value = self._meta_column(
            meta, "Last successful sync", "No successful sync recorded", 2
        )
        self.sync_source_value = self._meta_column(
            meta, "Source", "SSM Masterlist / Current workbook", 2
        )
        meta.addStretch(1)
        self.replace_token_button = ActionButton("Replace token", variant="secondary")
        self.sync_now_button = ActionButton("Sync now")
        for button in (self.replace_token_button, self.sync_now_button):
            button.setProperty("density", "compact")
            set_content_hugging_button(button, height=38)
            meta.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.replace_token_button.clicked.connect(self.prompt_replace_token)
        self.sync_now_button.clicked.connect(self.sync_now_requested.emit)
        layout.addLayout(meta)
        layout.addSpacing(18)
        notice = QLabel(
            "Synchronization updates student records but preserves office expenses and audit history."
        )
        notice.setObjectName("SettingsSyncNotice")
        notice.setFixedHeight(38)
        notice.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(notice)
        shell.addLayout(layout, 1)
        return card

    @staticmethod
    def _meta_column(parent, caption_text, value_text, stretch):
        column = QVBoxLayout()
        column.setSpacing(5)
        caption = QLabel(caption_text)
        caption.setObjectName("SettingsMetaLabel")
        value = QLabel(value_text)
        value.setObjectName("SettingsMetaValue")
        column.addWidget(caption)
        column.addWidget(value)
        parent.addLayout(column, stretch)
        return value

    @staticmethod
    def _project_id():
        url, _key = get_supabase_config()
        host = urlparse(url).hostname or ""
        return host.split(".", 1)[0] or "Not configured"

    def load_settings(self):
        self._loading_preferences = True
        self.workbook_path_input.setText(self._settings.value("workbook_path", "", type=str))
        theme = self._settings.value("theme", "Light", type=str)
        self.theme_combo.setCurrentText(theme if theme in THEMES else "Light")
        self.dark_theme_checkbox.setChecked(theme == "Dark")
        self.large_text_checkbox.setChecked(self._settings.value("large_text", False, type=bool))
        self.reduce_motion_checkbox.setChecked(self._settings.value("reduce_motion", False, type=bool))
        self._loading_preferences = False
        self._update_motion_preferences()
        self._set_sync_token_status(bool(get_sheet_sync_token()))
        self.project_value_label.setText(self._project_id())

    def save_settings(self):
        self._save_preferences()

    def _save_preferences(self, *_args):
        if self._loading_preferences:
            return
        theme = "Dark" if self.dark_theme_checkbox.isChecked() else "Light"
        self.theme_combo.setCurrentText(theme)
        self._settings.setValue("theme", theme)
        self._settings.setValue("large_text", self.large_text_checkbox.isChecked())
        self._settings.setValue("reduce_motion", self.reduce_motion_checkbox.isChecked())
        self._update_motion_preferences()
        self.theme_changed.emit(theme)
        self.preferences_changed.emit()

    def _update_motion_preferences(self):
        enabled = not self.reduce_motion_checkbox.isChecked()
        for toggle in (self.dark_theme_checkbox, self.large_text_checkbox, self.reduce_motion_checkbox):
            toggle.set_motion_enabled(enabled)

    def prompt_replace_token(self):
        dialog = TokenDialog(bool(get_sheet_sync_token()), self)
        removed = {"value": False}
        dialog.remove_requested.connect(lambda: removed.__setitem__("value", True))
        result = dialog.exec()
        if removed["value"]:
            clear_sheet_sync_token()
            self._set_sync_token_status(False)
            self.sync_token_changed.emit(False)
            return
        if result != QDialog.DialogCode.Accepted:
            return
        try:
            save_sheet_sync_token(dialog.token_input.text().strip())
        except (RuntimeError, ValueError) as error:
            message = MessageBox("Token not saved", str(error), self)
            message.cancelButton.hide()
            message.exec()
            return
        self._set_sync_token_status(True)
        self.sync_token_changed.emit(True)

    def _set_sync_token_status(self, configured):
        self.token_state_label.setText(
            "Stored securely on this computer" if configured else "Not configured on this computer"
        )
        self.sync_token_badge.set_state(
            "success" if configured else "warning",
            "Ready to sync" if configured else "Token needed",
        )
        self.replace_token_button.setText("Replace token" if configured else "Add token")
        self.sync_now_button.setEnabled(configured)

    def set_connection_state(self, text, state, checked_at=None):
        self.database_badge.set_state(state, text)
        moment = checked_at or datetime.now()
        self.connection_checked_label.setText(
            f"Last checked today at {moment.strftime('%I:%M %p').lstrip('0')}"
        )
        loading = state == "loading"
        self.test_connection_button.setEnabled(not loading)
        self.test_connection_button.setText("Testing…" if loading else "Test connection")

    def set_sync_status(
        self, *, configured, state, last_sync, active_rows=None,
        source="SSM Masterlist / Current workbook",
    ):
        self._set_sync_token_status(configured)
        self.sync_token_badge.set_state("success" if configured else "warning", state)
        suffix = f"  •  {active_rows} active rows" if active_rows is not None else ""
        self.sync_last_value.setText(f"{last_sync}{suffix}")
        self.sync_source_value.setText(source)

    def set_sync_busy(self, busy):
        self.sync_now_button.setEnabled(not busy and bool(get_sheet_sync_token()))
        self.sync_now_button.setText("Syncing…" if busy else "Sync now")

    def set_compact(self, compact):
        """Trim vertical cadence at the supported 980x700 window."""
        top_height = 276 if compact else 290
        self.appearance_card.setFixedHeight(top_height)
        self.connection_card.setFixedHeight(top_height)
        self.sync_card.setFixedHeight(280 if compact else 298)
