"""Raw Supabase CRUD operations for coordinator records."""

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


class CoordinatorRepository:
    """Data access for the ``coordinators`` table."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self.sb = client or _default_client()

    def list_coordinators(self, *, order_by: str = "location") -> List[Dict[str, Any]]:
        response = self.sb.table("coordinators").select("*").order(order_by).execute()
        return list(response.data or [])

    def insert_coordinator(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self.sb.table("coordinators").insert(record).execute()
        return list(response.data or [])

    def update_coordinator(
        self,
        coordinator_id: Any,
        fields: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("coordinators")
            .update(fields)
            .eq("id", coordinator_id)
            .execute()
        )
        return list(response.data or [])

    def delete_coordinator(self, coordinator_id: Any) -> List[Dict[str, Any]]:
        response = (
            self.sb.table("coordinators")
            .delete()
            .eq("id", coordinator_id)
            .execute()
        )
        return list(response.data or [])
    def insert_coordinators(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not records:
            return []
        response = self.sb.table("coordinators").insert(records).execute()
        return list(response.data or [])

    def delete_all_coordinators(self) -> List[Dict[str, Any]]:
        response = self.sb.table("coordinators").delete().neq("id", 0).execute()
        return list(response.data or [])
