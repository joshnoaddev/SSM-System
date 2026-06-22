"""Application configuration constants."""

from __future__ import annotations

import os

SUPABASE_URL = "https://oxkcghvcykddiptthapv.supabase.co"
SUPABASE_KEY = "sb_secret_EHTdEWgQapZrXI7vJCj4PQ_c5A2Lbk1"
KEEPALIVE_INTERVAL_MS = 4 * 24 * 60 * 60 * 1000
PHOTO_BUCKET = "student-photos"
LOGO_ASSET = os.path.join("assets", "ssm_logo.png")
USERS = ["Joshua", "Mary Rose", "Marylou"]
