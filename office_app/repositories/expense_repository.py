"""Raw Supabase CRUD operations for expenses and budgets.

Repositories intentionally contain no PyQt imports and no business rules.
They translate method calls directly into Supabase table operations and return
raw dictionaries/lists from Supabase responses.
"""

from __future__ import annotations

from datetime import datetime, timezone
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
        query = (
            self.sb.table("expenses")
            .select("*")
            .eq("student_id", student_id)
            .is_("archived_at", "null")
        )
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

    def update_expense(
        self,
        expense_id: Any,
        fields: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("expenses")
            .update(fields)
            .eq("id", expense_id)
            .execute()
        )
        return list(response.data or [])

    def archive_expense(
        self,
        expense_id: Any,
        operator: str,
    ) -> List[Dict[str, Any]]:
        return self.update_expense(
            expense_id,
            {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "archived_by": str(operator or "").strip() or "Unknown operator",
            },
        )

    def restore_expense(self, expense_id: Any) -> List[Dict[str, Any]]:
        return self.update_expense(
            expense_id,
            {"archived_at": None, "archived_by": None},
        )

    def list_archived_expenses(self) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("expenses")
            .select("*")
            .not_.is_("archived_at", "null")
            .order("archived_at", desc=True)
            .execute()
        )
        return list(response.data or [])

    def get_financial_summary(
        self,
        student_id: Any,
        school_year: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self.list_financial_summaries([student_id], school_year).get(student_id)

    def list_financial_summaries(
        self,
        student_ids: List[Any],
        school_year: Optional[str] = None,
    ) -> Dict[Any, Dict[str, Any]]:
        if not student_ids:
            return {}

        summaries: Dict[Any, Dict[str, Any]] = {}
        requested_ids = {
            self._student_id_key(student_id): student_id
            for student_id in student_ids
        }
        school_year_text = str(school_year or "").strip()
        sy_filter = (
            school_year
            if school_year_text and school_year_text.casefold() != "all years"
            else None
        )

        budget_query = (
            self.sb.table("budgets")
            .select("student_id,school_year,amount")
            .in_("student_id", student_ids)
        )
        if sy_filter:
            budget_query = budget_query.eq("school_year", sy_filter)
        budget_rows = list(budget_query.execute().data or [])

        expense_query = (
            self.sb.table("expenses")
            .select("student_id,school_year,amount")
            .in_("student_id", student_ids)
            .is_("archived_at", "null")
        )
        if sy_filter:
            expense_query = expense_query.eq("school_year", sy_filter)
        expense_rows = list(expense_query.execute().data or [])

        def summary_for(student_id: Any) -> Dict[str, Any]:
            requested_id = requested_ids.get(
                self._student_id_key(student_id),
                student_id,
            )
            return summaries.setdefault(
                requested_id,
                {
                    "student_id": requested_id,
                    "school_year": sy_filter or "All years",
                    "total_budget": 0.0,
                    "total_expenses": 0.0,
                    "remaining_balance": 0.0,
                },
            )

        for row in budget_rows:
            student_id = row.get("student_id")
            if student_id is None:
                continue
            summary = summary_for(student_id)
            try:
                summary["total_budget"] += float(row.get("amount") or 0)
            except (TypeError, ValueError):
                continue

        for row in expense_rows:
            student_id = row.get("student_id")
            if student_id is None:
                continue
            summary = summary_for(student_id)
            try:
                summary["total_expenses"] += float(row.get("amount") or 0)
            except (TypeError, ValueError):
                continue

        for summary in summaries.values():
            summary["remaining_balance"] = (
                summary["total_budget"] - summary["total_expenses"]
            )

        return summaries

    @staticmethod
    def _student_id_key(student_id: Any) -> str:
        """Normalize equivalent UUID/text IDs without changing public keys."""
        return str(student_id or "").strip().casefold()

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
