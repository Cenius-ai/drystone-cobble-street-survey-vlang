"""Password hashing and session helpers.

Passwords are stored as PBKDF2-HMAC-SHA256 with a per-user random salt.
Verification uses ``hmac.compare_digest`` so the comparison is constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Mapping

PBKDF2_ITERATIONS = 260_000
PBKDF2_SCHEME = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>``."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_SCHEME}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a password against a stored hash."""
    try:
        scheme, iterations_raw, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != PBKDF2_SCHEME:
            return False
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token(session: Mapping) -> str:
    """Read (and lazily create) the CSRF token stored in the signed session."""
    token = session.get("csrf_token")
    if not isinstance(token, str) or not token:
        token = new_csrf_token()
        session["csrf_token"] = token  # type: ignore[index]
    return token


def csrf_is_valid(session: Mapping, submitted: str | None) -> bool:
    expected = session.get("csrf_token")
    if not isinstance(expected, str) or not expected:
        return False
    if not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


def current_user_id(session: Mapping) -> int | None:
    user_id = session.get("user_id")
    return user_id if isinstance(user_id, int) else None
