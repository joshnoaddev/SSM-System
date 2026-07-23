from __future__ import annotations

import unittest
import os
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
)
from app import StartupDialog, StudentApp
from office_app import app_config
from office_app.repositories.student_repository import StudentRepository
from office_app.repositories.expense_repository import ExpenseRepository
from office_app.services.dashboard_service import DashboardService
from office_app.services.expense_service import ExpenseService
from office_app.services.student_service import StudentService
from office_app.services.student_list_service import StudentListService
from office_app.services.google_sheet_sync_service import (
    GoogleSheetSyncService,
    SheetSyncError,
)
from office_app.services.student_excel_service import StudentExcelService
from office_app.services.updater_service import UpdaterService
from office_app.services import supabase_client as supabase_client_module
from office_app.services.workbook_import_service import WorkbookImportService
from office_app.ui.configuration_dialog import (
    friendly_connection_error,
    is_connection_configuration_error,
)
from office_app.ui.components import (
    ActionButton,
    Card,
    EmptyState,
    set_content_hugging_button,
)
from office_app.ui.motion import (
    MotionCard,
    PulseController,
    animate_count,
    animate_progress,
)
from office_app.utils.background_tasks import BackgroundTask
from office_app.ui.views.student_list_model import (
    StudentCardDelegate,
    StudentListModel,
)


_QT_APPLICATION = None


def _qt_application():
    global _QT_APPLICATION
    if _QT_APPLICATION is None:
        _QT_APPLICATION = QApplication.instance() or QApplication([])
    return _QT_APPLICATION


class StartupDialogRegressionTests(unittest.TestCase):
    def setUp(self):
        _qt_application()
        self.dialog = StartupDialog()

    def tearDown(self):
        self.dialog.close()

    def test_operator_rows_have_one_synchronized_selection(self):
        selected_name = self.dialog._user_cards[-1].property("user_name")
        self.dialog._select_user(selected_name)

        checked = [card for card in self.dialog._user_cards if card.isChecked()]
        self.assertEqual([selected_name], [card.property("user_name") for card in checked])
        self.assertEqual(f"Continue as {selected_name}", self.dialog._continue_btn.text())
        self.assertEqual(selected_name, self.dialog.loading_user_name.text())

    def test_loading_phase_exposes_clear_step_states(self):
        self.dialog._set_loading_phase("database")

        states = [label.property("state") for label in self.dialog._loading_step_labels]
        self.assertEqual(["complete", "active", "pending", "pending"], states)
        self.assertIn("database", self.dialog._loading_step_labels[0].text().lower())
        self.assertIn("settings", self.dialog._loading_step_labels[1].text().lower())

    def test_continue_action_matches_full_width_figma_control(self):
        self.dialog.show()
        _qt_application().processEvents()

        self.assertEqual(
            QSizePolicy.Policy.Expanding,
            self.dialog._continue_btn.sizePolicy().horizontalPolicy(),
        )
        self.assertGreaterEqual(self.dialog._continue_btn.width(), 340)


class ButtonDensityRegressionTests(unittest.TestCase):
    def setUp(self):
        _qt_application()

    def test_content_hugging_resets_legacy_fixed_width(self):
        button = QPushButton("Save changes")
        button.setFixedWidth(240)

        set_content_hugging_button(button)

        self.assertEqual(52, button.minimumWidth())
        self.assertGreater(button.maximumWidth(), 240)
        self.assertEqual(40, button.minimumHeight())
        self.assertEqual(40, button.maximumHeight())
        self.assertEqual(
            QSizePolicy.Policy.Maximum,
            button.sizePolicy().horizontalPolicy(),
        )

    def test_action_button_uses_content_hugging_by_default(self):
        button = ActionButton("Sync now")

        self.assertEqual(
            QSizePolicy.Policy.Maximum,
            button.sizePolicy().horizontalPolicy(),
        )
        self.assertGreater(button.maximumWidth(), button.minimumWidth())


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


class _UpdateQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, columns):
        return self

    def eq(self, field, value):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _UpdateClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _UpdateQuery(self.rows)


class _DeleteQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def delete(self):
        return self

    def eq(self, field, value):
        self.client.delete_calls.append((self.table_name, field, value))
        return self

    def execute(self):
        return SimpleNamespace(data=[{"table": self.table_name}])


class _DeleteClient:
    def __init__(self):
        self.delete_calls = []

    def table(self, name):
        return _DeleteQuery(self, name)


