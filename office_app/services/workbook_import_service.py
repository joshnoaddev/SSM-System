"""Workbook parsing and Supabase sync business logic."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from office_app.repositories.coordinator_repository import CoordinatorRepository
from office_app.repositories.student_repository import StudentRepository
from office_app.repositories.workbook_repository import WorkbookRepository


class WorkbookImportService:
    """Parse supported Excel workbook sheets and sync them through repositories.

    This service intentionally contains no PyQt imports. It owns workbook parsing,
    record mapping, and repository orchestration for workbook imports.
    """

    def __init__(
        self,
        student_repository: Optional[StudentRepository] = None,
        coordinator_repository: Optional[CoordinatorRepository] = None,
        workbook_repository: Optional[WorkbookRepository] = None,
    ) -> None:
        self.student_repository = student_repository or StudentRepository()
        self.coordinator_repository = coordinator_repository or CoordinatorRepository()
        self.workbook_repository = workbook_repository or WorkbookRepository()

    def _get_student_id_map(self) -> Dict[tuple[str, str], str]:
        """Fetch all students and return a map from (last, first) to ID."""
        all_students = self.student_repository.list_students(columns="id,last_name,first_name")
        return {
            (
                str(s.get("last_name") or "").strip().lower(),
                str(s.get("first_name") or "").strip().lower(),
            ): s["id"]
            for s in all_students
            if s.get("id")
        }

    def sync_sheet(self, workbook: Any, sheet_name: str) -> Optional[int]:
        lower = sheet_name.lower()
        if "coordinator" in lower:
            return self.sync_coordinator_sheet(workbook, sheet_name)
        if "donor" in lower:
            return self.sync_donor_sheet(workbook, sheet_name)
        if "movement" in lower or "discrepancy" in lower:
            return self.sync_movements_sheet(workbook, sheet_name)
        if "master" in lower:
            return self.sync_masterlist_sheet(workbook, sheet_name)
        return None

    def sync_masterlist_sheet(self, workbook: Any, sheet_name: str) -> int:
        rows = self.sheet_values(workbook, sheet_name)
        header_idx = self.find_header_row(rows, ("last name", "first name"))
        if header_idx is None:
            return 0

        headers = self.header_map(rows[header_idx])
        last_i = headers.get("last name")
        first_i = headers.get("first name")
        if last_i is None or first_i is None:
            return 0

        loc_i = headers.get("location")
        records: List[Dict[str, Any]] = []
        current_area = ""
        for row in rows[header_idx + 1:]:
            first_cell = self.safe_cell(row, 0)
            last = self.safe_cell(row, last_i)
            first = self.safe_cell(row, first_i)

            if not last and not first:
                if first_cell and not first_cell.replace(".", "", 1).isdigit():
                    current_area = first_cell
                continue
            if not last or not first or last.lower() == "last name":
                continue

            birthday = self.safe_cell(row, headers.get("birthday"))
            grade = (
                self.safe_cell(row, headers.get("level"))
                or self.safe_cell(row, headers.get("grade"))
                or self.safe_cell(row, headers.get("grade level"))
            )
            marker = first_cell.lower()
            if marker in ("g", "graduated") or "graduat" in grade.lower():
                status = "Graduated"
            elif not marker or marker == "x":
                status = "Inactive/Removed"
            else:
                status = "Active"

            records.append({
                "last_name": last,
                "first_name": first,
                "gender": self.safe_cell(row, headers.get("gender")),
                "grade": grade,
                "address": self.safe_cell(row, loc_i),
                "city": self.safe_cell(row, loc_i + 1 if loc_i is not None else None),
                "area": self.safe_cell(row, loc_i + 2 if loc_i is not None else None) or current_area,
                "birthday": birthday,
                "sponsor": self.safe_cell(row, headers.get("sponsor")),
                "contact": self.safe_cell(row, headers.get("contact no.")) or self.safe_cell(row, headers.get("contact")),
                "school": self.safe_cell(row, headers.get("school")),
                "parents": self.safe_cell(row, headers.get("parents")),
                "course": self.safe_cell(row, headers.get("course")),
                "remarks": self.safe_cell(row, headers.get("remarks")),
                "status": status,
            })

        if not records:
            raise ValueError("Master list contains no importable records; existing data was preserved.")
        return self.student_repository.import_students(records)

    def sync_coordinator_sheet(self, workbook: Any, sheet_name: str) -> int:
        rows = self.sheet_values(workbook, sheet_name)
        header_idx = self.find_header_row(rows, ("location", "contact person"))
        if header_idx is None:
            return 0

        headers = self.header_map(rows[header_idx])
        records: List[Dict[str, Any]] = []
        for row in rows[header_idx + 1:]:
            location = self.safe_cell(row, headers.get("location"))
            person = self.safe_cell(row, headers.get("contact person"))
            if not location and not person:
                continue
            records.append({
                "location": location,
                "contact_person": person,
                "email": self.safe_cell(row, headers.get("e-mail")) or self.safe_cell(row, headers.get("email")),
                "contact_no": self.safe_cell(row, headers.get("contact no.")) or self.safe_cell(row, headers.get("contact no")),
                "fb_page": self.safe_cell(row, headers.get("fb page")),
                "remarks": self.safe_cell(row, headers.get("remarks")),
            })

        if not records:
            raise ValueError("Coordinator sheet contains no importable records; existing data was preserved.")
        return self.coordinator_repository.replace_coordinators(records)

    def sync_donor_sheet(self, workbook: Any, sheet_name: str) -> int:
        rows = self.sheet_values(workbook, sheet_name)
        school_year = self.school_year_from_sheet(sheet_name)
        student_id_map = self._get_student_id_map()
        records: List[Dict[str, Any]] = []
        donor_name = ""
        header: Dict[str, int] = {}
        for row in rows:
            mapped = self.header_map(row)
            if "last name" in mapped and "first name" in mapped:
                header = mapped
                continue

            last_i = header.get("last name")
            first_i = header.get("first name")
            last = self.safe_cell(row, last_i)
            first = self.safe_cell(row, first_i)
            first_cell = self.safe_cell(row, 0)

            if not last and not first:
                maybe_donor = first_cell or self.safe_cell(row, 1)
                if maybe_donor and not maybe_donor.lower().startswith("ywam students"):
                    donor_name = maybe_donor
                continue
            if not header or last.lower() == "last name":
                continue

            student_id = student_id_map.get((last.lower(), first.lower()))
            if not student_id:
                continue

            records.append({
                "school_year": school_year,
                "donor_name": donor_name,
                "student_id": student_id,
                "location": self.safe_cell(row, header.get("location")),
                "level": self.safe_cell(row, header.get("level")),
                "sponsor": self.safe_cell(row, header.get("sponsor")),
                "remarks": self.safe_cell(row, header.get("remarks")),
            })

        if not records:
            raise ValueError("Donor sheet contains no importable records; existing data was preserved.")
        return self.workbook_repository.replace_donor_students(school_year, records)

    def sync_movements_sheet(self, workbook: Any, sheet_name: str) -> int:
        rows = self.sheet_values(workbook, sheet_name)
        student_id_map = self._get_student_id_map()
        records: List[Dict[str, Any]] = []
        category = ""
        header: Dict[str, int] = {}
        for row in rows:
            mapped = self.header_map(row)
            if "last name" in mapped and ("name" in mapped or "first name" in mapped):
                header = mapped
                continue

            last_i = header.get("last name")
            first_i = header.get("first name") if "first name" in header else header.get("name")
            last = self.safe_cell(row, last_i)
            first = self.safe_cell(row, first_i)
            first_cell = self.safe_cell(row, 0)

            if not last and not first:
                if first_cell:
                    category = first_cell
                continue
            if not header or last.lower() == "last name":
                continue

            student_id = student_id_map.get((last.lower(), first.lower()))
            if not student_id:
                continue

            records.append({
                "category": category,
                "student_id": student_id,
                "location": self.safe_cell(row, header.get("location")),
                "level": self.safe_cell(row, header.get("level")),
                "remarks": self.safe_cell(row, header.get("remarks")),
            })

        if not records:
            raise ValueError("Movements sheet contains no importable records; existing data was preserved.")
        return self.workbook_repository.replace_student_movements(records)

    def sheet_values(self, workbook: Any, sheet_name: str) -> List[List[str]]:
        worksheet = workbook[sheet_name]
        return [
            [self.format_excel_value(cell) for cell in row]
            for row in worksheet.iter_rows(
                min_row=1,
                max_row=worksheet.max_row,
                max_col=worksheet.max_column,
                values_only=False,
            )
        ]

    def find_header_row(self, rows: Sequence[Sequence[Any]], required: Sequence[str]) -> Optional[int]:
        required_headers = set(required)
        for idx, row in enumerate(rows):
            normalized = {self.normalize_header(value) for value in row if self.normalize_header(value)}
            if required_headers.issubset(normalized):
                return idx
        return None

    def header_map(self, row: Sequence[Any]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for idx, value in enumerate(row):
            key = self.normalize_header(value)
            if key and key not in result:
                result[key] = idx
        return result

    def normalize_header(self, value: Any) -> str:
        return str(value or "").strip().lower().replace("\n", " ")

    def safe_cell(self, row: Sequence[Any], index: Optional[int]) -> str:
        if index is None or index < 0 or index >= len(row):
            return ""
        if hasattr(row[index], "strftime"):
            return row[index].strftime("%Y-%m-%d")
        value = str(row[index] or "").strip()
        if value.lower() in ("none", "nan"):
            return ""
        return value

    def school_year_from_sheet(self, sheet_name: str) -> str:
        match = re.search(r"(20\d{2})\s*-\s*(20\d{2})", sheet_name)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        match = re.search(r"(\d{2})\s*-\s*(\d{2})", sheet_name)
        if match:
            return f"20{match.group(1)}-20{match.group(2)}"
        return sheet_name

    def format_excel_value(self, value: Any) -> str:
        if hasattr(value, "value"):
            value = value.value
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)
