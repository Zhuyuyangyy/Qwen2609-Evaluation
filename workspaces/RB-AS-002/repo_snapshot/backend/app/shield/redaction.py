"""Credential redaction for behavior-graph parameter summaries.

Tool-call parameters are rendered into ``BehaviorNode.params_summary`` so the
graph can be inspected and exported.  Those summaries must never leak
credentials.

The previous implementation matched a small set of key names exactly and only
at the top level, so it missed both:

* nested values  -- ``{"db": {"password": "hunter2"}}``
* key variants   -- ``passwd``, ``api_key_id``, ``X-Api-Key``, ``AUTH_TOKEN``

This module redacts recursively and matches keys by normalised form plus known
sensitive substrings.
"""

from __future__ import annotations

from typing import Any, List, Optional

REDACTED = "***"

#: Exact key names (normalised) that must never appear in a summary.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "api_key_id",
        "authorization",
        "auth",
        "auth_token",
        "credential",
        "credentials",
        "private_key",
        "session_key",
        "cookie",
        "set_cookie",
        "bearer",
        "signature",
        "salt",
        "otp",
        "mfa_code",
        "ssn",
        "card_number",
        "cvv",
    }
)

#: Substrings that mark a key as sensitive even when the full name differs.
_SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
    "session_key",
    "cvv",
    "card_number",
)

#: Guards against pathological nesting / oversized payloads.
MAX_REDACT_DEPTH = 8
MAX_REDACT_ITEMS = 200


def normalize_key(key: Any) -> str:
    """Normalise a key for matching: lowercase, non-alphanumerics collapsed."""
    text = str(key).strip().lower()
    cleaned = [ch if ch.isalnum() else "_" for ch in text]
    return "_".join(part for part in "".join(cleaned).split("_") if part)


def is_sensitive_key(key: Any) -> bool:
    """True if ``key`` names a credential (exact match or known variant)."""
    normalized = normalize_key(key)
    if not normalized:
        return False
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_SUBSTRINGS)


def redact_sensitive(value: Any, depth: int = 0, budget: Optional[List[int]] = None) -> Any:
    """Recursively replace sensitive values with :data:`REDACTED`.

    Nested dicts and lists are handled, so ``{"db": {"password": "x"}}`` is
    redacted just like ``{"password": "x"}``.  Depth and item count are
    bounded so a hostile payload cannot blow up the summary.
    """
    if budget is None:
        budget = [MAX_REDACT_ITEMS]
    if depth > MAX_REDACT_DEPTH:
        return REDACTED
    if budget[0] <= 0:
        return value

    if isinstance(value, dict):
        budget[0] -= 1
        return {
            key: (
                REDACTED
                if is_sensitive_key(key)
                else redact_sensitive(item, depth + 1, budget)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        budget[0] -= 1
        return [redact_sensitive(item, depth + 1, budget) for item in value]
    return value


def summarize_params(tool_name: str, params: Any) -> str:
    """Render ``params`` into a redacted, human-readable summary string."""
    safe = redact_sensitive(params)
    if isinstance(safe, dict):
        body = ", ".join(f"{key}={value}" for key, value in safe.items())
    else:
        body = str(safe)
    return f"{tool_name}({body})"
