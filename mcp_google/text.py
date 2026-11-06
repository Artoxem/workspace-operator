"""Text hygiene shared by handlers.

Google APIs hand back three recurring nuisances that end up in tool output:

* HTML entities in Gmail snippets (``&#39;``, ``&amp;``, ``&quot;``);
* invisible padding — zero-width spaces, ``U+034F``, ``U+FEFF``, soft hyphens —
  which inflates snippets, wastes tokens and looks like broken output;
* raw ``HttpError`` dumps with request URLs and JSON details that no model
  should have to read.

Everything here is pure text processing: no network, no Google imports, so it
is cheap to unit test.
"""

import html
import re
from datetime import datetime, timezone

_INVISIBLE = {
    ord(char): None
    for char in "\u200b\u200c\u200d\u2060\ufeff\u034f\u00ad"
}

_SPACES = re.compile(r"[ \t\u00a0]+")
_NEWLINE_PAD = re.compile(r"[ \t]*\n[ \t]*")
_BLANK_LINES = re.compile(r"\n{3,}")
_TAGS = re.compile(r"<[^>]+>")
_DROP_BLOCKS = re.compile(r"(?is)<(script|style|head)\b.*?</\1>")
_BREAKS = re.compile(r"(?i)<br\s*/?>")
_BLOCK_ENDS = re.compile(r"(?i)</(p|div|tr|li|h[1-6]|table)>")
_HTTP_ERROR = re.compile(r'<HttpError (\d{3}) when requesting [^ ]+ returned "(.*?)"\.')
_LONG_LINK = re.compile(r"https?://\S{160,}")

_STATUS_HINTS = {
    400: ("bad request", "check the arguments"),
    401: ("authentication expired", "re-run the OAuth flow"),
    403: ("insufficient permissions", "check that the account can access this resource"),
    404: ("not found", "check the ID"),
    409: ("conflict", "the resource changed during the call"),
    429: ("rate limited", "retry later"),
    500: ("temporary Google API error", "retry later"),
    503: ("temporary Google API error", "retry later"),
}


def clean_text(
    value: object, limit: int | None = None, single_line: bool = False
) -> str:
    """Unescape entities, drop invisible characters, collapse whitespace."""
    if value is None:
        return ""

    text = html.unescape(str(value))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_INVISIBLE)
    text = _SPACES.sub(" ", text)
    text = _NEWLINE_PAD.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)

    if single_line:
        text = _SPACES.sub(" ", text.replace("\n", " "))

    text = text.strip()

    if limit is not None and len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text


def html_to_text(markup: object, limit: int | None = None) -> str:
    """Convert a small HTML fragment (email body) into readable plain text."""
    if not markup:
        return ""

    text = _DROP_BLOCKS.sub(" ", str(markup))
    text = _BREAKS.sub("\n", text)
    text = _BLOCK_ENDS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    return clean_text(text, limit)


def shorten_links(text: str, replacement: str = "[long link]") -> str:
    """Replace tracking/marketing URLs long enough to eat the context window."""
    return _LONG_LINK.sub(replacement, text)


def humanize_http_error(value: object, limit: int = 400) -> str:
    """Turn ``<HttpError 403 ...>`` noise into one readable line.

    Non-HTTP messages are passed through ``clean_text`` unchanged, so this is
    safe to apply to every error string.
    """
    text = str(value or "").strip()
    match = _HTTP_ERROR.search(text)
    if not match:
        return clean_text(text, limit)

    code = int(match.group(1))
    reason = clean_text(match.group(2)).rstrip(".")
    label, hint = _STATUS_HINTS.get(code, ("request failed", ""))

    message = f"Google API {code}: {reason or label}"
    if hint:
        message += f" — {hint}"

    prefix = clean_text(text[: match.start()]).rstrip()
    return f"{prefix} {message}" if prefix else message


def format_timestamp(value: object) -> str:
    """Normalise an RFC 3339 timestamp (Drive, Calendar) to ``YYYY-MM-DD HH:MM``."""
    raw = clean_text(value, single_line=True)
    if not raw:
        return "unknown"

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M")


def parse_email_date(value: object) -> str:
    """Normalise an RFC 2822 Date header to ``YYYY-MM-DD HH:MM`` (UTC)."""
    raw = clean_text(value, single_line=True)
    if not raw:
        return "unknown date"

    from email.utils import parsedate_to_datetime

    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw

    if parsed is None:
        return raw
    if parsed.tzinfo is not None:
        from datetime import timezone

        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M")
