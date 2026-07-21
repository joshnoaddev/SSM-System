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
        normalized = " ".join(str(status or "Active").strip().split())
        folded = normalized.casefold()
        words = set(re.findall(r"[a-z]+", folded))
        if "inactive" in words or "removed" in words:
            return "Inactive/Removed", "Inactive", "danger"
        if any(word.startswith("graduat") for word in words):
            return "Graduated", "Graduated", "graduated"
        return "Active", "Active", "success"

    status_style = _status_style

    @staticmethod
    def _format_grade_label(value: Any) -> str:
        """Return a compact, consistently capitalized grade label."""
        text = " ".join(str(value or "").strip().split())
        if not text:
            return ""

        folded = text.casefold()
        grade_match = re.fullmatch(r"(?:grade|g)\s*[-:]?\s*(\d{1,2})", folded)
        if grade_match:
            return f"G{int(grade_match.group(1))}"

        known = {
            "graduating": "Graduating",
            "graduated": "Graduated",
            "kindergarten": "Kindergarten",
            "kinder": "Kinder",
            "pre school": "Pre-school",
            "pre-school": "Pre-school",
            "college": "College",
        }
        if folded in known:
            return known[folded]

        acronyms = {"als", "jhs", "shs", "sped", "k"}
        return " ".join(
            word.upper() if word.casefold() in acronyms else word.capitalize()
            for word in text.split()
        )

    format_grade_label = _format_grade_label

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
