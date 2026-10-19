"""Rule tests: delete guards, sett counts, statuses, crew activity, heritage consent."""

from __future__ import annotations

from conftest import csrf_token, kpi_value


# ------------------------------------------------------------------ delete guards


def test_street_delete_is_blocked_while_patches_exist(auth_client):
    token = csrf_token(auth_client, "/streets/1")
    response = auth_client.post(
        "/streets/1/delete", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    page = auth_client.get("/streets/1").text
    assert "still has" in page
    assert "Cobble Lane" in auth_client.get("/streets").text


def test_patch_delete_is_blocked_while_a_job_references_it(auth_client):
    token = csrf_token(auth_client, "/patches/1")
    response = auth_client.post(
        "/patches/1/delete", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    page = auth_client.get("/patches/1").text
    assert "still references this patch" in page


def test_crew_delete_is_blocked_while_a_job_references_it(auth_client):
    token = csrf_token(auth_client, "/crews/1")
    response = auth_client.post(
        "/crews/1/delete", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    page = auth_client.get("/crews/1").text
    assert "Deactivate the crew instead" in page


def test_patch_without_jobs_can_be_deleted(auth_client):
    token = csrf_token(auth_client, "/patches/2")
    response = auth_client.post(
        "/patches/2/delete", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    assert auth_client.get("/patches/2", follow_redirects=False).status_code == 404


def test_crew_without_jobs_can_be_deleted(auth_client):
    created = auth_client.post(
        "/crews",
        data={
            "csrf_token": csrf_token(auth_client, "/crews"),
            "name": "Spare Gang",
            "foreman": "Lee Ash",
        },
        follow_redirects=False,
    )
    crew_path = created.headers["location"]
    deleted = auth_client.post(
        f"{crew_path}/delete",
        data={"csrf_token": csrf_token(auth_client, crew_path)},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    listing = auth_client.get("/crews").text
    assert f'href="{crew_path}"' not in listing
    assert auth_client.get(crew_path, follow_redirects=False).status_code == 404


# --------------------------------------------------------------- sett + statuses


def test_non_positive_sett_counts_are_rejected_on_create(auth_client):
    token = csrf_token(auth_client, "/streets/1")
    for value in ("0", "-3", "abc", ""):
        response = auth_client.post(
            "/streets/1/patches",
            data={
                "csrf_token": token,
                "location_description": "Invalid setts",
                "sett_count": value,
                "severity": "medium",
                "status": "open",
                "discovered_on": "2026-01-05",
            },
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert (
            "Enter the sett count as a whole number greater than zero." in response.text
        )
    assert "Invalid setts" not in auth_client.get("/streets/1").text


def test_non_positive_sett_counts_are_rejected_on_edit(auth_client):
    token = csrf_token(auth_client, "/patches/3")
    response = auth_client.post(
        "/patches/3/edit",
        data={
            "csrf_token": token,
            "location_description": "Kerb-side channel opposite the bonded warehouse",
            "sett_count": "-8",
            "severity": "medium",
            "status": "open",
            "discovered_on": "2026-01-02",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Enter the sett count as a whole number greater than zero." in response.text


def test_forged_patch_status_is_rejected(auth_client):
    token = csrf_token(auth_client, "/streets/1")
    response = auth_client.post(
        "/streets/1/patches",
        data={
            "csrf_token": token,
            "location_description": "Forged status patch",
            "sett_count": "9",
            "severity": "low",
            "status": "lost",
            "discovered_on": "2026-01-05",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Patch status must be open or repaired." in response.text


def test_forged_job_status_is_rejected(auth_client):
    token = csrf_token(auth_client, "/patches/6")
    response = auth_client.post(
        "/jobs",
        data={
            "csrf_token": token,
            "patch_id": "6",
            "crew_id": "1",
            "sett_count": "34",
            "status": "cancelled",
            "heritage_consent_ref": "",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Choose a status" in response.text


# ------------------------------------------------------------------- crew activity


def test_inactive_crew_cannot_be_assigned_even_when_forged(auth_client):
    token = csrf_token(auth_client, "/patches/6")
    response = auth_client.post(
        "/jobs",
        data={
            "csrf_token": token,
            "patch_id": "6",
            "crew_id": "3",
            "sett_count": "34",
            "status": "planned",
            "heritage_consent_ref": "",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "is inactive" in response.text
    assert "Setts Restoration Unit" not in auth_client.get("/jobs").text


def test_missing_crew_is_rejected(auth_client):
    token = csrf_token(auth_client, "/patches/6")
    response = auth_client.post(
        "/jobs",
        data={
            "csrf_token": token,
            "patch_id": "6",
            "crew_id": "",
            "sett_count": "34",
            "status": "planned",
            "heritage_consent_ref": "",
            "scheduled_for": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Choose a repair crew for this job." in response.text


# ----------------------------------------------------------------- heritage gate


def _job_form(patch_id: str, crew_id: str, status: str, consent: str, setts: str = "30"):
    return {
        "patch_id": patch_id,
        "crew_id": crew_id,
        "sett_count": setts,
        "status": status,
        "heritage_consent_ref": consent,
        "scheduled_for": "2026-03-02",
        "notes": "Heritage gate test.",
    }


def test_heritage_consent_required_on_create(auth_client):
    token = csrf_token(auth_client, "/patches/1")
    payload = _job_form("1", "1", "in-progress", "")
    payload["csrf_token"] = token
    response = auth_client.post("/jobs", data=payload, follow_redirects=False)
    assert response.status_code == 400
    assert "Record the heritage consent reference" in response.text
    # The operator's typed values are preserved in the re-rendered form.
    assert ">Heritage gate test.</textarea>" in response.text
    assert 'value="30"' in response.text
    assert 'value="in-progress" selected' in response.text


def test_planned_heritage_job_saves_without_a_consent_reference(auth_client):
    token = csrf_token(auth_client, "/patches/1")
    payload = _job_form("1", "1", "planned", "")
    payload["csrf_token"] = token
    response = auth_client.post("/jobs", data=payload, follow_redirects=False)
    assert response.status_code == 303
    detail = auth_client.get(response.headers["location"]).text
    assert "Heritage gate test." in detail
    assert "Planned" in detail


def test_non_heritage_job_can_be_scheduled_without_a_reference(auth_client):
    token = csrf_token(auth_client, "/patches/6")
    payload = _job_form("6", "1", "scheduled", "")
    payload["csrf_token"] = token
    response = auth_client.post("/jobs", data=payload, follow_redirects=False)
    assert response.status_code == 303


def test_heritage_consent_required_on_edit(auth_client):
    before = kpi_value(auth_client.get("/").text, "Consent gaps")
    assert before == 1  # the seeded planned heritage job with a blank reference

    token = csrf_token(auth_client, "/jobs/2")
    response = auth_client.post(
        "/jobs/2/edit",
        data={
            "csrf_token": token,
            "crew_id": "2",
            "sett_count": "27",
            "status": "scheduled",
            "heritage_consent_ref": "",
            "scheduled_for": "2026-03-02",
            "notes": "Waiting on the harbour office.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Record the heritage consent reference" in response.text
    # Values are preserved and the job has not moved out of planned.
    assert "Waiting on the harbour office." in response.text
    assert kpi_value(auth_client.get("/").text, "Consent gaps") == 1

    ok = auth_client.post(
        "/jobs/2/edit",
        data={
            "csrf_token": csrf_token(auth_client, "/jobs/2"),
            "crew_id": "2",
            "sett_count": "27",
            "status": "scheduled",
            "heritage_consent_ref": "HCA/2026/0185",
            "scheduled_for": "2026-03-02",
            "notes": "Consent granted by the conservation officer.",
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    detail = auth_client.get("/jobs/2").text
    assert "Scheduled" in detail
    assert "HCA/2026/0185" in detail
    assert kpi_value(auth_client.get("/").text, "Consent gaps") == 0


# ---------------------------------------------------------------------- CSRF gate


def test_state_changing_post_requires_a_csrf_token(auth_client):
    response = auth_client.post(
        "/crews",
        data={"name": "No Token Crew", "foreman": "Nobody"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "That form was out of date" in response.text
    assert "No Token Crew" not in auth_client.get("/crews").text
