"""Raw Supabase CRUD operations for expenses and budgets.

Repositories intentionally contain no PyQt imports and no business rules.
They translate method calls directly into Supabase table operations and return
raw dictionaries/lists from Supabase responses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _default_client() -> Any:
    """Resolve the shared Supabase client without coupling to a concrete name."""
    try:
        from office_app.services.supabase_client import get_supabase_client

        return get_supabase_client()
    except ImportError:
        from office_app.services.supabase_client import get_supabase

        return get_supabase()


class ExpenseRepository:
    """Data access for the ``expenses`` and ``budgets`` tables."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self.sb = client or _default_client()

    def list_expenses(
        self,
        student_id: Any,
        school_year: Optional[str] = None,
        *,
        order_by: str = "date",
    ) -> List[Dict[str, Any]]:
        query = self.sb.table("expenses").select("*").eq("student_id", student_id)
        if school_year:
            query = query.eq("school_year", school_year)
        response = query.order(order_by).execute()
        return list(response.data or [])

    def insert_expense(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self.sb.table("expenses").insert(record).execute()
        return list(response.data or [])

    def delete_expense(self, expense_id: Any) -> List[Dict[str, Any]]:
        response = self.sb.table("expenses").delete().eq("id", expense_id).execute()
        return list(response.data or [])

    def list_budgets(self, student_id: Any) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("budgets")
            .select("*")
            .eq("student_id", student_id)
            .execute()
        )
        return list(response.data or [])

    def get_budget(self, student_id: Any, school_year: str) -> Optional[Dict[str, Any]]:
        response = (
            self.sb.table("budgets")
            .select("*")
            .eq("student_id", student_id)
            .eq("school_year", school_year)
            .execute()
        )
        rows = list(response.data or [])
        return rows[0] if rows else None

    def insert_budget(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self.sb.table("budgets").insert(record).execute()
        return list(response.data or [])

    def update_budget(
        self,
        student_id: Any,
        school_year: str,
        fields: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("budgets")
            .update(fields)
            .eq("student_id", student_id)
            .eq("school_year", school_year)
            .execute()
        )
        return list(response.data or [])

