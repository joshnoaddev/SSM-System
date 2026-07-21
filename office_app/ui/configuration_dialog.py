"""Friendly first-run Supabase configuration for packaged desktop builds."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from office_app.app_config import (
    get_supabase_config,
    save_supabase_config,
    validate_desktop_supabase_config,
)
from office_app.ui.components import set_content_hugging_button
from office_app.ui.fluent import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TitleLabel,
    set_fluent_theme,
)


def is_connection_configuration_error(reason: str) -> bool:
    """Return whether a connection failure points to saved project settings."""
    text = str(reason or "").lower()
    markers = (
        "invalid api key",
        "invalid jwt",
        "jwt expired",
        "no api key",
        "api key",
        "unauthorized",
        "status code: 401",
        "'code': 401",
        '"code": 401',
    )
    return any(marker in text for marker in markers)


def friendly_connection_error(reason: str) -> str:
    """Translate transport and PostgREST failures into an actionable sentence."""
    text = str(reason or "").strip()
    lowered = text.lower()
    if is_connection_configuration_error(text):
        return (
            "The saved publishable key does not match this Supabase project. "
            "Paste the current publishable or anon key."
        )
    if any(
        marker in lowered
        for marker in (
            "permission denied",
            "row-level security",
            "42501",
            "not authorized",
        )
    ):
        return (
            "The project was reached, but office access is not ready. Run the "
            "latest database setup SQL in Supabase."
        )
    if any(
        marker in lowered
        for marker in (
            "name or service not known",
            "failed to resolve",
            "getaddrinfo failed",
            "connection refused",
            "timed out",
            "timeout",
            "network",
        )
    ):
        return (
            "The database could not be reached. Check this computer's internet "
            "connection and try again."
        )
    return (
        "The database could not be reached. Check the project details or try "
        "again when the connection is available."
    )


class ConfigurationDialog(QDialog):
    """Collect safe public project settings instead of requiring environment setup."""

    def __init__(self, reason: str = "", parent=None):
        super().__init__(parent)
        set_fluent_theme("Light")

        self.setWindowTitle("Connect SSM Student Profiling")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMaximumWidth(640)
        self.setObjectName("ConfigurationDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        banner = QFrame()
        banner.setObjectName("SetupBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(32, 24, 32, 24)
        banner_layout.setSpacing(16)

        mark = QLabel("SSM")
        mark.setObjectName("SetupMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(56, 56)
        banner_layout.addWidget(mark)

        banner_copy = QVBoxLayout()
        banner_copy.setSpacing(3)
        banner_title = TitleLabel("Connect this computer")
        banner_title.setObjectName("SetupBannerTitle")
        banner_subtitle = BodyLabel(
            "One-time setup for the SSM Student Profiling database"
        )
        banner_subtitle.setObjectName("SetupBannerSubtitle")
        banner_copy.addWidget(banner_title)
        banner_copy.addWidget(banner_subtitle)
        banner_layout.addLayout(banner_copy, 1)
        root.addWidget(banner)

        content_frame = QFrame()
        content_frame.setObjectName("SetupContent")
        content = QVBoxLayout(content_frame)
        content.setContentsMargins(32, 26, 32, 28)
        content.setSpacing(10)
        root.addWidget(content_frame)

        intro = BodyLabel(
            "Enter the public project details from Supabase. They will be saved "
            "for your Windows account so you only need to do this once."
        )
        intro.setWordWrap(True)
        content.addWidget(intro)
        content.addSpacing(6)

        content.addWidget(StrongBodyLabel("Project URL"))
        self.url_input = LineEdit()
        self.url_input.setPlaceholderText("https://your-project.supabase.co")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setMinimumHeight(40)
        content.addWidget(self.url_input)

        url_hint = CaptionLabel("Supabase Dashboard → Project Settings → Data API")
        url_hint.setObjectName("SetupHint")
        content.addWidget(url_hint)
        content.addSpacing(4)

        content.addWidget(StrongBodyLabel("Publishable key"))
        self.key_input = LineEdit()
        self.key_input.setPlaceholderText("Paste the publishable or anon key")
        self.key_input.setEchoMode(LineEdit.EchoMode.Password)
        self.key_input.setClearButtonEnabled(True)
        self.key_input.setMinimumHeight(40)
        self.key_input.returnPressed.connect(self.save_and_continue)
        content.addWidget(self.key_input)

        key_location = CaptionLabel(
            "Supabase Dashboard → Settings → API Keys → Publishable key"
        )
        key_location.setObjectName("SetupHint")
        content.addWidget(key_location)

        key_row = QHBoxLayout()
        key_hint = CaptionLabel(
            "A legacy anon key also works. Never use a secret/service-role key."
        )
        key_hint.setObjectName("SetupHint")
        self.show_key = CheckBox("Show key")
        self.show_key.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(key_hint, 1)
        key_row.addWidget(self.show_key)
        content.addLayout(key_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("SetupStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(38)
        content.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()
        cancel_button = PushButton("Cancel")
        cancel_button.setObjectName("SetupCancel")
        set_content_hugging_button(cancel_button)
        cancel_button.clicked.connect(self.reject)
        self.connect_button = PrimaryPushButton("Save and continue")
        self.connect_button.setObjectName("SetupPrimary")
        set_content_hugging_button(self.connect_button)
        self.connect_button.clicked.connect(self.save_and_continue)
        actions.addWidget(cancel_button)
        actions.addWidget(self.connect_button)
        content.addLayout(actions)

        self.setStyleSheet(
            """
            QDialog#ConfigurationDialog {
                background: #FBFCFA;
            }
            QFrame#SetupContent {
                background: #FBFCFA;
            }
            QFrame#SetupContent QLabel,
            QFrame#SetupContent QCheckBox {
                color: #24352E;
                background: transparent;
            }
            QFrame#SetupContent QLineEdit {
                color: #24352E;
                background: #FFFFFF;
                border: 1px solid #CBD5CF;
                border-radius: 8px;
                padding: 0 12px;
                selection-background-color: #176B4B;
                selection-color: #FFFFFF;
            }
            QFrame#SetupContent QLineEdit:focus {
                border: 2px solid #176B4B;
            }
            QFrame#SetupBanner {
                background: #176B4B;
            }
            QLabel#SetupMark {
                color: #176B4B;
                background: #F5C451;
                border-radius: 16px;
                font-size: 15px;
                font-weight: 800;
            }
            QLabel#SetupBannerTitle {
                color: white;
                background: transparent;
            }
            QLabel#SetupBannerSubtitle {
                color: rgba(255, 255, 255, 190);
                background: transparent;
            }
            QFrame#SetupContent QLabel#SetupHint {
                color: #65736C;
            }
            QFrame#SetupContent QLabel#SetupStatus {
                color: #B42318;
                background: transparent;
                padding-top: 4px;
            }
            QFrame#SetupContent QPushButton#SetupCancel {
                color: #24352E;
                background: #FFFFFF;
                border: 1px solid #CBD5CF;
                border-radius: 8px;
                padding: 0 12px;
            }
            QFrame#SetupContent QPushButton#SetupCancel:hover {
                background: #F2F5F3;
                border-color: #AEBBB4;
            }
            QFrame#SetupContent QPushButton#SetupPrimary {
                color: #FFFFFF;
                background: #176B4B;
                border: none;
                border-radius: 8px;
                padding: 0 12px;
                font-weight: 600;
            }
            QFrame#SetupContent QPushButton#SetupPrimary:hover {
                background: #125A3F;
            }
            QFrame#SetupContent QPushButton#SetupPrimary:pressed {
                background: #0F4B35;
            }
            """
        )

        saved_url, saved_key = get_supabase_config()
        self.url_input.setText(saved_url)
        if saved_key and not saved_key.startswith(("sb_secret_", "service_role")):
            self.key_input.setText(saved_key)
        if reason:
            self.status_label.setText(self._friendly_reason(reason))
        self.key_input.setFocus(Qt.FocusReason.OtherFocusReason)

    @staticmethod
    def _friendly_reason(reason: str) -> str:
        text = str(reason or "").strip()
        if not text:
            return ""
        if (
            "publishable or anon key" in text.lower()
            and "invalid api key" not in text.lower()
        ):
            return text
        return friendly_connection_error(text)

    def _toggle_key_visibility(self, checked: bool) -> None:
        mode = LineEdit.EchoMode.Normal if checked else LineEdit.EchoMode.Password
        self.key_input.setEchoMode(mode)

    def save_and_continue(self) -> None:
        url = self.url_input.text().strip()
        key = self.key_input.text().strip()
        try:
            validate_desktop_supabase_config(url, key)
            save_supabase_config(url, key)
        except (OSError, ValueError) as error:
            self.status_label.setText(str(error))
            if not url:
                self.url_input.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.key_input.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        self.status_label.setText("")
        self.accept()
