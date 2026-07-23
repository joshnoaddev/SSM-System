"""Expense receipt upload helpers independent of PyQt widgets."""

from __future__ import annotations

import os
import re
import urllib.request
from typing import Any, Optional


class ReceiptService:
    BUCKET = "expense-receipts"
    MAX_BYTES = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        client: Any = None,
    ) -> None:
        if not (supabase_url and supabase_key):
            from office_app.app_config import get_supabase_config

            cfg_url, cfg_key = get_supabase_config()
            supabase_url = supabase_url or cfg_url
            supabase_key = supabase_key or cfg_key
        self.supabase_url = str(supabase_url).rstrip("/")
        self.supabase_key = str(supabase_key)
        self.client = client

    def _auth_headers(self) -> dict[str, str]:
        access_token = ""
        if self.client is not None:
            session = self.client.auth.get_session()
            access_token = getattr(session, "access_token", "") if session else ""
        return {
            "Authorization": f"Bearer {access_token or self.supabase_key}",
            "apikey": self.supabase_key,
        }

    def upload_receipt(self, local_path: str, expense_id: Any) -> tuple[str, str]:
        if not local_path or not os.path.isfile(local_path):
            raise FileNotFoundError("Receipt file was not found.")
        extension = os.path.splitext(local_path)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise ValueError("Receipt must be a PDF, JPG, PNG, or WebP file.")
        size = os.path.getsize(local_path)
        if size > self.MAX_BYTES:
            raise ValueError("Receipt must be 10 MB or smaller.")

        original_name = os.path.basename(local_path)
        safe_stem = re.sub(
            r"[^A-Za-z0-9._-]+",
            "-",
            os.path.splitext(original_name)[0],
        ).strip("-._") or "receipt"
        remote_path = f"{expense_id}/{safe_stem}{extension}"
        with open(local_path, "rb") as receipt:
            data = receipt.read()
        content_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        request = urllib.request.Request(
            (
                f"{self.supabase_url}/storage/v1/object/"
                f"{self.BUCKET}/{remote_path}"
            ),
            data=data,
            headers={
                **self._auth_headers(),
                "Content-Type": content_types[extension],
                "x-upsert": "true",
            },
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=60):
            pass
        return (
            (
                f"{self.supabase_url}/storage/v1/object/public/"
                f"{self.BUCKET}/{remote_path}"
            ),
            original_name,
        )
