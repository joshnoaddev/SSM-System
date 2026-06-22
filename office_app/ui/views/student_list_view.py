"""Standalone student-list screen."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from PyQt6.QtCore import QRectF, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QVBoxLayout, QWidget,
)

from office_app.ui import ActionButton, Card, DESIGN_TOKENS, theme_color
from office_app.utils.background_tasks import BackgroundTask


class _CircularProgress(QWidget):
    def __init__(self, parent=None, size=96):
        super().__init__(parent)
        self.value = 0
        self.setFixedSize(size, size)

    def set_value(self, value):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_width = max(4, int(self.width() * 0.07))
        margin = pen_width + 2
        rect = QRectF(margin, margin, self.width() - margin * 2, self.height() - margin * 2)
        painter.setPen(QPen(theme_color("border_subtle"), pen_width))
        painter.drawArc(rect, 0, 360 * 16)
        if self.value == 100:
            color = DESIGN_TOKENS["success"]
        elif self.value >= 75:
            color = DESIGN_TOKENS["primary"]
        elif self.value >= 50:
            color = DESIGN_TOKENS["warning"]
        else:
            color = DESIGN_TOKENS["danger"]
        progress_pen = QPen(QColor(color), pen_width)
        progress_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(progress_pen)
        painter.drawArc(rect, 90 * 16, -int((self.value / 100) * 360 * 16))
        painter.setPen(theme_color("text_primary"))
        font = painter.font()
        font.setPixelSize(max(8, int(self.width() * 0.19)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.value}%")


class StudentListView(QWidget):
    student_selected = pyqtSignal(str)
    students_changed = pyqtSignal()

    def __init__(
        self,
        student_repository,
        student_list_service,
        student_excel_service,
        run_background_fn: Callable | None = None,
        *,
        filter_current_rows_fn: Callable[[Sequence[Mapping[str, Any]]], list] | None = None,
        status_message_fn: Callable[[str, int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.student_repository = student_repository
        self.student_list_service = student_list_service
        self.student_excel_service = student_excel_service
        self._student_service = student_list_service.student_service
        self._run_background_fn = run_background_fn
        self._filter_current_rows = filter_current_rows_fn or (lambda rows: list(rows))
        self._status_message = status_message_fn or (lambda _message, _timeout=0: None)
        self._thread_pool = QThreadPool(self) if run_background_fn is None else None
        self._student_list_request = 0
        self.student_list_mode = None
        self._student_list_rows = []
        self._area_options = []
        self._area_counts = {}
        self._setup_ui()

    @staticmethod
    def _secondary_button(text):
        button = ActionButton(text, variant="secondary")
        button.setObjectName("SecondaryBtn")
        return button

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        filter_card = Card()
        f_layout = QVBoxLayout(filter_card)
        f_layout.setContentsMargins(16, 16, 16, 16)
        f_layout.setSpacing(12)

        mode_bar = QHBoxLayout()
        mode_bar.setSpacing(8)
        self.btn_all_students = self._secondary_button("All Students")
        self.btn_all_students.setMinimumWidth(112)
        self.btn_all_students.setCheckable(True)
        self.btn_areas = self._secondary_button("Areas")
        self.btn_areas.setMinimumWidth(72)
        self.btn_areas.setCheckable(True)
        self.btn_all_students.clicked.connect(lambda: self.set_student_list_mode("all"))
        self.btn_areas.clicked.connect(lambda: self.set_student_list_mode("areas"))
        mode_bar.addWidget(self.btn_all_students)
        mode_bar.addWidget(self.btn_areas)
        mode_bar.addStretch()

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_name = QLineEdit()
        self.search_name.setPlaceholderText("Search name")
        self.search_name.setMinimumWidth(180)
        self.search_name.textChanged.connect(self.load_student_list)
        self.search_sponsor = QLineEdit()
        self.search_sponsor.setPlaceholderText("Filter sponsor")
        self.search_sponsor.setMinimumWidth(180)
        self.search_sponsor.textChanged.connect(self.load_student_list)
        search_row.addWidget(self.search_name, 1)
        search_row.addWidget(self.search_sponsor, 1)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.filter_grade = QComboBox()
        self.filter_grade.addItem("All Grades")
        self.filter_grade.currentTextChanged.connect(self.load_student_list)
        self.filter_grade.setMinimumWidth(120)
        self.area_select = QComboBox()
        self.area_select.addItem("Choose Area")
        self.area_select.setMinimumWidth(150)
        self.area_select.currentTextChanged.connect(self.load_student_list)
        self.area_select.setVisible(False)
        self.back_to_areas_btn = self._secondary_button("Back to Areas")
        self.back_to_areas_btn.clicked.connect(self.back_to_area_choices)
        self.back_to_areas_btn.setVisible(False)
        self.filter_status = QComboBox()
        self.filter_status.addItems(["All", "Active", "Inactive/Removed", "Graduated"])
        self.filter_status.setMinimumWidth(165)
        self.filter_status.currentTextChanged.connect(self.load_student_list)

        import_btn = self._secondary_button("Import Excel")
        import_btn.clicked.connect(self.import_from_excel)
        export_btn = self._secondary_button("Export Excel")
        export_btn.clicked.connect(self.export_to_excel)
        refresh_btn = self._secondary_button("Refresh")
        refresh_btn.clicked.connect(self.load_student_list)
        clear_btn = self._secondary_button("Clear Filters")
        clear_btn.clicked.connect(self.clear_student_filters)
        for button in (clear_btn, refresh_btn, import_btn, export_btn):
            button.setProperty("density", "compact")
        clear_btn.setMinimumWidth(96)
        refresh_btn.setMinimumWidth(80)
        import_btn.setMinimumWidth(96)
        export_btn.setMinimumWidth(96)
        mode_bar.addWidget(clear_btn)
        mode_bar.addWidget(refresh_btn)
        mode_bar.addWidget(import_btn)
        mode_bar.addWidget(export_btn)

        filter_row.addWidget(QLabel("Grade:"))
        filter_row.addWidget(self.filter_grade)
        filter_row.addWidget(self.area_select)
        filter_row.addWidget(self.back_to_areas_btn)
        filter_row.addWidget(QLabel("Status:"))
        filter_row.addWidget(self.filter_status)
        filter_row.addStretch()
        f_layout.addLayout(mode_bar)
        f_layout.addLayout(search_row)
        f_layout.addLayout(filter_row)
        layout.addWidget(filter_card)

        self.count_label = QLabel("Choose All Students or Areas to view records.")
        self.count_label.setObjectName("CountBanner")
        self.count_label.setMinimumHeight(42)
        layout.addWidget(self.count_label)
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("StudentList")
        self.list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_widget.itemClicked.connect(self._on_student_click)
        self.list_widget.itemActivated.connect(self._on_student_click)
        layout.addWidget(self.list_widget)
        self.show_student_view_prompt()

    def _run_background(self, function, on_success=None, on_error=None):
        if self._run_background_fn is not None:
            return self._run_background_fn(function, on_success, on_error)
        task = BackgroundTask(function)
        if on_success is not None:
            task.signals.succeeded.connect(on_success)
        if on_error is not None:
            task.signals.failed.connect(on_error)
        self._thread_pool.start(task)
        return task

    def load_student_list(self):
        self.list_widget.clear()
        if not self.student_list_mode:
            self.show_student_view_prompt()
            return None
        if self.student_list_mode == "areas":
            area_q = self.area_select.currentText().strip()
            if not area_q or area_q == "Choose Area":
                self.show_area_choice_prompt()
                return None
        columns = (
            "id,last_name,first_name,birthday,gender,grade,sponsor,area,status,"
            "address,city,contact,school,parents,course,photo_url,remarks"
        )
        name_q = self.search_name.text().strip()
        sponsor_q = self.search_sponsor.text().strip()
        area_q = self.area_select.currentText().strip() if self.student_list_mode == "areas" else ""
        status = self.filter_status.currentText()
        grade = self.filter_grade.currentText()
        self._student_list_request += 1
        request_id = self._student_list_request
        self._status_message("Loading students...", 30000)

        def fetch_rows():
            return self.student_repository.search_students(
                columns=columns, name_query=name_q or None,
                sponsor_query=sponsor_q or None,
                area=area_q if area_q and area_q != "Choose Area" else None,
                area_exact=False, order_by=["area", "last_name"],
            )

        def apply_rows(rows):
            if request_id != self._student_list_request:
                return
            rows = self.student_list_service.filter_rows(
                self._filter_current_rows(rows), status=status, grade=grade,
            )
            self._student_list_rows = rows
            self.render_student_list()
            self._status_message(f"Loaded {len(rows)} students", 3000)

        def show_error(error):
            if request_id == self._student_list_request:
                self._status_message(f"Load error: {error.strip().splitlines()[-1]}", 8000)

        return self._run_background(fetch_rows, apply_rows, show_error)

    def set_student_list_mode(self, mode):
        self.student_list_mode = mode
        self.btn_all_students.setChecked(mode == "all")
        self.btn_areas.setChecked(mode == "areas")
        self.area_select.setVisible(mode == "areas")
        self.back_to_areas_btn.setVisible(False)
        if mode == "areas":
            self._student_list_rows = []
            self.list_widget.clear()
            self.refresh_area_dropdown()
            self.show_area_choice_prompt()
            return
        self.load_student_list()

    def clear_student_filters(self):
        widgets = (self.search_name, self.search_sponsor, self.filter_grade, self.filter_status, self.area_select)
        for widget in widgets:
            widget.blockSignals(True)
        self.search_name.clear()
        self.search_sponsor.clear()
        self.filter_grade.setCurrentIndex(0)
        self.filter_status.setCurrentIndex(0)
        if self.area_select.count():
            self.area_select.setCurrentIndex(0)
        for widget in widgets:
            widget.blockSignals(False)
        if self.student_list_mode == "areas":
            self._student_list_rows = []
            self.back_to_areas_btn.setVisible(False)
            self.show_area_choice_prompt()
        elif self.student_list_mode:
            self.load_student_list()
        else:
            self.show_student_view_prompt()

    def back_to_area_choices(self):
        if self.student_list_mode != "areas":
            return
        self.area_select.blockSignals(True)
        self.area_select.setCurrentIndex(0)
        self.area_select.blockSignals(False)
        self._student_list_rows = []
        self.back_to_areas_btn.setVisible(False)
        self.show_area_choice_prompt()

    def show_student_view_prompt(self):
        self.btn_all_students.setChecked(False)
        self.btn_areas.setChecked(False)
        self.back_to_areas_btn.setVisible(False)
        self.count_label.setText("Students")
        self.list_widget.clear()
        item = QListWidgetItem("Select a view above to load student records.")
        item.setData(Qt.ItemDataRole.UserRole, None)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setForeground(theme_color("text_secondary"))
        self.list_widget.addItem(item)

    def show_area_choice_prompt(self):
        self.list_widget.clear()
        self.back_to_areas_btn.setVisible(False)
        if not self._area_options:
            item = QListWidgetItem("No areas found.")
            item.setData(Qt.ItemDataRole.UserRole, None)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setForeground(theme_color("text_secondary"))
            self.list_widget.addItem(item)
            return
        total = sum(self._area_counts.values())
        self.count_label.setText(f"Areas - {total} current students")
        for area in self._area_options:
            count = self._area_counts.get(area, 0)
            noun = "student" if count == 1 else "students"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, ("area", area))
            item.setSizeHint(QSize(0, 96))
            item.setToolTip(f"Open {area}")
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, self._area_choice_widget(area, f"{count} {noun}"))

    def refresh_area_dropdown(self):
        current = self.area_select.currentText()
        try:
            rows = self.student_repository.list_students(columns="last_name,first_name,birthday,area")
            area_counts = self.student_list_service.area_counts(self._filter_current_rows(rows))
            areas = sorted(area_counts)
        except Exception as error:
            self._status_message(f"Area load error ({type(error).__name__}): {error}", 8000)
            return
        self._area_options = areas
        self._area_counts = area_counts
        self.area_select.blockSignals(True)
        self.area_select.clear()
        self.area_select.addItem("Choose Area")
        self.area_select.addItems(areas)
        self.area_select.setCurrentText(current) if current in areas else self.area_select.setCurrentIndex(0)
        self.area_select.blockSignals(False)

    def refresh_grade_filter(self):
        current = self.filter_grade.currentText()
        try:
            rows = self.student_repository.list_students(columns="last_name,first_name,birthday,grade")
            grades = self.student_list_service.grade_options(self._filter_current_rows(rows))
        except Exception as error:
            self._status_message(f"Grade load error ({type(error).__name__}): {error}", 8000)
            return
        self.filter_grade.blockSignals(True)
        self.filter_grade.clear()
        self.filter_grade.addItem("All Grades")
        self.filter_grade.addItems(grades)
        self.filter_grade.setCurrentText(current) if current in grades else self.filter_grade.setCurrentIndex(0)
        self.filter_grade.blockSignals(False)

    def render_student_list(self):
        rows = self._student_list_rows
        self.list_widget.clear()
        if self.student_list_mode == "areas":
            selected_area = self.area_select.currentText().strip()
            if not selected_area or selected_area == "Choose Area":
                self.show_area_choice_prompt()
                return
            self.back_to_areas_btn.setVisible(True)
        else:
            self.back_to_areas_btn.setVisible(False)
        for student in rows:
            self._add_student_list_item(student)
        noun = "student" if len(rows) == 1 else "students"
        prefix = self.area_select.currentText() if self.student_list_mode == "areas" else "All Students"
        self.count_label.setText(f"{prefix} - {len(rows)} {noun}")

    def _render_students_by_area(self, rows):
        grouped = defaultdict(list)
        for student in rows:
            area = (student.get("area") or "No Area").strip() or "No Area"
            grouped[area].append(student)
        for area in sorted(grouped):
            students = sorted(grouped[area], key=lambda s: ((s.get("last_name") or "").lower(), (s.get("first_name") or "").lower()))
            header = QListWidgetItem(f"{area}  ({len(students)})")
            header.setData(Qt.ItemDataRole.UserRole, None)
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            header.setForeground(theme_color("text_primary"))
            header.setBackground(theme_color("primary_soft"))
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self.list_widget.addItem(header)
            for student in students:
                self._add_student_list_item(student, indent=True)

    def _add_student_list_item(self, student, indent=False):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, student["id"])
        name = f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
        completion = self._student_service.profile_completion_percent(student)
        item.setToolTip(f"Open {name or 'student'} profile - {completion}% complete")
        item.setSizeHint(QSize(0, 164))
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, self._student_card_widget(student, indent))

    def _area_choice_widget(self, area, count_text):
        row = QWidget()
        row.setObjectName("AreaChoice")
        row.setFixedHeight(86)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        area_label = QLabel(area)
        area_label.setObjectName("AreaName")
        hint_label = QLabel("Open this area")
        hint_label.setObjectName("AreaHint")
        text_col.addWidget(area_label)
        text_col.addWidget(hint_label)
        count_label = QLabel(count_text)
        count_label.setObjectName("AreaCount")
        action_label = QLabel(">")
        action_label.setObjectName("AreaAction")
        layout.addLayout(text_col, 1)
        layout.addWidget(count_label)
        layout.addWidget(action_label)
        return row

    def _student_card_widget(self, student, indent=False):
        full_status, status_text, _ = self._student_service.status_style(student.get("status"))
        first = student.get("first_name") or ""
        last = student.get("last_name") or ""
        gender = str(student.get("gender") or "").strip().upper()
        grade = student.get("grade") or "--"
        sponsor = student.get("sponsor") or "--"
        area = student.get("area") or "--"
        row = QWidget()
        row.setObjectName("StudentCard")
        row.setProperty("status", {"Active": "active", "Inactive/Removed": "inactive", "Graduated": "graduated"}.get(full_status, "inactive"))
        row.setFixedHeight(144)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(32 if indent else 16, 12, 16, 12)
        layout.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        dot = QLabel()
        dot.setObjectName("StatusDot")
        dot.setFixedSize(12, 16)
        name_text = f"{last}, {first}".strip(", ")
        if gender:
            name_text += f" ({gender})"
        name_label = QLabel(name_text or "Unnamed student")
        name_label.setObjectName("StudentName")
        name_label.setWordWrap(True)
        name_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        name_row.addWidget(name_label, 1)
        text_col.addLayout(name_row)
        meta_label = QLabel(f"Sponsor: {sponsor}    Area: {area}")
        meta_label.setObjectName("StudentMeta")
        meta_label.setWordWrap(True)
        text_col.addWidget(meta_label)
        grade_badge = QLabel(str(grade))
        grade_badge.setObjectName("GradeBadge")
        grade_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grade_badge.setFixedHeight(30)
        status_badge = QLabel(status_text)
        status_badge.setObjectName("StudentBadge")
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_badge.setFixedHeight(30)
        completion_ring = _CircularProgress(size=44)
        completion_ring.set_value(self._student_service.profile_completion_percent(student))
        completion_ring.setToolTip(f"Profile completion: {completion_ring.value}%")
        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.addWidget(grade_badge)
        badges.addWidget(status_badge)
        badges.addWidget(completion_ring)
        badges.addStretch()
        text_col.addLayout(badges)
        text_col.addStretch()
        layout.addLayout(text_col, 1)
        remarks = " ".join(str(student.get("remarks") or "").split())
        remarks_panel = QWidget()
        remarks_panel.setObjectName("RemarksPanel")
        remarks_panel.setMinimumWidth(300)
        remarks_panel.setMaximumWidth(500)
        remarks_layout = QVBoxLayout(remarks_panel)
        remarks_layout.setContentsMargins(12, 8, 12, 8)
        remarks_layout.setSpacing(4)
        remarks_title = QLabel("Remarks")
        remarks_title.setObjectName("RemarksTitle")
        remarks_text = QLabel(remarks or "No remarks")
        remarks_text.setObjectName("RemarksText")
        remarks_text.setWordWrap(True)
        remarks_text.setMaximumHeight(54)
        remarks_text.setToolTip(remarks or "No remarks")
        if not remarks:
            remarks_text.setProperty("empty", True)
        remarks_layout.addWidget(remarks_title)
        remarks_layout.addWidget(remarks_text, 1)
        layout.addWidget(remarks_panel, 2)
        return row

    def _on_student_click(self, item):
        item_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(item_data, tuple) and len(item_data) == 2 and item_data[0] == "area":
            area = item_data[1]
            self._status_message(f"Loading students in {area}...", 2500)
            area_index = self.area_select.findText(area)
            self.area_select.blockSignals(True)
            self.area_select.setCurrentIndex(area_index) if area_index >= 0 else self.area_select.setCurrentText(area)
            self.area_select.blockSignals(False)
            self.load_student_list()
            return
        if item_data:
            self.student_selected.emit(str(item_data))

    def export_all_students_to_excel(self):
        old = (self.student_list_mode, self.filter_status.currentText(), self.search_name.text(), self.search_sponsor.text(), self.filter_grade.currentText(), self.area_select.currentText())
        widgets = (self.filter_status, self.search_name, self.search_sponsor, self.filter_grade, self.area_select)
        try:
            for widget in widgets:
                widget.blockSignals(True)
            self.student_list_mode = "all"
            self.filter_status.setCurrentText("All")
            self.search_name.clear()
            self.search_sponsor.clear()
            self.filter_grade.setCurrentText("All Grades")
            self.export_to_excel()
        finally:
            self.student_list_mode, status, name, sponsor, grade, area = old
            self.filter_status.setCurrentText(status)
            self.search_name.setText(name)
            self.search_sponsor.setText(sponsor)
            self.filter_grade.setCurrentText(grade)
            area_index = self.area_select.findText(area)
            if area and area_index >= 0:
                self.area_select.setCurrentIndex(area_index)
            for widget in widgets:
                widget.blockSignals(False)

    def export_to_excel(self):
        try:
            columns = "last_name,first_name,gender,grade,address,city,area,birthday,sponsor,contact,school,parents,course,remarks,status"
            name_q = self.search_name.text().strip()
            sponsor_q = self.search_sponsor.text().strip()
            area_q = self.area_select.currentText().strip() if self.student_list_mode == "areas" else ""
            rows = self.student_repository.search_students(
                columns=columns, name_query=name_q or None, sponsor_query=sponsor_q or None,
                area=area_q if area_q and area_q != "Choose Area" else None,
                area_exact=True, order_by=["area", "last_name"],
            )
            rows = self.student_list_service.filter_rows(
                self._filter_current_rows(rows),
                status=self.filter_status.currentText(), grade=self.filter_grade.currentText(),
            )
            if not rows:
                QMessageBox.information(self, "Export", "No students to export with current filters.")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Save Excel File", "SSM_Students_Export.xlsx", "Excel Files (*.xlsx)")
            if not path:
                return
            exported = self.student_excel_service.export_students(rows, path)
            QMessageBox.information(self, "Export Complete", f"Exported {exported} students to:\n{path}")
            self._status_message(f"Exported {exported} students", 5000)
        except Exception as error:
            QMessageBox.critical(self, "Export Failed", f"({type(error).__name__}) {error}")

    def import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Excel File", "", "Excel Files (*.xlsx *.xls)")
        if not path:
            return
        try:
            sheet_name, imported = self.student_excel_service.import_students(path)
            QMessageBox.information(self, "Import Complete", f"Imported {imported} students from '{sheet_name}'.")
            self.load_student_list()
            self.students_changed.emit()
        except Exception as error:
            QMessageBox.critical(self, "Import Failed", f"({type(error).__name__}) {error}")