class _FinancialQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def select(self, _columns):
        return self

    def in_(self, _field, _values):
        return self

    def eq(self, _field, _value):
        return self

    def execute(self):
        return SimpleNamespace(data=self.client.rows.get(self.table_name, []))


class _FinancialClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _FinancialQuery(self, name)


class RegressionTests(unittest.TestCase):
    def test_fast_background_tasks_expose_completion_state(self):
        task = BackgroundTask(lambda: "ready")

        task.run()

        self.assertTrue(task.done)

    def test_negative_amounts_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            ExpenseService.parse_amount("-1.00")

    def test_expense_card_status_reports_no_allocated_budget(self):
        status = ExpenseService.budget_card_status(None)

        self.assertFalse(status["allocated"])
        self.assertEqual(status["title"], "No budget allocated")
        self.assertEqual(status["percent"], 0)

    def test_budget_usage_with_expenses_but_no_budget_is_neutral(self):
        status = ExpenseService.budget_card_status({
            "total_budget": 0,
            "total_expenses": 250,
            "remaining_balance": -250,
        })

        self.assertFalse(status["allocated"])
        self.assertEqual(status["title"], "No budget allocated")
        self.assertEqual(status["state"], "neutral")
        self.assertFalse(status["over_budget"])

    def test_expense_card_status_reports_budget_progress(self):
        status = ExpenseService.budget_card_status({
            "total_budget": 1000,
            "total_expenses": 250,
            "remaining_balance": 750,
        })

        self.assertTrue(status["allocated"])
        self.assertEqual(status["title"], "25% used")
        self.assertEqual(status["detail"], "PHP 250 / 1,000")

    def test_visible_expense_rows_reconcile_every_displayed_figure(self):
        summary = ExpenseService.reconcile_summary(
            {
                "total_budget": 4500,
                "total_expenses": 999,
                "remaining_balance": 3501,
            },
            [
                {"amount": 575},
                {"amount": 400},
            ],
            "2026-2027",
        )
        usage = ExpenseService.budget_usage(summary)

        self.assertEqual(975, summary["total_expenses"])
        self.assertEqual(3525, summary["remaining_balance"])
        self.assertEqual(21, usage["percent"])
        self.assertIn("PHP 975.00 of PHP 4,500.00", usage["message"])

    def test_financial_summaries_match_equivalent_uuid_and_text_ids(self):
        student_id = UUID("8a88f7c1-3287-4f75-856c-8f429db240e8")
        client = _FinancialClient({
            "budgets": [{
                "student_id": f"  {str(student_id).upper()}  ",
                "school_year": "2025-2026",
                "amount": 4500,
            }],
            "expenses": [{
                "student_id": str(student_id),
                "school_year": "2025-2026",
                "amount": 975,
            }],
        })
        repository = ExpenseRepository(client=client)

        summaries = repository.list_financial_summaries([student_id])

        self.assertIn(student_id, summaries)
        self.assertEqual(4500, summaries[student_id]["total_budget"])
        self.assertEqual(975, summaries[student_id]["total_expenses"])
        self.assertEqual(3525, summaries[student_id]["remaining_balance"])

    def test_all_years_summary_does_not_apply_a_literal_filter(self):
        school_years = []
        repository = SimpleNamespace(
            list_financial_summaries=lambda _ids, school_year: (
                school_years.append(school_year) or {}
            )
        )

        ExpenseService(repository=repository).get_financial_summaries(["student-1"])

        self.assertEqual([None], school_years)

    def test_grade_and_status_labels_are_consistently_capitalized(self):
        self.assertEqual("Graduating", StudentService.format_grade_label("graduating"))
        self.assertEqual("G10", StudentService.format_grade_label("grade 10"))
        self.assertEqual(
            ("Graduated", "Graduated", "graduated"),
            StudentService.status_style("  GRADUATING  "),
        )

    def test_status_filter_is_case_and_spacing_tolerant(self):
        service = StudentListService(
            student_service=StudentService(repository=SimpleNamespace())
        )

        rows = service.filter_rows(
            [
                {"id": "1", "status": " graduated "},
                {"id": "2", "status": "ACTIVE"},
            ],
            status="Graduated",
        )

        self.assertEqual(["1"], [row["id"] for row in rows])

    def test_student_directory_sponsor_sort_is_stable(self):
        service = StudentListService()

        self.assertEqual(
            service.sort_order(service.SORT_SPONSOR),
            ["sponsor", "last_name", "first_name", "id"],
        )
        self.assertEqual(
            service.sort_order(service.SORT_LAST_NAME),
            ["last_name", "first_name", "id"],
        )

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

    def test_delete_student_with_related_clears_dependencies_first(self):
        client = _DeleteClient()
        repository = StudentRepository(client=client)

        deleted = repository.delete_student_with_related("student-1")

        self.assertEqual(
            client.delete_calls,
            [
                ("expenses", "student_id", "student-1"),
                ("budgets", "student_id", "student-1"),
                ("donor_students", "student_id", "student-1"),
                ("student_movements", "student_id", "student-1"),
                ("students", "id", "student-1"),
            ],
        )
        self.assertIn("students", deleted)

    def test_student_model_appends_pages_without_row_widgets(self):
        model = StudentListModel()
        model.reset_rows([{"id": str(i)} for i in range(50)], has_more=True)
        model.append_rows([{"id": str(i)} for i in range(50, 100)], has_more=False)

        self.assertEqual(model.rowCount(), 100)
        self.assertFalse(model.has_more)

    def test_student_row_accessibility_includes_profile_and_budget_progress(self):
        model = StudentListModel()
        model.reset_rows([{
            "id": "student-1",
            "last_name": "Pajaron",
            "first_name": "Jovanie",
            "_completion": 71,
            "_budget_status": {
                "allocated": True,
                "title": "21% used",
                "detail": "PHP 975 / 4,500",
            },
        }])

        description = model.data(
            model.index(0, 0),
            Qt.ItemDataRole.AccessibleDescriptionRole,
        )

        self.assertIn("71% complete", description)
        self.assertIn("Budget 21% used", description)

    def test_student_card_delegate_leaves_row_width_to_the_viewport(self):
        size = StudentCardDelegate().sizeHint(None, None)

        self.assertEqual(size.width(), 1)
        self.assertEqual(StudentCardDelegate.CARD_HEIGHT, 72)
        self.assertEqual(size.height(), StudentCardDelegate.CARD_HEIGHT)

    def test_dashboard_counts_status_variants(self):
        service = DashboardService()

        counts = service.summary_counts([
            {"status": "Active"},
            {"status": "Inactive"},
            {"status": "Inactive/Removed"},
            {"status": "Removed"},
            {"status": "Graduated"},
            {"status": ""},
        ])

        self.assertEqual(counts, {
            "total": 6,
            "active": 2,
            "inactive": 3,
            "graduated": 1,
        })

    def test_dashboard_counts_use_deduped_students(self):
        service = DashboardService()
        rows = [
            {
                "last_name": "Cruz",
                "first_name": "Ana",
                "birthday": "2010-01-01",
                "status": "Active",
            },
            {
                "last_name": "Cruz",
                "first_name": "Ana",
                "birthday": "2010-01-01",
                "status": "Active",
                "contact": "0917",
            },
            {
                "last_name": "Reyes",
                "first_name": "Ben",
                "birthday": "2009-02-02",
                "status": "Inactive",
            },
        ]

        counts = service.summary_counts(service.dedupe_students(rows))

        self.assertEqual(counts, {
            "total": 2,
            "active": 1,
            "inactive": 1,
            "graduated": 0,
        })

    def test_dashboard_lists_report_full_attention_count(self):
        service = DashboardService()
        rows = [
            {
                "id": str(index),
                "last_name": f"Student {index}",
                "first_name": "Active",
                "birthday": "2010-01-01",
                "status": "Active",
                "area": "Manila",
                "sponsor": "Community partner",
            }
            for index in range(20)
        ]

        dashboard = service.build_lists(rows)

        self.assertEqual(dashboard["attention_count"], 20)
        self.assertEqual(len(dashboard["attention"]), 12)

    def test_dashboard_uses_only_latest_sheet_sync_cohort(self):
        service = DashboardService()
        rows = [
            {"id": "old", "sheet_synced_at": "2026-07-19T10:00:00+00:00"},
            {"id": "current-a", "sheet_synced_at": "2026-07-20T10:00:00+00:00"},
            {"id": "manual", "sheet_synced_at": None},
            {"id": "current-b", "sheet_synced_at": "2026-07-20T10:00:00+00:00"},
        ]

        cohort = service.latest_sync_cohort(rows)

        self.assertEqual(
            [row["id"] for row in cohort],
            ["current-a", "current-b"],
        )

    def test_dashboard_keeps_legacy_rows_without_sync_metadata(self):
        service = DashboardService()
        rows = [{"id": "a"}, {"id": "b", "sheet_synced_at": None}]

        self.assertEqual(service.latest_sync_cohort(rows), rows)

    def test_dashboard_sync_cohort_matches_workbook_status_totals(self):
        service = DashboardService()
        latest = "2026-07-20T11:59:00+00:00"
        older = "2026-07-19T11:59:00+00:00"
        rows = (
            [{"status": "Active", "sheet_synced_at": latest} for _ in range(145)]
            + [{"status": "Inactive/Removed", "sheet_synced_at": latest} for _ in range(10)]
            + [{"status": "Graduated", "sheet_synced_at": latest} for _ in range(9)]
            + [{"status": "Active", "sheet_synced_at": older}]
            + [{"status": "Inactive/Removed", "sheet_synced_at": older} for _ in range(5)]
        )

        counts = service.summary_counts(service.latest_sync_cohort(rows))

        self.assertEqual(counts, {
            "total": 164,
            "active": 145,
            "inactive": 10,
            "graduated": 9,
        })

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

    def test_update_check_requires_newer_version_and_download_url(self):
        updater = UpdaterService(_UpdateClient([{
            "latest_version": "9.9.9",
            "download_url": "",
        }]))

        self.assertIsNone(updater.check_for_update())

    def test_update_check_returns_newer_version_with_url(self):
        updater = UpdaterService(_UpdateClient([{
            "latest_version": "9.9.9",
            "download_url": "https://example.test/SSM.exe",
        }]))

        self.assertEqual(
            updater.check_for_update(),
            ("9.9.9", "https://example.test/SSM.exe"),
        )

    def test_update_download_validation_rejects_non_exe(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(b"<html>not an exe</html>")

        try:
            with self.assertRaisesRegex(RuntimeError, "too small"):
                UpdaterService._validate_downloaded_exe(temp_path)
        finally:
            os.remove(temp_path)

    def test_update_download_validation_accepts_large_exe(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(b"MZ")
            temp_file.seek(UpdaterService.MIN_INSTALLER_BYTES)
            temp_file.write(b"\0")

        try:
            UpdaterService._validate_downloaded_exe(temp_path)
        finally:
            os.remove(temp_path)

    def test_desktop_client_requires_publishable_key(self):
        supabase_client_module.get_supabase_client.cache_clear()
        with patch.object(
            supabase_client_module,
            "get_supabase_config",
            return_value=("https://example.supabase.co", ""),
        ):
            with self.assertRaisesRegex(RuntimeError, "publishable"):
                supabase_client_module.get_supabase_client()
        supabase_client_module.get_supabase_client.cache_clear()

    def test_desktop_client_rejects_secret_key(self):
        supabase_client_module.get_supabase_client.cache_clear()
        with patch.object(
            supabase_client_module,
            "get_supabase_config",
            return_value=(
                "https://example.supabase.co",
                "sb_secret_must_not_ship",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "secret/service-role"):
                supabase_client_module.get_supabase_client()
        supabase_client_module.get_supabase_client.cache_clear()

    def test_desktop_client_accepts_publishable_key(self):
        supabase_client_module.get_supabase_client.cache_clear()
        expected = object()
        with (
            patch.object(
                supabase_client_module,
                "get_supabase_config",
                return_value=(
                    "https://example.supabase.co",
                    "sb_publishable_test",
                ),
            ),
            patch.object(
                supabase_client_module,
                "create_client",
                return_value=expected,
            ) as create_client,
        ):
            client = supabase_client_module.get_supabase_client()

        self.assertIs(client, expected)
        create_client.assert_called_once()
        supabase_client_module.get_supabase_client.cache_clear()

    def test_user_supabase_config_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            with patch.dict(
                os.environ,
                {
                    "SSM_SUPABASE_URL": "",
                    "SSM_SUPABASE_PUBLISHABLE_KEY": "",
                    "SSM_SUPABASE_KEY": "",
                },
            ):
                saved_path = app_config.save_supabase_config(
                    "https://example.supabase.co/",
                    "sb_publishable_saved",
                    path,
                )
                url, key = app_config.get_supabase_config(path)

        self.assertEqual(saved_path, path)
        self.assertEqual(url, "https://example.supabase.co")
        self.assertEqual(key, "sb_publishable_saved")

    def test_environment_supabase_config_overrides_saved_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            app_config.save_supabase_config(
                "https://saved.supabase.co",
                "sb_publishable_saved",
                path,
            )
            with patch.dict(
                os.environ,
                {
                    "SSM_SUPABASE_URL": "https://environment.supabase.co",
                    "SSM_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_environment",
                },
            ):
                url, key = app_config.get_supabase_config(path)

        self.assertEqual(url, "https://environment.supabase.co")
        self.assertEqual(key, "sb_publishable_environment")

    def test_connection_save_preserves_protected_sync_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            with patch.object(
                app_config, "protect_secret", return_value="protected-value"
            ):
                app_config.save_sheet_sync_token("x" * 64, path)
            app_config.save_supabase_config(
                "https://example.supabase.co",
                "sb_publishable_saved",
                path,
            )

            payload = app_config.load_user_config(path)

        self.assertEqual(
            payload[app_config.SYNC_TOKEN_CONFIG_KEY],
            "protected-value",
        )

    def test_sheet_sync_requires_private_token(self):
        service = GoogleSheetSyncService(
            audit_repository=SimpleNamespace()
        )

        with self.assertRaisesRegex(SheetSyncError, "private"):
            service.synchronize("")

    def test_sync_count_copy_is_compact_and_specific(self):
        text = StudentApp._format_sync_counts({
            "students": 164,
            "donor_students": 158,
            "movements": 47,
            "coordinators": 10,
        })

        self.assertEqual(
            text,
            "164 students · 158 donors · 47 movements · 10 coordinators",
        )

    def test_metric_count_animation_progresses_and_finishes(self):
        application = _qt_application()
        label = QLabel("0")

        animate_count(
            label,
            42,
            motion_enabled=True,
            duration_ms=180,
        )
        QTest.qWait(80)
        intermediate = int(label.text())
        QTest.qWait(160)

        self.assertGreater(intermediate, 0)
        self.assertLess(intermediate, 42)
        self.assertEqual(label.text(), "42")
        self.assertIsNotNone(application)

    def test_progress_animation_finishes_at_synchronized_value(self):
        application = _qt_application()
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)

        animate_progress(
            progress,
            62,
            motion_enabled=True,
            duration_ms=180,
        )
        QTest.qWait(80)
        intermediate = progress.value()
        QTest.qWait(160)

        self.assertGreater(intermediate, 0)
        self.assertLess(intermediate, 62)
        self.assertEqual(progress.value(), 62)
        self.assertIsNotNone(application)

    def test_reduced_motion_skips_count_and_pulse_movement(self):
        application = _qt_application()
        label = QLabel("0")
        animate_count(label, 42, motion_enabled=False)
        progress = QProgressBar()
        animate_progress(progress, 62, motion_enabled=False)
        pulse = PulseController(label, lambda: False)
        pulse.start()
        card = MotionCard(motion_enabled=lambda: False)
        card.reveal()

        self.assertEqual(label.text(), "42")
        self.assertEqual(progress.value(), 62)
        self.assertIsNone(label.graphicsEffect())
        self.assertIsInstance(
            card.graphicsEffect(),
            QGraphicsDropShadowEffect,
        )
        self.assertIsNotNone(application)

    def test_interactive_container_cards_do_not_composite_children_by_default(self):
        application = _qt_application()
        card = Card()
        empty_state = EmptyState("No results")

        self.assertIsNone(card.graphicsEffect())
        self.assertIsNone(empty_state.graphicsEffect())
        self.assertIsNotNone(application)

    def test_invalid_api_key_error_has_actionable_copy(self):
        raw_error = (
            "postgrest.exceptions.APIError: {'code': 401, "
            "'message': 'Invalid API key'}"
        )

        self.assertTrue(is_connection_configuration_error(raw_error))
        message = friendly_connection_error(raw_error)
        self.assertIn("publishable key", message)
        self.assertNotIn("postgrest", message.lower())

    def test_network_error_has_actionable_copy(self):
        raw_error = "Connection timed out while reaching the database"

        self.assertFalse(is_connection_configuration_error(raw_error))
        self.assertIn("internet connection", friendly_connection_error(raw_error))


if __name__ == "__main__":
    unittest.main()
