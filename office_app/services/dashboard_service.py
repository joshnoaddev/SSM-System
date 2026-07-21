"""Dashboard aggregation and attention-list business logic."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

DashboardKey = Tuple[str, str, str]


class DashboardService:
    """Build dashboard summaries from student rows without PyQt dependencies."""

    def latest_sync_cohort(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return the roster written by the latest Google Sheet transaction.

        Workbook sync preserves older and manually created database records.
        Every row touched by one sync receives the same ``sheet_synced_at``
        transaction timestamp, so the newest timestamp identifies the current
        source roster. Legacy databases without sync metadata keep their
        previous all-row behavior.
        """
        copied = [dict(row) for row in rows]
        sync_timestamps = [
            str(row.get("sheet_synced_at") or "").strip()
            for row in copied
            if str(row.get("sheet_synced_at") or "").strip()
        ]
        if not sync_timestamps:
            return copied

        latest_timestamp = max(sync_timestamps)
        return [
            row
            for row in copied
            if str(row.get("sheet_synced_at") or "").strip() == latest_timestamp
        ]

    def summary_counts(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
        statuses = [self.status_bucket(row.get("status")) for row in rows]
        return {
            "total": len(rows),
            "active": statuses.count("active"),
            "inactive": statuses.count("inactive"),
            "graduated": statuses.count("graduated"),
        }

    def status_bucket(self, status: Any) -> str:
        normalized = " ".join(str(status or "Active").strip().lower().replace("/", " ").split())
        if "graduat" in normalized:
            return "graduated"
        if "inactive" in normalized or "removed" in normalized:
            return "inactive"
        return "active"

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

    def attention_items(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        limit: Optional[int] = 12,
    ) -> List[Dict[str, Any]]:
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

        items = [
            {"missing_count": count, "name": name, "missing_text": missing_text, "student_id": student_id}
            for count, name, missing_text, student_id in sorted(attention, reverse=True)
        ]
        return items if limit is None else items[:limit]

    def build_lists(self, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        deduped = self.dedupe_students(rows)
        attention = self.attention_items(deduped, limit=None)
        return {
            "rows": deduped,
            "area_counts": self.area_counts(deduped),
            "sponsor_counts": self.sponsor_counts(deduped),
            "attention": attention[:12],
            "attention_count": len(attention),
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
        if self.status_bucket(row.get("status")) == "active":
            score += 1
        return score
