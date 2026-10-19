"""CRUD paths: streets, patches, crews and repair jobs."""

from __future__ import annotations

from conftest import csrf_token, kpi_value


def test_street_list_shows_seeded_register(auth_client):
    response = auth_client.get("/streets")
    assert response.status_code == 200
    assert "Cobble Lane" in response.text
    assert "Rackhay Row" in response.text
    assert "Heritage area" in response.text
    assert "6</strong> street" in response.text.replace("\n", "")


def test_create_street_then_see_it_on_the_detail_page(auth_client):
    token = csrf_token(auth_client, "/streets")
    response = auth_client.post(
        "/streets",
        data={
            "csrf_token": token,
            "name": "Pembroke Mews",
            "district": "Kingsdown",
            "heritage": "1",
            "notes": "Narrow lane off the main road.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/streets/")

    detail = auth_client.get(location)
    assert detail.status_code == 200
    assert "Pembroke Mews" in detail.text
    assert "Heritage area" in detail.text
    assert "Kingsdown" in detail.text


def test_duplicate_street_name_is_rejected(auth_client):
    token = csrf_token(auth_client, "/streets")
    response = auth_client.post(
        "/streets",
        data={"csrf_token": token, "name": "Cobble Lane", "district": "Old Market"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "already registered" in response.text

    listing = auth_client.get("/streets").text
    assert listing.count("Cobble Lane") < 6


def test_blank_street_name_is_rejected(auth_client):
    token = csrf_token(auth_client, "/streets")
    response = auth_client.post(
        "/streets",
        data={"csrf_token": token, "name": "   ", "district": "Central"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Enter the street name." in response.text


def test_street_edit_toggles_heritage_badge(auth_client):
    token = csrf_token(auth_client, "/streets/3")
    response = auth_client.post(
        "/streets/3/edit",
        data={
            "csrf_token": token,
            "name": "Wellington Terrace",
            "district": "Clifton",
            "heritage": "1",
            "notes": "Terraced approach.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Heritage area" in auth_client.get("/streets/3").text


def test_log_patch_and_read_it_back(auth_client):
    token = csrf_token(auth_client, "/streets/1")
    response = auth_client.post(
        "/streets/1/patches",
        data={
            "csrf_token": token,
            "location_description": "Outside No. 21, kerbside course",
            "sett_count": "14",
            "severity": "high",
            "status": "open",
            "discovered_on": "2026-01-05",
            "notes": "Gully cover lifting.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    street_page = auth_client.get("/streets/1").text
    assert "Outside No. 21, kerbside course" in street_page

    patch_page = auth_client.get("/streets/1")
    assert ">14<" in patch_page.text
    assert "High" in patch_page.text


def test_patch_status_change_lowers_the_open_patch_metric(auth_client):
    before = kpi_value(auth_client.get("/").text, "Open patches")
    token = csrf_token(auth_client, "/patches/2")
    response = auth_client.post(
        "/patches/2/edit",
        data={
            "csrf_token": token,
            "location_description": "Junction with Rackhay Row, two missing courses",
            "sett_count": "18",
            "severity": "medium",
            "status": "repaired",
            "discovered_on": "2026-01-02",
            "notes": "Re-laid.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Repaired" in auth_client.get("/patches/2").text
    after = kpi_value(auth_client.get("/").text, "Open patches")
    assert after == before - 1


def test_create_crew_appears_active_with_no_jobs(auth_client):
    token = csrf_token(auth_client, "/crews")
    response = auth_client.post(
        "/crews",
        data={"csrf_token": token, "name": "North Yard", "foreman": "Pat"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = auth_client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "North Yard" in detail.text
    assert "Active" in detail.text
    assert "No jobs assigned to this crew yet" in detail.text


def test_crew_edit_updates_the_roster(auth_client):
    token = csrf_token(auth_client, "/crews/1")
    response = auth_client.post(
        "/crews/1/edit",
        data={"csrf_token": token, "name": "Yard Crew A", "foreman": "Sam Okonjo"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "Sam Okonjo" in auth_client.get("/crews/1").text
    assert "Sam Okonjo" in auth_client.get("/crews").text


def test_crew_toggle_hides_it_from_job_assignment(auth_client):
    token = csrf_token(auth_client, "/crews/2")
    response = auth_client.post(
        "/crews/2/toggle-active", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "Inactive" in auth_client.get("/crews/2").text

    patch_page = auth_client.get("/patches/6").text
    assert "Yard Crew B" not in patch_page

    reactivate = auth_client.post(
        "/crews/2/toggle-active",
        data={"csrf_token": csrf_token(auth_client, "/crews/2")},
        follow_redirects=False,
    )
    assert reactivate.status_code == 303
    assert "Yard Crew B" in auth_client.get("/patches/6").text


def test_raise_job_from_patch_and_filter_the_list(auth_client):
    patch_page = auth_client.get("/patches/6").text
    # The raise-job form prefills the patch sett count.
    assert 'value="34"' in patch_page

    token = csrf_token(auth_client, "/patches/6")
    response = auth_client.post(
        "/jobs",
        data={
            "csrf_token": token,
            "patch_id": "6",
            "crew_id": "2",
            "sett_count": "34",
            "status": "planned",
            "heritage_consent_ref": "",
            "scheduled_for": "",
            "notes": "Crossing setts to re-bed.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    job_location = response.headers["location"]
    assert job_location.startswith("/jobs/")

    detail = auth_client.get(job_location)
    assert detail.status_code == 200
    assert "Wellington Terrace" in detail.text
    assert "Planned" in detail.text

    jobs_list = auth_client.get("/jobs").text
    assert "Wellington Terrace" in jobs_list

    planned = auth_client.get("/jobs?status=planned").text
    assert "Dropped kerb crossing" in planned
    assert "Blocked: traffic management order" not in planned


def test_job_create_page_prefills_from_the_patch(auth_client):
    response = auth_client.get("/jobs/new?patch_id=10")
    assert response.status_code == 200
    assert "Quay Head Passage" in response.text
    assert 'value="55"' in response.text


def test_delete_job_frees_the_patch(auth_client):
    token = csrf_token(auth_client, "/jobs/5")
    response = auth_client.post(
        "/jobs/5/delete", data={"csrf_token": token}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/patches/9"

    patch_page = auth_client.get("/patches/9").text
    assert "No repair job has been raised for this patch yet." in patch_page


def test_delete_street_with_no_dependants(auth_client):
    token = csrf_token(auth_client, "/streets")
    created = auth_client.post(
        "/streets",
        data={"csrf_token": token, "name": "Temporary Lane", "district": "Central"},
        follow_redirects=False,
    )
    street_path = created.headers["location"]
    street_id = street_path.rsplit("/", 1)[-1]

    deleted = auth_client.post(
        f"/streets/{street_id}/delete",
        data={"csrf_token": csrf_token(auth_client, street_path)},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert deleted.headers["location"] == "/streets"
    listing = auth_client.get("/streets").text
    assert f'href="/streets/{street_id}"' not in listing
    assert auth_client.get(street_path, follow_redirects=False).status_code == 404


def test_job_counts_by_status_on_the_dashboard(auth_client):
    html = auth_client.get("/").text
    assert "Jobs by status" in html
    for label in ("Planned", "Scheduled", "In progress", "Complete", "Blocked"):
        assert label in html
