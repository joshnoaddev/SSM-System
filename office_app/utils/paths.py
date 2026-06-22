"""Path helpers for source and PyInstaller builds."""

from __future__ import annotations

import os
import sys


def app_root() -> str:
    """Return the runtime root, compatible with PyInstaller's _MEIPASS."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resource_path(relative_path: str) -> str:
    """Resolve an app resource path in dev and frozen builds."""
    base_path = getattr(sys, "_MEIPASS", app_root())
    candidate = os.path.join(base_path, relative_path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(app_root(), relative_path)


def asset_path(*parts: str) -> str:
    """Resolve a path under the assets directory."""
    return resource_path(os.path.join("assets", *parts))
