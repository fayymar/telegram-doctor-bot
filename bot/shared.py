"""Shared in-memory state между main.py и bot handlers."""
from datetime import datetime

# web_auth_codes: code -> {telegram_id, first_name, last_name, username, photo_url, verified, created_at}
web_auth_codes: dict = {}
