"""Student business logic independent of PyQt widgets."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

try:
    from office_app.repositories.student_repository import StudentRepository
except ImportError:  # Keeps this module importable while the refactor is staged.
    StudentRepository = None  # type: ignore[assignment]


StatusStyle = Tuple[str, str, str]


class StudentService:
    """Business operations and formatting helpers for student records."""

    def __init__(self, repository: Optional[Any] = None) -> None:
        if repository is not None:
            self.repository = repository
        elif StudentRepository is not None:
            self.repository = StudentRepository()
        else:
            raise ImportError(
                "StudentRepository is not available. Create "
                "office_app/repositories/student_repository.py before using "
                "StudentService without injecting a repository."
            )

    @staticmethod
    def _normalize_grade(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    normalize_grade = _normalize_grade

    @staticmethod
    def _grade_sort_key(grade: Any) -> Tuple[str, int, str]:
        text = str(grade or "").strip()
        upper = text.upper()
        match = re.match(r"^([A-Z]+)\s*(\d+)", upper)
        if match:
            return (match.group(1), int(match.group(2)), upper)
        return ("ZZZ", 999, upper)

    grade_sort_key = _grade_sort_key

    @staticmethod
    def _status_style(status: Any) -> StatusStyle:
        normalized = str(status or "Active").strip()
        folded = normalized.lower()
        if folded in {"inactive/removed", "inactive", "removed"}:
            return "Inactive/Removed", "Inactive", "#ba2525"
        if folded == "graduated":
            return "Graduated", "Graduated", "#6b46c1"
        return "Active", "Active", "#2f855a"

    status_style = _status_style

    @staticmethod
    def _profile_completion_percent(student: Dict[str, Any]) -> int:
        fields_to_check = [
            "last_name",
            "first_name",
            "gender",
            "grade",
            "address",
            "city",
            "area",
            "birthday",
            "sponsor",
            "contact",
            "school",
            "parents",
            "photo_url",
        ]

        grade_str = str(student.get("grade", "")).strip().upper()
        needs_course = True
        if grade_str.startswith("G"):
            match = re.search(r"\d+", grade_str)
            if match and int(match.group()) < 11:
                needs_course = False

        if needs_course:
            fields_to_check.append("course")

        filled = sum(
            1
            for field in fields_to_check
            if str(student.get(field) or "").strip()
        )
        return int((filled / len(fields_to_check)) * 100) if fields_to_check else 0

    profile_completion_percent = _profile_completion_percent

