"""Application settings screen."""

from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setAccessibleName("Application settings")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 2, 8, 20)
        layout.setSpacing(12)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        intro = BodyLabel(
            "Settings are saved on this computer and apply to every office operator."
        )
        intro.setObjectName("Caption")
        layout.addWidget(intro)

        connection_card = CardWidget()
        connection_card.setObjectName("SettingsCard")
        connection_layout = QHBoxLayout(connection_card)
        connection_layout.setContentsMargins(16, 14, 16, 14)
        connection_layout.setSpacing(18)
        connection_copy = QVBoxLayout()
        connection_copy.setSpacing(5)
        connection_title = StrongBodyLabel("Office database")
        connection_copy.addWidget(connection_title)
        connection_description = CaptionLabel(
            "Manage the Supabase connection stored on this computer. "
            "A restart is required after changing it."
        )
        connection_description.setWordWrap(True)
        connection_copy.addWidget(connection_description)
        connection_layout.addLayout(connection_copy, 1)
        self.connection_button = PushButton("Edit connection")
        set_content_hugging_button(self.connection_button)
        self.connection_button.setAccessibleName("Edit Supabase connection")
        self.connection_button.clicked.connect(
            self.connection_settings_requested.emit
        )
        connection_layout.addWidget(
            self.connection_button,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(connection_card)

        sync_card = CardWidget()
        sync_card.setObjectName("SyncSettingsCard")
        sync_layout = QVBoxLayout(sync_card)
        sync_layout.setContentsMargins(16, 14, 16, 16)
        sync_layout.setSpacing(9)

        sync_header = QHBoxLayout()
        sync_title = StrongBodyLabel("Google Sheets synchronization")
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
            "Store the private token used by the Sync now action. Windows "
            "encrypts it for this user; it is never displayed again."
        )
        sync_description.setWordWrap(True)
        sync_layout.addWidget(sync_description)

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
        layout.addWidget(sync_card)

        workbook_card = CardWidget()
        workbook_card.setObjectName("SettingsCard")
        workbook_layout = QVBoxLayout(workbook_card)
        workbook_layout.setContentsMargins(16, 14, 16, 16)
        workbook_layout.setSpacing(10)
        workbook_title = StrongBodyLabel("Master workbook")
        workbook_layout.addWidget(workbook_title)
        workbook_description = CaptionLabel(
            "Choose the local workbook used by the Workbook screen."
        )
        workbook_layout.addWidget(workbook_description)

        workbook_row = QHBoxLayout()
        workbook_row.setSpacing(8)
        self.workbook_path_input = LineEdit()
        self.workbook_path_input.setPlaceholderText(
            r"e.g., C:\Users\YourUser\Documents\SSM_Masterlist.xlsx"
        )
        self.pick_workbook_button = PushButton("Browse")
        set_content_hugging_button(self.pick_workbook_button)
        self.pick_workbook_button.clicked.connect(self.pick_workbook)
        workbook_row.addWidget(self.workbook_path_input, 1)
        workbook_row.addWidget(self.pick_workbook_button)
        workbook_layout.addLayout(workbook_row)
        layout.addWidget(workbook_card)

        appearance_card = CardWidget()
        appearance_card.setObjectName("SettingsCard")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(16, 14, 16, 16)
        appearance_layout.setSpacing(10)
        appearance_title = StrongBodyLabel("Appearance")
        appearance_layout.addWidget(appearance_title)
        appearance_description = CaptionLabel(
            "Choose the color scheme that is most comfortable for your workspace."
        )
        appearance_layout.addWidget(appearance_description)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)
        theme_label = BodyLabel("Color scheme")
        theme_label.setMinimumWidth(140)
        self.theme_combo = ComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setAccessibleName("Application color scheme")
        self.theme_combo.setMaximumWidth(360)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        appearance_layout.addLayout(theme_row)

        self.large_text_checkbox = CheckBox("Use larger interface text")
        self.large_text_checkbox.setAccessibleDescription(
            "Increases key labels, controls, and dashboard values."
        )
        self.reduce_motion_checkbox = CheckBox(
            "Reduce interface motion"
        )
        self.reduce_motion_checkbox.setAccessibleDescription(
            "Disables page fade animations and continuous decorative motion."
        )
        appearance_layout.addWidget(self.large_text_checkbox)
        appearance_layout.addWidget(self.reduce_motion_checkbox)
        layout.addWidget(appearance_card)

        actions = QHBoxLayout()
        actions.addStretch()
        self.save_button = PrimaryPushButton("Save changes")
        set_content_hugging_button(self.save_button)
        self.save_button.setAccessibleName("Save application settings")
        self.save_button.clicked.connect(self.save_settings)
        actions.addWidget(self.save_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(actions)
        layout.addStretch()

        self.load_settings()
        self._clear_token_requested = False

    def load_settings(self):
        workbook_path = self._settings.value("workbook_path", "", type=str)
        self.workbook_path_input.setText(workbook_path)

        theme = self._settings.value("theme", "Light", type=str)
        self.theme_combo.setCurrentText(theme if theme in THEMES else "Light")
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
