"""Photo upload and cache helpers independent of PyQt widgets."""

from __future__ import annotations

import os
import shutil
import urllib.request
from typing import Any, List, Optional


def _photo_config() -> tuple[str, str, str]:
    from office_app.app_config import PHOTO_BUCKET, get_supabase_config

    supabase_url, supabase_key = get_supabase_config()
    return supabase_url, supabase_key, PHOTO_BUCKET


class PhotoService:
    """Handles storage uploads and local photo cache management."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        photo_bucket: Optional[str] = None,
        cache_dir: Optional[str] = None,
        client=None,
    ) -> None:
        if not (supabase_url and supabase_key and photo_bucket):
            cfg_url, cfg_key, cfg_bucket = _photo_config()
            supabase_url = supabase_url or cfg_url
            supabase_key = supabase_key or cfg_key
            photo_bucket = photo_bucket or cfg_bucket

        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.photo_bucket = photo_bucket
        self.client = client
        self.cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".ssm_photo_cache"
        )

    def _auth_headers(self) -> dict[str, str]:
        """Use a session JWT when present, otherwise the shared office key."""
        access_token = ""
        if self.client is not None:
            session = self.client.auth.get_session()
            access_token = getattr(session, "access_token", "") if session else ""
        return {
            "Authorization": f"Bearer {access_token or self.supabase_key}",
            "apikey": self.supabase_key,
        }

    def _photo_cache_path(self, url: str) -> str:
        """Stable local cache path derived from the URL filename."""
        name = str(url or "").rstrip("/").split("/")[-1].split("?")[0]
        if not name:
            name = "photo"
        os.makedirs(self.cache_dir, exist_ok=True)
        return os.path.join(self.cache_dir, name)

    photo_cache_path = _photo_cache_path

    def _upload_photo(
        self,
        local_path: str,
        student_id: Any,
        log: Optional[List[str]] = None,
    ) -> str:
        """Upload a photo with direct Storage REST calls and explicit timeouts."""

        def write_log(message: str) -> None:
            if log is not None:
                log.append(message)

        if not local_path or not os.path.exists(local_path):
            raise FileNotFoundError(f"Photo file not found: {local_path}")

        ext = os.path.splitext(local_path)[1].lower()
        if not ext:
            raise ValueError("Photo file must have an extension.")

        remote_path = f"{student_id}{ext}"
        content_type = self._content_type_for_extension(ext)
        write_log(f"remote_path={remote_path} content_type={content_type}")

        with open(local_path, "rb") as file:
            data = file.read()
        write_log(f"File bytes: {len(data)}")

        storage_url = (
            f"{self.supabase_url}/storage/v1/object/"
            f"{self.photo_bucket}/{remote_path}"
        )
        headers = {
            **self._auth_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",
        }

        self._save_debug_log("About to PUT file...", log)
        request = urllib.request.Request(
            storage_url,
            data=data,
            headers=headers,
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
        self._save_debug_log(f"PUT response: {body[:200]}", log)

        public_url = (
            f"{self.supabase_url}/storage/v1/object/public/"
            f"{self.photo_bucket}/{remote_path}"
        )
        self._save_debug_log(f"Final URL: {public_url!r}", log)
        return public_url

    upload_photo = _upload_photo

    def _download_photo_to_cache(self, url: str, *, timeout: int = 30) -> tuple[str, bytes]:
        """Download a storage/public photo URL into the deterministic cache path."""
        if not url:
            raise ValueError("Photo URL is required.")

        fetch_url, headers = self._download_request_parts(url)
        request = urllib.request.Request(fetch_url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
        if not data:
            raise ValueError("Empty response")

        cache_path = self._photo_cache_path(url)
        with open(cache_path, "wb") as file:
            file.write(data)
        return cache_path, data

    download_photo_to_cache = _download_photo_to_cache

    def clear_student_cache(
        self,
        student_id: Any,
        extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg"),
    ) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        for ext in extensions:
            cache_path = os.path.join(self.cache_dir, f"{student_id}{ext}")
            try:
                if os.path.exists(cache_path):
                    os.remove(cache_path)
            except Exception:
                pass

    def delete_storage_photo_variants(
        self,
        student_id: Any,
        extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg"),
        *,
        timeout: int = 10,
    ) -> None:
        for ext in extensions:
            try:
                storage_url = (
                    f"{self.supabase_url}/storage/v1/object/"
                    f"{self.photo_bucket}/{student_id}{ext}"
                )
                request = urllib.request.Request(
                    storage_url,
                    method="DELETE",
                    headers=self._auth_headers(),
                )
                with urllib.request.urlopen(request, timeout=timeout):
                    pass
            except Exception:
                pass

    def _download_request_parts(self, url: str) -> tuple[str, dict[str, str]]:
        marker = "/storage/v1/object/public/"
        if marker in url:
            after = url.split(marker, 1)[1]
            return (
                f"{self.supabase_url}/storage/v1/object/authenticated/{after}",
                self._auth_headers(),
            )
        return url, {"User-Agent": "Mozilla/5.0"}
    def _cache_uploaded_photo(self, source_path: str, url: str) -> Optional[str]:
        """Copy a just-uploaded local photo into the deterministic cache path."""
        if not source_path or not os.path.exists(source_path):
            return None
        cache_path = self._photo_cache_path(url)
        shutil.copy2(source_path, cache_path)
        return cache_path

    cache_uploaded_photo = _cache_uploaded_photo

    @staticmethod
    def _content_type_for_extension(ext: str) -> str:
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mapping.get(ext.lower(), f"image/{ext.lstrip('.')}")

    @staticmethod
    def _save_debug_log(message: str, log: Optional[List[str]]) -> None:
        if log is not None:
            log.append(message)
            try:
                path = os.path.join(os.path.expanduser("~"), "ssm_photo_debug.txt")
                with open(path, "w", encoding="utf-8") as file:
                    file.write("\n".join(log))
            except Exception:
                pass
