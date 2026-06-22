"""Dashboard aggregation and attention-list business logic."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

DashboardKey = Tuple[str, str, str]


class DashboardService:
    """Build dashboard summaries from student rows without PyQt dependencies."""

    def summary_counts(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
        return {
            "total": len(rows),
            "active": sum(1 for row in rows if str(row.get("status", "")) == "Active"),
            "inactive": sum(1 for row in rows if str(row.get("status", "")) == "Inactive/Removed"),
            "graduated": sum(1 for row in rows if str(row.get("status", "")) == "Graduated"),
        }

    def dedupe_students(self, rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        students: Dict[DashboardKey, Mapping[str, Any]] = {}
        for row in rows:
            key = self.student_key(row)
            if not key:
                continue

            existing = students.get(key)
            if existing is None or self.row_score(row) >= self.row_score(existing):
                students[key] = row
        return [dict(row) for row in students.values()]

    def area_counts(self, rows: Sequence[Mapping[str, Any]], *, limit: int = 12) -> List[Tuple[str, int]]:
        counts = Counter((row.get("area") or "No area").strip() or "No area" for row in rows)
        return counts.most_common(limit)

    def sponsor_counts(self, rows: Sequence[Mapping[str, Any]], *, limit: int = 12) -> List[Tuple[str, int]]:
        counts = Counter((row.get("sponsor") or "No sponsor").strip() or "No sponsor" for row in rows)
        return counts.most_common(limit)

    def attention_items(self, rows: Sequence[Mapping[str, Any]], *, limit: int = 12) -> List[Dict[str, Any]]:
        attention = []
        required = ("contact", "school", "birthday", "photo_url")
        for student in rows:
            missing = [
                field.replace("_url", "").replace("_", " ")
                for field in required
                if not str(student.get(field) or "").strip()
            ]
            if missing:
                name = f"{student.get('last_name', '')}, {student.get('first_name', '')}".strip(", ")
                attention.append((len(missing), name or "Unnamed student", ", ".join(missing[:3]), student.get("id")))

        return [
            {"missing_count": count, "name": name, "missing_text": missing_text, "student_id": student_id}
            for count, name, missing_text, student_id in sorted(attention, reverse=True)[:limit]
        ]

    def build_lists(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        deduped = self.dedupe_students(rows)
        return {
            "rows": deduped,
            "area_counts": self.area_counts(deduped),
            "sponsor_counts": self.sponsor_counts(deduped),
            "attention": self.attention_items(deduped),
        }

    def student_key(self, row: Mapping[str, Any]) -> Optional[DashboardKey]:
        last = str(row.get("last_name") or "").strip().lower()
        first = str(row.get("first_name") or "").strip().lower()
        if not last or not first:
            return None
        birthday = str(row.get("birthday") or "").strip().lower()
        area = str(row.get("area") or "").strip().lower()
        return last, first, birthday or area

    def row_score(self, row: Mapping[str, Any]) -> int:
        fields = ("contact", "school", "birthday", "photo_url", "sponsor", "area", "grade")
        score = sum(1 for field in fields if str(row.get(field) or "").strip())
        if str(row.get("status") or "") == "Active":
            score += 1
        return score