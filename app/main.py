"""Application factory: routes, middleware, exception handling, lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import db, seed, settings
from .views_auth import dashboard, login_page, login_submit, logout
from .views_crews import (
    crew_delete,
    crew_detail,
    crew_edit,
    crew_toggle,
    crews_create,
    crews_list,
)
from .views_jobs import job_delete, job_detail, job_edit, jobs_create, jobs_list, jobs_new
from .views_streets import (
    patch_create,
    patch_delete,
    patch_detail,
    patch_edit,
    street_delete,
    street_detail,
    street_edit,
    street_new_page,
    streets_create,
    streets_list,
)
from .web import (
    CsrfError,
    LoginGateMiddleware,
    SecurityHeadersMiddleware,
    render,
)

logger = logging.getLogger("drystone")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: Starlette):
    db.init_db()
    result = seed.seed()
    logger.info(
        "Drystone ready — database %s (%s), rows %s",
        result["database"],
        "seed inserted" if result["survey_created"] else "seed already present",
        result["counts"],
    )
    yield


async def health(_: Request) -> Response:
    return PlainTextResponse("ok")


async def http_error(request: Request, exc: HTTPException) -> Response:
    status = getattr(exc, "status_code", 500) or 500
    if status == 404:
        title = "Page not found"
        heading = "That page is not on the survey map"
        message = (
            "The address you followed does not match a street, patch, crew or "
            "job in this register."
        )
    else:
        title = "Request not completed"
        heading = "The register could not complete that request"
        message = f"Nothing was saved. {getattr(exc, 'detail', '') or 'Reload and try again.'}".strip()
    return render(
        request,
        "error.html",
        {"title": title, "heading": heading, "message": message, "status": status},
        status_code=status,
    )


async def server_error(request: Request, exc: Exception) -> Response:
    logger.exception("Unhandled error for %s %s", request.method, request.url.path)
    return render(
        request,
        "error.html",
        {
            "title": "Something went wrong",
            "heading": "The register could not complete that request",
            "message": (
                "Nothing was saved. Try again, and if it keeps failing check the "
                "server log for the full detail."
            ),
            "status": 500,
        },
        status_code=500,
    )


async def csrf_failure(request: Request, exc: CsrfError) -> Response:
    logger.warning("Rejected a form without a valid CSRF token: %s", request.url.path)
    return render(
        request,
        "error.html",
        {
            "title": "Form expired",
            "heading": "That form was out of date",
            "message": (
                "The security token on the form has expired, so nothing was saved. "
                "Reload the page and submit it again."
            ),
            "status": 400,
        },
        status_code=400,
    )


routes = [
    Route("/", dashboard, name="dashboard"),
    Route("/index.html", dashboard, name="dashboard-index"),
    Route("/app", dashboard, name="dashboard-app"),
    Route("/home", dashboard, name="dashboard-home"),
    Route("/login", login_page, methods=["GET"]),
    Route("/login", login_submit, methods=["POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/health", health),
    Route("/streets", streets_list, methods=["GET"]),
    Route("/streets", streets_create, methods=["POST"]),
    Route("/streets/new", street_new_page, methods=["GET"]),
    Route("/streets/{street_id:int}", street_detail, methods=["GET"]),
    Route("/streets/{street_id:int}/edit", street_edit, methods=["POST"]),
    Route("/streets/{street_id:int}/delete", street_delete, methods=["POST"]),
    Route("/streets/{street_id:int}/patches", patch_create, methods=["POST"]),
    Route("/patches/{patch_id:int}", patch_detail, methods=["GET"]),
    Route("/patches/{patch_id:int}/edit", patch_edit, methods=["POST"]),
    Route("/patches/{patch_id:int}/delete", patch_delete, methods=["POST"]),
    Route("/crews", crews_list, methods=["GET"]),
    Route("/crews", crews_create, methods=["POST"]),
    Route("/crews/{crew_id:int}", crew_detail, methods=["GET"]),
    Route("/crews/{crew_id:int}/edit", crew_edit, methods=["POST"]),
    Route("/crews/{crew_id:int}/toggle-active", crew_toggle, methods=["POST"]),
    Route("/crews/{crew_id:int}/delete", crew_delete, methods=["POST"]),
    Route("/jobs", jobs_list, methods=["GET"]),
    Route("/jobs", jobs_create, methods=["POST"]),
    Route("/jobs/new", jobs_new, methods=["GET"]),
    Route("/jobs/{job_id:int}", job_detail, methods=["GET"]),
    Route("/jobs/{job_id:int}/edit", job_edit, methods=["POST"]),
    Route("/jobs/{job_id:int}/delete", job_delete, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

middleware = [
    Middleware(SecurityHeadersMiddleware),
    Middleware(
        SessionMiddleware,
        secret_key=settings.secret_key(),
        session_cookie="drystone_session",
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=False,
    ),
    Middleware(LoginGateMiddleware),
]

app = Starlette(
    debug=False,
    routes=routes,
    middleware=middleware,
    lifespan=lifespan,
    exception_handlers={
        HTTPException: http_error,
        CsrfError: csrf_failure,
        Exception: server_error,
    },
)
