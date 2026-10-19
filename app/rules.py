"""Server-side validation for every write.

Forms are advisory: each of these functions re-reads the submitted values,
returns a cleaned ``values`` dict for re-rendering and an ``errors`` dict keyed
by field name. An empty ``errors`` dict means the write may proceed.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Mapping

from . import repo

MAX_NAME = 120
MAX_TEXT = 400

# Statuses that mean "work is going ahead" and therefore need heritage consent
# on a conservation-area street.
CONSENT_REQUIRED_STATUSES = frozenset({"scheduled", "in-progress", "complete"})

STATUS_LABELS = {
    "planned": "Planned",
    "scheduled": "Scheduled",
    "in-progress": "In progress",
    "complete": "Complete",
    "blocked": "Blocked",
}


def _text(form: Mapping[str, str], key: str) -> str:
    return (form.get(key) or "").strip()


def _checked(form: Mapping[str, str], key: str) -> bool:
    return (form.get(key) or "").strip().lower() in {"1", "on", "true", "yes"}


def parse_positive_int(raw: str) -> int | None:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _iso_date(raw: str) -> str | None:
    """Return a normalised ISO date, '' for blank, or None when malformed."""
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def today_iso() -> str:
    return date.today().isoformat()


def heritage_consent_error(
    conn: sqlite3.Connection, patch_id: int | None, status: str, consent_ref: str
) -> str | None:
    """The shared heritage consent gate used by both job create and job edit."""
    if status not in CONSENT_REQUIRED_STATUSES:
        return None
    if patch_id is None:
        return None
    patch = repo.get_patch(conn, patch_id)
    if patch is None or not patch["heritage_conservation_area"]:
        return None
    if consent_ref.strip():
        return None
    return (
        "This street is a heritage conservation area. Record the heritage consent "
        "reference before the job can be scheduled, started or completed."
    )


def validate_street(
    conn: sqlite3.Connection, form: Mapping[str, str], exclude_id: int | None = None
) -> tuple[dict[str, object], dict[str, str]]:
    values: dict[str, object] = {
        "name": _text(form, "name"),
        "district": _text(form, "district"),
        "heritage": _checked(form, "heritage"),
        "notes": _text(form, "notes"),
    }
    errors: dict[str, str] = {}

    name = str(values["name"])
    if not name:
        errors["name"] = "Enter the street name."
    elif len(name) > MAX_NAME:
        errors["name"] = f"Keep the street name under {MAX_NAME} characters."
    elif repo.street_name_taken(conn, name, exclude_id):
        errors["name"] = f"“{name}” is already registered. Street names must be unique."

    if len(str(values["district"])) > MAX_NAME:
        errors["district"] = f"Keep the district under {MAX_NAME} characters."
    if len(str(values["notes"])) > MAX_TEXT:
        errors["notes"] = f"Keep notes under {MAX_TEXT} characters."

    return values, errors


def validate_patch(form: Mapping[str, str]) -> tuple[dict[str, object], dict[str, str]]:
    sett_raw = _text(form, "sett_count")
    severity = _text(form, "severity") or "medium"
    status = _text(form, "status") or "open"
    discovered_raw = _text(form, "discovered_on")

    values: dict[str, object] = {
        "location_description": _text(form, "location_description"),
        "sett_count": sett_raw,
        "severity": severity,
        "status": status,
        "discovered_on": discovered_raw or today_iso(),
        "notes": _text(form, "notes"),
    }
    errors: dict[str, str] = {}

    location = str(values["location_description"])
    if not location:
        errors["location_description"] = "Describe where the loose setts are."
    elif len(location) > MAX_TEXT:
        errors["location_description"] = f"Keep the location under {MAX_TEXT} characters."

    sett_count = parse_positive_int(sett_raw)
    if sett_count is None:
        errors["sett_count"] = "Enter the sett count as a whole number greater than zero."

    if severity not in repo.SEVERITIES:
        errors["severity"] = "Choose low, medium or high severity."

    if status not in repo.PATCH_STATUSES:
        errors["status"] = "Patch status must be open or repaired."

    discovered = _iso_date(discovered_raw)
    if discovered is None:
        errors["discovered_on"] = "Enter the discovery date as YYYY-MM-DD."

    if len(str(values["notes"])) > MAX_TEXT:
        errors["notes"] = f"Keep notes under {MAX_TEXT} characters."

    return values, errors


def validate_crew(form: Mapping[str, str]) -> tuple[dict[str, object], dict[str, str]]:
    values: dict[str, object] = {
        "name": _text(form, "name"),
        "foreman": _text(form, "foreman"),
    }
    errors: dict[str, str] = {}

    if not values["name"]:
        errors["name"] = "Enter the crew name."
    elif len(str(values["name"])) > MAX_NAME:
        errors["name"] = f"Keep the crew name under {MAX_NAME} characters."

    if not values["foreman"]:
        errors["foreman"] = "Enter the foreman for this crew."
    elif len(str(values["foreman"])) > MAX_NAME:
        errors["foreman"] = f"Keep the foreman name under {MAX_NAME} characters."

    return values, errors


def validate_job(
    conn: sqlite3.Connection, form: Mapping[str, str], patch_id: int
) -> tuple[dict[str, object], dict[str, str]]:
    sett_raw = _text(form, "sett_count")
    status = _text(form, "status") or "planned"
    crew_raw = _text(form, "crew_id")
    consent_ref = _text(form, "heritage_consent_ref")
    scheduled_raw = _text(form, "scheduled_for")

    values: dict[str, object] = {
        "crew_id": crew_raw,
        "sett_count": sett_raw,
        "status": status,
        "heritage_consent_ref": consent_ref,
        "scheduled_for": scheduled_raw,
        "notes": _text(form, "notes"),
    }
    errors: dict[str, str] = {}

    crew_id: int | None = None
    if not crew_raw:
        errors["crew_id"] = "Choose a repair crew for this job."
    else:
        crew_id = parse_positive_int(crew_raw)
        crew = repo.get_crew(conn, crew_id) if crew_id is not None else None
        if crew is None:
            errors["crew_id"] = "Choose a repair crew from the roster."
        elif not crew["active"]:
            errors["crew_id"] = (
                f"{crew['name']} is inactive. Choose an active crew or reactivate it first."
            )
    values["crew_id"] = crew_id

    sett_count = parse_positive_int(sett_raw)
    if sett_count is None:
        errors["sett_count"] = "Enter the sett count as a whole number greater than zero."
    values["sett_count"] = sett_count

    if status not in repo.JOB_STATUSES:
        errors["status"] = (
            "Choose a status: planned, scheduled, in-progress, complete or blocked."
        )

    scheduled = _iso_date(scheduled_raw)
    if scheduled is None:
        errors["scheduled_for"] = "Enter the scheduled date as YYYY-MM-DD."
    values["scheduled_for"] = scheduled if scheduled is not None else scheduled_raw

    consent_error = heritage_consent_error(conn, patch_id, status, consent_ref)
    if consent_error:
        errors["heritage_consent_ref"] = consent_error

    if len(str(values["notes"])) > MAX_TEXT:
        errors["notes"] = f"Keep notes under {MAX_TEXT} characters."

    return values, errors
