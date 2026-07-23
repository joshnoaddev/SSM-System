"""Application configuration and per-user desktop settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from office_app.services.secure_store import (
    SecureStoreError,
    protect_secret,
    unprotect_secret,
)

DEFAULT_SUPABASE_URL = "https://oxkcghvcykddiptthapv.supabase.co"
APP_CONFIG_DIR_NAME = "SSM Student Profiling"
APP_CONFIG_FILE_NAME = "config.json"
SYNC_TOKEN_CONFIG_KEY = "sheet_sync_token_protected"

KEEPALIVE_INTERVAL_MS = 4 * 24 * 60 * 60 * 1000
PHOTO_BUCKET = "student-photos"
LOGO_ASSET = os.path.join("assets", "ssm_logo.png")
APP_ICON_ASSET = os.path.join("assets", "ssm_app_icon.png")
USERS = ["Joshua", "Mary Rose", "Marylou"]


def user_config_path() -> Path:
    """Return the Windows-user configuration path used by the packaged app."""
    app_data = os.environ.get("APPDATA", "").strip()
    root = Path(app_data) if app_data else Path.home() / ".config"
    return root / APP_CONFIG_DIR_NAME / APP_CONFIG_FILE_NAME


def load_user_config(path: Path | None = None) -> dict[str, Any]:
    """Read non-secret desktop settings, tolerating a missing or damaged file."""
    config_path = path or user_config_path()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_user_config(
    payload: dict[str, Any],
    path: Path | None = None,
) -> Path:
    config_path = path or user_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config_path)
    return config_path


def get_supabase_config(path: Path | None = None) -> tuple[str, str]:
    """Resolve desktop credentials with environment variables taking priority."""
    saved = load_user_config(path)
    url = (
        os.environ.get("SSM_SUPABASE_URL")
        or saved.get("supabase_url")
        or DEFAULT_SUPABASE_URL
    )
    key = (
        os.environ.get("SSM_SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SSM_SUPABASE_KEY")
        or saved.get("supabase_publishable_key")
        or ""
    )
    return str(url).strip(), str(key).strip()


def get_supabase_admin_config() -> tuple[str, str]:
    """Resolve administrator-only credentials without persisting the secret."""
    url, _ = get_supabase_config()
    key = os.environ.get("SSM_SUPABASE_SERVICE_KEY", "").strip()
    return url, key


def validate_desktop_supabase_config(url: str, key: str) -> None:
    """Reject malformed endpoints and privileged keys before saving or use."""
    normalized_url = str(url or "").strip()
    normalized_key = str(key or "").strip()
    if not normalized_url:
        raise ValueError("Enter the Supabase project URL.")
    if (
        not normalized_url.startswith("https://")
        or ".supabase.co" not in normalized_url
    ):
        raise ValueError(
            "Enter a valid Supabase project URL, such as "
            "https://your-project.supabase.co."
        )
    if not normalized_key:
        raise ValueError("Enter the project's publishable or anon key.")
    if normalized_key.startswith(("sb_secret_", "service_role")):
        raise ValueError(
            "This is a secret/service-role key. Use the publishable or anon key "
            "instead."
        )


def save_supabase_config(
    url: str,
    key: str,
    path: Path | None = None,
) -> Path:
    """Validate and atomically store safe, non-secret desktop configuration."""
    normalized_url = str(url or "").strip().rstrip("/")
    normalized_key = str(key or "").strip()
    validate_desktop_supabase_config(normalized_url, normalized_key)

    payload = load_user_config(path)
    payload.update({
        "supabase_url": normalized_url,
        "supabase_publishable_key": normalized_key,
    })
    return _write_user_config(payload, path)


def get_sheet_sync_token(path: Path | None = None) -> str:
    """Return the per-user sync token from env or Windows DPAPI storage."""
    environment_token = os.environ.get("SSM_SHEET_SYNC_TOKEN", "").strip()
    if environment_token:
        return environment_token
    protected = str(
        load_user_config(path).get(SYNC_TOKEN_CONFIG_KEY) or ""
    ).strip()
    if not protected:
        return ""
    try:
        return unprotect_secret(protected).strip()
    except SecureStoreError:
        return ""


def save_sheet_sync_token(
    token: str,
    path: Path | None = None,
) -> Path:
    """Protect and persist the Edge Function sync token for this Windows user."""
    normalized = str(token or "").strip()
    if len(normalized) < 32:
        raise ValueError("The private sync token must contain at least 32 characters.")
    payload = load_user_config(path)
    payload[SYNC_TOKEN_CONFIG_KEY] = protect_secret(normalized)
    return _write_user_config(payload, path)


def clear_sheet_sync_token(path: Path | None = None) -> Path:
    """Remove the stored sync token while preserving other app settings."""
    payload = load_user_config(path)
    payload.pop(SYNC_TOKEN_CONFIG_KEY, None)
    return _write_user_config(payload, path)


# Compatibility values for older imports. Runtime services use the accessors
# above so a first-run configuration can take effect without restarting.
SUPABASE_URL, SUPABASE_KEY = get_supabase_config()
SUPABASE_SERVICE_KEY = os.environ.get("SSM_SUPABASE_SERVICE_KEY", "").strip()
