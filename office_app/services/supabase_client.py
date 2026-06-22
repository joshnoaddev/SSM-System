"""Supabase client factory."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from office_app.app_config import SUPABASE_KEY, SUPABASE_URL


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Return the shared Supabase client used by repositories."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_supabase() -> Client:
    """Compatibility alias for the current monolithic app."""
    return get_supabase_client()
