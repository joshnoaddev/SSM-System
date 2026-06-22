import sys
import subprocess


def ensure_packages():
    # Skip entirely when running as a compiled exe (PyInstaller) — there's no
    # pip available inside a frozen build, and sys.executable points at the
    # exe itself rather than a real Python interpreter.
    if getattr(sys, "frozen", False):
        return
    required = ["openpyxl", "pandas", "supabase"]
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            print(f"Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_packages()

import os
import logging
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QTextEdit,
    QLabel, QPushButton, QStackedWidget, QFormLayout, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QComboBox, QStatusBar, QDialog, QTabWidget,
    QProgressBar, QFrame, QGridLayout, QScrollBar, QDateEdit,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QStyle
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QRectF, QSettings, QSize, QDate,
    QPropertyAnimation, QEasingCurve, QThreadPool, pyqtProperty, QPointF
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QIcon, QImage, QLinearGradient,
    QRadialGradient, QPainterPath
)
from supabase import Client
from office_app.app_config import KEEPALIVE_INTERVAL_MS, LOGO_ASSET, USERS
from office_app.services.supabase_client import get_supabase
from office_app.utils.paths import resource_path
from office_app.utils.background_tasks import BackgroundTask
from office_app.repositories.coordinator_repository import CoordinatorRepository
from office_app.repositories.student_repository import StudentRepository
from office_app.repositories.workbook_repository import WorkbookRepository
from office_app.services.expense_service import ExpenseService
from office_app.services.dashboard_service import DashboardService
from office_app.services.masterlist_service import MasterListService
from office_app.services.photo_service import PhotoService
from office_app.services.student_service import StudentService
from office_app.services.student_excel_service import StudentExcelService
from office_app.services.student_list_service import StudentListService
from office_app.services.workbook_import_service import WorkbookImportService
from office_app.ui import (
    ActionButton, Card, DESIGN_TOKENS, EmptyState, Spacing, StatusBadge,
    theme_color,
)
from office_app.ui.views import StudentListView


def render_qss(template: str) -> str:
    """Expand @token references because Qt QSS does not support variables."""
    dropdown_icon = resource_path(
        os.path.join("assets", "icons", "chevron-down.svg")
    ).replace("\\", "/")
    template = template.replace("@dropdown_icon", dropdown_icon)
    # Replace longer names first so @primary does not partially consume
    # @primary_hover, @primary_pressed, and similar prefixed tokens.
    for name in sorted(DESIGN_TOKENS, key=len, reverse=True):
        value = DESIGN_TOKENS[name]
        template = template.replace(f"@{name}", value)
    return template





def trim_transparent_pixmap(pixmap, alpha_threshold=8):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    left, top = image.width(), image.height()
    right, bottom = -1, -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > alpha_threshold:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    if right < left or bottom < top:
        return pixmap
    return pixmap.copy(left, top, right - left + 1, bottom - top + 1)


