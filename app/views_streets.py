"""Street registry and cobble patch register views."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from . import db, repo, rules
from .web import form_text, read_form, redirect, render, set_flash

DISTRICT_HINT = "Clifton"


def _street_form_defaults() -> dict[str, Any]:
    return {"name": "", "district": "", "heritage": False, "notes": ""}


def _street_form_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "name": row["name"],
        "district": row["district"],
        "heritage": bool(row["heritage_conservation_area"]),
        "notes": row["notes"],
    }


def _patch_form_defaults() -> dict[str, Any]:
    return {
        "location_description": "",
        "sett_count": "",
        "severity": "medium",
        "status": "open",
        "discovered_on": rules.today_iso(),
        "notes": "",
    }


def _street_detail_context(
    conn: sqlite3.Connection,
    street: sqlite3.Row,
    street_form: Mapping[str, Any] | None = None,
    street_errors: Mapping[str, str] | None = None,
    patch_form: Mapping[str, Any] | None = None,
    patch_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    _, job_count = repo.street_dependants(conn, int(street["id"]))
    return {
        "street": street,
        "patches": repo.list_patches_for_street(conn, int(street["id"])),
        "job_count": job_count,
        "form": street_form or _street_form_from_row(street),
        "errors": street_errors or {},
        "patch_form": patch_form or _patch_form_defaults(),
        "patch_errors": patch_errors or {},
        "district_hint": DISTRICT_HINT,
    }


def _streets_list_context(
    conn: sqlite3.Connection,
    query: str = "",
    heritage_raw: str = "",
    sort: str = "name",
    form: Mapping[str, Any] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    heritage = True if heritage_raw == "1" else False if heritage_raw == "0" else None
    return {
        "streets": repo.list_streets(conn, query=query, heritage=heritage, sort=sort),
        "filters": {"q": query, "heritage": heritage_raw, "sort": sort},
        "filters_active": bool(query or heritage_raw or sort != "name"),
        "district_count": len(repo.distinct_districts(conn)),
        "form": form or _street_form_defaults(),
        "errors": errors or {},
        "district_hint": DISTRICT_HINT,
    }


# -------------------------------------------------------------------- street routes


async def streets_list(request: Request) -> Response:
    query = (request.query_params.get("q") or "").strip()
    heritage_raw = (request.query_params.get("heritage") or "").strip()
    sort = (request.query_params.get("sort") or "name").strip()
    if sort not in repo.STREET_SORTS:
        sort = "name"
    with db.session() as conn:
        context = _streets_list_context(conn, query, heritage_raw, sort)
    return render(request, "streets.html", context)


async def street_new_page(request: Request) -> Response:
    return render(
        request,
        "street_new.html",
        {"form": _street_form_defaults(), "errors": {}, "district_hint": DISTRICT_HINT},
    )


async def streets_create(request: Request) -> Response:
    form = await read_form(request)
    from_new_page = form_text(form, "origin") == "new"
    with db.session() as conn:
        values, errors = rules.validate_street(conn, form)
        if errors:
            if from_new_page:
                return render(
                    request,
                    "street_new.html",
                    {"form": values, "errors": errors, "district_hint": DISTRICT_HINT},
                    status_code=400,
                )
            context = _streets_list_context(conn, form=values, errors=errors)
            return render(request, "streets.html", context, status_code=400)
        street_id = repo.create_street(
            conn,
            str(values["name"]),
            str(values["district"]),
            bool(values["heritage"]),
            str(values["notes"]),
        )
    set_flash(request, "success", f"Street “{values['name']}” registered.")
    return redirect(f"/streets/{street_id}")


async def street_detail(request: Request) -> Response:
    street_id = request.path_params["street_id"]
    with db.session() as conn:
        street = repo.get_street(conn, street_id)
        if street is None:
            raise HTTPException(status_code=404)
        context = _street_detail_context(conn, street)
    return render(request, "street_detail.html", context)


async def street_edit(request: Request) -> Response:
    street_id = request.path_params["street_id"]
    form = await read_form(request)
    with db.session() as conn:
        street = repo.get_street(conn, street_id)
        if street is None:
            raise HTTPException(status_code=404)
        values, errors = rules.validate_street(conn, form, exclude_id=street_id)
        if errors:
            context = _street_detail_context(
                conn, street, street_form=values, street_errors=errors
            )
            return render(request, "street_detail.html", context, status_code=400)
        repo.update_street(
            conn,
            street_id,
            str(values["name"]),
            str(values["district"]),
            bool(values["heritage"]),
            str(values["notes"]),
        )
    set_flash(request, "success", "Street details updated.")
    return redirect(f"/streets/{street_id}")


async def street_delete(request: Request) -> Response:
    street_id = request.path_params["street_id"]
    await read_form(request)
    with db.session() as conn:
        street = repo.get_street(conn, street_id)
        if street is None:
            raise HTTPException(status_code=404)
        patch_count, job_count = repo.street_dependants(conn, street_id)
        if patch_count or job_count:
            parts = []
            if patch_count:
                parts.append(f"{patch_count} patch{'es' if patch_count != 1 else ''}")
            if job_count:
                parts.append(f"{job_count} repair job{'s' if job_count != 1 else ''}")
            set_flash(
                request,
                "error",
                f"“{street['name']}” still has {' and '.join(parts)} on record. "
                "Delete those first, then remove the street.",
            )
            return redirect(f"/streets/{street_id}")
        street_name = street["name"]
        repo.delete_street(conn, street_id)
    set_flash(request, "success", f"Street “{street_name}” deleted.")
    return redirect("/streets")


# --------------------------------------------------------------------- patch routes


async def patch_create(request: Request) -> Response:
    street_id = request.path_params["street_id"]
    form = await read_form(request)
    with db.session() as conn:
        street = repo.get_street(conn, street_id)
        if street is None:
            raise HTTPException(status_code=404)
        values, errors = rules.validate_patch(form)
        if errors:
            context = _street_detail_context(
                conn, street, patch_form=values, patch_errors=errors
            )
            return render(request, "street_detail.html", context, status_code=400)
        repo.create_patch(
            conn,
            street_id,
            str(values["location_description"]),
            int(values["sett_count"]),
            str(values["severity"]),
            str(values["status"]),
            str(values["discovered_on"]),
            str(values["notes"]),
        )
        street_name = street["name"]
    set_flash(request, "success", f"Patch logged on {street_name}.")
    return redirect(f"/streets/{street_id}")


def _patch_detail_context(
    conn: sqlite3.Connection,
    patch: sqlite3.Row,
    patch_form: Mapping[str, Any] | None = None,
    patch_errors: Mapping[str, str] | None = None,
    job_form: Mapping[str, Any] | None = None,
    job_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    crews = repo.list_crews(conn, only_active=True)
    return {
        "patch": patch,
        "jobs": repo.jobs_for_patch(conn, int(patch["id"])),
        "crews": crews,
        "patch_form": patch_form
        or {
            "location_description": patch["location_description"],
            "sett_count": patch["sett_count"],
            "severity": patch["severity"],
            "status": patch["status"],
            "discovered_on": patch["discovered_on"],
            "notes": patch["notes"],
        },
        "patch_errors": patch_errors or {},
        "job_form": job_form
        or {
            "crew_id": int(crews[0]["id"]) if crews else None,
            "sett_count": patch["sett_count"],
            "status": "planned",
            "heritage_consent_ref": "",
            "scheduled_for": "",
            "notes": "",
        },
        "job_errors": job_errors or {},
    }


async def patch_detail(request: Request) -> Response:
    patch_id = request.path_params["patch_id"]
    with db.session() as conn:
        patch = repo.get_patch(conn, patch_id)
        if patch is None:
            raise HTTPException(status_code=404)
        context = _patch_detail_context(conn, patch)
    return render(request, "patch_detail.html", context)


async def patch_edit(request: Request) -> Response:
    patch_id = request.path_params["patch_id"]
    form = await read_form(request)
    with db.session() as conn:
        patch = repo.get_patch(conn, patch_id)
        if patch is None:
            raise HTTPException(status_code=404)
        values, errors = rules.validate_patch(form)
        if errors:
            context = _patch_detail_context(
                conn, patch, patch_form=values, patch_errors=errors
            )
            return render(request, "patch_detail.html", context, status_code=400)
        repo.update_patch(
            conn,
            patch_id,
            str(values["location_description"]),
            int(values["sett_count"]),
            str(values["severity"]),
            str(values["status"]),
            str(values["discovered_on"]),
            str(values["notes"]),
        )
    set_flash(request, "success", "Patch updated.")
    return redirect(f"/patches/{patch_id}")


async def patch_delete(request: Request) -> Response:
    patch_id = request.path_params["patch_id"]
    await read_form(request)
    with db.session() as conn:
        patch = repo.get_patch(conn, patch_id)
        if patch is None:
            raise HTTPException(status_code=404)
        street_id = int(patch["street_id"])
        job_count = repo.patch_job_count(conn, patch_id)
        if job_count:
            set_flash(
                request,
                "error",
                f"{job_count} repair job{'s' if job_count != 1 else ''} still "
                f"reference{'s' if job_count == 1 else ''} this patch. "
                "Delete the job first, then remove the patch.",
            )
            return redirect(f"/patches/{patch_id}")
        street_name = patch["street_name"]
        repo.delete_patch(conn, patch_id)
    set_flash(request, "success", f"Patch removed from {street_name}.")
    return redirect(f"/streets/{street_id}")
