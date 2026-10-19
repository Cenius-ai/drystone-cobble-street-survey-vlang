"""Configuration read from the environment, with boot-safe defaults.

Every value has a working default so the app boots on a bare clone with no
``.env`` present. ``SECRET_KEY`` falls back to a clearly-marked development key
and logs a warning; nothing is ever required at import time.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("drystone.settings")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Development-only session key. Documented in README/INSTALL and replaced by the
# SECRET_KEY environment variable in any real deployment.
DEV_SECRET_KEY = "cenius-dev-6b1d3f8a94c27e05"
DEFAULT_DATABASE_URL = "sqlite:///./drystone.db"
DEFAULT_PORT = 8000

_warned_about_dev_secret = False


def load_env_file() -> None:
    """Load a local .env file without overriding real environment variables.

    The app boots fine with no .env at all; this only makes the documented
    ``cp .env.example .env`` workflow behave as users expect, without adding a
    dependency.
    """
    path = PROJECT_ROOT / ".env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        logger.warning("Could not read %s; continuing with environment defaults", path)
        return
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, _, value = entry.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


def secret_key() -> str:
    """Return the session signing key, falling back to the dev key."""
    global _warned_about_dev_secret
    configured = os.environ.get("SECRET_KEY", "").strip()
    if configured:
        return configured
    if not _warned_about_dev_secret:
        logger.warning(
            "SECRET_KEY is not set: signing sessions with the development "
            "fallback key. Set SECRET_KEY before deploying."
        )
        _warned_about_dev_secret = True
    return DEV_SECRET_KEY


def database_path() -> Path:
    """Resolve the SQLite file path from DATABASE_URL (relative by default)."""
    raw = os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///") :]
    elif raw.startswith("sqlite://"):
        raw = raw[len("sqlite://") :]
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def port() -> int:
    """Port for the standalone ``python3 -m app`` runner."""
    raw = os.environ.get("PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_PORT
