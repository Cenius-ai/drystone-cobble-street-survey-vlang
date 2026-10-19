"""Repair crew roster views."""

from __future__ import annotations

from typing import Any, Mapping

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from . import db, repo, rules
from .web import read_form, redirect, render, set_flash


def _crew_form_defaults() -> dict[str, Any]:
    return {"name": "", "foreman": ""}


async def crews_list(request: Request) -> Response:
    with db.session() as conn:
        crews = repo.list_crews(conn)
        active = sum(1 for crew in crews if crew["active"])
        context = {
            "crews": crews,
            "active_count": active,
            "inactive_count": len(crews) - active,
            "form": _crew_form_defaults(),
            "errors": {},
        }
    return render(request, "crews.html", context)


async def crews_create(request: Request) -> Response:
    form = await read_form(request)
    with db.session() as conn:
        values, errors = rules.validate_crew(form)
        if errors:
            crews = repo.list_crews(conn)
            active = sum(1 for crew in crews if crew["active"])
            return render(
                request,
                "crews.html",
                {
                    "crews": crews,
                    "active_count": active,
                    "inactive_count": len(crews) - active,
                    "form": values,
                    "errors": errors,
                },
                status_code=400,
            )
        crew_id = repo.create_crew(conn, str(values["name"]), str(values["foreman"]))
    set_flash(request, "success", f"Crew “{values['name']}” added to the roster.")
    return redirect(f"/crews/{crew_id}")


def _crew_detail_context(
    conn,
    crew,
    form: Mapping[str, Any] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "crew": crew,
        "jobs": repo.jobs_for_crew(conn, int(crew["id"])),
        "form": form or {"name": crew["name"], "foreman": crew["foreman"]},
        "errors": errors or {},
    }


async def crew_detail(request: Request) -> Response:
    crew_id = request.path_params["crew_id"]
    with db.session() as conn:
        crew = repo.get_crew(conn, crew_id)
        if crew is None:
            raise HTTPException(status_code=404)
        context = _crew_detail_context(conn, crew)
    return render(request, "crew_detail.html", context)


async def crew_edit(request: Request) -> Response:
    crew_id = request.path_params["crew_id"]
    form = await read_form(request)
    with db.session() as conn:
        crew = repo.get_crew(conn, crew_id)
        if crew is None:
            raise HTTPException(status_code=404)
        values, errors = rules.validate_crew(form)
        if errors:
            context = _crew_detail_context(conn, crew, form=values, errors=errors)
            return render(request, "crew_detail.html", context, status_code=400)
        repo.update_crew(conn, crew_id, str(values["name"]), str(values["foreman"]))
    set_flash(request, "success", "Crew details updated.")
    return redirect(f"/crews/{crew_id}")


async def crew_toggle(request: Request) -> Response:
    crew_id = request.path_params["crew_id"]
    await read_form(request)
    with db.session() as conn:
        crew = repo.get_crew(conn, crew_id)
        if crew is None:
            raise HTTPException(status_code=404)
        repo.toggle_crew_active(conn, crew_id)
        now_active = not crew["active"]
    if now_active:
        set_flash(request, "success", f"{crew['name']} is active and can be assigned jobs.")
    else:
        set_flash(
            request,
            "success",
            f"{crew['name']} is now inactive. Existing job history is unchanged.",
        )
    return redirect(f"/crews/{crew_id}")


async def crew_delete(request: Request) -> Response:
    crew_id = request.path_params["crew_id"]
    await read_form(request)
    with db.session() as conn:
        crew = repo.get_crew(conn, crew_id)
        if crew is None:
            raise HTTPException(status_code=404)
        job_count = repo.crew_job_count(conn, crew_id)
        if job_count:
            set_flash(
                request,
                "error",
                f"{job_count} repair job{'s' if job_count != 1 else ''} "
                f"reference{'s' if job_count == 1 else ''} {crew['name']}. "
                "Deactivate the crew instead to keep the job history intact.",
            )
            return redirect(f"/crews/{crew_id}")
        crew_name = crew["name"]
        repo.delete_crew(conn, crew_id)
    set_flash(request, "success", f"Crew “{crew_name}” removed from the roster.")
    return redirect("/crews")
