"""Standalone student-list screen."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from PyQt6.QtCore import QItemSelectionModel, QTimer, Qt, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListView, QListWidget, QListWidgetItem, QMessageBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from office_app.ui import ActionButton, Card, EmptyState, theme_color
from office_app.ui.views.student_list_model import (
    StudentCardDelegate, StudentListModel, StudentSkeleton,
)
from office_app.utils.background_tasks import BackgroundTask


class StudentListView(QWidget):
    student_selected = pyqtSignal(str)
    students_changed = pyqtSignal()
    students_imported = pyqtSignal(int)

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
        self._area_request = 0
        self._grade_request = 0
        self.student_list_mode = "all"
        self._student_list_rows = []
        self._area_options = []
        self._area_counts = {}
        self._selected_area = ""
        self._page_size = 50
        self._page_offset = 0
        self._loading_page = False
        self._setup_ui()

    @staticmethod
    def _secondary_button(text):
        button = ActionButton(text, variant="secondary")
        button.setObjectName("SecondaryBtn")
        return button

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        filter_card = Card()
        filters = QVBoxLayout(filter_card)
        filters.setContentsMargins(12, 10, 12, 10)
        filters.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_name = QLineEdit()
        self.search_name.setPlaceholderText("Search name")
        self.search_name.setMinimumWidth(180)
        self.search_sponsor = QLineEdit()
        self.search_sponsor.setPlaceholderText("Filter sponsor")
        self.search_sponsor.setMinimumWidth(180)
        search_row.addWidget(self.search_name, 1)
        search_row.addWidget(self.search_sponsor, 1)

        self.filter_grade = QComboBox()
        self.filter_grade.addItem("All Grades")
        self.filter_grade.setMinimumWidth(120)
        self.filter_status = QComboBox()
        self.filter_status.addItems(["All", "Active", "Inactive/Removed", "Graduated"])
        self.filter_status.setMinimumWidth(150)
        search_row.addWidget(self.filter_grade)
        search_row.addWidget(self.filter_status)

        clear_btn = self._secondary_button("Clear")
        refresh_btn = self._secondary_button("Refresh")
        self.import_btn = self._secondary_button("Import")
        self.export_btn = self._secondary_button("Export")
        for button in (clear_btn, refresh_btn, self.import_btn, self.export_btn):
            button.setProperty("density", "compact")
            search_row.addWidget(button)
        clear_btn.clicked.connect(self.clear_student_filters)
        refresh_btn.clicked.connect(self.load_student_list)
        self.import_btn.clicked.connect(self.import_from_excel)
        self.export_btn.clicked.connect(self.export_to_excel)
        filters.addLayout(search_row)
        layout.addWidget(filter_card)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.load_student_list)
        self.search_name.textChanged.connect(self._search_timer.start)
        self.search_sponsor.textChanged.connect(self._search_timer.start)
        self.filter_grade.currentTextChanged.connect(self.load_student_list)
        self.filter_status.currentTextChanged.connect(self.load_student_list)

        # Kept as a hidden compatibility control for export state restoration.
        self.area_select = QComboBox()
        self.area_select.addItem("All Areas")
        self.area_select.hide()

        self.count_label = QLabel("Students")
        self.count_label.setObjectName("CountBanner")
        self.count_label.setMinimumHeight(36)
        layout.addWidget(self.count_label)

        content = QHBoxLayout()
        content.setSpacing(10)
        facet_card = Card(shadow=False)
        facet_card.setObjectName("AreaFacetCard")
        facet_card.setFixedWidth(190)
        facet_layout = QVBoxLayout(facet_card)
        facet_layout.setContentsMargins(8, 10, 8, 8)
        facet_layout.setSpacing(6)
        facet_title = QLabel("Areas")
        facet_title.setObjectName("CardTitle")
        facet_layout.addWidget(facet_title)
        self.area_facet = QListWidget()
        self.area_facet.setObjectName("AreaFacet")
        self.area_facet.setFrameShape(QFrame.Shape.NoFrame)
        self.area_facet.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area_facet.itemClicked.connect(self._on_area_selected)
        facet_layout.addWidget(self.area_facet, 1)
        content.addWidget(facet_card)

        self.student_model = StudentListModel(self)
        self.student_model.fetch_more_requested.connect(lambda: self._load_page(reset=False))
        self.list_widget = QListView()
        self.list_widget.setObjectName("StudentList")
        self.list_widget.setModel(self.student_model)
        self.list_widget.setItemDelegate(StudentCardDelegate(self.list_widget))
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_widget.clicked.connect(self._on_student_index)
        self.list_widget.activated.connect(self._on_student_index)

        self.loading_state = StudentSkeleton()
        self.empty_state = EmptyState(
            "No students found",
            "No students match the current filters. Try clearing a filter or choosing another area.",
            shadow=False,
        )
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self.list_widget)
        self.results_stack.addWidget(self.loading_state)
        self.results_stack.addWidget(self.empty_state)
        content.addWidget(self.results_stack, 1)
        layout.addLayout(content, 1)

        self.results_stack.setCurrentWidget(self.loading_state)
        self.refresh_area_dropdown()

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

    def load_student_list(self, *_args, reset=True):
        if not reset:
            return self._load_page(reset=False)
        self._search_timer.stop()
        self._student_list_request += 1
        self._page_offset = 0
        self._student_list_rows = []
        self.student_model.reset_rows([], has_more=False)
        self.results_stack.setCurrentWidget(self.loading_state)
        return self._load_page(reset=True, request_id=self._student_list_request)

    def _load_page(self, *, reset=False, request_id=None):
        if self._loading_page and not reset:
            return None
        request_id = self._student_list_request if request_id is None else request_id
        offset = 0 if reset else self._page_offset
        name_q = self.search_name.text().strip()
        sponsor_q = self.search_sponsor.text().strip()
        area_q = self._selected_area
        status = self.filter_status.currentText()
        grade = self.filter_grade.currentText()
        columns = (
            "id,last_name,first_name,birthday,gender,grade,sponsor,area,status,"
            "address,city,contact,school,parents,course,photo_url,remarks"
        )
        self._loading_page = True
        self.student_model.set_loading(True)
        self._status_message("Loading students...", 30000)

        def fetch_rows():
            return self.student_repository.search_students(
                columns=columns,
                name_query=name_q or None,
                sponsor_query=sponsor_q or None,
                area=area_q or None,
                area_exact=True,
                order_by=["area", "last_name", "id"],
                limit=self._page_size,
                offset=offset,
            )

        def apply_rows(raw_rows):
            if request_id != self._student_list_request:
                return
            self._loading_page = False
            filtered = self.student_list_service.filter_rows(
                self._filter_current_rows(raw_rows), status=status, grade=grade,
            )
            rows = []
            for student in filtered:
                row = dict(student)
                full_status, status_text, _ = self._student_service.status_style(row.get("status"))
                row["_full_status"] = full_status
                row["_status_text"] = status_text
                row["_completion"] = self._student_service.profile_completion_percent(row)
                rows.append(row)

            has_more = len(raw_rows) == self._page_size
            self._page_offset = offset + len(raw_rows)
            if reset:
                self._student_list_rows = rows
                self.student_model.reset_rows(rows, has_more=has_more)
            else:
                self._student_list_rows.extend(rows)
                self.student_model.append_rows(rows, has_more=has_more)
            if self.student_model.rowCount() == 0 and has_more:
                self.results_stack.setCurrentWidget(self.loading_state)
                self._status_message("Searching the next page for matching students...", 30000)
                QTimer.singleShot(0, lambda: self._load_page(reset=False))
                return
            self.render_student_list()
            self._status_message(f"Loaded {self.student_model.rowCount()} students", 3000)

        def show_error(error):
            if request_id != self._student_list_request:
                return
            self._loading_page = False
            self.student_model.append_rows([], has_more=False)
            if self.student_model.rowCount() == 0:
                self.empty_state.title_label.setText("Could not load students")
                self.empty_state.description_label.setText(error.strip().splitlines()[-1])
                self.results_stack.setCurrentWidget(self.empty_state)
            self._status_message(f"Load error: {error.strip().splitlines()[-1]}", 8000)

        return self._run_background(fetch_rows, apply_rows, show_error)

    def clear_student_filters(self):
        for widget in (self.search_name, self.search_sponsor, self.filter_grade, self.filter_status):
            widget.blockSignals(True)
        self.search_name.clear()
        self.search_sponsor.clear()
        self.filter_grade.setCurrentIndex(0)
        self.filter_status.setCurrentIndex(0)
        for widget in (self.search_name, self.search_sponsor, self.filter_grade, self.filter_status):
            widget.blockSignals(False)
        self._select_area("", reload=False)
        self.load_student_list()

    def refresh_area_dropdown(self):
        current = self._selected_area
        self._area_request += 1
        request_id = self._area_request

        def fetch_options():
            rows = self.student_repository.list_students(columns="last_name,first_name,birthday,area")
            counts = self.student_list_service.area_counts(self._filter_current_rows(rows))
            return sorted(counts), counts

        def apply_options(result):
            if request_id != self._area_request:
                return
            self._area_options, self._area_counts = result
            self.area_facet.clear()
            total = sum(self._area_counts.values())
            all_item = QListWidgetItem(f"All Students  ({total})")
            all_item.setData(Qt.ItemDataRole.UserRole, "")
            self.area_facet.addItem(all_item)
            self.area_select.blockSignals(True)
            self.area_select.clear()
            self.area_select.addItem("All Areas")
            for area in self._area_options:
                item = QListWidgetItem(f"{area}  ({self._area_counts[area]})")
                item.setData(Qt.ItemDataRole.UserRole, area)
                item.setToolTip(f"Filter students in {area}")
                self.area_facet.addItem(item)
                self.area_select.addItem(area)
            self.area_select.blockSignals(False)
            target = current if current in self._area_options else ""
            self._select_area(target, reload=False)
            if self.student_model.rowCount() == 0 and not self._loading_page:
                self.load_student_list()

        def show_error(error):
            if request_id == self._area_request:
                self._status_message(f"Area load error: {error.strip().splitlines()[-1]}", 8000)

        return self._run_background(fetch_options, apply_options, show_error)

    def refresh_grade_filter(self):
        current = self.filter_grade.currentText()
        self._grade_request += 1
        request_id = self._grade_request

        def fetch_options():
            rows = self.student_repository.list_students(columns="last_name,first_name,birthday,grade")
            return self.student_list_service.grade_options(self._filter_current_rows(rows))

        def apply_options(grades):
            if request_id != self._grade_request:
                return
            self.filter_grade.blockSignals(True)
            self.filter_grade.clear()
            self.filter_grade.addItem("All Grades")
            self.filter_grade.addItems(grades)
            self.filter_grade.setCurrentText(current) if current in grades else self.filter_grade.setCurrentIndex(0)
            self.filter_grade.blockSignals(False)

        def show_error(error):
            if request_id == self._grade_request:
                self._status_message(f"Grade load error: {error.strip().splitlines()[-1]}", 8000)

        return self._run_background(fetch_options, apply_options, show_error)

    def refresh_filter_options(self):
        area_task = self.refresh_area_dropdown()
        self.refresh_grade_filter()
        return area_task

    def _on_area_selected(self, item):
        self._select_area(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _select_area(self, area, *, reload=True):
        self._selected_area = area
        self.student_list_mode = "areas" if area else "all"
        index = self.area_select.findText(area) if area else 0
        if index >= 0:
            self.area_select.setCurrentIndex(index)
        for row in range(self.area_facet.count()):
            item = self.area_facet.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == area:
                self.area_facet.setCurrentItem(
                    item, QItemSelectionModel.SelectionFlag.ClearAndSelect
                )
                break
        if reload:
            self.load_student_list()

    def set_student_list_mode(self, mode):
        if mode == "all":
            self._select_area("")
        elif mode == "areas":
            self.area_facet.setFocus()

    def back_to_area_choices(self):
        self._select_area("")

    def show_student_view_prompt(self):
        self.load_student_list()

    def show_area_choice_prompt(self):
        self.area_facet.setFocus()

    def render_student_list(self):
        count = self.student_model.rowCount()
        has_more = self.student_model.has_more
        if count:
            self.results_stack.setCurrentWidget(self.list_widget)
        elif not self._loading_page:
            self.empty_state.title_label.setText("No students found")
            area_text = f" in {self._selected_area}" if self._selected_area else ""
            self.empty_state.description_label.setText(
                f"No students{area_text} match the current filters. Try clearing a filter."
            )
            self.results_stack.setCurrentWidget(self.empty_state)
        noun = "student" if count == 1 else "students"
        area_label = self._selected_area or "All Students"
        suffix = " — scroll for more" if has_more else ""
        self.count_label.setText(f"{area_label} · {count} {noun} loaded{suffix}")

    def _on_student_index(self, index):
        student_id = index.data(Qt.ItemDataRole.UserRole)
        if student_id:
            self.student_selected.emit(str(student_id))

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
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel File", "SSM_Students_Export.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return None
        columns = "last_name,first_name,gender,grade,address,city,area,birthday,sponsor,contact,school,parents,course,remarks,status"
        name_q = self.search_name.text().strip()
        sponsor_q = self.search_sponsor.text().strip()
        area_q = self.area_select.currentText().strip() if self.student_list_mode == "areas" else ""
        status = self.filter_status.currentText()
        grade = self.filter_grade.currentText()
        self.export_btn.setEnabled(False)
        self._status_message("Exporting students...", 30000)

        def export():
            rows = self.student_repository.search_students(
                columns=columns, name_query=name_q or None, sponsor_query=sponsor_q or None,
                area=area_q if area_q and area_q != "Choose Area" else None,
                area_exact=True, order_by=["area", "last_name", "id"],
            )
            rows = self.student_list_service.filter_rows(
                self._filter_current_rows(rows),
                status=status, grade=grade,
            )
            if not rows:
                return 0
            return self.student_excel_service.export_students(rows, path)

        def exported(count):
            self.export_btn.setEnabled(True)
            if not count:
                QMessageBox.information(self, "Export", "No students to export with current filters.")
                return
            QMessageBox.information(self, "Export Complete", f"Exported {count} students to:\n{path}")
            self._status_message(f"Exported {count} students", 5000)

        def failed(error):
            self.export_btn.setEnabled(True)
            QMessageBox.critical(self, "Export Failed", error.strip().splitlines()[-1])

        return self._run_background(export, exported, failed)

    def import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Excel File", "", "Excel Files (*.xlsx)")
        if not path:
            return None
        self.import_btn.setEnabled(False)
        self._status_message("Importing students...", 30000)

        def import_students():
            return self.student_excel_service.import_students(path)

        def imported(result):
            self.import_btn.setEnabled(True)
            sheet_name, count = result
            QMessageBox.information(self, "Import Complete", f"Imported {count} students from '{sheet_name}'.")
            self.students_imported.emit(count)
            self.students_changed.emit()

        def failed(error):
            self.import_btn.setEnabled(True)
            QMessageBox.critical(self, "Import Failed", error.strip().splitlines()[-1])

        return self._run_background(import_students, imported, failed)
