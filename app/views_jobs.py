"""Repair job list, creation, detail, edit and delete views."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from . import db, repo, rules
from .web import form_text, read_form, redirect, render, set_flash

PATCH_OPTIONS_SQL = """
    SELECT p.id, p.location_description, p.sett_count, p.status, p.severity,
           s.name AS street_name, s.heritage_conservation_area
      FROM patches p
      JOIN streets s ON s.id = p.street_id
     ORDER BY s.name COLLATE NOCASE ASC, p.discovered_on DESC, p.id DESC
"""


def _patch_options(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(PATCH_OPTIONS_SQL).fetchall())


def _assignable_crews(
    conn: sqlite3.Connection, current_crew_id: int | None = None
) -> list[sqlite3.Row]:
    """Active crews plus the crew already on the job, even if it is inactive."""
    crews = repo.list_crews(conn, only_active=True)
    if current_crew_id is not None and all(
        int(crew["id"]) != current_crew_id for crew in crews
    ):
        current = repo.get_crew(conn, current_crew_id)
        if current is not None:
            crews = [current, *crews]
    return crews


def _job_form_defaults(
    patch: sqlite3.Row | None, crews: list[sqlite3.Row]
) -> dict[str, Any]:
    return {
        "patch_id": int(patch["id"]) if patch is not None else None,
        "crew_id": int(crews[0]["id"]) if crews else None,
        "sett_count": patch["sett_count"] if patch is not None else "",
        "status": "planned",
        "heritage_consent_ref": "",
        "scheduled_for": "",
        "notes": "",
    }


def _job_form_from_row(job: sqlite3.Row) -> dict[str, Any]:
    return {
        "patch_id": int(job["patch_id"]),
        "crew_id": int(job["crew_id"]),
        "sett_count": job["sett_count"],
        "status": job["status"],
        "heritage_consent_ref": job["heritage_consent_ref"],
        "scheduled_for": job["scheduled_for"],
        "notes": job["notes"],
    }


# ---------------------------------------------------------------------- job list


async def jobs_list(request: Request) -> Response:
    statuses = [value for value in request.query_params.getlist("status") if value]
    street_raw = (request.query_params.get("street_id") or "").strip()
    street_id = int(street_raw) if street_raw.isdigit() else None
    query = (request.query_params.get("q") or "").strip()

    with db.session() as conn:
        jobs = repo.list_jobs(conn, statuses=statuses, street_id=street_id, query=query)
        streets = repo.list_streets(conn, sort="name")
        total_jobs = len(repo.list_jobs(conn))

    return render(
        request,
        "jobs.html",
        {
            "jobs": jobs,
            "streets": streets,
            "statuses": statuses,
            "selected_street_id": street_id,
            "query": query,
            "total_jobs": total_jobs,
            "filters_active": bool(statuses or street_id is not None or query),
        },
    )


# -------------------------------------------------------------------- job create


def _jobs_new_context(
    conn: sqlite3.Connection,
    form: Mapping[str, Any] | None = None,
    errors: Mapping[str, str] | None = None,
    selected_patch: sqlite3.Row | None = None,
) -> dict[str, Any]:
    patches = _patch_options(conn)
    if selected_patch is None and form is not None:
        patch_id = form.get("patch_id")
        if isinstance(patch_id, int):
            selected_patch = repo.get_patch(conn, patch_id)
    if selected_patch is None and patches:
        # Default to a real patch so the form is submittable in one pass.
        selected_patch = repo.get_patch(conn, int(patches[0]["id"]))
    crews = _assignable_crews(conn)
    return {
        "patches": patches,
        "crews": crews,
        "selected_patch": selected_patch,
        "form": form or _job_form_defaults(selected_patch, crews),
        "errors": errors or {},
    }


async def jobs_new(request: Request) -> Response:
    patch_raw = (request.query_params.get("patch_id") or "").strip()
    patch_id = int(patch_raw) if patch_raw.isdigit() else None
    with db.session() as conn:
        selected_patch = repo.get_patch(conn, patch_id) if patch_id else None
        context = _jobs_new_context(conn, selected_patch=selected_patch)
    return render(request, "jobs_new.html", context)


async def jobs_create(request: Request) -> Response:
    form = await read_form(request)
    with db.session() as conn:
        patch_raw = form_text(form, "patch_id")
        patch_id = int(patch_raw) if patch_raw.isdigit() else None
        patch = repo.get_patch(conn, patch_id) if patch_id else None
        if patch is None:
            context = _jobs_new_context(
                conn, errors={"patch_id": "Choose the patch this repair job is raised from."}
            )
            return render(request, "jobs_new.html", context, status_code=400)

        values, errors = rules.validate_job(conn, form, patch_id)
        values["patch_id"] = patch_id
        if errors:
            context = _jobs_new_context(
                conn, form=values, errors=errors, selected_patch=patch
            )
            return render(request, "jobs_new.html", context, status_code=400)

        job_id = repo.create_job(
            conn,
            patch_id,
            int(values["crew_id"]),
            int(values["sett_count"]),
            str(values["status"]),
            str(values["heritage_consent_ref"]),
            str(values["scheduled_for"] or ""),
            str(values["notes"]),
        )
        patch_label = patch["location_description"]
    set_flash(request, "success", f"Repair job raised for {patch_label}.")
    return redirect(f"/jobs/{job_id}")


# --------------------------------------------------------------- job detail + edit


def _job_detail_context(
    conn: sqlite3.Connection,
    job: sqlite3.Row,
    form: Mapping[str, Any] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "job": job,
        "form": form or _job_form_from_row(job),
        "errors": errors or {},
        "crews": _assignable_crews(conn, int(job["crew_id"])),
    }


async def job_detail(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    with db.session() as conn:
        job = repo.get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404)
        context = _job_detail_context(conn, job)
    return render(request, "job_detail.html", context)


async def job_edit(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    form = await read_form(request)
    with db.session() as conn:
        job = repo.get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404)
        values, errors = rules.validate_job(conn, form, int(job["patch_id"]))
        values["patch_id"] = int(job["patch_id"])
        if errors:
            context = _job_detail_context(conn, job, form=values, errors=errors)
            return render(request, "job_detail.html", context, status_code=400)
        repo.update_job(
            conn,
            job_id,
            int(values["crew_id"]),
            int(values["sett_count"]),
            str(values["status"]),
            str(values["heritage_consent_ref"]),
            str(values["scheduled_for"] or ""),
            str(values["notes"]),
        )
    set_flash(request, "success", "Repair job updated.")
    return redirect(f"/jobs/{job_id}")


async def job_delete(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    await read_form(request)
    with db.session() as conn:
        job = repo.get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404)
        repo.delete_job(conn, job_id)
        patch_id = int(job["patch_id"])
    set_flash(
        request,
        "success",
        f"Repair job deleted. Patch #{patch_id} is now free of jobs.",
    )
    return redirect(f"/patches/{patch_id}")
