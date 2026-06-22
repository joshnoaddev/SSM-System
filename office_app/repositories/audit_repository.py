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
        self.sb.table("app_audit_log").insert({
            "operator": operator,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "details": details or {},
        }).execute()
