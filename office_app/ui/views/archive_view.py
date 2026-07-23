"""Recoverable archive for students and expenses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from office_app.ui import ActionButton, Card, EmptyState, set_content_hugging_button


class ArchiveView(QWidget):
    records_changed = pyqtSignal()

    def __init__(
        self,
        student_repository: Any,
        expense_repository: Any,
        run_background: Callable[..., Any],
        operator_fn: Callable[[], str],
        audit_fn: Callable[..., None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.student_repository = student_repository
        self.expense_repository = expense_repository
        self.run_background = run_background
        self.operator_fn = operator_fn
        self.audit_fn = audit_fn
        self._students: List[Dict[str, Any]] = []
        self._expenses: List[Dict[str, Any]] = []
        self._request_id = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        tools = Card()
        tools.setFixedHeight(72)
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(16, 12, 16, 12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search archived names or expense descriptions")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._render)
        self.count_label = QLabel("0 archived records")
        self.count_label.setObjectName("Caption")
        self.refresh_button = ActionButton("Refresh", variant="secondary")
        self.refresh_button.clicked.connect(self.load_records)
        tools_layout.addWidget(self.search, 1)
        tools_layout.addWidget(self.refresh_button)
        layout.addWidget(tools)

        self.tabs = QTabWidget()
        self.student_table, self.student_stack = self._make_table(
            ["Student", "Area", "Status", "Archived by", "Archived", ""],
            "No archived students",
        )
        self.expense_table, self.expense_stack = self._make_table(
            ["Description", "Amount", "School year", "Archived by", "Archived", ""],
            "No archived expenses",
        )
        self.tabs.addTab(self.student_stack, "Students")
        self.tabs.addTab(self.expense_stack, "Expenses")
        layout.addWidget(self.tabs, 1)

    @staticmethod
    def _make_table(headers, empty_title):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(56)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        empty = EmptyState(
            empty_title,
            "Records moved to the archive will appear here and can be restored.",
        )
        stack = QStackedWidget()
        stack.addWidget(table)
        stack.addWidget(empty)
        stack.setCurrentWidget(empty)
        return table, stack

    def load_records(self):
        self._request_id += 1
        request_id = self._request_id
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing…")
        self.count_label.setText("Loading…")

        def work():
            return (
                self.student_repository.list_archived_students(),
                self.expense_repository.list_archived_expenses(),
            )

        def loaded(result):
            if request_id != self._request_id:
                return
            self._students, self._expenses = result
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh")
            self._render()

        def failed(_error):
            if request_id != self._request_id:
                return
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh")
            self.count_label.setText("Archive unavailable")

        return self.run_background(work, loaded, failed)

    def _render(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        students = [
            row for row in self._students
            if not query or query in " ".join(
                str(row.get(key) or "")
                for key in ("last_name", "first_name", "area", "status", "archived_by")
            ).casefold()
        ]
        expenses = [
            row for row in self._expenses
            if not query or query in " ".join(
                str(row.get(key) or "")
                for key in ("description", "school_year", "category", "archived_by")
            ).casefold()
        ]
        self._render_students(students)
        self._render_expenses(expenses)
        total = len(students) + len(expenses)
        self.count_label.setText(
            f"{total} archived record{'s' if total != 1 else ''}"
        )
        self.tabs.setTabText(0, f"Students ({len(students)})")
        self.tabs.setTabText(1, f"Expenses ({len(expenses)})")

    @staticmethod
    def _archive_time(value: Any) -> str:
        text = str(value or "")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone().strftime("%b %d, %Y")
        except ValueError:
            return text or "—"

    def _render_students(self, rows) -> None:
        self.student_table.setRowCount(0)
        for index, student in enumerate(rows):
            self.student_table.insertRow(index)
            name = ", ".join(
                part for part in (
                    str(student.get("last_name") or "").strip(),
                    str(student.get("first_name") or "").strip(),
                ) if part
            )
            values = [
                name or "Unnamed student",
                student.get("area") or "—",
                student.get("status") or "—",
                student.get("archived_by") or "—",
                self._archive_time(student.get("archived_at")),
            ]
            for column, value in enumerate(values):
                self.student_table.setItem(index, column, QTableWidgetItem(str(value)))
            self.student_table.setCellWidget(
                index,
                5,
                self._restore_button(
                    lambda _checked=False, sid=student.get("id"): self._restore_student(sid),
                    f"Restore {name}",
                ),
            )
        self.student_stack.setCurrentWidget(
            self.student_table if rows else self.student_stack.widget(1)
        )

    def _render_expenses(self, rows) -> None:
        self.expense_table.setRowCount(0)
        for index, expense in enumerate(rows):
            self.expense_table.insertRow(index)
            try:
                amount = f"PHP {float(expense.get('amount') or 0):,.2f}"
            except (TypeError, ValueError):
                amount = "PHP 0.00"
            values = [
                expense.get("description") or "Untitled expense",
                amount,
                expense.get("school_year") or "—",
                expense.get("archived_by") or "—",
                self._archive_time(expense.get("archived_at")),
            ]
            for column, value in enumerate(values):
                self.expense_table.setItem(index, column, QTableWidgetItem(str(value)))
            self.expense_table.setCellWidget(
                index,
                5,
                self._restore_button(
                    lambda _checked=False, eid=expense.get("id"): self._restore_expense(eid),
                    f"Restore {values[0]}",
                ),
            )
        self.expense_stack.setCurrentWidget(
            self.expense_table if rows else self.expense_stack.widget(1)
        )

    @staticmethod
    def _restore_button(callback, accessible_name):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        button = ActionButton("Restore", variant="secondary")
        set_content_hugging_button(button, min_width=76, height=40)
        button.setAccessibleName(accessible_name)
        button.clicked.connect(callback)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        return container

    def _restore_student(self, student_id) -> None:
        if not student_id:
            return

        def done(_rows):
            self.audit_fn("restore", "student", student_id)
            self.records_changed.emit()
            self.load_records()

        self.run_background(
            lambda: self.student_repository.restore_student(student_id),
            done,
        )

    def _restore_expense(self, expense_id) -> None:
        if not expense_id:
            return

        def done(_rows):
            self.audit_fn("restore", "expense", expense_id)
            self.records_changed.emit()
            self.load_records()

        self.run_background(
            lambda: self.expense_repository.restore_expense(expense_id),
            done,
        )
