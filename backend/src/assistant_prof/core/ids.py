"""Identifier generation and validation."""

import re
import uuid

# Strict on purpose: correlation IDs may come from a request header and end up in logs.
_CORRELATION_ID_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")


def new_uuid() -> str:
    """Return a random UUID string for documents, templates and other entities."""
    return str(uuid.uuid4())


def new_correlation_id() -> str:
    """Return a fresh correlation ID (32 hex characters)."""
    return uuid.uuid4().hex


def is_valid_correlation_id(value: str) -> bool:
    """Tell whether a client-supplied correlation ID is safe to reuse."""
    return _CORRELATION_ID_RE.fullmatch(value) is not None