def set_logo_pixmap(label, width, height, fallback_text="\u271d"):
    pix = QPixmap(resource_path(LOGO_ASSET))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(width, height)
    if pix.isNull():
        label.setText(fallback_text)
        label.setObjectName("BrandLogoFallback")
        return
    pix = trim_transparent_pixmap(pix)
    label.setPixmap(pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    label.setObjectName("BrandLogo")


# ── SIGNALS (used to safely call UI from background threads) ──────────────────
class WorkerSignals(QObject):
    connected = pyqtSignal()
    failed    = pyqtSignal(str)


class AnimatedSplashPanel(QWidget):
    """Paint a softly moving brand gradient behind the splash content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._background_animation = QPropertyAnimation(self, b"phase", self)
        self._background_animation.setDuration(12000)
        self._background_animation.setKeyValueAt(0.0, 0.0)
        self._background_animation.setKeyValueAt(0.5, 1.0)
        self._background_animation.setKeyValueAt(1.0, 0.0)
        self._background_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._background_animation.setLoopCount(-1)
        self._background_animation.start()

    def get_phase(self):
        return self._phase

    def set_phase(self, value):
        self._phase = float(value)
        self.update()

    phase = pyqtProperty(float, get_phase, set_phase)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 24, 24)
        painter.setClipPath(clip)

        width = max(1, self.width())
        height = max(1, self.height())
        drift = (self._phase - 0.5) * width * 0.16
        gradient = QLinearGradient(
            QPointF(drift, 0), QPointF(width + drift, height)
        )
        gradient.setColorAt(0.0, theme_color("splash_start"))
        gradient.setColorAt(0.52, theme_color("primary"))
        gradient.setColorAt(1.0, theme_color("splash_end"))
        painter.fillPath(clip, gradient)

        bloom_x = width * (0.32 + 0.36 * self._phase)
        bloom = QRadialGradient(QPointF(bloom_x, height * 0.16), width * 0.58)
        bloom.setColorAt(0.0, theme_color("on_brand", 22))
        bloom.setColorAt(0.48, theme_color("on_brand", 8))
        bloom.setColorAt(1.0, theme_color("on_brand", 0))
        painter.fillPath(clip, bloom)

        painter.setClipping(False)
        painter.setPen(QPen(theme_color("on_brand", 54), 1))
        painter.drawRoundedRect(bounds, 24, 24)


# ── STARTUP SPLASH ────────────────────────────────────────────────────────────

class StartupDialog(QDialog):
    """Two-phase splash: (1) user selection, (2) connection progress."""

    _SPLASH_SS = """
        QDialog {
            background: transparent;
        }
        QDialog QWidget#SplashPanel {
            background: transparent;
            border: none;
            border-radius: 24px;
        }
        QDialog QWidget#SplashPage { background: transparent; }
        QDialog QLabel { color: white; background: transparent; }
        QDialog QStackedWidget { background: transparent; }
        QDialog QLabel#SplashOrg {
            color: rgba(255,255,255,0.76);
            font-size: 11px;
            font-weight: 600;
        }
        QDialog QLabel#SplashTitle {
            color: white;
            font-size: 24px;
            font-weight: 800;
        }
        QDialog QLabel#SplashPrompt {
            color: rgba(255,255,255,0.88);
            font-size: 13px;
            font-weight: 600;
        }
        QDialog QLabel#SplashVersion {
            color: rgba(255,255,255,0.58);
            font-size: 10px;
        }
        QDialog QLabel#SplashWelcome {
            color: white;
            font-size: 26px;
            font-weight: 800;
        }
        QDialog QLabel#SplashStatus {
            color: rgba(255,255,255,0.88);
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        QDialog QProgressBar {
            border: none;
            border-radius: 4px;
            background: rgba(255,255,255,0.22);
            max-height: 6px;
        }
        QDialog QProgressBar::chunk { background: white; border-radius: 4px; }

        QDialog QPushButton#UserBtn {
            background: rgba(255,255,255,0.12);
            color: white;
            border: 1.5px solid rgba(255,255,255,0.40);
            border-radius: 16px;
            padding: 12px 8px;
            font-size: 13px;
            font-weight: 700;
        }
        QDialog QPushButton#UserBtn:hover {
            background: rgba(255,255,255,0.22);
            border: 1.5px solid rgba(255,255,255,0.76);
            color: white;
        }
        QDialog QPushButton#UserBtn:checked {
            background: white;
            color: @primary_pressed;
            border: 2px solid white;
            font-weight: 800;
        }
        QDialog QPushButton#UserBtn:pressed {
            background: @primary_selected;
            color: @primary_pressed;
            border: 2px solid white;
        }

        QDialog QPushButton#ContinueBtn {
            background: white;
            color: @primary_pressed;
            border: none;
            border-radius: 22px;
            padding: 0px;
            font-size: 14px;
            font-weight: 800;
        }
        QDialog QPushButton#ContinueBtn:hover { background: @primary_soft; color: @primary_pressed; }
        QDialog QPushButton#ContinueBtn:pressed { background: @primary_selected; }

        QDialog QPushButton#RetryBtn {
            background: white; color: @primary_pressed; border: none;
            border-radius: 20px; padding: 8px 24px;
            font-weight: 700; font-size: 13px;
        }
        QDialog QPushButton#RetryBtn:hover { background: @primary_selected; }
        QDialog QPushButton#OfflineBtn {
            background: rgba(255,255,255,0.12); color: white;
            border: 1.5px solid rgba(255,255,255,0.35);
            border-radius: 20px; padding: 8px 24px;
            font-weight: 700; font-size: 13px;
        }
        QDialog QPushButton#OfflineBtn:hover { background: rgba(255,255,255,0.22); }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YWAM Balut SSM")
        logo_path = resource_path(LOGO_ASSET)
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.setFixedSize(560, 460)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Apply stylesheet AFTER setting flags; prepend * reset to override app-level QPushButton
        ss = "* { font-family: 'Segoe UI', Arial, sans-serif; }\n" + render_qss(self._SPLASH_SS)
        self.setStyleSheet(ss)

        self.success = False
        self.error_msg = ""
        self.selected_user = USERS[0]
        self._welcome_anim = None
        self._progress_anim = None
        self._dot_timer = None
        self._dot_count = 0
        self._pending_sb = None

        self._signals = WorkerSignals()
        self._signals.connected.connect(self._on_connected)
        self._signals.failed.connect(self._on_failed)

        # ── Root stacked layout (page 0 = user select, page 1 = connecting) ──
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        panel = AnimatedSplashPanel()
        panel.setObjectName("SplashPanel")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(34)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(theme_color("primary_pressed", 95))
        panel.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        panel_layout.addWidget(self._stack)
        root.addWidget(panel)

        self._stack.addWidget(self._build_user_page())
        self._stack.addWidget(self._build_connect_page())
        self._stack.setCurrentIndex(0)
        self.setWindowOpacity(0.0)
        QTimer.singleShot(80, self._start_splash_entrance)

    # ── Page 1: User Selection ─────────────────────────────────────────────────
    def _build_user_page(self):
        page = QWidget()
        page.setObjectName("SplashPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 36, 48, 32)
        lay.setSpacing(0)

        logo_lbl = QLabel()
        set_logo_pixmap(logo_lbl, 120, 84)
        logo_effect = QGraphicsOpacityEffect(logo_lbl)
        logo_lbl.setGraphicsEffect(logo_effect)
        self._logo_breathe = QPropertyAnimation(logo_effect, b"opacity", self)
        self._logo_breathe.setDuration(4000)
        self._logo_breathe.setKeyValueAt(0.0, 0.94)
        self._logo_breathe.setKeyValueAt(0.5, 1.0)
        self._logo_breathe.setKeyValueAt(1.0, 0.94)
        self._logo_breathe.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._logo_breathe.setLoopCount(-1)
        self._logo_breathe.start()
        lay.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(12)

        org = QLabel("YWAM BALUT")
        self._user_org = org
        org.setObjectName("SplashOrg")
        org.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(org)
        lay.addSpacing(8)

        title = QLabel("Student Profiling System")
        self._user_title = title
        title.setObjectName("SplashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        lay.addSpacing(32)

        who = QLabel("Choose your profile to continue")
        self._user_prompt = who
        who.setObjectName("SplashPrompt")
        who.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(who)
        lay.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setContentsMargins(0, 0, 0, 0)
        self._user_btns = []
        for name in USERS:
            btn = QPushButton(name)
            btn.setObjectName("UserBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(54)
            btn.setMaximumHeight(60)
            btn.clicked.connect(lambda checked, n=name: self._select_user(n))
            btn_row.addWidget(btn)
            self._user_btns.append(btn)
        self._user_btns[0].setChecked(True)
        lay.addLayout(btn_row)

        lay.addSpacing(24)

        continue_btn = QPushButton("Continue  →")
        self._continue_btn = continue_btn
        continue_btn.setObjectName("ContinueBtn")
        continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        continue_btn.setFixedHeight(48)
        continue_btn.setMinimumWidth(224)
        continue_btn.setMaximumWidth(224)
        continue_btn.clicked.connect(self._on_continue)
        lay.addWidget(continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        lay.addStretch()

        ver = QLabel("SSM v1.0 - YWAM Balut")
        self._user_version = ver
        ver.setObjectName("SplashVersion")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        return page

    def _start_splash_entrance(self):
        """Start compositor-safe splash motion without child paint effects."""
        self._window_entrance = QPropertyAnimation(self, b"windowOpacity", self)
        self._window_entrance.setDuration(520)
        self._window_entrance.setStartValue(0.0)
        self._window_entrance.setEndValue(1.0)
        self._window_entrance.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._window_entrance.start()

    def _select_user(self, name):
        self.selected_user = name
        for btn in self._user_btns:
            btn.setChecked(btn.text() == name)

    def _on_continue(self):
        self._stack.setCurrentIndex(1)
        if self._pending_sb is not None:
            self.start_ping(self._pending_sb)

    def queue_ping(self, sb: Client):
        """Call this before exec() so the ping fires after the user clicks Continue."""
        self._pending_sb = sb

    # ── Page 2: Connecting ─────────────────────────────────────────────────────
    def _build_connect_page(self):
        page = QWidget()
        page.setObjectName("SplashPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(48, 40, 48, 32)
        lay.setSpacing(0)

        logo_lbl = QLabel()
        set_logo_pixmap(logo_lbl, 118, 82)
        lay.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(8)

        org = QLabel("YWAM BALUT")
        org.setObjectName("SplashOrg")
        org.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(org)
        lay.addSpacing(4)

        title = QLabel("Student Profiling System")
        title.setObjectName("SplashTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        lay.addSpacing(28)

        # Welcome label (fades in on success)
        self.welcome_label = QLabel(f"Welcome, {self.selected_user}!")
        self.welcome_label.setObjectName("SplashWelcome")
        self.welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_label.setFixedHeight(42)
        self.welcome_effect = QGraphicsOpacityEffect(self.welcome_label)
        self.welcome_effect.setOpacity(0.0)
        self.welcome_label.setGraphicsEffect(self.welcome_effect)
        self.welcome_label.setVisible(False)
        lay.addWidget(self.welcome_label)

        self.status_label = QLabel("Connecting to database")
        self.status_label.setObjectName("SplashStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status_label)

        lay.addSpacing(14)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)

        lay.addStretch()

        ver = QLabel("SSM v1.0 - YWAM Balut")
        ver.setObjectName("SplashVersion")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver)

        return page
    # ── Connection logic ───────────────────────────────────────────────────────
    def start_ping(self, sb: Client):
        # Update welcome text now that we know the user
        self.welcome_label.setText(f"Welcome, {self.selected_user}!")
        self._start_dot_anim()

        task = BackgroundTask(lambda: StudentRepository(client=sb).ping())
        task.signals.succeeded.connect(lambda _rows: self._signals.connected.emit())
        task.signals.failed.connect(
            lambda error: self._signals.failed.emit(error.strip().splitlines()[-1])
        )
        QThreadPool.globalInstance().start(task)

    def _start_dot_anim(self):
        self._dot_count = 0
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(420)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._dot_timer.start()

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        self.status_label.setText("Connecting to database" + "." * self._dot_count)

    def _on_connected(self):
        if self._dot_timer:
            self._dot_timer.stop()
        self.success = True
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("Connected - opening workspace...")
        self.welcome_label.setVisible(True)

        self._welcome_anim = QPropertyAnimation(self.welcome_effect, b"opacity", self)
        self._welcome_anim.setDuration(600)
        self._welcome_anim.setStartValue(0.0)
        self._welcome_anim.setEndValue(1.0)
        self._welcome_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setDuration(850)
        self._progress_anim.setStartValue(0)
        self._progress_anim.setEndValue(100)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._welcome_anim.start()
        self._progress_anim.start()
        QTimer.singleShot(1350, self.accept)

    def _on_failed(self, msg):
        if self._dot_timer:
            self._dot_timer.stop()
        self.error_msg = msg
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status_label.setText("Could not reach database")
        connect_page = self._stack.widget(1)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        retry_btn   = QPushButton("Retry")
        offline_btn = QPushButton("Continue Offline")
        retry_btn.setObjectName("RetryBtn")
        offline_btn.setObjectName("OfflineBtn")
        retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        offline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Insert above the version label (last widget)
        connect_page.layout().insertLayout(connect_page.layout().count() - 1, btn_row)
        btn_row.addWidget(retry_btn)
        btn_row.addWidget(offline_btn)
        retry_btn.clicked.connect(lambda: QMessageBox.information(self, "Retry", "Please restart the application to retry."))
        offline_btn.clicked.connect(self.reject)

# ── MAIN APP ──────────────────────────────────────────────────────────────────
class CircularProgress(QWidget):
    def __init__(self, parent=None, size=96):
        super().__init__(parent)
        self.value = 0
        self.setFixedSize(size, size)

    def set_value(self, val):
        self.value = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen_width = max(4, int(self.width() * 0.07))
        margin = pen_width + 2
        rect = QRectF(margin, margin, self.width() - (margin * 2), self.height() - (margin * 2))
        
        # Draw background track
        pen_bg = QPen(theme_color("border_subtle"), pen_width)
        painter.setPen(pen_bg)
        painter.drawArc(rect, 0, 360 * 16)
        
        # Determine color based on completion
        if self.value == 100: color = DESIGN_TOKENS["success"]
        elif self.value >= 75: color = DESIGN_TOKENS["primary"]
        elif self.value >= 50: color = DESIGN_TOKENS["warning"]
        else: color = DESIGN_TOKENS["danger"]
        
        # Draw progress arc
        pen_fg = QPen(QColor(color), pen_width)
        pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_fg)
        span_angle = int((self.value / 100) * 360 * 16)
        painter.drawArc(rect, 90 * 16, -span_angle) # Start at top (90 degrees)
        
        # Draw percentage text
        painter.setPen(theme_color("text_primary"))
        font = painter.font()
        font.setPixelSize(max(8, int(self.width() * 0.19)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.value}%")

class StudentApp(QMainWindow):
    def __init__(self, sb: Client, initial_user: str = "Joshua"):
        super().__init__()
        self.sb = sb
        self.student_service = StudentService()
        self.student_repository = self.student_service.repository
        self.student_excel_service = StudentExcelService(self.student_repository)
        self.student_list_service = StudentListService(self.student_service)
        self.dashboard_service = DashboardService()
        self.photo_service = PhotoService()
        self.expense_service = ExpenseService()
        self.coordinator_repository = CoordinatorRepository()
        self.workbook_repository = WorkbookRepository()
        self.workbook_import_service = WorkbookImportService(
            self.student_repository,
            self.coordinator_repository,
            self.workbook_repository,
        )
        self.masterlist_service = MasterListService(self.workbook_import_service)
        self.thread_pool = QThreadPool(self)
        self._initial_user = initial_user
        self.current_student_id = None
        self._pending_photo = None
        self._editing_id = None
        self._workbook = None
        self._workbook_path = None
        self._loaded_workbook_sheets = set()
        self._workbook_dirty = False
        self._loading_workbook_sheet = False
        self._master_ref_cache_key = None
        self._master_ref_cache = None
        self._workbook_revision = 0
        self._dashboard_request = 0

        self.setWindowTitle("SSM Student Profiling System")
        logo_path = resource_path(LOGO_ASSET)
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.resize(1100, 750)
        self.setMinimumSize(980, 680)
        
        self.apply_modern_stylesheet()

        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)

        # Main Layout: Sidebar + Main Content
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        self.create_sidebar(main_layout)

        # 2. Main Content Area
        content_widget = QWidget()
        content_widget.setObjectName("MainContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(32, 24, 32, 24)
        content_layout.setSpacing(16)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        app_title = QLabel("SSM Student Profiling System")
        app_title.setObjectName("HeaderTitle")
        app_subtitle = QLabel("YWAM Balut Student Sponsorship Ministry")
        app_subtitle.setObjectName("HeaderSubtitle")
        header_layout.addWidget(app_title)
        header_layout.addWidget(app_subtitle)
        
        content_layout.addLayout(header_layout)
        
        # Divider
        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        content_layout.addWidget(divider)

        # Stacked Widget for Screens
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        
        main_layout.addWidget(content_widget)

        # Build Screens
        self.create_dashboard_screen()  # Index 0
        self.student_list_view = StudentListView(
            self.student_repository,
            self.student_list_service,
            self.student_excel_service,
            self._run_background,
            filter_current_rows_fn=self._filter_current_master_rows,
            status_message_fn=self.status_bar.showMessage,
        )
        self.student_list_view.student_selected.connect(self._open_student_profile)
        self.student_list_view.students_changed.connect(self.refresh_dashboard)
        self.stacked_widget.addWidget(self.student_list_view)  # Index 1
        self.create_profile_screen()    # Index 2
        self.create_add_screen()        # Index 3
        self.create_expenses_screen()   # Index 4
        self.create_workbook_screen()   # Index 5
        self.create_coordinators_screen()  # Index 6
        self._apply_button_cursors()

        # Initialize Data
        self.nav_dashboard()
        self._start_keepalive()

    def _run_background(self, function, on_success=None, on_error=None):
        """Run blocking work in Qt's managed thread pool."""
        task = BackgroundTask(function)
        if on_success is not None:
            task.signals.succeeded.connect(on_success)
        if on_error is not None:
            task.signals.failed.connect(on_error)
        self.thread_pool.start(task)
        return task

    def _switch_page(self, index: int):
        if not hasattr(self, "stacked_widget") or index < 0:
            return
        if index >= self.stacked_widget.count():
            return
        if self.stacked_widget.currentIndex() == index:
            return

        self.stacked_widget.setCurrentIndex(index)
        page = self.stacked_widget.currentWidget()
        if page is None:
            return

        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(170)
        animation.setStartValue(0.88)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda page=page: page.setGraphicsEffect(None))
        self._page_transition = animation
        animation.start()
    def _apply_button_cursors(self):
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        for combo in self.findChildren(QComboBox):
            combo.setCursor(Qt.CursorShape.PointingHandCursor)

    def apply_modern_stylesheet(self):
        qss_path = resource_path(os.path.join("assets", "styles", "app.qss"))
        try:
            with open(qss_path, "r", encoding="utf-8") as file:
                self.setStyleSheet(render_qss(file.read()))
        except Exception as e:
            print(f"Stylesheet load error: {e}")

    # ── SIDEBAR NAVIGATION ────────────────────────────────────────────────────
    def create_sidebar(self, layout):
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 24)
        sidebar_layout.setSpacing(8)

        # Brand header
        brand_container = QWidget()
        brand_container.setObjectName("BrandPanel")
        brand_container.setFixedHeight(168)
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(16, 16, 16, 16)
        brand_layout.setSpacing(4)
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_lbl = QLabel()
        set_logo_pixmap(logo_lbl, 104, 78)
        
        self.brand_lbl = QLabel("Joshua")
        self.brand_lbl.setObjectName("BrandTitle")
        self.brand_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        brand_sub = QLabel("SSM Portal")
        brand_sub.setObjectName("BrandSubtitle")
        brand_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        brand_layout.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        brand_layout.addWidget(self.brand_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        brand_layout.addWidget(brand_sub, alignment=Qt.AlignmentFlag.AlignHCenter)
        
        sidebar_layout.addWidget(brand_container)
        sidebar_layout.addSpacing(16)

        self.btn_dash = QPushButton("Dashboard")
        self.btn_stud = QPushButton("Students")
        self.btn_exp  = QPushButton("Expenses")
        self.btn_coordinators = QPushButton("Coordinators")
        self.btn_add  = QPushButton("Add Student")
        self.btn_workbook = QPushButton("Workbook Tabs")

        for btn in [self.btn_dash, self.btn_stud, self.btn_exp, self.btn_coordinators, self.btn_add, self.btn_workbook]:
            btn.setProperty("class", "SidebarBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(44)
            sidebar_layout.addWidget(btn)

        self.btn_dash.clicked.connect(self.nav_dashboard)
        self.btn_stud.clicked.connect(self.nav_students)
        self.btn_add.clicked.connect(self.nav_add)
        self.btn_exp.clicked.connect(self.nav_expenses)
        self.btn_workbook.clicked.connect(self.nav_workbook)
        self.btn_coordinators.clicked.connect(self.nav_coordinators)

        sidebar_layout.addStretch()

        # User selector
        user_label = QLabel("Logged in as")
        user_label.setObjectName("SidebarCaption")
        self.user_combo = QComboBox()
        self.user_combo.addItems(USERS)
        idx = self.user_combo.findText(self._initial_user)
        if idx >= 0:
            self.user_combo.setCurrentIndex(idx)
        self.brand_lbl.setText(self._initial_user)
        self.user_combo.setObjectName("SidebarUserCombo")
        self.user_combo.currentTextChanged.connect(self._on_user_changed)
        sidebar_layout.addWidget(user_label)
        sidebar_layout.addWidget(self.user_combo)
        sidebar_layout.addSpacing(8)

        self.sidebar_refresh_btn = QPushButton("Refresh")
        self.sidebar_refresh_btn.setObjectName("SidebarRefreshBtn")
        self.sidebar_refresh_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.sidebar_refresh_btn.setIconSize(QSize(15, 15))
        self.sidebar_refresh_btn.setToolTip("Refresh data from Supabase")
        self.sidebar_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_refresh_btn.setMinimumHeight(34)
        self.sidebar_refresh_btn.setMaximumHeight(36)
        self.sidebar_refresh_btn.clicked.connect(self._sidebar_refresh)
        sidebar_layout.addWidget(self.sidebar_refresh_btn)

        layout.addWidget(self.sidebar)

    def nav_dashboard(self):
        self._set_active_nav(self.btn_dash)
        self.refresh_dashboard()
        self._switch_page(0)

    def nav_students(self):
        self._set_active_nav(self.btn_stud)
        self.student_list_view.refresh_grade_filter()
        if self.student_list_view.student_list_mode:
            self.student_list_view.load_student_list()
        else:
            self.student_list_view.show_student_view_prompt()
        self._switch_page(1)

    def _on_dashboard_student_click(self, item):
        student_id = item.data(Qt.ItemDataRole.UserRole)
        if student_id:
            self._open_student_profile(str(student_id))

    def _open_student_profile(self, student_id: str):
        self.current_student_id = student_id
        self._load_profile(student_id)
        self._switch_page(2)

    def nav_add(self):
        self._set_active_nav(self.btn_add)
        self._open_add_screen()

    def nav_expenses(self):
        if self.current_student_id:
            self._set_active_nav(self.btn_exp)
            self.open_expenses_screen()
        else:
            QMessageBox.information(self, "Select Student", "Please select a student from the Students list first to view expenses.")
            self.nav_students()

    def nav_workbook(self):
        self._set_active_nav(self.btn_workbook)
        self._switch_page(5)

    def nav_coordinators(self):
        self._set_active_nav(self.btn_coordinators)
        self._switch_page(6)
        self.load_coordinators()

    def _on_user_changed(self, name):
        self.brand_lbl.setText(name)
        hour = time.localtime().tm_hour
        greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        self.greet_lbl.setText(f"{greeting}, {name}")

    def _sidebar_refresh(self):
        button = getattr(self, "sidebar_refresh_btn", None)
        if button is not None:
            button.setEnabled(False)
            button.setText("Refreshing...")
        self.status_bar.showMessage("Refreshing...", 1200)

        idx = self.stacked_widget.currentIndex()
        task = None
        if idx == 0:
            task = self.refresh_dashboard()
        elif idx == 1:
            task = self.student_list_view.load_student_list()
        elif idx == 6:
            self.load_coordinators()

        if button is not None and task is not None:
            task.signals.finished.connect(
                lambda: (button.setEnabled(True), button.setText("Refresh"))
            )
        elif button is not None:
            QTimer.singleShot(450, lambda: (button.setEnabled(True), button.setText("Refresh")))
    def _set_active_nav(self, active_btn):
        for btn in [self.btn_dash, self.btn_stud, self.btn_exp, self.btn_coordinators, self.btn_add, self.btn_workbook]:
            btn.setChecked(btn is active_btn)

    # ── KEEPALIVE ─────────────────────────────────────────────────────────────
    def _start_keepalive(self):
        self.keepalive_timer = QTimer(self)
        self.keepalive_timer.setInterval(KEEPALIVE_INTERVAL_MS)
        self.keepalive_timer.timeout.connect(self._do_keepalive)
        self.keepalive_timer.start()
        self.status_bar.showMessage("Connected to Supabase", 5000)

    def _do_keepalive(self):
        self._run_background(
            self.student_repository.ping,
            lambda _rows: self.status_bar.showMessage("Supabase keepalive OK", 4000),
            lambda error: self.status_bar.showMessage(
                f"Keepalive error: {error.strip().splitlines()[-1]}", 8000
            ),
        )

    def _update_field(self, table: str, field: str, value, record_id):
        try:
            if table != "students":
                raise ValueError(f"Unsupported table for field update: {table}")
            self.student_repository.update_student(record_id, {field: value})
            self.status_bar.showMessage(f"{field.replace('_', ' ').capitalize()} saved", 3000)
        except Exception as e:
            self.status_bar.showMessage(f"Error saving {field} ({type(e).__name__}): {e}", 8000)

    # ── SCREEN 0: DASHBOARD ───────────────────────────────────────────────────
    def create_dashboard_screen(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(16)

        # Greeting banner
        import datetime
        hour = datetime.datetime.now().hour
        if hour < 12:   greeting = "Good morning"
        elif hour < 17: greeting = "Good afternoon"
        else:           greeting = "Good evening"

        hello_card = QWidget()
        hello_card.setObjectName("GreetingCard")
        h_layout = QVBoxLayout(hello_card)
        h_layout.setContentsMargins(24, 16, 24, 16)
        h_layout.setSpacing(4)
        self.greet_lbl = QLabel(f"{greeting}, {self._initial_user}")
        self.greet_lbl.setObjectName("OnBrandTitle")
        sub_lbl   = QLabel("Today's overview for students, sponsors, and records.")
        sub_lbl.setObjectName("OnBrandCaption")
        h_layout.addWidget(self.greet_lbl)
        h_layout.addWidget(sub_lbl)
        layout.addWidget(hello_card)

        overview_lbl = QLabel("Overview")
        overview_lbl.setObjectName("SectionTitle")
        layout.addWidget(overview_lbl)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self.lbl_total_val    = QLabel("--"); self.lbl_total_val.setObjectName("CardValue")
        self.lbl_active_val   = QLabel("--"); self.lbl_active_val.setObjectName("CardValue")
        self.lbl_inactive_val = QLabel("--"); self.lbl_inactive_val.setObjectName("CardValue")
        self.lbl_graduated_val = QLabel("--"); self.lbl_graduated_val.setObjectName("CardValue")

        cards_row.addWidget(self._build_card("Total Students", self.lbl_total_val, "primary"), 1)
        cards_row.addWidget(self._build_card("Active Students", self.lbl_active_val, "success"), 1)
        cards_row.addWidget(self._build_card("Inactive Students", self.lbl_inactive_val, "danger"), 1)
        cards_row.addWidget(self._build_card("Graduated Students", self.lbl_graduated_val, "graduated"), 1)

        layout.addLayout(cards_row)

        insights_row = QHBoxLayout()
        insights_row.setSpacing(16)
        self.dashboard_area_list = QListWidget()
        self.dashboard_sponsor_list = QListWidget()
        self.dashboard_attention_list = QListWidget()
        self.dashboard_attention_list.itemClicked.connect(self._on_dashboard_student_click)
        insights_row.addWidget(self._build_dashboard_list_card("Students by Area", self.dashboard_area_list), 1)
        insights_row.addWidget(self._build_dashboard_list_card("Sponsor Summary", self.dashboard_sponsor_list), 1)
        insights_row.addWidget(self._build_dashboard_list_card("Needs Attention", self.dashboard_attention_list), 1)
        layout.addLayout(insights_row, 1)
        self.stacked_widget.addWidget(widget)

    def _build_card(self, title_text, value_label, tone="primary"):
        card = Card(tone=tone)
        card.setFixedHeight(120)
        l = QVBoxLayout(card)
        l.setContentsMargins(24, 16, 24, 16)
        l.setSpacing(8)
        t = QLabel(title_text)
        t.setObjectName("CardTitle")
        l.addWidget(t)
        l.addWidget(value_label)
        return card

    def _build_dashboard_list_card(self, title_text, list_widget):
        card = Card()
        card.setMinimumHeight(260)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        list_widget.setFrameShape(QFrame.Shape.NoFrame)
        list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        list_widget.setMinimumHeight(210)

        layout.addWidget(title)
        layout.addWidget(list_widget, 1)
        return card

    def refresh_dashboard(self):
        """Fetch dashboard data without blocking Qt's event loop."""
        self._dashboard_request += 1
        request_id = self._dashboard_request
        for label in (self.lbl_total_val, self.lbl_active_val, self.lbl_inactive_val, self.lbl_graduated_val):
            label.setText("...")

        def fetch_rows():
            return self.student_repository.list_students(columns=(
                "id,last_name,first_name,status,sponsor,area,grade,contact,school,birthday,photo_url"
            ))

        def apply_rows(raw_rows):
            if request_id != self._dashboard_request:
                return
            rows = self._filter_current_master_rows(raw_rows)
            counts = self.dashboard_service.summary_counts(rows)
            self.lbl_total_val.setText(str(counts["total"]))
            self.lbl_active_val.setText(str(counts["active"]))
            self.lbl_inactive_val.setText(str(counts["inactive"]))
            self.lbl_graduated_val.setText(str(counts["graduated"]))
            self._refresh_dashboard_lists(rows)

        def show_error(error):
            if request_id != self._dashboard_request:
                return
            err = error.strip().splitlines()[-1][:40]
            self.lbl_total_val.setText("ERR")
            self.lbl_active_val.setText(err)
            self.lbl_inactive_val.setText("")
            self.lbl_graduated_val.setText("")
            logging.getLogger(__name__).error("Dashboard refresh failed:\n%s", error)

        return self._run_background(fetch_rows, apply_rows, show_error)
    def _filter_current_master_rows(self, rows):
        return self.masterlist_service.filter_current_rows(
            rows,
            self._current_master_student_reference(),
        )

    def _apply_current_master_status(self, row):
        return self.masterlist_service.apply_current_status(
            row,
            self._current_master_student_reference(),
        )

    def _current_master_student_keys(self):
        return self.masterlist_service.current_student_keys(
            self._current_master_student_reference(),
        )

    def _current_master_student_reference(self):
        try:
            return self.masterlist_service.current_student_reference(
                workbook=self._workbook,
                workbook_path=self._workbook_path,
                workbook_revision=self._workbook_revision,
                saved_workbook_path=self._settings().value("workbook_path", "", type=str),
                cwd=os.getcwd(),
                fallback_paths=[r"F:\SSM Masterlist.xlsx"],
            )
        except Exception as e:
            print(f"Masterlist reference error: {e}")
            return {}

    def _invalidate_master_reference_cache(self):
        self._master_ref_cache_key = None
        self._master_ref_cache = None
        self.masterlist_service.invalidate_cache()

    def _current_masterlist_path(self):
        return self.masterlist_service.current_masterlist_path(
            workbook_path=self._workbook_path,
            saved_workbook_path=self._settings().value("workbook_path", "", type=str),
            cwd=os.getcwd(),
            fallback_paths=[r"F:\SSM Masterlist.xlsx"],
        )

    def _latest_master_sheet_name_from_names(self, sheet_names):
        return self.masterlist_service.latest_master_sheet_name_from_names(sheet_names)

    def _master_sheet_student_keys(self, worksheet):
        return self.masterlist_service.master_sheet_student_keys(worksheet)

    def _master_sheet_student_reference(self, worksheet):
        return self.masterlist_service.master_sheet_student_reference(worksheet)

    def _student_reference_key(self, row):
        return self.masterlist_service.student_reference_key(row)

    def _normalize_student_key_value(self, value):
        return self.masterlist_service.normalize_student_key_value(value)
    def _status_style(self, status):
        return self.student_service.status_style(status)

    def _profile_completion_percent(self, student):
        return self.student_service.profile_completion_percent(student)

    def _dedupe_dashboard_students(self, rows):
        return self.dashboard_service.dedupe_students(rows)

    def _dashboard_student_key(self, row):
        return self.dashboard_service.student_key(row)

    def _dashboard_row_score(self, row):
        return self.dashboard_service.row_score(row)

    def _refresh_dashboard_lists(self, rows):
        dashboard = self.dashboard_service.build_lists(rows)

        self.dashboard_area_list.clear()
        for area, count in dashboard["area_counts"]:
            item = QListWidgetItem(f"{area}  -  {count}")
            item.setToolTip(f"{count} students in {area}")
            self.dashboard_area_list.addItem(item)

        self.dashboard_sponsor_list.clear()
        for sponsor, count in dashboard["sponsor_counts"]:
            item = QListWidgetItem(f"{sponsor}  -  {count}")
            item.setToolTip(f"{count} students for {sponsor}")
            self.dashboard_sponsor_list.addItem(item)

        self.dashboard_attention_list.clear()
        attention = dashboard["attention"]
        for entry in attention:
            item = QListWidgetItem(f"{entry['name']}    Missing: {entry['missing_text']}")
            item.setData(Qt.ItemDataRole.UserRole, entry["student_id"])
            item.setToolTip("Open student profile")
            self.dashboard_attention_list.addItem(item)
        if not attention:
            item = QListWidgetItem("All visible records look complete.")
            item.setData(Qt.ItemDataRole.UserRole, None)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(theme_color("text_secondary"))
            self.dashboard_attention_list.addItem(item)
    # ── SCREEN 2: PROFILE ─────────────────────────────────────────────────────
    def create_profile_screen(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("Back"); back_btn.setObjectName("SecondaryBtn")
        back_btn.clicked.connect(self.nav_students)
        self.edit_btn = QPushButton("Edit"); self.edit_btn.clicked.connect(self.open_edit_screen)
        self.deactivate_btn = QPushButton("Mark Inactive"); self.deactivate_btn.setObjectName("DangerBtn")
        self.deactivate_btn.clicked.connect(self.toggle_active_status)
        
        top_bar.addWidget(back_btn); top_bar.addStretch()
        top_bar.addWidget(self.edit_btn); top_bar.addWidget(self.deactivate_btn)
        outer.addLayout(top_bar)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = Card()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(24)

        top_row = QHBoxLayout()
        top_row.setSpacing(24)
        
        # Left side: Photo
        pcol = QVBoxLayout()
        pcol.setSpacing(8)
        pcol.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.photo_label = QLabel("No Photo")
        self.photo_label.setFixedSize(140, 170)
        self.photo_label.setObjectName("PhotoFrame")
        self.photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.change_photo_btn = QPushButton("Change Photo"); self.change_photo_btn.setObjectName("SecondaryBtn")
        self.change_photo_btn.clicked.connect(self.change_photo)
        self.change_photo_btn.setMinimumWidth(176)
        self.change_photo_btn.setMaximumWidth(200)
        self.remove_photo_btn = QPushButton("Remove Photo"); self.remove_photo_btn.setObjectName("DangerBtn")
        self.remove_photo_btn.clicked.connect(self.remove_photo)
        self.remove_photo_btn.setMinimumWidth(176)
        self.remove_photo_btn.setMaximumWidth(200)
        self.remove_photo_btn.setVisible(False)
        pcol.addWidget(self.photo_label)
        pcol.addWidget(self.change_photo_btn)
        pcol.addWidget(self.remove_photo_btn)
        top_row.addLayout(pcol)
        
        # Middle: Info (native QGridLayout)
        info_layout = QVBoxLayout()
        info_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        info_layout.setSpacing(16)
        
        # Header Row: Name & Status
        self.lbl_profile_name = QLabel("Student Name")
        self.lbl_profile_name.setObjectName("ProfileTitle")
        self.lbl_profile_name.setWordWrap(True)
        self.lbl_profile_status = QLabel("Active")
        self.lbl_profile_status.setObjectName("StatusLabel")
        self.lbl_profile_status.setMinimumHeight(28)
        self.lbl_profile_status.setTextFormat(Qt.TextFormat.RichText)
        
        info_layout.addWidget(self.lbl_profile_name)
        info_layout.addWidget(self.lbl_profile_status)

        # Data Grid Layout — one field per row, value column takes all
        # remaining width. A single column avoids two text blocks ever
        # competing for width on the same row, so this never forces a
        # horizontal scrollbar, no matter how the window is resized.
        self.profile_grid = QGridLayout()
        self.profile_grid.setHorizontalSpacing(24)
        self.profile_grid.setVerticalSpacing(16)
        self.profile_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.profile_grid.setColumnMinimumWidth(0, 110)  # Label column
        self.profile_grid.setColumnStretch(1, 1)          # Value column fills the rest

        # Dictionary to store our dynamic value labels for easy updating
        self.profile_data_labels = {}

        # Helper function to create a uniform row in the grid
        def add_grid_item(row, label_text, key):
            title_lbl = QLabel(label_text)
            title_lbl.setObjectName("FieldLabel")
            val_lbl = QLabel("--")
            val_lbl.setObjectName("FieldValue")
            val_lbl.setWordWrap(True)
            self.profile_grid.addWidget(title_lbl, row, 0, Qt.AlignmentFlag.AlignTop)
            self.profile_grid.addWidget(val_lbl, row, 1)
            self.profile_data_labels[key] = val_lbl

        # Grid Population
        add_grid_item(0, "Gender:", "gender")
        add_grid_item(1, "Grade/Level:", "grade")
        add_grid_item(2, "Area:", "area")
        add_grid_item(3, "City:", "city")
        add_grid_item(4, "Address:", "address")
        add_grid_item(5, "Birthday:", "birthday")
        add_grid_item(6, "Contact:", "contact")
        add_grid_item(7, "Sponsor:", "sponsor")
        self.profile_data_labels["sponsor"].setProperty("emphasis", True)
        
        add_grid_item(8, "School:", "school")
        add_grid_item(9, "Parents:", "parents")
        add_grid_item(10, "Course:", "course")

        info_layout.addLayout(self.profile_grid)
        top_row.addLayout(info_layout, 3)

        # Right side: Progress
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.profile_progress = CircularProgress()
        progress_lbl = QLabel("Profile\nCompletion")
        progress_lbl.setObjectName("CaptionStrong")
        progress_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.profile_progress, alignment=Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(progress_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        top_row.addLayout(progress_layout)
        
        layout.addLayout(top_row)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        # Remarks (grows to fill any leftover space instead of leaving a dead gap)
        remarks_lbl = QLabel("Remarks")
        remarks_lbl.setObjectName("CardHeading")
        layout.addWidget(remarks_lbl)
        self.remarks_edit = QTextEdit()
        self.remarks_edit.setMinimumHeight(120)
        layout.addWidget(self.remarks_edit, 1)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Remarks"); save_btn.clicked.connect(self.save_remarks)
        exp_btn  = QPushButton("View / Add Expenses")
        exp_btn.setObjectName("WarningBtn")
        exp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        exp_btn.setMinimumHeight(42); exp_btn.clicked.connect(self.nav_expenses)
        btn_row.addWidget(save_btn); btn_row.addStretch(); btn_row.addWidget(exp_btn)
        layout.addLayout(btn_row)

        scroll.setWidget(content); outer.addWidget(scroll)
        self.stacked_widget.addWidget(widget)

    # ── SCREEN 3: ADD / EDIT ──────────────────────────────────────────────────
    def create_add_screen(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)

        top_bar = QHBoxLayout()
        cancel_btn = QPushButton("Cancel"); cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.nav_students)
        self.form_title_label = QLabel("Add New Student")
        self.form_title_label.setObjectName("SectionTitle")
        top_bar.addWidget(cancel_btn); top_bar.addWidget(self.form_title_label); top_bar.addStretch()
        outer.addLayout(top_bar)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = Card()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        photo_row = QHBoxLayout()
        self.add_photo_label = QLabel("No Photo")
        self.add_photo_label.setFixedSize(100, 120)
        self.add_photo_label.setObjectName("PhotoFrame")
        self.add_photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pick_btn = QPushButton("Pick Photo"); pick_btn.setObjectName("SecondaryBtn")
        pick_btn.clicked.connect(self.pick_add_photo)
        photo_row.addWidget(self.add_photo_label); photo_row.addWidget(pick_btn); photo_row.addStretch()
        layout.addLayout(photo_row)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.inp_last    = QLineEdit()
        self.inp_first   = QLineEdit()
        self.inp_gender  = QComboBox(); self.inp_gender.addItems(["F", "M", ""])
        self.inp_grade   = QLineEdit()
        self.inp_address = QLineEdit()
        self.inp_city    = QLineEdit()
        self.inp_area    = QLineEdit()
        self.inp_bday    = QLineEdit(); self.inp_bday.setPlaceholderText("YYYY-MM-DD")
        self.inp_sponsor = QLineEdit(); self.inp_sponsor.setPlaceholderText("e.g. Schnurbein, Word of Life...")
        self.inp_contact = QLineEdit()
        self.inp_school  = QLineEdit()
        self.inp_parents = QLineEdit()
        self.inp_course  = QLineEdit()
        self.inp_remarks = QTextEdit(); self.inp_remarks.setFixedHeight(70)
        self.inp_status  = QComboBox(); self.inp_status.addItems(["Active", "Inactive/Removed", "Graduated"])

        # Cap field widths so they stay readable instead of stretching
        # edge-to-edge on wide windows.
        for fld in [self.inp_last, self.inp_first, self.inp_gender, self.inp_grade,
                    self.inp_address, self.inp_city, self.inp_area, self.inp_bday,
                    self.inp_sponsor, self.inp_contact, self.inp_school,
                    self.inp_parents, self.inp_course, self.inp_remarks, self.inp_status]:
            fld.setMaximumWidth(460)

        form.addRow("Last Name *:",          self.inp_last)
        form.addRow("First Name *:",         self.inp_first)
        form.addRow("Gender:",               self.inp_gender)
        form.addRow("Grade/Level:",          self.inp_grade)
        form.addRow("Address:",              self.inp_address)
        form.addRow("City:",                 self.inp_city)
        form.addRow("Area/Coordinator:",     self.inp_area)
        form.addRow("Birthday:",             self.inp_bday)
        form.addRow("Sponsor:",              self.inp_sponsor)
        form.addRow("Contact No.:",          self.inp_contact)
        form.addRow("School:",               self.inp_school)
        form.addRow("Parents & Occupation:", self.inp_parents)
        form.addRow("Course:",               self.inp_course)
        form.addRow("Remarks:",              self.inp_remarks)
        form.addRow("Status:",               self.inp_status)
        layout.addLayout(form)

        self.save_form_btn = QPushButton("Save Student")
        self.save_form_btn.clicked.connect(self.save_student_form)
        layout.addWidget(self.save_form_btn, alignment=Qt.AlignmentFlag.AlignRight)

        scroll.setWidget(content); outer.addWidget(scroll)
        self.stacked_widget.addWidget(widget)

    # ── SCREEN 4: EXPENSES ────────────────────────────────────────────────────
    def create_expenses_screen(self):
        widget = QWidget()
        widget.setObjectName("MainContent")
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("MainContent")
        layout = QVBoxLayout(inner)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        # Top bar
        top_bar = QHBoxLayout()
        back_btn = QPushButton("Back"); back_btn.setObjectName("SecondaryBtn")
        back_btn.clicked.connect(lambda: self._switch_page(2))
        self.expenses_title = QLabel()
        self.expenses_title.setObjectName("SectionTitle")
        top_bar.addWidget(back_btn); top_bar.addWidget(self.expenses_title); top_bar.addStretch()
        layout.addLayout(top_bar)

        # School year selector
        sy_card = Card()
        sy_layout = QHBoxLayout(sy_card)
        sy_layout.setContentsMargins(16, 16, 16, 16)
        sy_layout.setSpacing(8)
        sy_lbl = QLabel("School Year:")
        sy_lbl.setObjectName("FieldLabel")
        self.exp_school_year = QComboBox()
        import datetime
        sy_list = [f"{y}-{y+1}" for y in range(2020, 2032)]
        self.exp_school_year.addItems(["All Years"] + sy_list)
        cy = datetime.date.today().year
        cm = datetime.date.today().month
        cur_sy = f"{cy}-{cy+1}" if cm >= 6 else f"{cy-1}-{cy}"
        idx = self.exp_school_year.findText(cur_sy)
        if idx >= 0: self.exp_school_year.setCurrentIndex(idx)
        self.exp_school_year.currentTextChanged.connect(self._on_sy_changed)
        self.exp_school_year.setMinimumWidth(150)
        sy_layout.addWidget(sy_lbl)
        sy_layout.addWidget(self.exp_school_year)
        sy_layout.addStretch()
        layout.addWidget(sy_card)

        # ── Budget card ────────────────────────────────────────────────────
        budget_card = Card()
        budget_main = QVBoxLayout(budget_card)
        budget_main.setContentsMargins(16, 16, 16, 16)
        budget_main.setSpacing(8)

        budget_hdr = QHBoxLayout()
        budget_icon_lbl = QLabel("Budget Allocated")
        budget_icon_lbl.setObjectName("CardHeading")
        budget_hdr.addWidget(budget_icon_lbl)
        budget_hdr.addStretch()

        # Edit budget row
        self.budget_input = QLineEdit()
        self.budget_input.setPlaceholderText("Enter budget e.g. 5000")
        self.budget_input.setMaximumWidth(200)
        self.budget_input.setMinimumHeight(34)
        save_budget_btn = QPushButton("Save Budget")
        save_budget_btn.setMinimumHeight(34)
        save_budget_btn.setMinimumWidth(192)
        save_budget_btn.setMaximumWidth(200)
        save_budget_btn.clicked.connect(self.save_budget)
        budget_hdr.addWidget(self.budget_input)
        budget_hdr.addWidget(save_budget_btn)
        budget_main.addLayout(budget_hdr)

        # Progress bar row
        self.budget_bar = QProgressBar()
        self.budget_bar.setRange(0, 100)
        self.budget_bar.setValue(0)
        self.budget_bar.setTextVisible(False)
        self.budget_bar.setFixedHeight(18)
        self.budget_bar.setObjectName("BudgetProgress")
        self.budget_bar.setProperty("state", "success")
        budget_main.addWidget(self.budget_bar)

        self.budget_status_lbl = QLabel("No budget set for this school year.")
        self.budget_status_lbl.setObjectName("BudgetStatus")
        budget_main.addWidget(self.budget_status_lbl)
        layout.addWidget(budget_card)

        # Add expense card
        add_card = Card()
        add_layout = QVBoxLayout(add_card)
        add_layout.setContentsMargins(16, 16, 16, 16)
        add_layout.setSpacing(8)
        add_hdr = QLabel("Add New Expense")
        add_hdr.setObjectName("CardHeading")
        add_layout.addWidget(add_hdr)

        add_grid = QGridLayout()
        add_grid.setHorizontalSpacing(8)
        add_grid.setVerticalSpacing(8)
        self.exp_desc = QLineEdit(); self.exp_desc.setPlaceholderText("Description")
        self.exp_desc.setMinimumHeight(36)
        self.exp_amount = QLineEdit(); self.exp_amount.setPlaceholderText("Amount e.g. 250.00")
        self.exp_amount.setMinimumHeight(36)
        self.exp_date = QDateEdit()
        self.exp_date.setCalendarPopup(True)
        self.exp_date.setDisplayFormat("yyyy-MM-dd")
        self.exp_date.setDate(QDate.currentDate())
        self.exp_date.setMinimumHeight(36)
        self.exp_date.setMinimumWidth(170)
        self.exp_date.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exp_date.setToolTip("Click the blue date button to pick a date.")
        self.exp_sy_entry = QComboBox()
        self.exp_sy_entry.addItems(sy_list)
        if idx >= 1: self.exp_sy_entry.setCurrentIndex(idx - 1)
        self.exp_sy_entry.setMinimumHeight(36)
        add_exp_btn = QPushButton("Add Expense")
        add_exp_btn.setMinimumHeight(36)
        add_exp_btn.clicked.connect(self.add_expense)
        add_grid.addWidget(self.exp_desc, 0, 0, 1, 2)
        add_grid.addWidget(self.exp_amount, 0, 2)
        add_grid.addWidget(self.exp_date, 1, 0)
        add_grid.addWidget(self.exp_sy_entry, 1, 1)
        add_grid.addWidget(add_exp_btn, 1, 2)
        add_grid.setColumnStretch(0, 2)
        add_grid.setColumnStretch(1, 1)
        add_grid.setColumnStretch(2, 1)
        add_layout.addLayout(add_grid)
        layout.addWidget(add_card)

        # Expenses table
        table_card = Card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(8)
        self.expenses_table = QTableWidget(0, 5)
        self.expenses_table.setObjectName("ExpensesTable")
        self.expenses_table.setHorizontalHeaderLabels(["Description", "Amount (PHP)", "Date", "School Year", ""])
        self.expenses_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.expenses_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.expenses_table.horizontalHeader().setStretchLastSection(False)
        self.expenses_table.verticalHeader().setVisible(False)
        self.expenses_table.setAlternatingRowColors(True)
        self.expenses_table.setShowGrid(False)
        self.expenses_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.expenses_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.expenses_table.setMinimumHeight(260)
        self.expenses_table.verticalHeader().setMinimumSectionSize(40)
        self.expenses_table.verticalHeader().setDefaultSectionSize(40)
        table_layout.addWidget(self.expenses_table)

        self.total_label = QLabel("Total: PHP 0.00")
        self.total_label.setObjectName("TotalLabel")
        table_layout.addWidget(self.total_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(table_card)

        layout.addStretch()
        outer_scroll.setWidget(inner)
        w_layout = QVBoxLayout(widget)
        w_layout.setContentsMargins(0, 0, 0, 0)
        w_layout.addWidget(outer_scroll)
        self.stacked_widget.addWidget(widget)

    def create_coordinators_screen(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Header bar
        top_bar = QHBoxLayout()
        title = QLabel("Coordinators")
        title.setObjectName("SectionTitle")
        self.coord_search = QLineEdit()
        self.coord_search.setPlaceholderText("Search by name, location, email…")
        self.coord_search.setMinimumWidth(280)
        self.coord_search.textChanged.connect(self._filter_coordinators)
        add_coord_btn = ActionButton("Add Coordinator")
        add_coord_btn.clicked.connect(self._add_coordinator_dialog)
        refresh_coord_btn = ActionButton("Refresh", variant="secondary")
        refresh_coord_btn.clicked.connect(self.load_coordinators)
        top_bar.addWidget(title)
        top_bar.addStretch()
        top_bar.addWidget(add_coord_btn)
        top_bar.addWidget(refresh_coord_btn)
        layout.addLayout(top_bar)

        search_row = QHBoxLayout()
        search_row.addWidget(self.coord_search, 1)
        layout.addLayout(search_row)

        # Table
        self.coord_table = QTableWidget()
        self.coord_table.setObjectName("CoordTable")
        self.coord_table.setColumnCount(6)
        self.coord_table.setHorizontalHeaderLabels(["Location", "Contact Person", "Email", "Contact No.", "FB Page", "Remarks"])
        self.coord_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.coord_table.horizontalHeader().setStretchLastSection(True)
        self.coord_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.coord_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.coord_table.setAlternatingRowColors(True)
        self.coord_table.setShowGrid(False)
        self.coord_table.verticalHeader().setVisible(False)
        self.coord_table.setWordWrap(True)
        self.coord_table.verticalHeader().setDefaultSectionSize(48)
        self.coord_table.setColumnWidth(0, 130)
        self.coord_table.setColumnWidth(1, 180)
        self.coord_table.setColumnWidth(2, 230)
        self.coord_table.setColumnWidth(3, 130)
        self.coord_table.setColumnWidth(4, 160)
        self.coord_table.doubleClicked.connect(self._edit_coordinator_dialog)
        layout.addWidget(self.coord_table, 1)

        self.coord_status = QLabel("")
        self.coord_status.setObjectName("Caption")
        layout.addWidget(self.coord_status)

        self._coord_all_rows = []  # cache for filtering
        self.stacked_widget.addWidget(widget)

    def load_coordinators(self):
        try:
            data = self.coordinator_repository.list_coordinators()
            self._coord_all_rows = data
            self._populate_coord_table(data)
        except Exception as e:
            self.coord_status.setText(f"Could not load coordinators: {e}")

    def _populate_coord_table(self, rows):
        self.coord_table.setRowCount(0)
        for r in rows:
            row_idx = self.coord_table.rowCount()
            self.coord_table.insertRow(row_idx)
            for col, key in enumerate(["location", "contact_person", "email", "contact_no", "fb_page", "remarks"]):
                val = r.get(key) or ""
                item = QTableWidgetItem(val)
                item.setData(Qt.ItemDataRole.UserRole, r.get("id"))
                self.coord_table.setItem(row_idx, col, item)
        self.coord_status.setText(f"{len(rows)} coordinator(s)")

    def _filter_coordinators(self, text):
        q = text.strip().lower()
        if not q:
            self._populate_coord_table(self._coord_all_rows)
            return
        filtered = [
            r for r in self._coord_all_rows
            if any(q in str(r.get(k) or "").lower()
                   for k in ["location", "contact_person", "email", "contact_no", "fb_page", "remarks"])
        ]
        self._populate_coord_table(filtered)

    def _coord_row_data(self, row_idx):
        keys = ["location", "contact_person", "email", "contact_no", "fb_page", "remarks"]
        d = {}
        for col, key in enumerate(keys):
            item = self.coord_table.item(row_idx, col)
            d[key] = item.text() if item else ""
            if col == 0:
                d["_id"] = item.data(Qt.ItemDataRole.UserRole) if item else None
        return d

    def _coord_dialog(self, title, prefill=None):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        form.setSpacing(8)
        form.setContentsMargins(24, 24, 24, 24)
        fields = {}
        for label, key in [("Location", "location"), ("Contact Person", "contact_person"),
                            ("Email", "email"), ("Contact No.", "contact_no"),
                            ("FB Page", "fb_page"), ("Remarks", "remarks")]:
            w = QLineEdit()
            if prefill:
                w.setText(prefill.get(key, ""))
            form.addRow(label, w)
            fields[key] = w
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        save_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addStretch(); btn_row.addWidget(cancel_btn); btn_row.addWidget(save_btn)
        form.addRow(btn_row)
        return dlg, fields

    def _add_coordinator_dialog(self):
        dlg, fields = self._coord_dialog("Add Coordinator")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        record = {k: v.text().strip() for k, v in fields.items()}
        if not record["location"] and not record["contact_person"]:
            return
        try:
            self.coordinator_repository.insert_coordinator(record)
            self.load_coordinators()
            self.status_bar.showMessage("Coordinator added", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _edit_coordinator_dialog(self, index):
        row = index.row()
        prefill = self._coord_row_data(row)
        rec_id = prefill.pop("_id", None)
        dlg, fields = self._coord_dialog("Edit Coordinator", prefill)
        # Add delete button
        del_btn = QPushButton("Delete")
        del_btn.setObjectName("DangerBtn")
        del_btn.clicked.connect(lambda: dlg.done(2))
        form = dlg.layout()
        last_row = form.rowCount() - 1
        btn_row_item = form.itemAt(last_row, QFormLayout.ItemRole.FieldRole)
        if btn_row_item and btn_row_item.layout():
            btn_row_item.layout().insertWidget(0, del_btn)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted and rec_id:
            record = {k: v.text().strip() for k, v in fields.items()}
            try:
                self.coordinator_repository.update_coordinator(rec_id, record)
                self.load_coordinators()
                self.status_bar.showMessage("Coordinator updated", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        elif result == 2 and rec_id:
            confirm = QMessageBox.question(self, "Delete", "Delete this coordinator?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    self.coordinator_repository.delete_coordinator(rec_id)
                    self.load_coordinators()
                    self.status_bar.showMessage("Coordinator deleted", 4000)
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

    def create_workbook_screen(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        title = QLabel("Workbook")
        title.setObjectName("SectionTitle")
        self.workbook_state_badge = StatusBadge(
            "No Workbook", role="WorkbookStateBadge"
        )
        header_row.addWidget(title)
        header_row.addWidget(self.workbook_state_badge)
        header_row.addStretch()
        layout.addLayout(header_row)

        def workbook_btn(text, slot, object_name=None, icon=None):
            variant = {
                "SecondaryBtn": "secondary",
                "DangerBtn": "danger",
                "SuccessBtn": "success",
            }.get(object_name, "primary")
            button = ActionButton(text, variant=variant)
            if object_name:
                button.setObjectName(object_name)
            if icon is not None:
                button.setIcon(self.style().standardIcon(icon))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            return button

        info_card = Card()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(8)

        self.workbook_path_label = QLabel("No workbook loaded")
        self.workbook_path_label.setObjectName("WorkbookFileLabel")
        self.workbook_path_label.setWordWrap(True)
        self.workbook_status_label = QLabel("No workbook selected.")
        self.workbook_status_label.setObjectName("WorkbookPathLabel")
        self.workbook_status_label.setWordWrap(True)
        info_layout.addWidget(self.workbook_path_label)
        info_layout.addWidget(self.workbook_status_label)

        self.workbook_open_saved_btn = workbook_btn(
            "Open Saved",
            self.load_saved_workbook,
            icon=QStyle.StandardPixmap.SP_DialogOpenButton,
        )
        self.workbook_choose_btn = workbook_btn(
            "Choose File",
            self.choose_workbook_file,
            "SecondaryBtn",
            QStyle.StandardPixmap.SP_DirIcon,
        )
        self.workbook_save_btn = workbook_btn(
            "Save Workbook",
            self.save_workbook_tabs,
            "SuccessBtn",
            QStyle.StandardPixmap.SP_DialogSaveButton,
        )
        self.workbook_reload_btn = workbook_btn(
            "Reload",
            lambda: self.load_workbook_tabs(self._workbook_path) if self._workbook_path else self.choose_workbook_file(),
            "SecondaryBtn",
            QStyle.StandardPixmap.SP_BrowserReload,
        )
        self.workbook_excel_btn = workbook_btn(
            "Excel",
            self.open_workbook_in_excel,
            "SecondaryBtn",
            QStyle.StandardPixmap.SP_FileIcon,
        )

        file_primary_actions = QHBoxLayout()
        file_primary_actions.setSpacing(Spacing.XS)
        for button in (
            self.workbook_open_saved_btn,
            self.workbook_choose_btn,
            self.workbook_save_btn,
        ):
            file_primary_actions.addWidget(button)
        file_primary_actions.addStretch()

        file_secondary_actions = QHBoxLayout()
        file_secondary_actions.setSpacing(Spacing.XS)
        for button in (
            self.workbook_reload_btn,
            self.workbook_excel_btn,
        ):
            file_secondary_actions.addWidget(button)
        file_secondary_actions.addStretch()
        info_layout.addLayout(file_primary_actions)
        info_layout.addLayout(file_secondary_actions)
        layout.addWidget(info_card)

        toolbar = QWidget()
        toolbar.setObjectName("WorkbookToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 16, 16, 16)
        toolbar_layout.setSpacing(8)

        sheet_row = QHBoxLayout()
        sheet_row.setSpacing(8)
        sheet_lbl = QLabel("Sheet")
        sheet_lbl.setObjectName("ToolbarLabel")
        self.workbook_sheet_combo = QComboBox()
        self.workbook_sheet_combo.setObjectName("WorkbookSheetCombo")
        self.workbook_sheet_combo.setMinimumWidth(230)
        self.workbook_sheet_combo.currentIndexChanged.connect(self._on_workbook_sheet_combo_changed)
        self.workbook_sheet_summary_label = QLabel("No sheet selected")
        self.workbook_sheet_summary_label.setObjectName("WorkbookSheetSummary")
        sheet_row.addWidget(sheet_lbl)
        sheet_row.addWidget(self.workbook_sheet_combo)
        sheet_row.addWidget(self.workbook_sheet_summary_label, 1)
        toolbar_layout.addLayout(sheet_row)

        self.workbook_add_column_btn = workbook_btn("Insert Column", self.insert_workbook_column, "SecondaryBtn")
        self.workbook_delete_column_btn = workbook_btn("Delete Column", self.delete_workbook_column, "DangerBtn")
        self.workbook_sync_current_btn = workbook_btn("Sync Current", self.sync_current_sheet_to_supabase)
        self.workbook_sync_all_btn = workbook_btn("Sync All", self.sync_all_workbook_sheets_to_supabase, "SecondaryBtn")
        self.workbook_export_btn = workbook_btn(
            "Export Students",
            self.student_list_view.export_all_students_to_excel,
            "SecondaryBtn",
        )

        column_action_row = QHBoxLayout()
        column_action_row.setSpacing(Spacing.XS)
        column_action_row.addWidget(self.workbook_add_column_btn)
        column_action_row.addWidget(self.workbook_delete_column_btn)
        column_action_row.addStretch()
        toolbar_layout.addLayout(column_action_row)

        sync_action_row = QHBoxLayout()
        sync_action_row.setSpacing(Spacing.XS)
        sync_action_row.addWidget(self.workbook_sync_current_btn)
        sync_action_row.addWidget(self.workbook_sync_all_btn)
        sync_action_row.addWidget(self.workbook_export_btn)
        sync_action_row.addStretch()
        toolbar_layout.addLayout(sync_action_row)
        layout.addWidget(toolbar)

        empty_actions = QWidget()
        empty_actions.setObjectName("EmptyStateActions")
        empty_btn_row = QHBoxLayout(empty_actions)
        empty_btn_row.setContentsMargins(0, 0, 0, 0)
        empty_btn_row.setSpacing(Spacing.XS)
        empty_saved_btn = ActionButton("Open Saved")
        empty_saved_btn.clicked.connect(self.load_saved_workbook)
        empty_open_btn = ActionButton("Choose File", variant="secondary")
        empty_open_btn.clicked.connect(self.choose_workbook_file)
        empty_btn_row.addWidget(empty_saved_btn)
        empty_btn_row.addWidget(empty_open_btn)
        self.workbook_empty_card = EmptyState(
            "No workbook loaded",
            "Open the saved workbook or choose an Excel file to begin.",
            empty_actions,
        )
        layout.addWidget(self.workbook_empty_card, 1)

        self.workbook_tabs = QTabWidget()
        self.workbook_tabs.setDocumentMode(True)
        self.workbook_tabs.setUsesScrollButtons(True)
        self.workbook_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.workbook_tabs.setMovable(False)
        self.workbook_tabs.currentChanged.connect(self._on_workbook_tab_changed)
        self.workbook_tabs.setVisible(False)
        layout.addWidget(self.workbook_tabs, 1)

        self._refresh_workbook_controls()
        self.stacked_widget.addWidget(widget)
    def _settings(self):
        return QSettings("YWAMBalut", "SSMStudentProfilingSystem")

    def _refresh_workbook_controls(self):
        has_workbook = bool(self._workbook)
        for button_name in (
            "workbook_save_btn",
            "workbook_reload_btn",
            "workbook_excel_btn",
            "workbook_add_column_btn",
            "workbook_delete_column_btn",
            "workbook_sync_current_btn",
            "workbook_sync_all_btn",
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(has_workbook)
        if hasattr(self, "workbook_save_btn"):
            self.workbook_save_btn.setEnabled(has_workbook and self._workbook_dirty)
        if hasattr(self, "workbook_sheet_combo"):
            self.workbook_sheet_combo.setEnabled(has_workbook and self.workbook_tabs.count() > 0)
        self._refresh_workbook_state_badge()

    def _refresh_workbook_state_badge(self):
        if not hasattr(self, "workbook_state_badge"):
            return
        if not self._workbook:
            text, state = "No Workbook", "empty"
        elif self._workbook_dirty:
            text, state = "Unsaved", "dirty"
        else:
            text, state = "Saved", "saved"
        self.workbook_state_badge.set_state(state, text)

    def _on_workbook_sheet_combo_changed(self, index):
        if not hasattr(self, "workbook_tabs") or index < 0:
            return
        if self.workbook_tabs.currentIndex() != index:
            self.workbook_tabs.setCurrentIndex(index)

    def _update_workbook_sheet_summary(self, index=None):
        if not hasattr(self, "workbook_sheet_summary_label"):
            return
        if not self._workbook or not hasattr(self, "workbook_tabs") or self.workbook_tabs.count() == 0:
            self.workbook_sheet_summary_label.setText("No sheet selected")
            return
        if index is None:
            index = self.workbook_tabs.currentIndex()
        if index < 0:
            self.workbook_sheet_summary_label.setText("No sheet selected")
            return
        table = self.workbook_tabs.widget(index)
        sheet_name = self.workbook_tabs.tabText(index)
        if isinstance(table, QTableWidget) and sheet_name in self._loaded_workbook_sheets:
            self.workbook_sheet_summary_label.setText(f"{sheet_name}: {table.rowCount()} rows x {table.columnCount()} columns")
        else:
            self.workbook_sheet_summary_label.setText(f"{sheet_name}: not loaded")

    def load_saved_workbook(self):
        saved_path = self._settings().value("workbook_path", "", type=str)
        if saved_path and os.path.exists(saved_path):
            self.load_workbook_tabs(saved_path)
            return

        if saved_path:
            QMessageBox.information(
                self,
                "Saved Workbook Missing",
                f"The saved workbook path was not found:\n{saved_path}\n\nChoose the workbook location for this computer."
            )
        self.choose_workbook_file()

    def choose_workbook_file(self):
        saved_path = self._settings().value("workbook_path", "", type=str)
        start_dir = os.path.dirname(self._workbook_path or saved_path) if (self._workbook_path or saved_path) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open SSM Workbook",
            start_dir,
            "Excel Files (*.xlsx *.xlsm *.xltx *.xltm)"
        )
        if path:
            self.load_workbook_tabs(path)

    def open_workbook_in_excel(self):
        path = self._workbook_path
        if not path:
            saved_path = self._settings().value("workbook_path", "", type=str)
            start_dir = os.path.dirname(saved_path) if saved_path else os.path.expanduser("~")
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Workbook in Excel",
                start_dir,
                "Excel Files (*.xlsx *.xlsm *.xltx *.xltm)"
            )
            if not path:
                return

        if self._workbook_dirty:
            confirm = QMessageBox.question(
                self,
                "Unsaved Workbook Changes",
                "Save workbook changes before opening it in Excel?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if confirm == QMessageBox.StandardButton.Cancel:
                return
            if confirm == QMessageBox.StandardButton.Yes:
                self.save_workbook_tabs()

        try:
            os.startfile(path)
            self.status_bar.showMessage("Opened workbook in Excel", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Open in Excel Failed", f"Could not open workbook:\n({type(e).__name__}) {e}")

    def load_workbook_tabs(self, path):
        if not path:
            return
        try:
            from openpyxl import load_workbook

            if self._workbook and hasattr(self._workbook, "close"):
                self._workbook.close()

            self._workbook = load_workbook(path, read_only=False, data_only=False)
            self._workbook_path = path
            self._settings().setValue("workbook_path", path)
            self._loaded_workbook_sheets.clear()
            self._workbook_dirty = False
            self._workbook_revision += 1
            self._invalidate_master_reference_cache()
            self.workbook_tabs.blockSignals(True)
            self.workbook_tabs.clear()
            self.workbook_sheet_combo.blockSignals(True)
            self.workbook_sheet_combo.clear()

            for sheet_name in self._workbook.sheetnames:
                table = QTableWidget()
                table.setObjectName("WorkbookTable")
                table.setAlternatingRowColors(True)
                table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
                table.setEditTriggers(
                    QTableWidget.EditTrigger.DoubleClicked |
                    QTableWidget.EditTrigger.EditKeyPressed |
                    QTableWidget.EditTrigger.AnyKeyPressed
                )
                table.horizontalHeader().setDefaultSectionSize(150)
                table.horizontalHeader().setMinimumSectionSize(96)
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                table.horizontalHeader().setStretchLastSection(False)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
                table.verticalHeader().setDefaultSectionSize(42)
                table.verticalHeader().setMinimumSectionSize(42)
                table.setWordWrap(False)
                table.cellChanged.connect(self._on_workbook_cell_changed)
                self.workbook_tabs.addTab(table, sheet_name)

            self.workbook_sheet_combo.addItems(self._workbook.sheetnames)
            if self._workbook.sheetnames:
                self.workbook_sheet_combo.setCurrentIndex(0)
            self.workbook_sheet_combo.blockSignals(False)
            self.workbook_tabs.blockSignals(False)
            self.workbook_path_label.setText(os.path.basename(path))
            self.workbook_path_label.setToolTip(path)
            self.workbook_status_label.setText(path)
            self.workbook_empty_card.setVisible(False)
            self.workbook_tabs.setVisible(True)
            self._refresh_workbook_controls()
            if self.workbook_tabs.count():
                self.workbook_tabs.setCurrentIndex(0)
                self._load_workbook_sheet(0)
        except Exception as e:
            QMessageBox.critical(self, "Workbook Error", f"Could not open workbook:\n({type(e).__name__}) {e}")

    def _on_workbook_tab_changed(self, index):
        if index < 0:
            self._update_workbook_sheet_summary(index)
            return
        if hasattr(self, "workbook_sheet_combo") and self.workbook_sheet_combo.currentIndex() != index:
            self.workbook_sheet_combo.blockSignals(True)
            self.workbook_sheet_combo.setCurrentIndex(index)
            self.workbook_sheet_combo.blockSignals(False)
        self._load_workbook_sheet(index)
        self._update_workbook_sheet_summary(index)

    def _current_workbook_table(self):
        if not hasattr(self, "workbook_tabs"):
            return None
        index = self.workbook_tabs.currentIndex()
        if index < 0:
            return None
        table = self.workbook_tabs.widget(index)
        return table if isinstance(table, QTableWidget) else None

    def _sync_workbook_side_scroll(self, table=None):
        pass  # external scroll bar removed; native table scrollbar is used

    def _on_workbook_h_scroll_changed(self, value):
        pass  # external scroll bar removed

    def _set_workbook_column_widths(self, table):
        for col in range(table.columnCount()):
            table.setColumnWidth(col, 150)

    def _load_workbook_sheet(self, index):
        if not self._workbook or index < 0:
            return
        sheet_name = self.workbook_tabs.tabText(index)
        if sheet_name in self._loaded_workbook_sheets:
            self._update_workbook_sheet_summary(index)
            return

        table = self.workbook_tabs.widget(index)
        self._loading_workbook_sheet = True
        table.blockSignals(True)
        table.clear()
        table.setRowCount(0)
        table.setColumnCount(0)
        self.workbook_sheet_summary_label.setText(f"Loading {sheet_name}...")
        QApplication.processEvents()

        ws = self._workbook[sheet_name]
        rows = []
        max_cols = ws.max_column or 0
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=max_cols, values_only=False):
            values = [self._format_excel_value(value) for value in row]
            rows.append(values)

        table.setRowCount(len(rows))
        table.setColumnCount(max_cols)
        # Use the first row as column headers if available, fall back to A/B/C
        if rows:
            header_labels = [
                v if v else self._excel_column_label(i + 1)
                for i, v in enumerate(rows[0])
            ]
        else:
            header_labels = [self._excel_column_label(i + 1) for i in range(max_cols)]
        table.setHorizontalHeaderLabels(header_labels)
        self._set_workbook_column_widths(table)

        for row_idx, values in enumerate(rows):
            for col_idx, value in enumerate(values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(value))

        table.blockSignals(False)
        self._loading_workbook_sheet = False
        self._loaded_workbook_sheets.add(sheet_name)
        self._update_workbook_sheet_summary(index)
        if not self._workbook_dirty:
            self.workbook_status_label.setText(self._workbook_path or "")
        self._refresh_workbook_controls()

    def _on_workbook_cell_changed(self, row, column):
        if self._loading_workbook_sheet or not self._workbook:
            return
        table = self.sender()
        index = self.workbook_tabs.indexOf(table)
        if index < 0:
            return

        sheet_name = self.workbook_tabs.tabText(index)
        item = table.item(row, column)
        text = item.text() if item else ""
        self._workbook[sheet_name].cell(row=row + 1, column=column + 1).value = text if text != "" else None
        self._workbook_dirty = True
        self._workbook_revision += 1
        self._invalidate_master_reference_cache()
        self.workbook_status_label.setText(f"Unsaved changes in {sheet_name}.")
        self._refresh_workbook_controls()
        self._update_workbook_sheet_summary(index)

    def insert_workbook_column(self):
        if not self._workbook:
            QMessageBox.information(self, "Workbook", "Open a workbook first.")
            return

        index = self.workbook_tabs.currentIndex()
        if index < 0:
            return

        sheet_name = self.workbook_tabs.tabText(index)
        table = self.workbook_tabs.widget(index)
        ws = self._workbook[sheet_name]

        if sheet_name not in self._loaded_workbook_sheets:
            self._load_workbook_sheet(index)

        selected_col = table.currentColumn()
        insert_col = selected_col if selected_col >= 0 else table.columnCount()
        excel_col = insert_col + 1
        ws.insert_cols(excel_col)

        table.blockSignals(True)
        table.insertColumn(insert_col)
        table.setHorizontalHeaderItem(insert_col, QTableWidgetItem(self._excel_column_label(excel_col)))
        table.setColumnWidth(insert_col, 150)

        if table.rowCount() == 0:
            table.setRowCount(1)

        for row in range(table.rowCount()):
            table.setItem(row, insert_col, QTableWidgetItem(""))

        table.item(0, insert_col).setText("New Column")
        ws.cell(row=1, column=excel_col).value = "New Column"
        self._refresh_workbook_table_headers(table)
        table.blockSignals(False)

        self._workbook_dirty = True
        self._workbook_revision += 1
        self._invalidate_master_reference_cache()
        self._refresh_workbook_controls()
        self._update_workbook_sheet_summary(index)
        table.setCurrentCell(0, insert_col)
        table.editItem(table.item(0, insert_col))
        self.workbook_status_label.setText(f"Inserted column in {sheet_name}.")

    def delete_workbook_column(self):
        if not self._workbook:
            QMessageBox.information(self, "Workbook", "Open a workbook first.")
            return

        index = self.workbook_tabs.currentIndex()
        if index < 0:
            return

        sheet_name = self.workbook_tabs.tabText(index)
        table = self.workbook_tabs.widget(index)
        ws = self._workbook[sheet_name]

        if sheet_name not in self._loaded_workbook_sheets:
            self._load_workbook_sheet(index)

        selected_col = table.currentColumn()
        if selected_col < 0:
            QMessageBox.information(self, "Delete Column", "Select a column or cell first.")
            return

        col_label = self._excel_column_label(selected_col + 1)
        confirm = QMessageBox.question(
            self,
            "Delete Column",
            f"Delete column {col_label} from '{sheet_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ws.delete_cols(selected_col + 1)
        table.blockSignals(True)
        table.removeColumn(selected_col)
        self._refresh_workbook_table_headers(table)
        table.blockSignals(False)

        self._workbook_dirty = True
        self._workbook_revision += 1
        self._invalidate_master_reference_cache()
        self._refresh_workbook_controls()
        self._update_workbook_sheet_summary(index)
        self.workbook_status_label.setText(f"Deleted column {col_label} from {sheet_name}.")

    def _refresh_workbook_table_headers(self, table):
        for col in range(table.columnCount()):
            table.setHorizontalHeaderItem(col, QTableWidgetItem(self._excel_column_label(col + 1)))

    def save_workbook_tabs(self):
        if not self._workbook or not self._workbook_path:
            QMessageBox.information(self, "Workbook", "No workbook is open.")
            return
        try:
            self._workbook.save(self._workbook_path)
            self._workbook_dirty = False
            self._workbook_revision += 1
            self._invalidate_master_reference_cache()
            self.workbook_status_label.setText(self._workbook_path)
            self._refresh_workbook_controls()
            self.status_bar.showMessage("Workbook saved", 4000)
        except PermissionError:
            QMessageBox.warning(
                self,
                "Workbook Is Open",
                "Could not save the workbook. Please close it in Excel, then click Save Workbook again."
            )
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save workbook:\n({type(e).__name__}) {e}")

    def sync_current_sheet_to_supabase(self):
        if not self._workbook:
            QMessageBox.information(self, "Sync", "Open a workbook first.")
            return
        index = self.workbook_tabs.currentIndex()
        if index < 0:
            return
        sheet_name = self.workbook_tabs.tabText(index)
        if self._is_old_master_sheet(sheet_name):
            latest_master = self._latest_master_sheet_name()
            QMessageBox.warning(
                self,
                "Old Master Sheet",
                f"'{sheet_name}' looks like an older master list.\n\nUse '{latest_master}' for student sync, or export from Supabase instead."
            )
            return
        try:
            count = self._sync_workbook_sheet_to_supabase(sheet_name)
            if count is None:
                QMessageBox.information(self, "Sync", f"'{sheet_name}' is not a supported Supabase sync sheet.")
                return
            QMessageBox.information(self, "Sync Complete", f"Synced {count} records from '{sheet_name}'.")
            self.workbook_status_label.setText(f"Synced {count} records from {sheet_name}.")
            self.refresh_dashboard()
        except Exception as e:
            QMessageBox.critical(self, "Sync Failed", f"Could not sync '{sheet_name}':\n({type(e).__name__}) {e}")

    def sync_all_workbook_sheets_to_supabase(self):
        if not self._workbook:
            QMessageBox.information(self, "Sync", "Open a workbook first.")
            return
        try:
            results = []
            latest_master = self._latest_master_sheet_name()
            for sheet_name in self._workbook.sheetnames:
                if "master" in sheet_name.lower() and sheet_name != latest_master:
                    continue
                count = self._sync_workbook_sheet_to_supabase(sheet_name)
                if count is not None:
                    results.append(f"{sheet_name}: {count}")
            if not results:
                QMessageBox.information(self, "Sync", "No supported workbook sheets were found.")
                return
            QMessageBox.information(self, "Sync Complete", "Synced sheets:\n" + "\n".join(results))
            self.workbook_status_label.setText(f"Synced {len(results)} sheets to Supabase.")
            self.refresh_dashboard()
        except Exception as e:
            QMessageBox.critical(self, "Sync Failed", f"Could not sync workbook:\n({type(e).__name__}) {e}")

    def _sync_workbook_sheet_to_supabase(self, sheet_name):
        return self.workbook_import_service.sync_sheet(self._workbook, sheet_name)

    def _is_old_master_sheet(self, sheet_name):
        latest_master = self._latest_master_sheet_name()
        return "master" in sheet_name.lower() and latest_master and sheet_name != latest_master

    def _sync_masterlist_sheet(self, sheet_name):
        return self.workbook_import_service.sync_masterlist_sheet(self._workbook, sheet_name)

    def _sync_coordinator_sheet(self, sheet_name):
        return self.workbook_import_service.sync_coordinator_sheet(self._workbook, sheet_name)

    def _sync_donor_sheet(self, sheet_name):
        return self.workbook_import_service.sync_donor_sheet(self._workbook, sheet_name)

    def _sync_movements_sheet(self, sheet_name):
        return self.workbook_import_service.sync_movements_sheet(self._workbook, sheet_name)

    def _insert_chunks(self, table_name, records, size=100):
        self.workbook_repository.insert_records(table_name, records, chunk_size=size)
    def _sheet_values(self, sheet_name):
        return self.workbook_import_service.sheet_values(self._workbook, sheet_name)

    def _find_header_row(self, rows, required):
        return self.workbook_import_service.find_header_row(rows, required)

    def _header_map(self, row):
        return self.workbook_import_service.header_map(row)

    def _normalize_header(self, value):
        return self.workbook_import_service.normalize_header(value)

    def _safe_cell(self, row, index):
        return self.workbook_import_service.safe_cell(row, index)

    def _school_year_from_sheet(self, sheet_name):
        return self.workbook_import_service.school_year_from_sheet(sheet_name)

    def _format_excel_value(self, value):
        return self.workbook_import_service.format_excel_value(value)
    def _excel_column_label(self, number):
        label = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            label = chr(65 + remainder) + label
        return label

    # ── LIST ──────────────────────────────────────────────────────────────────
    def _latest_master_sheet_name(self):
        return self._latest_master_sheet_name_from_names(self._workbook.sheetnames)

    def _sheet_year_score(self, sheet_name):
        return self.masterlist_service.sheet_year_score(sheet_name)
    def _load_profile(self, sid):
        try:
            student = self.student_repository.get_student_single(sid)
            s = self._apply_current_master_status(student)
            full_status, short_status, _status_token = self._status_style(s.get("status"))
            inactive = (full_status != "Active")
            
            # 1. Update Buttons and Status
            master_status = s.get("_status_source") == "masterlist"
            self.deactivate_btn.setVisible(not master_status)
            self.deactivate_btn.setEnabled(True)
            self.deactivate_btn.setToolTip("")
            if inactive:
                self.deactivate_btn.setText("Mark Active")
                self.deactivate_btn.setObjectName("SuccessBtn")
                self.deactivate_btn.style().unpolish(self.deactivate_btn)
                self.deactivate_btn.style().polish(self.deactivate_btn)
            else:
                self.deactivate_btn.setText("Mark Inactive")
                self.deactivate_btn.setObjectName("DangerBtn")
                self.deactivate_btn.style().unpolish(self.deactivate_btn)
                self.deactivate_btn.style().polish(self.deactivate_btn)
            status_key = {
                "Active": "active",
                "Inactive/Removed": "inactive",
                "Graduated": "graduated",
            }.get(full_status, "inactive")
            self.lbl_profile_status.setText(f"●  {full_status}")
            self.lbl_profile_status.setProperty("status", status_key)
            self.lbl_profile_status.style().unpolish(self.lbl_profile_status)
            self.lbl_profile_status.style().polish(self.lbl_profile_status)

            # 2. Update Header Name
            self.lbl_profile_name.setText(f"{s.get('last_name', '')}, {s.get('first_name', '')}")

            # 3. Safely update all grid labels
            fields = [
                "gender", "grade", "area", "city", "address", 
                "birthday", "contact", "sponsor", "school", 
                "parents", "course"
            ]
            
            for field in fields:
                val = s.get(field)
                # Ensure we handle None or empty strings gracefully
                display_text = str(val).strip() if val and str(val).strip() else "--"
                self.profile_data_labels[field].setText(display_text)

            self.remarks_edit.setPlainText(s.get("remarks") or "")

            photo_url = s.get("photo_url")
            self._load_photo_from_url(self.photo_label, photo_url)
            self.remove_photo_btn.setVisible(bool(photo_url))

            self.profile_progress.set_value(self._profile_completion_percent(s))

        except Exception as e:
            self.status_bar.showMessage(f"Load error ({type(e).__name__}): {e}", 8000)
    

    # ── PHOTO ─────────────────────────────────────────────────────────────────
    # Local photo cache: {url_without_query -> local_path}
    _photo_cache: dict = {}

    def _photo_cache_path(self, url: str) -> str:
        return self.photo_service.photo_cache_path(url)

    def _load_photo_from_url(self, label, url, log=None):
        """Show photo from local cache instantly; download in background if missing.

        A generation counter (_photo_gen) is stamped at call-time so that if
        the user navigates to another student before the download finishes, the
        stale callback detects the mismatch and discards its result instead of
        overwriting the newly-loaded profile photo.
        """
        def L(msg):
            if log is not None: log.append(msg)
        if not url:
            label.clear(); label.setText("No Photo"); return

        cache_path = self._photo_cache_path(url)

        # Serve from disk cache immediately if available — no network needed.
        if os.path.exists(cache_path):
            self._set_photo_local(label, cache_path)
            return

        # Bump the generation so any in-flight fetch for the *previous* student
        # can detect it is now stale.
        self._photo_gen = getattr(self, "_photo_gen", 0) + 1
        my_gen = self._photo_gen

        def fetch():
            _path, data = self.photo_service.download_photo_to_cache(url)
            return data

        def apply(data):
            if getattr(self, "_photo_gen", 0) != my_gen:
                return
            pix = QPixmap()
            if pix.loadFromData(data) and not pix.isNull():
                w = label.width() or 140
                h = label.height() or 170
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setPixmap(self._scale_cover(pix, w, h))
            else:
                label.clear()
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setText("No Photo")

        def fail(error):
            L(f"Photo fetch failed: {error.strip().splitlines()[-1]}")
            if getattr(self, "_photo_gen", 0) == my_gen:
                label.clear()
                label.setText("No Photo")

        self._run_background(fetch, apply, fail)
    @staticmethod
    def _scale_cover(pixmap: "QPixmap", w: int, h: int) -> "QPixmap":
        """Scale pixmap to fill w x h (cover), then centre-crop — no letterbox."""
        scaled = pixmap.scaled(w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        if scaled.width() > w or scaled.height() > h:
            x = (scaled.width()  - w) // 2
            y = (scaled.height() - h) // 2
            scaled = scaled.copy(x, y, w, h)
        return scaled

    def _set_photo_local(self, label, path):
        if path and os.path.exists(path):
            w = label.width() or 140
            h = label.height() or 170
            pix = self._scale_cover(QPixmap(path), w, h)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setPixmap(pix)
        else:
            label.clear()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setText("No Photo")

    def _upload_photo(self, local_path, student_id, log=None):
        return self.photo_service.upload_photo(local_path, student_id, log)

    def _cache_uploaded_photo(self, source_path, url):
        try:
            return self.photo_service.cache_uploaded_photo(source_path, url)
        except Exception:
            return None

    def change_photo(self):
        if not self.current_student_id:
            QMessageBox.warning(self, "No Student", "No student selected.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select Photo", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        sid = self.current_student_id
        self.status_bar.showMessage("Uploading photo... please wait")
        self.change_photo_btn.setEnabled(False)

        def upload():
            log = []
            logging.getLogger(__name__).info("Uploading photo for student %s", sid)
            url = self._upload_photo(path, sid, log)
            self.student_repository.update_photo_url(sid, url)
            self._cache_uploaded_photo(path, url)
            return url

        def done(_url):
            self.change_photo_btn.setEnabled(True)
            if self.current_student_id == sid:
                self._load_profile(sid)
            self.status_bar.showMessage("Photo updated", 5000)

        def failed(error):
            self.change_photo_btn.setEnabled(True)
            logging.getLogger(__name__).error("Photo upload failed:\n%s", error)
            self.status_bar.showMessage("Photo upload failed", 5000)
            QMessageBox.critical(self, "Photo Upload Failed", error.strip().splitlines()[-1])

        self._run_background(upload, done, failed)

    def remove_photo(self):
        """Delete the student's photo from Storage and clear photo_url in the DB."""
        if not self.current_student_id:
            return
        confirm = QMessageBox.question(
            self, "Remove Photo",
            "Remove this student's photo? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        sid = self.current_student_id
        self.status_bar.showMessage("Removing photo…", 30000)
        self.remove_photo_btn.setEnabled(False)

        def remove():
            self.student_repository.update_photo_url(sid, None)
            self.photo_service.clear_student_cache(sid)
            self.photo_service.delete_storage_photo_variants(sid)

        def done(_result):
            self.remove_photo_btn.setEnabled(True)
            if self.current_student_id == sid:
                self._load_profile(sid)
            self.status_bar.showMessage("Photo removed", 4000)

        def failed(error):
            self.remove_photo_btn.setEnabled(True)
            self.status_bar.showMessage("Remove failed", 5000)
            QMessageBox.critical(self, "Remove Photo Failed", error.strip().splitlines()[-1])

        self._run_background(remove, done, failed)

    def pick_add_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Photo", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self._pending_photo = path
            self._set_photo_local(self.add_photo_label, path)

    # ── REMARKS ───────────────────────────────────────────────────────────────
    def save_remarks(self):
        if not self.current_student_id: return
        self._update_field("students", "remarks", self.remarks_edit.toPlainText(), self.current_student_id)

    # ── TOGGLE STATUS ─────────────────────────────────────────────────────────
    def toggle_active_status(self):
        if not self.current_student_id: return
        try:
            student = self.student_repository.get_student_single(self.current_student_id)
            current = self._apply_current_master_status(student).get("status")
            new_status = "Active" if current == "Inactive/Removed" else "Inactive/Removed"
            self.student_repository.update_status(self.current_student_id, new_status)
            self._load_profile(self.current_student_id)
            self.status_bar.showMessage(f"Status set to {new_status}", 3000)
            self.refresh_dashboard() # Update dashboard stats silently
        except Exception as e:
            self.status_bar.showMessage(f"Status update error ({type(e).__name__}): {e}", 8000)

    # ── ADD / EDIT FORM ───────────────────────────────────────────────────────
    def _open_add_screen(self):
        self._clear_form()
        self._switch_page(3)

    def open_edit_screen(self):
        if not self.current_student_id: return
        try:
            student = self.student_repository.get_student_single(self.current_student_id)
            s = self._apply_current_master_status(student)
            self.form_title_label.setText("Edit Student")
            self._editing_id = self.current_student_id
            self.inp_last.setText(s.get("last_name") or "")
            self.inp_first.setText(s.get("first_name") or "")
            self.inp_gender.setCurrentIndex(max(self.inp_gender.findText(s.get("gender") or ""), 0))
            self.inp_grade.setText(s.get("grade") or "")
            self.inp_address.setText(s.get("address") or "")
            self.inp_city.setText(s.get("city") or "")
            self.inp_area.setText(s.get("area") or "")
            self.inp_bday.setText(s.get("birthday") or "")
            self.inp_sponsor.setText(s.get("sponsor") or "")
            self.inp_contact.setText(s.get("contact") or "")
            self.inp_school.setText(s.get("school") or "")
            self.inp_parents.setText(s.get("parents") or "")
            self.inp_course.setText(s.get("course") or "")
            self.inp_remarks.setPlainText(s.get("remarks") or "")
            self.inp_status.setCurrentIndex(max(self.inp_status.findText(s.get("status") or "Active"), 0))
            master_status = s.get("_status_source") == "masterlist"
            self.inp_status.setEnabled(not master_status)
            self.inp_status.setToolTip("Edit the latest masterlist workbook to change this status." if master_status else "")
            self._pending_photo = None
            self.add_photo_label.clear(); self.add_photo_label.setText("No Photo")
            self._switch_page(3)
        except Exception as e:
            self.status_bar.showMessage(f"Load error ({type(e).__name__}): {e}", 8000)

    def _clear_form(self):
        for w in (self.inp_last, self.inp_first, self.inp_grade, self.inp_address,
                  self.inp_city, self.inp_area, self.inp_bday, self.inp_sponsor,
                  self.inp_contact, self.inp_school, self.inp_parents, self.inp_course):
            w.clear()
        self.inp_remarks.clear()
        self.inp_gender.setCurrentIndex(0)
        self.inp_status.setCurrentIndex(0)
        self.inp_status.setEnabled(True)
        self.inp_status.setToolTip("")
        self.add_photo_label.clear(); self.add_photo_label.setText("No Photo")
        self._pending_photo = None
        self._editing_id = None
        self.form_title_label.setText("Add New Student")

    def save_student_form(self):
        if not self.inp_last.text().strip() or not self.inp_first.text().strip():
            QMessageBox.warning(self, "Required", "Last Name and First Name are required.")
            return
        payload = {
            "last_name":  self.inp_last.text().strip(),
            "first_name": self.inp_first.text().strip(),
            "gender":     self.inp_gender.currentText(),
            "grade":      self.inp_grade.text(),
            "address":    self.inp_address.text(),
            "city":       self.inp_city.text(),
            "area":       self.inp_area.text(),
            "birthday":   self.inp_bday.text(),
            "sponsor":    self.inp_sponsor.text(),
            "contact":    self.inp_contact.text(),
            "school":     self.inp_school.text(),
            "parents":    self.inp_parents.text(),
            "course":     self.inp_course.text(),
            "remarks":    self.inp_remarks.toPlainText(),
            "status":     self.inp_status.currentText(),
        }
        editing = self._editing_id
        pending_photo = self._pending_photo
        self.save_form_btn.setEnabled(False)
        self.status_bar.showMessage("Saving student...", 30000)

        def save():
            if editing:
                self.student_repository.update_student(editing, payload)
                student_id = editing
            else:
                rows = self.student_repository.insert_student(payload)
                if not rows or "id" not in rows[0]:
                    raise RuntimeError("The database did not return the new student ID.")
                student_id = rows[0]["id"]

            if pending_photo:
                url = self._upload_photo(pending_photo, student_id)
                self.student_repository.update_photo_url(student_id, url)
                self._cache_uploaded_photo(pending_photo, url)
            return student_id, bool(editing)

        def saved(result):
            student_id, was_editing = result
            self.save_form_btn.setEnabled(True)
            self._clear_form()
            if was_editing:
                self.current_student_id = student_id
                self._load_profile(student_id)
                self._switch_page(2)
            else:
                self.nav_students()
            self.refresh_dashboard()
            self.status_bar.showMessage("Student saved", 4000)

        def failed(error):
            self.save_form_btn.setEnabled(True)
            logging.getLogger(__name__).error("Student save failed:\n%s", error)
            self.status_bar.showMessage("Student save failed", 5000)
            QMessageBox.critical(self, "Save Error", error.strip().splitlines()[-1])

        self._run_background(save, saved, failed)

    # ── EXPENSES ──────────────────────────────────────────────────────────────
    def open_expenses_screen(self):
        if not self.current_student_id: return
        try:
            s = self.student_repository.get_student_single(self.current_student_id, columns="last_name,first_name")
            self.expenses_title.setText(f"Expenses - {s['last_name']}, {s['first_name']}")
            self.load_expenses()
            self.load_budget()
            self._switch_page(4)
        except Exception as e:
            self.status_bar.showMessage(f"Error ({type(e).__name__}): {e}", 8000)

    def _on_sy_changed(self):
        """Called when school year filter changes; reload expenses and budget."""
        sy = self.exp_school_year.currentText()
        if sy != "All Years":
            idx = self.exp_sy_entry.findText(sy)
            if idx >= 0:
                self.exp_sy_entry.setCurrentIndex(idx)
        self.load_expenses()
        self.load_budget()

    def load_expenses(self):
        self.expenses_table.setRowCount(0)
        if not self.current_student_id:
            return
        try:
            sy_filter = self.exp_school_year.currentText()
            rows = self.expense_service.list_expenses(self.current_student_id, sy_filter)
            total = self.expense_service.calculate_total(rows)
            for exp in rows:
                row_idx = self.expenses_table.rowCount()
                self.expenses_table.insertRow(row_idx)
                self.expenses_table.setRowHeight(row_idx, 40)
                self.expenses_table.setItem(row_idx, 0, QTableWidgetItem(exp.get("description", "")))
                amount = exp.get("amount", 0) or 0
                self.expenses_table.setItem(row_idx, 1, QTableWidgetItem(f"{amount:,.2f}"))
                self.expenses_table.setItem(row_idx, 2, QTableWidgetItem(exp.get("date") or ""))
                self.expenses_table.setItem(row_idx, 3, QTableWidgetItem(exp.get("school_year") or ""))
                del_btn = ActionButton("Delete", variant="danger")
                del_btn.setProperty("density", "compact")
                expense_id = exp["id"]
                del_btn.clicked.connect(lambda _, e=expense_id: self.delete_expense(e))
                action_cell = QWidget()
                action_cell.setObjectName("TableActionCell")
                action_layout = QHBoxLayout(action_cell)
                action_layout.setContentsMargins(0, 0, 0, 0)
                action_layout.setSpacing(0)
                action_layout.addWidget(del_btn)
                self.expenses_table.setCellWidget(row_idx, 4, action_cell)
            self.total_label.setText(self.expense_service.total_label(total, sy_filter))
            self._update_budget_bar(total)
        except Exception as e:
            self.status_bar.showMessage(f"Load error ({type(e).__name__}): {e}", 8000)

    def load_budget(self):
        """Load budget for current student + selected school year and update UI."""
        sy = self.exp_school_year.currentText()
        if sy == "All Years" or not self.current_student_id:
            self.budget_input.clear()
            self.budget_bar.setValue(0)
            self.budget_status_lbl.setText("Select a specific school year to set/view a budget.")
            self._set_budget_state("neutral")
            self.budget_input.setEnabled(False)
            return
        self.budget_input.setEnabled(True)
        try:
            budget = self.expense_service.get_budget(self.current_student_id, sy)
            if budget and budget.get("amount"):
                amount = budget.get("amount") or 0
                self.budget_input.setText(f"{amount:,.2f}")
            else:
                self.budget_input.clear()
                self.budget_status_lbl.setText("No budget set for this school year.")
                self._set_budget_state("neutral")
                self.budget_bar.setValue(0)
        except Exception as e:
            self.status_bar.showMessage(f"Load error ({type(e).__name__}): {e}", 8000)

    def _update_budget_bar(self, total_spent):
        """Update the progress bar and status label based on budget vs spent."""
        sy = self.exp_school_year.currentText()
        if sy == "All Years" or not self.current_student_id:
            self.budget_bar.setValue(0)
            self.budget_status_lbl.setText("Select a specific school year to view budget progress.")
            self._set_budget_state("neutral")
            return
        try:
            budget = self.expense_service.get_budget(self.current_student_id, sy)
            if not budget or not budget.get("amount"):
                self.budget_bar.setValue(0)
                self.budget_status_lbl.setText("No budget set. Enter a budget above and click Save.")
                self._set_budget_state("neutral")
                return
            usage = self.expense_service.budget_usage(total_spent, budget.get("amount"))
            self.budget_bar.setValue(usage["percent"])
            self.budget_status_lbl.setText(usage["message"])
            if usage["over_budget"] or usage["percent"] >= 100:
                state = "danger"
            elif usage["percent"] >= 75:
                state = "warning"
            else:
                state = "success"
            self._set_budget_state(state)
        except Exception as e:
            print(f"Budget bar error: {e}")

    def _set_budget_state(self, state):
        for widget in (self.budget_bar, self.budget_status_lbl):
            widget.setProperty("state", state)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def save_budget(self):
        """Upsert budget for current student + school year."""
        sy = self.exp_school_year.currentText()
        if sy == "All Years":
            QMessageBox.warning(self, "Budget", "Please select a specific school year before saving a budget.")
            return
        try:
            amount = self.expense_service.parse_amount(self.budget_input.text())
        except ValueError:
            self.status_bar.showMessage("Invalid budget amount", 4000)
            return
        try:
            self.expense_service.save_budget(self.current_student_id, sy, amount)
            self.status_bar.showMessage(f"Budget saved: PHP {amount:,.2f} for {sy}", 4000)
            self.load_expenses()
        except Exception as e:
            self.status_bar.showMessage(f"Budget save error: {e}", 8000)

    def add_expense(self):
        if not self.current_student_id:
            QMessageBox.information(self, "Select Student", "Please select a student before adding an expense.")
            return
        desc = self.exp_desc.text().strip()
        if not desc:
            self.status_bar.showMessage("Description is required", 4000)
            return
        try:
            amount = self.expense_service.parse_amount(self.exp_amount.text())
        except ValueError:
            self.status_bar.showMessage("Invalid amount - enter a number like 250.00", 4000)
            return
        school_year = self.exp_sy_entry.currentText()
        expense_date = self.exp_date.date().toString("yyyy-MM-dd")
        try:
            self.expense_service.add_expense(
                self.current_student_id, desc, amount, expense_date, school_year
            )
            self.exp_desc.clear()
            self.exp_amount.clear()
            self.exp_date.setDate(QDate.currentDate())
            if self.exp_school_year.currentText() not in ("All Years", school_year):
                self.exp_school_year.setCurrentText(school_year)
            self.load_expenses()
            self.status_bar.showMessage("Expense added", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Add Expense Failed", f"Could not add expense:\n({type(e).__name__}) {e}")

    def delete_expense(self, eid):
        try:
            self.expense_service.delete_expense(eid)
            self.load_expenses()
        except Exception as e:
            self.status_bar.showMessage(f"Error ({type(e).__name__}): {e}", 8000)

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    logo_path = resource_path(LOGO_ASSET)
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # 1. Create Supabase client
    sb = get_supabase()

    # 2. Show startup splash — user picks their name, then we connect
    splash = StartupDialog()
    splash.queue_ping(sb)
    result = splash.exec()

    if result == QDialog.DialogCode.Rejected and not splash.success:
        QMessageBox.warning(
            None, "Offline Mode",
            "Could not reach Supabase.\n\nThe app will open, but data may not load correctly.\n\n"
            f"Error: {splash.error_msg}"
        )

    # 3. Launch main window
    window = StudentApp(sb, initial_user=splash.selected_user)
    window.show()
    sys.exit(app.exec())
