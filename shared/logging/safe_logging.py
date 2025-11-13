"""Safe logging helpers that avoid leaking credential material."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os

_LOGGER = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
DEBUG_TOKENS_ENABLED = os.getenv("DEBUG_TOKENS", "false").strip().lower() in _TRUTHY

_fingerprint_key_raw = os.getenv("LOG_FINGERPRINT_KEY", "").strip()
_FINGERPRINT_KEY: bytes | None = _fingerprint_key_raw.encode("utf-8") if _fingerprint_key_raw else None

if DEBUG_TOKENS_ENABLED and not _FINGERPRINT_KEY:
    _LOGGER.warning(
        "[safe-logging] DEBUG_TOKENS enabled but LOG_FINGERPRINT_KEY missing; "
        "token fingerprints will be suppressed"
    )


def header_presence(header_name: str, value_present: bool) -> str:
    """Return a stable descriptor for header presence."""
    return f"{header_name}={'present' if value_present else 'absent'}"


def token_presence(label: str, token: str | None) -> str:
    """
    Describe whether a token was present without logging its value.

    When DEBUG_TOKENS=true and LOG_FINGERPRINT_KEY is set, emit a short,
    non-reversible fingerprint for correlating logs in development.
    """
    if not token:
        return f"{label}=absent"
    if not DEBUG_TOKENS_ENABLED:
        return f"{label}=present"
    if not _FINGERPRINT_KEY:
        return f"{label}=fp-disabled"
    return f"{label}_fp={token_fingerprint(token)}"


def token_fingerprint(token: str) -> str:
    """
    Produce a stable fingerprint for a token using HMAC-SHA256 + base64url.

    When LOG_FINGERPRINT_KEY is missing, returns "fp-disabled".
    """
    if not _FINGERPRINT_KEY:
        return "fp-disabled"
    digest = hmac.new(_FINGERPRINT_KEY, token.encode("utf-8"), hashlib.sha256).digest()
    # Shorten for readability while keeping enough entropy for debugging
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:24]
