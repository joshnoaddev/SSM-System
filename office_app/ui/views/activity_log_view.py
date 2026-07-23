"""Searchable operational activity log workspace."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Dict, List

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from office_app.ui import ActionButton, Card, EmptyState


class ActivityLogView(QWidget):
    def __init__(
        self,
        repository: Any,
        run_background: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.run_background = run_background
        self._rows: List[Dict[str, Any]] = []
        self._request_id = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        tools = Card()
        tools.setFixedHeight(72)
        tools_layout = QHBoxLayout(tools)
        tools_layout.setContentsMargins(16, 12, 16, 12)
        tools_layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search operator, action, record, or details")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search activity log")
        self.search.textChanged.connect(self._apply_filters)
        self.action_filter = QComboBox()
        self.action_filter.addItem("All actions")
        self.action_filter.currentTextChanged.connect(self._apply_filters)
        self.record_filter = QComboBox()
        self.record_filter.addItem("All record types")
        self.record_filter.currentTextChanged.connect(self._apply_filters)
        self.refresh_button = ActionButton("Refresh", variant="secondary")
        self.refresh_button.clicked.connect(self.load_events)
        tools_layout.addWidget(self.search, 2)
        tools_layout.addWidget(self.action_filter, 1)
        tools_layout.addWidget(self.record_filter, 1)
        tools_layout.addWidget(self.refresh_button)
        layout.addWidget(tools)

        table_card = Card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(10)
        heading_row = QHBoxLayout()
        heading = QLabel("Office activity")
        heading.setObjectName("CardHeading")
        self.count_label = QLabel("0 events")
        self.count_label.setObjectName("Caption")
        heading_row.addWidget(heading)
        heading_row.addWidget(self.count_label)
        heading_row.addStretch()
        table_layout.addLayout(heading_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Operator", "Action", "Record type", "Record", "Details"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAccessibleName("Office activity log")
        header = self.table.horizontalHeader()
        widths = [150, 92, 118, 94, 100]
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        self.empty = EmptyState(
            "No activity to show",
            "Activity appears here as office workers update shared records.",
        )
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)
        table_layout.addWidget(self.stack, 1)
        layout.addWidget(table_card, 1)

    def load_events(self):
        self._request_id += 1
        request_id = self._request_id
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Refreshing…")
        self.count_label.setText("Loading…")

        def loaded(rows):
            if request_id != self._request_id:
                return
            self._rows = list(rows or [])
            self._rebuild_filters()
            self._apply_filters()
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh")

        def failed(_error):
            if request_id != self._request_id:
                return
            self._rows = []
            self.count_label.setText("Unavailable")
            self.empty.title_label.setText("Activity log unavailable")
            self.empty.description_label.setText(
                "Check the office connection, then refresh this view."
            )
            self.stack.setCurrentWidget(self.empty)
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Refresh")

        return self.run_background(self.repository.list_events, loaded, failed)

    def _rebuild_filters(self) -> None:
        current_action = self.action_filter.currentText()
        current_record = self.record_filter.currentText()
        actions = sorted(
            {str(row.get("action") or "").strip() for row in self._rows if row.get("action")}
        )
        records = sorted(
            {
                str(row.get("entity_type") or "").strip()
                for row in self._rows
                if row.get("entity_type")
            }
        )
        self.action_filter.blockSignals(True)
        self.record_filter.blockSignals(True)
        self.action_filter.clear()
        self.action_filter.addItems(["All actions", *actions])
        self.record_filter.clear()
        self.record_filter.addItems(["All record types", *records])
        self.action_filter.setCurrentText(
            current_action if current_action in actions else "All actions"
        )
        self.record_filter.setCurrentText(
            current_record if current_record in records else "All record types"
        )
        self.action_filter.blockSignals(False)
        self.record_filter.blockSignals(False)

    def _apply_filters(self, *_args) -> None:
        query = self.search.text().strip().casefold()
        action = self.action_filter.currentText()
        record_type = self.record_filter.currentText()
        visible = []
        for row in self._rows:
            if action != "All actions" and row.get("action") != action:
                continue
            if (
                record_type != "All record types"
                and row.get("entity_type") != record_type
            ):
                continue
            details = json.dumps(row.get("details") or {}, ensure_ascii=False)
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("operator", "action", "entity_type", "entity_id")
            )
            if query and query not in f"{haystack} {details}".casefold():
                continue
            visible.append(row)
        self._render(visible)

    def _render(self, rows: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        for row_index, event in enumerate(rows):
            self.table.insertRow(row_index)
            created_at = str(event.get("created_at") or "")
            try:
                parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                created_at = parsed.astimezone().strftime("%b %d, %Y  %I:%M %p")
            except ValueError:
                pass
            details = event.get("details") or {}
            details_text = ", ".join(
                f"{str(key).replace('_', ' ').title()}: {value}"
                for key, value in details.items()
            )
            values = [
                created_at,
                event.get("operator") or "System",
                str(event.get("action") or "").replace("_", " ").title(),
                str(event.get("entity_type") or "").replace("_", " ").title(),
                event.get("entity_id") or "—",
                details_text or "—",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row_index, column, item)
        self.count_label.setText(f"{len(rows)} event{'s' if len(rows) != 1 else ''}")
        self.stack.setCurrentWidget(self.table if rows else self.empty)
