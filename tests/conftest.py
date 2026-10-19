"""Shared pytest fixtures: a fresh seeded database and a signed-in operator."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set before app.main is imported: the session middleware reads this at import.
os.environ.setdefault("SECRET_KEY", "drystone-test-session-key")

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DEMO_EMAIL = "cenius@cenius.ai"
DEMO_PASSWORD = "cenius"

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient backed by its own freshly seeded SQLite file."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'drystone-test.db'}")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_client(client):
    """An authenticated client (the seeded demo operator)."""
    response = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text[:400]
    return client


def csrf_token(test_client: TestClient, path: str = "/streets") -> str:
    """Read a CSRF token from a rendered page (and its session cookie)."""
    response = test_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    match = CSRF_PATTERN.search(response.text)
    assert match, f"no CSRF token rendered on {path}"
    return match.group(1)


def kpi_value(html: str, label: str) -> int:
    """Pull a metric tile value out of the dashboard HTML (plain string search)."""
    marker = '<p class="kpi-value">'
    label_at = html.find(label + "</p>")
    assert label_at != -1, f"metric tile {label!r} not found"
    value_at = html.find(marker, label_at)
    assert value_at != -1, f"metric tile {label!r} has no value element"
    start = value_at + len(marker)
    end = html.find("</p>", start)
    assert end != -1, f"metric tile {label!r} value is unterminated"
    return int(html[start:end].replace(",", "").strip())
