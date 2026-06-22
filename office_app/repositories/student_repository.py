"""Raw Supabase CRUD operations for student records."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


from office_app.services.supabase_client import get_supabase_client


class StudentRepository:
    """Data access for the students table.

    This class intentionally contains no PyQt imports and no business logic.
    Methods return raw dictionaries/lists from Supabase responses.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self.sb = client or get_supabase_client()

    def list_students(
        self,
        *,
        columns: str = "*",
        order_by: str = "last_name",
        ascending: bool = True,
    ) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("students")
            .select(columns)
            .order(order_by, desc=not ascending)
            .execute()
        )
        return list(response.data or [])

    def ping(self) -> List[Dict[str, Any]]:
        response = self.sb.table("students").select("id").limit(1).execute()
        return list(response.data or [])
    def get_student(self, student_id: Any, *, columns: str = "*") -> Optional[Dict[str, Any]]:
        response = (
            self.sb.table("students")
            .select(columns)
            .eq("id", student_id)
            .execute()
        )
        rows = list(response.data or [])
        return rows[0] if rows else None

    def get_student_single(self, student_id: Any, *, columns: str = "*") -> Dict[str, Any]:
        response = (
            self.sb.table("students")
            .select(columns)
            .eq("id", student_id)
            .single()
            .execute()
        )
        return dict(response.data or {})

    def insert_student(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self.sb.table("students").insert(record).execute()
        return list(response.data or [])

    def update_student(self, student_id: Any, fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("students")
            .update(fields)
            .eq("id", student_id)
            .execute()
        )
        return list(response.data or [])

    def delete_student(self, student_id: Any) -> List[Dict[str, Any]]:
        response = self.sb.table("students").delete().eq("id", student_id).execute()
        return list(response.data or [])

    def update_photo_url(self, student_id: Any, photo_url: Optional[str]) -> List[Dict[str, Any]]:
        return self.update_student(student_id, {"photo_url": photo_url})

    def update_status(self, student_id: Any, status: str) -> List[Dict[str, Any]]:
        return self.update_student(student_id, {"status": status})

    def find_students_by_field(
        self,
        field: str,
        value: Any,
        *,
        columns: str = "*",
    ) -> List[Dict[str, Any]]:
        response = self.sb.table("students").select(columns).eq(field, value).execute()
        return list(response.data or [])
    def insert_students(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not records:
            return []
        response = self.sb.table("students").insert(records).execute()
        return list(response.data or [])

    def import_students(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        response = self.sb.rpc(
            "import_students_transactional",
            {"payload": records},
        ).execute()
        return int(response.data or 0)

    def find_by_identity(
        self,
        last_name: str,
        first_name: str,
        birthday: Optional[str] = None,
        *,
        columns: str = "id",
    ) -> List[Dict[str, Any]]:
        query = (
            self.sb.table("students")
            .select(columns)
            .eq("last_name", last_name)
            .eq("first_name", first_name)
        )
        if birthday:
            query = query.eq("birthday", birthday)
        response = query.limit(1).execute()
        return list(response.data or [])
    def search_students(
        self,
        *,
        columns: str = "*",
        name_query: Optional[str] = None,
        sponsor_query: Optional[str] = None,
        area: Optional[str] = None,
        area_exact: bool = False,
        order_by: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        def build_query():
            query = self.sb.table("students").select(columns)
            if name_query:
                escaped = name_query.replace("\\", "\\\\").replace('"', '\\"')
                query = query.or_(
                    f'last_name.ilike."%{escaped}%",first_name.ilike."%{escaped}%"'
                )
            if sponsor_query:
                query = query.ilike("sponsor", f"%{sponsor_query}%")
            if area:
                query = query.eq("area", area) if area_exact else query.ilike("area", area)
            for field in order_by or []:
                query = query.order(field)
            return query

        query = build_query()
        if limit is not None:
            query = query.range(offset, offset + limit - 1)
        response = query.execute()
        return list(response.data or [])
