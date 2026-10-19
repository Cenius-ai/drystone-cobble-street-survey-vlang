"""Shared web plumbing: templates, rendering, formatting, guard middleware.

Everything here is presentation-layer glue used by the view modules:
a single Jinja environment, the CSRF-protected form reader, the navigation
context, the login gate and the security response headers.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from starlette.datastructures import FormData, MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.templating import Jinja2Templates

from . import auth, db, repo, rules

APP_NAME = "Drystone Cobble Street Survey"
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"

logger = logging.getLogger("drystone")

SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    (
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; font-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    ),
)

# The entry paths always answer with a rendered HTML page (the survey dashboard
# when signed in, the sign-in card when not) so "/" is never an empty redirect.
ENTRY_PATHS = ("/", "/index.html", "/app", "/home")

# Routes reachable without a session. Every other app route redirects to /login.
PUBLIC_PATHS = frozenset({*ENTRY_PATHS, "/login", "/health", "/favicon.ico"})
PUBLIC_PREFIXES = ("/static/",)


# --------------------------------------------------------------------- formatting


def human_date(value: Any) -> str:
    """Render an ISO date as a human label: Today / Yesterday / 6 days ago."""
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        moment = date.fromisoformat(text[:10])
    except ValueError:
        return text
    delta = (date.today() - moment).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta == -1:
        return "Tomorrow"
    if 1 < delta <= 13:
        return f"{delta} days ago"
    if -13 <= delta < -1:
        return f"In {-delta} days"
    return moment.strftime("%d %b %Y").lstrip("0")


def human_stamp(value: Any) -> str:
    """Render a stored ISO timestamp as a short human label."""
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    return f"{human_date(moment.date().isoformat())}, {moment.strftime('%H:%M')}"


templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.filters["human_date"] = human_date
templates.env.filters["human_stamp"] = human_stamp
templates.env.globals.update(
    APP_NAME=APP_NAME,
    PATCH_STATUSES=repo.PATCH_STATUSES,
    SEVERITIES=repo.SEVERITIES,
    JOB_STATUSES=repo.JOB_STATUSES,
    STATUS_LABELS=rules.STATUS_LABELS,
)


# ------------------------------------------------------------------ form handling


class CsrfError(Exception):
    """Raised when a state-changing form arrives without a valid CSRF token."""


async def read_form(request: Request) -> FormData:
    """Parse a submitted form and enforce the CSRF token held in the session."""
    form = await request.form()
    if not auth.csrf_is_valid(request.session, form.get("csrf_token")):
        raise CsrfError()
    return form


def form_text(form: Mapping[str, Any], key: str) -> str:
    value = form.get(key)
    return value.strip() if isinstance(value, str) else ""


def safe_next(raw: str | None, fallback: str = "/") -> str:
    """Only allow same-origin relative redirect targets."""
    if not raw:
        return fallback
    if not raw.startswith("/") or raw.startswith("//"):
        return fallback
    return raw


# -------------------------------------------------------------------- rendering


def current_operator(request: Request) -> sqlite3.Row | None:
    user_id = auth.current_user_id(request.session)
    if user_id is None:
        return None
    with db.session() as conn:
        return repo.get_user(conn, user_id)


def active_nav(path: str) -> str:
    if path.startswith("/streets") or path.startswith("/patches"):
        return "streets"
    if path.startswith("/jobs"):
        return "jobs"
    if path.startswith("/crews"):
        return "crews"
    return "dashboard"


def pop_flash(request: Request) -> dict[str, str] | None:
    flash = request.session.pop("flash", None)
    return flash if isinstance(flash, dict) else None


def set_flash(request: Request, kind: str, message: str) -> None:
    request.session["flash"] = {"kind": kind, "message": message}


def render(
    request: Request,
    template_name: str,
    context: Mapping[str, Any] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    payload: dict[str, Any] = dict(context or {})
    payload.setdefault("operator", current_operator(request))
    payload.setdefault("active_nav", active_nav(request.url.path))
    payload.setdefault("csrf_token", auth.csrf_token(request.session))
    payload.setdefault("flash", pop_flash(request))
    payload.setdefault("today", rules.today_iso())
    return templates.TemplateResponse(
        request, template_name, payload, status_code=status_code
    )


def redirect(path: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(path, status_code=status_code)


# --------------------------------------------------------------------- middleware


class SecurityHeadersMiddleware:
    """Attach the baseline security headers to every HTTP response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


class LoginGateMiddleware(BaseHTTPMiddleware):
    """Redirect anonymous visitors to /login, remembering where they were going."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if is_public_path(path) or auth.current_user_id(request.session) is not None:
            return await call_next(request)

        target = path
        if request.url.query:
            target = f"{path}?{request.url.query}"
        return redirect(f"/login?next={quote(target, safe='/')}")
