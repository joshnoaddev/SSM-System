"""Server-side Google Sheet synchronization client for the desktop UI."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from office_app.app_config import get_supabase_config
from office_app.repositories.audit_repository import AuditRepository


class SheetSyncError(RuntimeError):
    """A user-actionable synchronization failure."""


class GoogleSheetSyncService:
    FUNCTION_NAME = "sync-google-sheet"
    CONFIRMATION = "SYNC_SSM_MASTERLIST"

    def __init__(
        self,
        audit_repository: Optional[AuditRepository] = None,
        *,
        timeout_seconds: int = 120,
    ) -> None:
        self.audit_repository = audit_repository or AuditRepository()
        self.timeout_seconds = timeout_seconds

    def synchronize(self, sync_token: str) -> Dict[str, Any]:
        token = str(sync_token or "").strip()
        if not token:
            raise SheetSyncError(
                "Add the private Google Sheet sync token in Settings first."
            )
        return self._invoke(
            {
                "mode": "commit",
                "confirmation": self.CONFIRMATION,
            },
            sync_token=token,
        )

    def dry_run(self) -> Dict[str, Any]:
        return self._invoke({"mode": "dry-run"})

    def latest_success(self) -> Optional[Dict[str, Any]]:
        return self.audit_repository.latest_google_sheet_sync()

    def _invoke(
        self,
        payload: Dict[str, Any],
        *,
        sync_token: str = "",
    ) -> Dict[str, Any]:
        project_url, publishable_key = get_supabase_config()
        if not project_url or not publishable_key:
            raise SheetSyncError("The Supabase connection is not configured.")

        endpoint = (
            f"{project_url.rstrip('/')}/functions/v1/{self.FUNCTION_NAME}"
        )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "apikey": publishable_key,
            "Authorization": f"Bearer {publishable_key}",
            "User-Agent": "SSM-Student-Profiling-Desktop",
        }
        if sync_token:
            headers["x-ssm-sync-token"] = sync_token

        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            message = self._response_error(raw)
            if error.code == 401:
                raise SheetSyncError(
                    "The sync request was not authorized. Check the private "
                    "token and Edge Function authentication setting."
                ) from error
            raise SheetSyncError(message or f"Sync failed with HTTP {error.code}.") from error
        except URLError as error:
            raise SheetSyncError(
                "Could not reach the sync service. Check the internet connection."
            ) from error
        except TimeoutError as error:
            raise SheetSyncError(
                "The sync service took too long to respond. Try again."
            ) from error

        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SheetSyncError(
                "The sync service returned an unreadable response."
            ) from error
        if not isinstance(result, dict) or not result.get("ok"):
            message = result.get("error") if isinstance(result, dict) else ""
            raise SheetSyncError(str(message or "The workbook sync failed."))
        return result

    @staticmethod
    def _response_error(raw: str) -> str:
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if isinstance(result, dict):
            return str(result.get("error") or result.get("message") or "")
        return ""

    @staticmethod
    def format_timestamp(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "No successful sync recorded"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        return parsed.astimezone().strftime("%b %d, %Y at %I:%M %p")
