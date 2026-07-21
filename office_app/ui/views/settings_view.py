"""Application settings screen."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from office_app.app_config import (
    clear_sheet_sync_token,
    get_sheet_sync_token,
    save_sheet_sync_token,
)
from office_app.ui.components import StatusBadge, set_content_hugging_button
from office_app.ui.fluent import (
    BodyLabel,
    CardWidget,
    CaptionLabel,
    CheckBox,
    ComboBox,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)
from office_app.ui.theme import THEMES


class SettingsView(QWidget):
    theme_changed = pyqtSignal(str)
    connection_settings_requested = pyqtSignal()
    preferences_changed = pyqtSignal()
    sync_token_changed = pyqtSignal(bool)

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(20)

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setHorizontalSpacing(20)
        top_grid.setColumnStretch(0, 1)
        top_grid.setColumnStretch(1, 1)

        appearance_card = CardWidget()
        appearance_card.setObjectName("SettingsCard")
        appearance_card.setFixedHeight(290)
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(20, 18, 20, 18)
        appearance_layout.setSpacing(13)
        appearance_title = StrongBodyLabel("Appearance and accessibility")
        appearance_title.setObjectName("CardHeading")
        appearance_layout.addWidget(appearance_title)
        appearance_description = CaptionLabel(
            "Personalize this computer without changing shared student data."
        )
        appearance_description.setWordWrap(True)
        appearance_layout.addWidget(appearance_description)

        self.theme_combo = ComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.hide()
        self.dark_theme_checkbox = CheckBox("Dark theme")
        self.dark_theme_checkbox.setAccessibleDescription(
            "Uses a dark, high-contrast workspace on this computer."
        )
        self.dark_theme_checkbox.toggled.connect(
            lambda enabled: self.theme_combo.setCurrentText("Dark" if enabled else "Light")
        )
        self.large_text_checkbox = CheckBox("Larger interface text")
        self.large_text_checkbox.setAccessibleDescription(
            "Increases key labels, controls, and dashboard values."
        )
        self.reduce_motion_checkbox = CheckBox("Reduce interface motion")
        self.reduce_motion_checkbox.setAccessibleDescription(
            "Disables page fades and decorative motion."
        )
        for checkbox in (
            self.dark_theme_checkbox,
            self.large_text_checkbox,
            self.reduce_motion_checkbox,
        ):
            row = QFrame()
            row.setObjectName("SettingsToggleRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.addWidget(checkbox)
            appearance_layout.addWidget(row)
        appearance_layout.addStretch()
        top_grid.addWidget(appearance_card, 0, 0)

        connection_card = CardWidget()
        connection_card.setObjectName("SettingsCard")
        connection_card.setFixedHeight(290)
        connection_layout = QVBoxLayout(connection_card)
        connection_layout.setContentsMargins(20, 18, 20, 18)
        connection_layout.setSpacing(12)
        connection_title = StrongBodyLabel("Database connection")
        connection_title.setObjectName("CardHeading")
        connection_layout.addWidget(connection_title)
        connection_description = CaptionLabel(
            "This installation uses the shared Supabase office database."
        )
        connection_description.setWordWrap(True)
        connection_layout.addWidget(connection_description)
        database_state = QFrame()
        database_state.setObjectName("DatabaseStatePanel")
        database_state_layout = QVBoxLayout(database_state)
        database_state_layout.setContentsMargins(14, 12, 14, 12)
        state_label = StrongBodyLabel("Connected workspace")
        state_copy = CaptionLabel("Student records synchronize across authorized office PCs.")
        state_copy.setWordWrap(True)
        database_state_layout.addWidget(state_label)
        database_state_layout.addWidget(state_copy)
        connection_layout.addWidget(database_state)
        connection_layout.addStretch()
        self.connection_button = PushButton("Edit connection")
        set_content_hugging_button(self.connection_button)
        self.connection_button.setAccessibleName("Edit Supabase connection")
        self.connection_button.clicked.connect(
            self.connection_settings_requested.emit
        )
        connection_layout.addWidget(
            self.connection_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        top_grid.addWidget(connection_card, 0, 1)
        outer_layout.addLayout(top_grid)

        sync_card = CardWidget()
        sync_card.setObjectName("SyncSettingsCard")
        sync_card.setFixedHeight(298)
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(20, 18, 20, 18)
        sync_layout.setSpacing(10)

        sync_header = QHBoxLayout()
        sync_title = StrongBodyLabel("Google Sheets synchronization")
        sync_title.setObjectName("CardHeading")
        self.sync_token_badge = StatusBadge(
            "Not configured",
            state="warning",
            role="SyncTokenBadge",
        )
        self.sync_token_badge.setAccessibleName("Sync token status")
        sync_header.addWidget(sync_title)
        sync_header.addStretch()
        sync_header.addWidget(self.sync_token_badge)
        sync_layout.addLayout(sync_header)

        sync_description = CaptionLabel(
            "Securely connect the office sheet and local master workbook. Saved tokens remain encrypted for this Windows user."
        )
        sync_description.setWordWrap(True)
        sync_layout.addWidget(sync_description)

        token_label = QLabel("PRIVATE SYNC TOKEN")
        token_label.setObjectName("UtilityLabel")
        sync_layout.addWidget(token_label)
        token_row = QHBoxLayout()
        token_row.setSpacing(8)
        self.sync_token_input = LineEdit()
        self.sync_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.sync_token_input.setPlaceholderText(
            "Paste a new private sync token"
        )
        self.sync_token_input.setAccessibleName("Private sheet sync token")
        self.sync_token_input.setAccessibleDescription(
            "A token of at least 32 characters. The saved value stays hidden."
        )
        self.show_sync_token_button = PushButton("Show")
        self.show_sync_token_button.setCheckable(True)
        set_content_hugging_button(self.show_sync_token_button)
        self.show_sync_token_button.setAccessibleName(
            "Show or hide the entered sync token"
        )
        self.show_sync_token_button.toggled.connect(
            self._toggle_sync_token_visibility
        )
        self.clear_sync_token_button = PushButton("Remove saved token")
        self.clear_sync_token_button.setProperty("variant", "secondary")
        set_content_hugging_button(self.clear_sync_token_button)
        self.clear_sync_token_button.clicked.connect(
            self._mark_sync_token_for_removal
        )
        token_row.addWidget(self.sync_token_input, 1)
        token_row.addWidget(self.show_sync_token_button)
        token_row.addWidget(self.clear_sync_token_button)
        sync_layout.addLayout(token_row)

        workbook_row = QHBoxLayout()
        workbook_row.setSpacing(8)
        workbook_label = QLabel("MASTER WORKBOOK")
        workbook_label.setObjectName("UtilityLabel")
        sync_layout.addWidget(workbook_label)
        self.workbook_path_input = LineEdit()
        self.workbook_path_input.setPlaceholderText(
            r"e.g., C:\Users\YourUser\Documents\SSM_Masterlist.xlsx"
        )
        self.pick_workbook_button = PushButton("Browse")
        set_content_hugging_button(self.pick_workbook_button)
        self.pick_workbook_button.clicked.connect(self.pick_workbook)
        workbook_row.addWidget(self.workbook_path_input, 1)
        workbook_row.addWidget(self.pick_workbook_button)
        sync_layout.addLayout(workbook_row)

        actions = QHBoxLayout()
        saved_copy = CaptionLabel("Changes apply to this computer after saving.")
        actions.addWidget(saved_copy)
        actions.addStretch()
        self.save_button = PrimaryPushButton("Save changes")
        set_content_hugging_button(self.save_button)
        self.save_button.setAccessibleName("Save application settings")
        self.save_button.clicked.connect(self.save_settings)
        actions.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignRight)
        sync_layout.addLayout(actions)
        outer_layout.addWidget(sync_card)
        outer_layout.addStretch()

        self.load_settings()
        self._clear_token_requested = False

    def load_settings(self):
        workbook_path = self._settings.value("workbook_path", "", type=str)
        self.workbook_path_input.setText(workbook_path)

        theme = self._settings.value("theme", "Light", type=str)
        self.theme_combo.setCurrentText(theme if theme in THEMES else "Light")
        self.dark_theme_checkbox.setChecked(theme == "Dark")
        self.large_text_checkbox.setChecked(
            self._settings.value("large_text", False, type=bool)
        )
        self.reduce_motion_checkbox.setChecked(
            self._settings.value("reduce_motion", False, type=bool)
        )
        self._set_sync_token_status(bool(get_sheet_sync_token()))

    def pick_workbook(self):
        current_path = self.workbook_path_input.text().strip()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select master workbook",
            current_path,
            "Excel workbooks (*.xlsx *.xlsm *.xls)",
        )
        if path:
            self.workbook_path_input.setText(path)

    def save_settings(self):
        workbook_path = self.workbook_path_input.text().strip()
        self._settings.setValue("workbook_path", workbook_path)

        theme = self.theme_combo.currentText()
        self._settings.setValue("theme", theme)
        self._settings.setValue(
            "large_text", self.large_text_checkbox.isChecked()
        )
        self._settings.setValue(
            "reduce_motion", self.reduce_motion_checkbox.isChecked()
        )

        token_changed = False
        try:
            entered_token = self.sync_token_input.text().strip()
            if self._clear_token_requested:
                clear_sheet_sync_token()
                token_changed = True
            elif entered_token:
                save_sheet_sync_token(entered_token)
                token_changed = True
        except (RuntimeError, ValueError) as error:
            dlg = MessageBox("Token not saved", str(error), self)
            dlg.cancelButton.hide()
            dlg.exec()
            return

        self._clear_token_requested = False
        self.sync_token_input.clear()
        has_token = bool(get_sheet_sync_token())
        self._set_sync_token_status(has_token)
        self.theme_changed.emit(theme)
        self.preferences_changed.emit()
        if token_changed:
            self.sync_token_changed.emit(has_token)

        dlg = MessageBox("Settings saved", "Your settings have been saved.", self)
        dlg.cancelButton.hide()
        dlg.exec()

    def _toggle_sync_token_visibility(self, visible: bool) -> None:
        self.sync_token_input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible
            else QLineEdit.EchoMode.Password
        )
        self.show_sync_token_button.setText("Hide" if visible else "Show")

    def _mark_sync_token_for_removal(self) -> None:
        self._clear_token_requested = True
        self.sync_token_input.clear()
        self.sync_token_badge.set_state("warning", "Remove when saved")

    def _set_sync_token_status(self, configured: bool) -> None:
        self.sync_token_badge.set_state(
            "success" if configured else "warning",
            "Configured" if configured else "Not configured",
        )
        self.clear_sync_token_button.setEnabled(configured)
