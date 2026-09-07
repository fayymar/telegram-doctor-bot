"""Helpers for safely inserting user-supplied text into Telegram Markdown messages."""
import re

# Characters with special meaning in Telegram's legacy "Markdown" parse_mode.
_MARKDOWN_SPECIAL_CHARS = re.compile(r'([_*`\[])')


def escape_markdown(text) -> str:
    """Escape special characters so arbitrary text is safe inside parse_mode="Markdown".

    Without this, user-entered symptom text containing '_', '*', '`' or '[' can break
    message formatting or cause the send call to fail outright.
    """
    if text is None:
        return ""
    return _MARKDOWN_SPECIAL_CHARS.sub(r'\\\1', str(text))
