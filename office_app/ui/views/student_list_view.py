"""Standalone student-list screen."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from PyQt6.QtCore import QItemSelectionModel, QSize, QTimer, Qt, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QListView,
    QLabel, QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget,
)

from office_app.ui.fluent import (
    BodyLabel, CardWidget, ComboBox, LineEdit, ListWidget, MessageBox,
    PushButton, StrongBodyLabel, TitleLabel,
)
from office_app.ui.components import ActionButton, set_content_hugging_button
from office_app.ui import theme_color
from office_app.ui.views.student_list_model import (
    StudentCardDelegate, StudentListModel, StudentSkeleton,
)
from office_app.utils.background_tasks import BackgroundTask


class StudentListView(QWidget):
    student_selected = pyqtSignal(str)
    new_student_requested = pyqtSignal()
    students_changed = pyqtSignal()
    students_imported = pyqtSignal(int)

    def __init__(
        self,
        student_repository,
        student_list_service,
        student_excel_service,
        run_background_fn: Callable | None = None,
        *,
        expense_service=None,
        filter_current_rows_fn: Callable[[Sequence[Mapping[str, Any]]], list] | None = None,
        status_message_fn: Callable[[str, int], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.student_repository = student_repository
        self.student_list_service = student_list_service
        self.student_excel_service = student_excel_service
        self.expense_service = expense_service
        self._student_service = student_list_service.student_service
        self._run_background_fn = run_background_fn
        self._filter_current_rows = filter_current_rows_fn or (lambda rows: list(rows))
        self._status_message = status_message_fn or (lambda _message, _timeout=0: None)
        self._thread_pool = QThreadPool(self) if run_background_fn is None else None
        self._student_list_request = 0
        self._area_request = 0
        self._grade_request = 0
        self._sponsor_request = 0
        self.student_list_mode = "all"
        self._student_list_rows = []
        self._area_options = []
        self._area_counts = {}
        self._selected_area = ""
        self._page_size = 50
        self._page_offset = 0
        self._loading_page = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        filter_bar = QFrame()
        filter_bar.setObjectName("StudentFilterBar")
        filters = QVBoxLayout(filter_bar)
        filters.setContentsMargins(0, 0, 0, 8)
        filters.setSpacing(10)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_name = LineEdit()
        self.search_name.setPlaceholderText("Search students")
        self.search_name.setAccessibleName("Search students by name")
        self.search_name.setClearButtonEnabled(True)
        self.search_name.setMinimumWidth(190)
        self.search_name.setMaximumWidth(430)
        self.search_name.setFixedHeight(38)
        self.search_sponsor = LineEdit()
        self.search_sponsor.setPlaceholderText("Search sponsors")
        self.search_sponsor.setAccessibleName("Search students by sponsor")
        self.search_sponsor.setClearButtonEnabled(True)
        self.search_sponsor.hide()

        self.filter_grade = ComboBox()
        self.filter_grade.addItem(self.student_list_service.ALL_GRADES)
        self.filter_grade.setAccessibleName("Filter students by grade")
        self.filter_grade.setFixedWidth(128)
        self.filter_grade.setFixedHeight(38)
        self.filter_status = ComboBox()
        self.filter_status.addItem("All statuses", "All")
        self.filter_status.addItem("Active", "Active")
        self.filter_status.addItem("Inactive", "Inactive/Removed")
        self.filter_status.addItem("Graduated", "Graduated")
        self.filter_status.setAccessibleName("Filter students by status")
        self.filter_status.setFixedWidth(148)
        self.filter_status.setFixedHeight(38)

        self.sponsor_select = ComboBox()
        self.sponsor_select.addItem("All sponsors", "")
        self.sponsor_select.setAccessibleName("Filter students by sponsor")
        self.sponsor_select.setAccessibleDescription(
            "Choose a sponsor name to show only their students."
        )
        self.sponsor_select.setFixedWidth(240)
        self.sponsor_select.setFixedHeight(34)
        self.sponsor_select.setToolTip("Choose a sponsor name")

        # Last-name ordering remains the stable directory default. The former
        # Sponsor sort is now the sponsor-name filter users expected.
        self.sort_select = ComboBox()
        self.sort_select.addItem(
            "Last name", self.student_list_service.SORT_LAST_NAME,
        )
        self.sort_select.hide()

        clear_btn = ActionButton("Clear", variant="tertiary")
        refresh_btn = ActionButton("Refresh", variant="tertiary")
        self.import_btn = ActionButton("Import", variant="tertiary")
        self.export_btn = ActionButton("Export", variant="secondary")
        self.new_student_btn = ActionButton("+  New student")
        for button in (
            clear_btn, refresh_btn, self.import_btn,
            self.export_btn, self.new_student_btn,
        ):
            button.setProperty("density", "compact")
            set_content_hugging_button(button, height=38)

        search_row.addWidget(self.search_name, 1)
        search_row.addWidget(self.filter_status)
        search_row.addWidget(self.filter_grade)
        search_row.addStretch(1)
        search_row.addWidget(self.new_student_btn)
        search_row.addWidget(self.export_btn)
        filters.addLayout(search_row)
        layout.addWidget(filter_bar)

        clear_btn.setToolTip("Reset all student filters")
        refresh_btn.setToolTip("Reload the current result set")
        self.import_btn.setToolTip("Import student records from an Excel workbook")
        self.export_btn.setToolTip("Export the filtered student list to Excel")
        results_toolbar = QFrame()
        results_toolbar.setObjectName("StudentResultsToolbar")
        actions_row = QHBoxLayout(results_toolbar)
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(6)
        self.count_label = BodyLabel("All students")
        self.count_label.setObjectName("StudentDirectoryLabel")
        actions_row.addWidget(self.count_label)
        actions_row.addStretch(1)
        sponsor_label = QLabel("Sponsor")
        sponsor_label.setObjectName("Caption")
        sponsor_label.setBuddy(self.sponsor_select)
        actions_row.addWidget(sponsor_label)
        actions_row.addWidget(self.sponsor_select)
        # Clear and refresh are covered by the search affordance and shared
        # page header. Import remains callable from Workbook without adding a
        # second, visually noisy action cluster here.
        for button in (clear_btn, refresh_btn, self.import_btn):
            button.hide()
        clear_btn.clicked.connect(self.clear_student_filters)
        refresh_btn.clicked.connect(self.load_student_list)
        self.import_btn.clicked.connect(self.import_from_excel)
        self.export_btn.clicked.connect(self.export_to_excel)
        self.new_student_btn.clicked.connect(self.new_student_requested)
        layout.addWidget(results_toolbar)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.load_student_list)
        self.search_name.textChanged.connect(self._search_timer.start)
        self.search_sponsor.textChanged.connect(self._search_timer.start)
        self.filter_grade.currentTextChanged.connect(self.load_student_list)
        self.filter_status.currentTextChanged.connect(self.load_student_list)
        self.sponsor_select.currentIndexChanged.connect(self.load_student_list)
        self.sponsor_select.currentTextChanged.connect(
            lambda text: self.sponsor_select.setToolTip(
                text if text != "All sponsors" else "Choose a sponsor name"
            )
        )

        # Kept as a hidden compatibility control for export state restoration.
        self.area_select = ComboBox()
        self.area_select.addItem("All areas")
        self.area_select.hide()

        content = QHBoxLayout()
        content.setSpacing(0)
        facet_card = CardWidget()
        self.area_facet_card = facet_card
        facet_card.setObjectName("AreaFacetCard")
        facet_card.setFixedWidth(174)
        facet_card.setFixedHeight(280)
        facet_layout = QVBoxLayout(facet_card)
        facet_layout.setContentsMargins(8, 10, 8, 8)
        facet_layout.setSpacing(6)
        facet_title = StrongBodyLabel("Areas")
        facet_title.setObjectName("CardTitle")
        facet_layout.addWidget(facet_title)
        self.area_facet = ListWidget()
        self.area_facet.setObjectName("AreaFacet")
        self.area_facet.setAccessibleName("Filter students by area")
        self.area_facet.setAccessibleDescription(
            "Choose an area to limit the student directory."
        )
        self.area_facet.setFrameShape(QFrame.Shape.NoFrame)
        self.area_facet.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area_facet.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.area_facet.itemClicked.connect(self._on_area_selected)
        facet_layout.addWidget(self.area_facet, 1)
        facet_card.hide()

        self.student_model = StudentListModel(self)
        self.student_model.fetch_more_requested.connect(lambda: self._load_page(reset=False))
        self.list_widget = QListView()
        self.list_widget.setObjectName("StudentList")
        self.list_widget.setAccessibleName("Student records")
        self.list_widget.setAccessibleDescription(
            "Select a student row to open the complete profile."
        )
        self.list_widget.setModel(self.student_model)
        self.list_widget.setItemDelegate(StudentCardDelegate(self.list_widget))
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_widget.clicked.connect(self._on_student_index)
        self.list_widget.activated.connect(self._on_student_index)

        self.loading_state = StudentSkeleton()
        self.empty_state = CardWidget()
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.title_label = TitleLabel("No students found")
        self.empty_state.description_label = BodyLabel(
            "No students match the current filters. Try clearing a filter or choosing another area."
        )
        self.empty_state.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.description_label.setWordWrap(True)
        self.empty_state_action = PushButton("Clear filters")
        set_content_hugging_button(self.empty_state_action)
        self.empty_state_action.clicked.connect(self._run_empty_state_action)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self.empty_state.title_label)
        empty_layout.addWidget(self.empty_state.description_label)
        empty_layout.addWidget(
            self.empty_state_action,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        empty_layout.addStretch(1)
        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self.list_widget)
        self.results_stack.addWidget(self.loading_state)
        self.results_stack.addWidget(self.empty_state)
        results_card = QFrame()
        results_card.setObjectName("StudentTableCard")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(10, 10, 10, 0)
        results_layout.setSpacing(0)
        table_header = QFrame()
        table_header.setObjectName("StudentTableHeader")
        table_header.setFixedHeight(36)
        table_header_layout = QHBoxLayout(table_header)
        table_header_layout.setContentsMargins(14, 0, 14, 0)
        table_header_layout.setSpacing(0)
        for heading, stretch in (
            ("STUDENT", 32),
            ("STATUS", 15),
            ("PROFILE", 16),
            ("BUDGET", 23),
            ("UPDATED", 10),
        ):
            label = QLabel(heading)
            label.setObjectName("StudentTableHeading")
            table_header_layout.addWidget(label, stretch)
        results_layout.addWidget(table_header)
        results_layout.addWidget(self.results_stack, 1)
        content.addWidget(results_card, 1)
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
        sponsor_q = (
            self.search_sponsor.text().strip()
            or str(self.sponsor_select.currentData() or "").strip()
        )
        area_q = self._selected_area
        status_text = self.filter_status.currentText()
        status = {
            "All statuses": "All",
            "Inactive": "Inactive/Removed",
        }.get(status_text, status_text)
        grade = self.filter_grade.currentText()
        order_by = self.student_list_service.sort_order(
            self.sort_select.currentData()
        )
        columns = (
            "id,last_name,first_name,birthday,gender,grade,sponsor,area,status,"
            "address,city,contact,school,parents,course,photo_url,remarks,"
            "sheet_synced_at,source_sheet_name"
        )
        self._loading_page = True
        self.student_model.set_loading(True)
        self._status_message("Loading students...", 30000)

        def fetch_rows():
            rows = self.student_repository.search_students(
                columns=columns,
                name_query=name_q or None,
                sponsor_query=sponsor_q or None,
                area=area_q or None,
                area_exact=True,
                order_by=order_by,
                limit=self._page_size,
                offset=offset,
            )
            if self.expense_service is None:
                return rows, {}

            student_ids = [row.get("id") for row in rows if row.get("id")]
            summaries = self.expense_service.get_financial_summaries(student_ids)
            return rows, summaries

        def apply_rows(result):
            if request_id != self._student_list_request:
                return
            raw_rows, summaries = result
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
                row["_grade_text"] = self._student_service.format_grade_label(
                    row.get("grade")
                )
                row["_completion"] = self._student_service.profile_completion_percent(row)
                if self.expense_service is not None:
                    row["_budget_status"] = self.expense_service.budget_card_status(
                        summaries.get(row.get("id"))
                    )
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
                self.empty_state.description_label.setText(
                    "Check the office database connection, then try again."
                )
                self.empty_state_action.setText("Try again")
                self.empty_state_action.setProperty("mode", "retry")
                self.results_stack.setCurrentWidget(self.empty_state)
            logging.getLogger(__name__).error("Student list load failed:\n%s", error)
            self._status_message("Could not load student records", 8000)

        return self._run_background(fetch_rows, apply_rows, show_error)

    def clear_student_filters(self):
        for widget in (
            self.search_name, self.search_sponsor, self.filter_grade,
            self.filter_status, self.sponsor_select, self.sort_select,
        ):
            widget.blockSignals(True)
        self.search_name.clear()
        self.search_sponsor.clear()
        self.filter_grade.setCurrentIndex(0)
        self.filter_status.setCurrentIndex(0)
        self.sponsor_select.setCurrentIndex(0)
        self.sort_select.setCurrentIndex(0)
        for widget in (
            self.search_name, self.search_sponsor, self.filter_grade,
            self.filter_status, self.sponsor_select, self.sort_select,
        ):
            widget.blockSignals(False)
        self._select_area("", reload=False)
        self.load_student_list()

    def _run_empty_state_action(self):
        if self.empty_state_action.property("mode") == "retry":
            self.load_student_list()
            return
        self.clear_student_filters()

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
            all_item = QListWidgetItem(f"All students  ({total})")
            all_item.setData(Qt.ItemDataRole.UserRole, "")
            all_item.setSizeHint(QSize(0, 42))
            self.area_facet.addItem(all_item)
            self.area_select.blockSignals(True)
            self.area_select.clear()
            self.area_select.addItem("All areas")
            for area in self._area_options:
                item = QListWidgetItem(f"{area}  ({self._area_counts[area]})")
                item.setData(Qt.ItemDataRole.UserRole, area)
                item.setToolTip(f"Filter students in {area}")
                item.setSizeHint(QSize(0, 42))
                self.area_facet.addItem(item)
                self.area_select.addItem(area)
            visible_rows = max(3, min(self.area_facet.count(), 7))
            self.area_facet_card.setFixedHeight(70 + visible_rows * 42)
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
            self.filter_grade.addItem(self.student_list_service.ALL_GRADES)
            self.filter_grade.addItems(grades)
            self.filter_grade.setCurrentText(current) if current in grades else self.filter_grade.setCurrentIndex(0)
            self.filter_grade.blockSignals(False)

        def show_error(error):
            if request_id == self._grade_request:
                self._status_message(f"Grade load error: {error.strip().splitlines()[-1]}", 8000)

        return self._run_background(fetch_options, apply_options, show_error)

    def refresh_sponsor_filter(self):
        current = str(self.sponsor_select.currentData() or "")
        self._sponsor_request += 1
        request_id = self._sponsor_request

        def fetch_options():
            rows = self.student_repository.list_students(
                columns="last_name,first_name,birthday,sponsor"
            )
            return self.student_list_service.sponsor_options(
                self._filter_current_rows(rows)
            )

        def apply_options(sponsors):
            if request_id != self._sponsor_request:
                return
            self.sponsor_select.blockSignals(True)
            self.sponsor_select.clear()
            self.sponsor_select.addItem("All sponsors", "")
            for sponsor in sponsors:
                self.sponsor_select.addItem(sponsor, sponsor)
            index = self.sponsor_select.findData(current) if current else 0
            self.sponsor_select.setCurrentIndex(max(index, 0))
            self.sponsor_select.setToolTip(
                current or "Choose a sponsor name"
            )
            self.sponsor_select.blockSignals(False)

        def show_error(error):
            if request_id == self._sponsor_request:
                self._status_message(
                    f"Sponsor load error: {error.strip().splitlines()[-1]}",
                    8000,
                )

        return self._run_background(fetch_options, apply_options, show_error)

    def refresh_filter_options(self):
        area_task = self.refresh_area_dropdown()
        self.refresh_grade_filter()
        self.refresh_sponsor_filter()
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
            self.empty_state_action.setText("Clear filters")
            self.empty_state_action.setProperty("mode", "clear")
            self.results_stack.setCurrentWidget(self.empty_state)
        noun = "student" if count == 1 else "students"
        area_label = self._selected_area
        suffix = "  ·  Scroll for more" if has_more else ""
        prefix = f"{area_label}  ·  " if area_label else ""
        self.count_label.setText(f"{prefix}{count} {noun}{suffix}")

    def _on_student_index(self, index):
        student_id = index.data(Qt.ItemDataRole.UserRole)
        if student_id:
            self.student_selected.emit(str(student_id))

    def export_all_students_to_excel(self):
        old = (
            self.student_list_mode,
            self.filter_status.currentIndex(),
            self.search_name.text(),
            self.search_sponsor.text(),
            self.filter_grade.currentText(),
            self.area_select.currentText(),
            self.sponsor_select.currentIndex(),
        )
        widgets = (
            self.filter_status,
            self.search_name,
            self.search_sponsor,
            self.filter_grade,
            self.area_select,
            self.sponsor_select,
        )
        try:
            for widget in widgets:
                widget.blockSignals(True)
            self.student_list_mode = "all"
            self.filter_status.setCurrentIndex(0)
            self.search_name.clear()
            self.search_sponsor.clear()
            self.filter_grade.setCurrentText(self.student_list_service.ALL_GRADES)
            self.sponsor_select.setCurrentIndex(0)
            self.export_to_excel()
        finally:
            (
                self.student_list_mode,
                status_index,
                name,
                sponsor,
                grade,
                area,
                sponsor_index,
            ) = old
            self.filter_status.setCurrentIndex(status_index)
            self.search_name.setText(name)
            self.search_sponsor.setText(sponsor)
            self.filter_grade.setCurrentText(grade)
            self.sponsor_select.setCurrentIndex(sponsor_index)
            area_index = self.area_select.findText(area)
            if area and area_index >= 0:
                self.area_select.setCurrentIndex(area_index)
            for widget in widgets:
                widget.blockSignals(False)

    def export_to_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel file", "SSM_Students_Export.xlsx", "Excel files (*.xlsx)"
        )
        if not path:
            return None
        columns = "last_name,first_name,gender,grade,address,city,area,birthday,sponsor,contact,school,parents,course,remarks,status"
        name_q = self.search_name.text().strip()
        sponsor_q = (
            self.search_sponsor.text().strip()
            or str(self.sponsor_select.currentData() or "").strip()
        )
        area_q = self.area_select.currentText().strip() if self.student_list_mode == "areas" else ""
        status_text = self.filter_status.currentText()
        status = {
            "All statuses": "All",
            "Inactive": "Inactive/Removed",
        }.get(status_text, status_text)
        grade = self.filter_grade.currentText()
        order_by = self.student_list_service.sort_order(
            self.sort_select.currentData()
        )
        self.export_btn.setEnabled(False)
        self._status_message("Exporting students...", 30000)

        def export():
            rows = self.student_repository.search_students(
                columns=columns, name_query=name_q or None, sponsor_query=sponsor_q or None,
                area=area_q if area_q and area_q != "Choose area" else None,
                area_exact=True, order_by=order_by,
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
                dlg = MessageBox("Export", "No students to export with current filters.", self)
                dlg.cancelButton.hide()
                dlg.exec()
                return
            dlg = MessageBox("Export complete", f"Exported {count} students to:\n{path}", self)
            dlg.cancelButton.hide()
            dlg.exec()
            self._status_message(f"Exported {count} students", 5000)

        def failed(error):
            self.export_btn.setEnabled(True)
            dlg = MessageBox("Export failed", error.strip().splitlines()[-1], self)
            dlg.cancelButton.hide()
            dlg.exec()

        return self._run_background(export, exported, failed)

    def import_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Excel file", "", "Excel files (*.xlsx)")
        if not path:
            return None
        self.import_btn.setEnabled(False)
        self._status_message("Importing students...", 30000)

        def import_students():
            return self.student_excel_service.import_students(path)

        def imported(result):
            self.import_btn.setEnabled(True)
            sheet_name, count = result
            dlg = MessageBox("Import complete", f"Imported {count} students from '{sheet_name}'.", self)
            dlg.cancelButton.hide()
            dlg.exec()
            self.students_imported.emit(count)
            self.students_changed.emit()

        def failed(error):
            self.import_btn.setEnabled(True)
            dlg = MessageBox("Import failed", error.strip().splitlines()[-1], self)
            dlg.cancelButton.hide()
            dlg.exec()

        return self._run_background(import_students, imported, failed)
