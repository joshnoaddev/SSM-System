"""Render deterministic offscreen screenshots for GUI visual QA."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QAbstractButton, QApplication

import app as app_module
from office_app.repositories.audit_repository import AuditRepository
from office_app.repositories.coordinator_repository import CoordinatorRepository
from office_app.repositories.expense_repository import ExpenseRepository
from office_app.repositories.student_repository import StudentRepository
from office_app.services.masterlist_service import MasterListService


def build_sample_students():
    """Create a deterministic cohort matching the latest sync audit."""
    synced_at = "2026-07-20T11:59:00+00:00"
    active_areas = ["Manila"] * 52 + ["Alabang"] * 39 + ["Tondo"] * 31 + ["Pasay"] * 23
    active_sponsors = (
        ["Community partner"] * 54
        + ["Local church"] * 42
        + ["YWAM staff"] * 31
        + [""] * 18
    )
    rows = []
    for index, (area, sponsor) in enumerate(zip(active_areas, active_sponsors), 1):
        rows.append({
            "id": f"active-{index}",
            "last_name": f"Student {index:03d}",
            "first_name": "Active",
            "status": "Active",
            "sponsor": sponsor,
            "area": area,
            "grade": f"G{7 + (index % 6)}",
            "contact": f"0917 000 {index:04d}",
            "school": "Public High School",
            "birthday": f"2010-02-{1 + (index % 27):02d}",
            "photo_url": f"https://example.test/photo-{index}.jpg",
            "sheet_synced_at": synced_at,
        })
    for index in range(1, 29):
        rows[index - 1]["photo_url"] = ""
    for index in range(1, 11):
        rows.append({
            **rows[index - 1],
            "id": f"inactive-{index}",
            "last_name": f"Inactive {index:02d}",
            "status": "Inactive/Removed",
        })
    for index in range(1, 10):
        rows.append({
            **rows[index - 1],
            "id": f"graduated-{index}",
            "last_name": f"Graduate {index:02d}",
            "status": "Graduated",
            "grade": "Graduated",
        })
    return rows


SAMPLE_STUDENTS = build_sample_students()
SAMPLE_EXPENSES = [
    {
        "id": "expense-1",
        "student_id": "active-1",
        "description": "School supplies",
        "amount": 575.0,
        "date": "2026-07-08",
        "school_year": "2026-2027",
    },
    {
        "id": "expense-2",
        "student_id": "active-1",
        "description": "Transport allowance",
        "amount": 400.0,
        "date": "2026-07-15",
        "school_year": "2026-2027",
    },
]
SAMPLE_COORDINATORS = [
    {
        "id": "coord-1",
        "location": "Alabang",
        "contact_person": "Mara Santos",
        "email": "mara@example.test",
        "contact_no": "0917 555 0142",
        "fb_page": "SSM Alabang",
        "remarks": "Primary area contact",
    },
    {
        "id": "coord-2",
        "location": "Manila",
        "contact_person": "Paolo Reyes",
        "email": "paolo@example.test",
        "contact_no": "0917 555 0188",
        "fb_page": "SSM Manila",
        "remarks": "Weekday coordination",
    },
]


def sample_financial_summaries(_repository, student_ids, school_year=None):
    """Return varied budget states so row meters are covered by visual QA."""
    summaries = {}
    for position, student_id in enumerate(student_ids, 1):
        variant = position % 3
        if variant == 1:
            budget, spent = 4500.0, 975.0
        elif variant == 2:
            budget, spent = 4000.0, 3300.0
        else:
            budget, spent = 0.0, 225.0
        summaries[student_id] = {
            "student_id": student_id,
            "school_year": school_year or "All years",
            "total_budget": budget,
            "total_expenses": spent,
            "remaining_balance": budget - spent,
        }
    return summaries


def sample_expenses(_repository, student_id, school_year=None, **_kwargs):
    return [
        dict(expense)
        for expense in SAMPLE_EXPENSES
        if expense["student_id"] == student_id
        and (not school_year or expense["school_year"] == school_year)
    ]


def render(path: Path, width: int, height: int) -> None:
    application = QApplication.instance() or QApplication(sys.argv)
    StudentRepository.list_students = lambda self, **kwargs: list(
        SAMPLE_STUDENTS
    )
    StudentRepository.search_students = lambda self, *args, **kwargs: list(
        SAMPLE_STUDENTS
    )
    StudentRepository.get_student_single = (
        lambda self, student_id, **kwargs: next(
            row for row in SAMPLE_STUDENTS if row.get("id") == student_id
        )
    )
    MasterListService.current_student_reference = (
        lambda self, **kwargs: {}
    )
    ExpenseRepository.list_financial_summaries = sample_financial_summaries
    ExpenseRepository.list_expenses = sample_expenses
    CoordinatorRepository.list_coordinators = lambda self, **kwargs: list(
        SAMPLE_COORDINATORS
    )
    AuditRepository.latest_google_sheet_sync = lambda self: {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "details": {
            "students": 164,
            "donor_students": 158,
            "movements": 47,
            "coordinators": 10,
        },
    }
    app_module.StudentApp._start_update_poller = lambda self: None
    window = app_module.StudentApp(object(), initial_user="Joshua")
    window.resize(width, height)
    window.show()
    page = sys.argv[4].lower() if len(sys.argv) > 4 else "dashboard"
    if page == "students":
        window.nav_students()
    elif page == "profile":
        window._open_student_profile("active-1")
    elif page == "add":
        window.nav_add()
    elif page == "expenses":
        window.current_student_id = "active-1"
        window.open_expenses_screen()
    elif page == "workbook":
        window.nav_workbook()
    elif page == "coordinators":
        window.nav_coordinators()
    elif page == "settings":
        window.nav_settings()

    # Native Windows may recenter a window after a page changes its size hint.
    # Pinning the test window keeps 980×700 captures deterministic on smaller
    # desktop work areas instead of clipping the top edge.
    window.move(0, 0)

    def capture() -> None:
        window.move(0, 0)
        application.processEvents()
        if len(sys.argv) > 6 and sys.argv[6].lower() == "buttons":
            minimum = window.minimumSizeHint()
            print(
                f"window\t{window.width()}x{window.height()}\t"
                f"minimum={minimum.width()}x{minimum.height()}",
                flush=True,
            )
            buttons = [
                button
                for button in window.findChildren(QAbstractButton)
                if button.isVisibleTo(window)
            ]
            for button in sorted(
                buttons,
                key=lambda item: (
                    item.mapTo(window, item.rect().topLeft()).y(),
                    item.mapTo(window, item.rect().topLeft()).x(),
                    item.text(),
                ),
            ):
                position = button.mapTo(window, button.rect().topLeft())
                hint = button.sizeHint()
                print(
                    f"{page}\t{button.text() or '<custom>'}\t"
                    f"{button.objectName() or '<unnamed>'}\t"
                    f"{button.width()}x{button.height()}\t"
                    f"hint={hint.width()}x{hint.height()}\t"
                    f"at={position.x()},{position.y()}",
                    flush=True,
                )
        window.grab().save(str(path), "PNG")
        window.close()
        application.quit()

    capture_delay = int(sys.argv[5]) if len(sys.argv) > 5 else 900
    QTimer.singleShot(capture_delay, capture)
    application.exec()


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    render(output, int(sys.argv[2]), int(sys.argv[3]))
