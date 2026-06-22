from __future__ import annotations

import unittest
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtWidgets import QMessageBox
from app import StudentApp
from office_app.repositories.student_repository import StudentRepository
from office_app.services.expense_service import ExpenseService
from office_app.services.student_excel_service import StudentExcelService
from office_app.services.workbook_import_service import WorkbookImportService
from office_app.ui.views.student_list_model import StudentListModel


class _StudentQuery:
    def __init__(self, client):
        self.client = client
        self.name_filter = None

    def select(self, columns):
        return self

    def ilike(self, field, value):
        self.client.ilike_calls.append((field, value))
        if field in ("last_name", "first_name"):
            self.name_filter = field
        return self

    def or_(self, expression):
        self.client.or_calls.append(expression)
        self.name_filter = "or"
        return self

    def eq(self, field, value):
        return self

    def order(self, field, **kwargs):
        return self

    def range(self, start, end):
        self.client.range_calls.append((start, end))
        return self

    def execute(self):
        rows = {
            "last_name": [{"id": "1", "last_name": "Smith, Jr.", "first_name": "Ana"}],
            "first_name": [
                {"id": "1", "last_name": "Smith, Jr.", "first_name": "Ana"},
                {"id": "2", "last_name": "Cruz", "first_name": "Smith, Jr."},
            ],
            "or": [
                {"id": "1", "last_name": "Smith, Jr.", "first_name": "Ana"},
                {"id": "2", "last_name": "Cruz", "first_name": "Smith, Jr."},
            ],
        }
        return SimpleNamespace(data=rows.get(self.name_filter, []))


class _StudentClient:
    def __init__(self):
        self.ilike_calls = []
        self.or_calls = []
        self.range_calls = []

    def table(self, name):
        return _StudentQuery(self)


class _CoordinatorRepository:
    def __init__(self):
        self.old = [{"id": 7, "location": "Old", "contact_person": "Keeper"}]
        self.insert_calls = []
        self.delete_calls = 0
        self.replaced = None

    def list_coordinators(self):
        return list(self.old)

    def delete_all_coordinators(self):
        self.delete_calls += 1

    def insert_coordinators(self, records):
        self.insert_calls.append(records)
        if len(self.insert_calls) == 1:
            raise RuntimeError("simulated insert failure")

    def replace_coordinators(self, records):
        self.replaced = list(records)
        return len(records)


class _WorkbookImportService(WorkbookImportService):
    def __init__(self, coordinator_repository, rows):
        self.student_repository = SimpleNamespace()
        self.coordinator_repository = coordinator_repository
        self.workbook_repository = SimpleNamespace()
        self._rows = rows

    def sheet_values(self, workbook, sheet_name):
        return self._rows


class RegressionTests(unittest.TestCase):
    def test_negative_amounts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            ExpenseService.parse_amount("-1.00")

    def test_name_search_uses_quoted_server_filter(self):
        client = _StudentClient()
        repository = StudentRepository(client=client)

        rows = repository.search_students(name_query="Smith, Jr.")

        self.assertEqual([row["id"] for row in rows], ["1", "2"])
        self.assertEqual(client.ilike_calls, [])
        self.assertEqual(
            client.or_calls,
            ['last_name.ilike."%Smith, Jr.%",first_name.ilike."%Smith, Jr.%"'],
        )

    def test_unfiltered_search_applies_requested_page_range(self):
        client = _StudentClient()
        repository = StudentRepository(client=client)

        repository.search_students(limit=50, offset=100)

        self.assertEqual(client.range_calls, [(100, 149)])

    def test_student_model_appends_pages_without_row_widgets(self):
        model = StudentListModel()
        model.reset_rows([{"id": str(i)} for i in range(50)], has_more=True)
        model.append_rows([{"id": str(i)} for i in range(50, 100)], has_more=False)

        self.assertEqual(model.rowCount(), 100)
        self.assertFalse(model.has_more)

    def test_excel_import_uses_transactional_identity_import(self):
        repository = SimpleNamespace()
        repository.received = None
        repository.import_students = lambda records: (
            setattr(repository, "received", records) or len(records)
        )
        service = StudentExcelService(repository)
        records = [{"last_name": "Cruz", "first_name": "Ana", "birthday": "2010-01-01"}]
        service.parse_students = lambda path: ("Students", records)

        sheet, count = service.import_students("ignored.xlsx")

        self.assertEqual((sheet, count), ("Students", 1))
        self.assertEqual(repository.received, records)

    def test_workbook_save_is_atomic_and_creates_backup(self):
        class Workbook:
            def save(self, path):
                Path(path).write_text("new workbook", encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.xlsx"
            path.write_text("old workbook", encoding="utf-8")
            window = SimpleNamespace(
                _workbook=Workbook(),
                _workbook_path=str(path),
                _workbook_mtime_ns=path.stat().st_mtime_ns,
                _workbook_dirty=True,
                _workbook_revision=0,
                _workbook_lock=threading.RLock(),
                status_bar=SimpleNamespace(showMessage=lambda *args: None),
                workbook_status_label=SimpleNamespace(setText=lambda *args: None),
                _invalidate_master_reference_cache=lambda: None,
                _refresh_workbook_controls=lambda: None,
            )
            window._backup_workbook_file = lambda: StudentApp._backup_workbook_file(window)

            saved = StudentApp.save_workbook_tabs(window)

            self.assertTrue(saved)
            self.assertEqual(path.read_text(encoding="utf-8"), "new workbook")
            backups = list((Path(directory) / "SSM Backups").glob("master-*.xlsx"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "old workbook")

    def test_workbook_save_refuses_external_change(self):
        class Workbook:
            saved = False

            def save(self, path):
                self.saved = True

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "master.xlsx"
            path.write_text("first", encoding="utf-8")
            original_mtime = path.stat().st_mtime_ns
            path.write_text("changed elsewhere", encoding="utf-8")
            os.utime(path, ns=(original_mtime + 1_000_000, original_mtime + 1_000_000))
            workbook = Workbook()
            window = SimpleNamespace(
                _workbook=workbook,
                _workbook_path=str(path),
                _workbook_mtime_ns=original_mtime,
            )

            with patch.object(QMessageBox, "warning"):
                saved = StudentApp.save_workbook_tabs(window)

            self.assertFalse(saved)
            self.assertFalse(workbook.saved)

    def test_coordinator_sync_delegates_to_transactional_replacement(self):
        repository = _CoordinatorRepository()
        rows = [
            ["Location", "Contact Person"],
            ["New", "Replacement"],
        ]
        service = _WorkbookImportService(repository, rows)

        count = service.sync_coordinator_sheet(None, "Coordinators")

        self.assertEqual(count, 1)
        self.assertEqual(repository.delete_calls, 0)
        self.assertEqual(repository.replaced[0]["location"], "New")

    def test_empty_coordinator_sheet_preserves_existing_data(self):
        repository = _CoordinatorRepository()
        service = _WorkbookImportService(
            repository,
            [["Location", "Contact Person"]],
        )

        with self.assertRaisesRegex(ValueError, "preserved"):
            service.sync_coordinator_sheet(None, "Coordinators")

        self.assertEqual(repository.delete_calls, 0)


if __name__ == "__main__":
    unittest.main()
