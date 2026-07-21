"""Student list filtering and option-building logic."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from office_app.services.student_service import StudentService


class StudentListService:
    """Business logic for student list filters, area counts, and grade options."""

    ALL_GRADES = "All grades"

    def __init__(self, student_service: StudentService | None = None) -> None:
        self.student_service = student_service or StudentService()

    def filter_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        status: str = "All",
        grade: str = ALL_GRADES,
    ) -> List[Dict[str, Any]]:
        filtered = [dict(row) for row in rows]
        if status != "All":
            filtered = [
                row
                for row in filtered
                if self.student_service.status_style(row.get("status"))[0] == status
            ]
        if self.student_service.normalize_grade(grade) != "all grades":
            normalized_grade = self.student_service.normalize_grade(grade)
            filtered = [
                row for row in filtered
                if self.student_service.normalize_grade(row.get("grade")) == normalized_grade
            ]
        return filtered

    def area_counts(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in rows:
            area = str(row.get("area") or "").strip()
            if area:
                counts[area] = counts.get(area, 0) + 1
        return counts

    def grade_options(self, rows: Sequence[Mapping[str, Any]]) -> List[str]:
        grades_by_key: Dict[str, str] = {}
        for row in rows:
            raw = str(row.get("grade") or "").strip()
            if not raw:
                continue
            key = self.student_service.normalize_grade(raw)
            grades_by_key.setdefault(
                key,
                self.student_service.format_grade_label(raw),
            )
        return sorted(
            grades_by_key.values(),
            key=self.student_service.grade_sort_key,
        )
