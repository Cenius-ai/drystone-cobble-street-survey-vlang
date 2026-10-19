"""Sign-in, sign-out and the survey dashboard."""

from __future__ import annotations

import sqlite3
import time

from starlette.requests import Request
from starlette.responses import Response

from . import auth, db, repo, rules
from .web import form_text, redirect, render, safe_next, set_flash

# In-process failure counter: this deployment is a single operator instance, so
# a small windowed map is enough to blunt credential stuffing without any
# external store (and it resets on restart).
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 20
_login_failures: dict[str, list[float]] = {}


def _client_key(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


def _too_many_failures(key: str) -> bool:
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    recent = [moment for moment in _login_failures.get(key, []) if moment > cutoff]
    if recent:
        _login_failures[key] = recent
    else:
        _login_failures.pop(key, None)
    return len(recent) >= LOGIN_MAX_FAILURES


def _record_failure(key: str) -> None:
    if len(_login_failures) > 512:  # keep the map bounded
        _login_failures.clear()
    _login_failures.setdefault(key, []).append(time.monotonic())


def _clear_failures(key: str) -> None:
    _login_failures.pop(key, None)


# ----------------------------------------------------------------------------- auth


async def login_page(request: Request) -> Response:
    if auth.current_user_id(request.session) is not None:
        return redirect(safe_next(request.query_params.get("next")))
    return render(
        request,
        "login.html",
        {
            "form": {"email": ""},
            "errors": {},
            "next_path": safe_next(request.query_params.get("next")),
        },
    )


async def login_submit(request: Request) -> Response:
    form = await request.form()
    email = form_text(form, "email")
    raw_password = form.get("password")
    password = raw_password if isinstance(raw_password, str) else ""
    next_path = safe_next(form_text(form, "next"))
    client_key = _client_key(request)

    errors: dict[str, str] = {}
    if not email:
        errors["email"] = "Enter your operator email."
    if not password:
        errors["password"] = "Enter your password."

    if errors:
        return render(
            request,
            "login.html",
            {"form": {"email": email}, "errors": errors, "next_path": next_path},
            status_code=400,
        )

    if _too_many_failures(client_key):
        return render(
            request,
            "login.html",
            {
                "form": {"email": email},
                "errors": {
                    "form": "Too many sign-in attempts. Wait a few minutes and try again."
                },
                "next_path": next_path,
            },
            status_code=429,
        )

    with db.session() as conn:
        user = repo.get_user_by_email(conn, email)
    if user is None or not auth.verify_password(password, user["password_hash"]):
        _record_failure(client_key)
        # One non-enumerating message: never reveal whether the email exists.
        return render(
            request,
            "login.html",
            {
                "form": {"email": email},
                "errors": {"form": "Those credentials did not match an operator account."},
                "next_path": next_path,
            },
            status_code=401,
        )

    _clear_failures(client_key)
    request.session.clear()
    request.session["user_id"] = int(user["id"])
    request.session["email"] = user["email"]
    request.session["display_name"] = user["display_name"]
    auth.csrf_token(request.session)
    set_flash(request, "success", f"Signed in as {user['display_name']}.")
    return redirect(next_path)


async def logout(request: Request) -> Response:
    request.session.clear()
    request.session["flash"] = {"kind": "success", "message": "You have signed out."}
    return redirect("/login")


# ------------------------------------------------------------------------ dashboard


def _bar_class(count: int, total: int) -> str:
    """Map a count onto a fixed width utility class (keeps CSS out of markup)."""
    if total <= 0 or count <= 0:
        return "w0"
    percent = max(4, round(count * 100 / total))
    return f"w{min(100, int(round(percent / 5.0)) * 5)}"


def _dashboard_context(conn: sqlite3.Connection) -> dict[str, object]:
    job_counts = repo.job_counts_by_status(conn)
    job_total = sum(job_counts.values())
    street_total = repo.street_count(conn)
    return {
        "open_patches": repo.open_patch_count(conn),
        "total_patches": repo.total_patch_count(conn),
        "street_count": street_total,
        "heritage_streets": repo.heritage_street_count(conn),
        "job_counts": job_counts,
        "job_total": job_total,
        "job_bars": [
            {
                "status": status,
                "label": rules.STATUS_LABELS[status],
                "count": job_counts[status],
                "bar_class": _bar_class(job_counts[status], job_total),
            }
            for status in repo.JOB_STATUSES
        ],
        "consent_gaps": repo.heritage_consent_gap_count(conn),
        "gap_jobs": repo.heritage_gap_jobs(conn, limit=5),
        "setts_open": repo.setts_in_open_patches(conn),
        "setts_total": repo.total_setts_recorded(conn),
        "recent_patches": repo.recent_patches(conn, limit=5),
        "recent_jobs": repo.recent_jobs(conn, limit=5),
        "is_empty": street_total == 0,
    }


async def dashboard(request: Request) -> Response:
    """The survey dashboard, or the sign-in card for a visitor without a session.

    Rendering the sign-in card here (instead of redirecting) keeps the entry URL
    answering with a real HTML page; the card posts to /login and every other app
    route is still redirected to the login page by the session guard.
    """
    if auth.current_user_id(request.session) is None:
        return render(
            request,
            "login.html",
            {"form": {"email": ""}, "errors": {}, "next_path": "/"},
        )
    with db.session() as conn:
        context = _dashboard_context(conn)
    return render(request, "dashboard.html", context)
