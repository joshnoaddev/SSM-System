"""Raw Supabase CRUD operations for workbook-imported tables."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from office_app.services.supabase_client import get_supabase_client


class WorkbookRepository:
    """Data access for tables populated from Excel workbook sheets.

    This class intentionally contains no PyQt imports and no business logic.
    Methods return raw dictionaries/lists from Supabase responses.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self.sb = client or get_supabase_client()

    def delete_donor_students_by_school_year(self, school_year: str) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("donor_students")
            .delete()
            .eq("school_year", school_year)
            .execute()
        )
        return list(response.data or [])

    def delete_all_student_movements(self) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("student_movements")
            .delete()
            .neq("id", 0)
            .execute()
        )
        return list(response.data or [])

    def insert_records(
        self,
        table_name: str,
        records: List[Dict[str, Any]],
        *,
        chunk_size: int = 100,
    ) -> List[Dict[str, Any]]:
        if not records:
            return []

        inserted: List[Dict[str, Any]] = []
        for start in range(0, len(records), chunk_size):
            chunk = records[start:start + chunk_size]
            if not chunk:
                continue
            response = self.sb.table(table_name).insert(chunk).execute()
            inserted.extend(list(response.data or []))
        return inserted