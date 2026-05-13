"""Shared password complexity validator used by user-creation and password-change schemas."""

import re

_MIN_LENGTH = 12
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate_password_complexity(password: str) -> str:
    parts: list[str] = []
    if len(password) < _MIN_LENGTH:
        parts.append(f"be at least {_MIN_LENGTH} characters")
    if not _UPPER_RE.search(password):
        parts.append("include an uppercase letter")
    if not _LOWER_RE.search(password):
        parts.append("include a lowercase letter")
    if not _DIGIT_RE.search(password):
        parts.append("include a digit")
    if not _SPECIAL_RE.search(password):
        parts.append("include a special character")

    if parts:
        raise ValueError("Password must " + ", ".join(parts) + ".")
    return password
