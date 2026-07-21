"""QFluentWidgets adapter with PyQt fallbacks."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

from PyQt6.QtWidgets import (
    QLabel,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QToolButton,
)

from .components import Card

HAS_FLUENT = False
FluentIcon = None
NavigationInterface = None
NavigationItemPosition = None
Theme = None
setTheme = None
setThemeColor = None

try:
    with redirect_stdout(StringIO()):
        from qfluentwidgets import (  # type: ignore
            BodyLabel,
            CardWidget,
            CaptionLabel,
            CheckBox,
            ComboBox,
            FluentIcon,
            InfoBar,
            InfoBarPosition,
            LineEdit,
            ListWidget,
            MessageBox,
            NavigationInterface,
            NavigationItemPosition,
            PrimaryPushButton,
            ProgressBar,
            PushButton,
            StrongBodyLabel,
            SubtitleLabel,
            TableWidget as _FluentTableWidget,
            TextEdit,
            Theme,
            TitleLabel,
            setTheme,
            setThemeColor,
        )
    if not any(base.__module__.startswith("PyQt6.") for base in NavigationInterface.mro()):
        raise ImportError("qfluentwidgets is not using PyQt6")

    class TableWidget(_FluentTableWidget):
        def __init__(self, rows=0, columns=0, parent=None):
            if not isinstance(rows, int):
                parent = rows
                rows = 0
                columns = 0
            super().__init__(parent)
            if rows:
                self.setRowCount(rows)
            if columns:
                self.setColumnCount(columns)

    HAS_FLUENT = True
except ImportError:
    BodyLabel = QLabel
    CaptionLabel = QLabel
    CardWidget = Card
    CheckBox = QCheckBox
    ComboBox = QComboBox
    InfoBar = None
    InfoBarPosition = None
    LineEdit = QLineEdit
    ListWidget = QListWidget
    PrimaryPushButton = QPushButton
    ProgressBar = QProgressBar
    PushButton = QPushButton
    StrongBodyLabel = QLabel
    SubtitleLabel = QLabel
    TableWidget = QTableWidget
    TextEdit = QTextEdit
    TitleLabel = QLabel

    class MessageBox(QMessageBox):
        def __init__(self, title, content, parent=None):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setText(content)
            self.addButton(QMessageBox.StandardButton.Ok)
            self.cancelButton = self.addButton(QMessageBox.StandardButton.Cancel)


ToolButton = QToolButton


def set_fluent_theme(theme_name: str) -> None:
    """Keep QFluentWidgets in sync with the app token theme when available."""
    if not HAS_FLUENT or setTheme is None or Theme is None:
        return
    setTheme(Theme.DARK if theme_name == "Dark" else Theme.LIGHT)
    if setThemeColor is not None:
        from .theme import theme_color

        setThemeColor(theme_color("primary"))
