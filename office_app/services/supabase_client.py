"""Supabase client factory."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from office_app.app_config import (
    get_supabase_admin_config,
    get_supabase_config,
    validate_desktop_supabase_config,
)


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return the shared Supabase client used by repositories."""
    url, key = get_supabase_config()
    try:
        validate_desktop_supabase_config(url, key)
    except ValueError as error:
        raise RuntimeError(str(error)) from error
    return create_client(url, key)


def get_supabase() -> Client:
    """Compatibility alias for the current monolithic app."""
    return get_supabase_client()


def reset_supabase_clients() -> None:
    """Discard cached clients after configuration changes."""
    get_supabase_client.cache_clear()
    get_supabase_admin_client.cache_clear()


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
    """Return a service-role client for explicit local administration scripts."""
    url, service_key = get_supabase_admin_config()
    if not url or not service_key:
        raise RuntimeError(
            "Admin access is not configured. Set SSM_SUPABASE_URL and "
            "SSM_SUPABASE_SERVICE_KEY for this administration command."
        )
    if not service_key.startswith(("sb_secret_", "service_role")):
        raise RuntimeError(
            "SSM_SUPABASE_SERVICE_KEY must contain a Supabase secret/service-role "
            "key. Never use this client from the desktop application."
        )
    return create_client(url, service_key)
