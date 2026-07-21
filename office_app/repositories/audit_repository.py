"""Append-only operational audit log."""

from __future__ import annotations

from typing import Any, Dict, Optional

from office_app.services.supabase_client import get_supabase_client


class AuditRepository:
    def __init__(self, client: Optional[Any] = None) -> None:
        self.sb = client or get_supabase_client()

    def log(
        self,
        *,
        operator: str,
        action: str,
        entity_type: str,
        entity_id: Any = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            self.sb.table("app_audit_log").insert({
                "operator": operator,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id) if entity_id is not None else None,
                "details": details or {},
            }).execute()
        except Exception as e:
            print(f"Audit log failed: {e}")

    def latest_google_sheet_sync(self) -> Optional[Dict[str, Any]]:
        """Return the newest successful server-side workbook audit entry."""
        response = (
            self.sb.table("app_audit_log")
            .select("created_at,details")
            .eq("operator", "Google Sheets Sync")
            .eq("action", "synchronize")
            .eq("entity_type", "workbook")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = list(response.data or [])
        return dict(rows[0]) if rows else None
