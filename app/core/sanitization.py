"""Redaction helpers.

The service deliberately stores only opaque identifiers for external entities,
but free-text fields (title/description) and any future payloads could still
contain secrets or PII. Everything that leaves the process as a *log line* or a
*domain event* is passed through :func:`sanitize` so that emails, URLs (incl.
signed/provider URLs), bearer tokens, JWTs and obviously-named secret fields can
never leak.
"""
from __future__ import annotations

import re
from typing import Any

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Dict keys whose *values* are always redacted wholesale, regardless of content.
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "signed_url",
        "signedurl",
        "storage_key",
        "storagekey",
        "provider_url",
        "providerurl",
        "provider_payload",
        "providerpayload",
        "credentials",
        "cookie",
        "set-cookie",
    }
)


def sanitize_string(value: str) -> str:
    value = _URL_RE.sub("[REDACTED_URL]", value)
    value = _JWT_RE.sub("[REDACTED_TOKEN]", value)
    value = _BEARER_RE.sub("[REDACTED_TOKEN]", value)
    value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    return value


def sanitize(value: Any) -> Any:
    """Recursively redact secrets/PII from arbitrary JSON-like structures."""
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = sanitize(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return sanitize_string(value)
    return value
