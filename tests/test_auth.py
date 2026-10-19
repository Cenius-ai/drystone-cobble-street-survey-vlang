"""Login guard, sign-in, sign-out and static asset tests."""

from __future__ import annotations

from conftest import DEMO_EMAIL, DEMO_PASSWORD, csrf_token, kpi_value


def test_entry_path_serves_html_and_never_dashboard_data_to_anonymous_visitors(client):
    for path in ("/", "/index.html", "/app", "/home"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert response.headers["content-type"].startswith("text/html")
        # The sign-in card is rendered, and no survey data leaks to a visitor.
        assert 'name="email"' in response.text
        assert 'type="password"' in response.text
        assert "Citywide survey state" not in response.text
        assert "Cobble Lane" not in response.text


def test_data_routes_redirect_anonymous_visitors_to_the_login_page(client):
    for path in ("/streets", "/jobs", "/crews"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == f"/login?next={path}"


def test_login_page_is_public_and_shows_demo_hint(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Demo account" in response.text
    assert DEMO_EMAIL in response.text
    assert DEMO_PASSWORD in response.text
    assert 'type="password"' in response.text
    assert "data-password-toggle" in response.text


def test_static_assets_are_served_without_a_session(client):
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert css.text.count("{") == css.text.count("}")

    script = client.get("/static/js/app.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


def test_login_success_redirects_to_dashboard(client):
    response = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "drystone_session" in response.cookies

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Citywide survey state" in dashboard.text
    assert "Cobble Lane" in dashboard.text


def test_signing_in_from_the_entry_page_reaches_the_dashboard(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "/login" in page.text  # the card posts to the login route
    login = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "next": "/"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/"
    assert "Citywide survey state" in client.get("/").text


def test_wrong_password_message_does_not_reveal_accounts(client):
    known = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": "not-the-password"},
        follow_redirects=False,
    )
    unknown = client.post(
        "/login",
        data={"email": "stranger@example.com", "password": "not-the-password"},
        follow_redirects=False,
    )
    assert known.status_code == 401
    assert unknown.status_code == 401
    message = "Those credentials did not match an operator account."
    assert message in known.text
    assert message in unknown.text
    # The typed email survives the failed attempt.
    assert f'value="{DEMO_EMAIL}"' in known.text


def test_blank_credentials_show_inline_errors(client):
    response = client.post(
        "/login", data={"email": "", "password": ""}, follow_redirects=False
    )
    assert response.status_code == 400
    assert "Enter your operator email." in response.text
    assert "Enter your password." in response.text


def test_login_returns_to_the_requested_page(client):
    guarded = client.get("/jobs?status=planned", follow_redirects=False)
    assert guarded.status_code == 303
    assert guarded.headers["location"] == "/login?next=/jobs%3Fstatus%3Dplanned"

    login = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "next": "/jobs?status=planned"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/jobs?status=planned"
    assert client.get("/jobs?status=planned").status_code == 200


def test_logout_clears_the_session(auth_client):
    assert kpi_value(auth_client.get("/").text, "Open patches") > 0
    response = auth_client.post(
        "/logout",
        data={"csrf_token": csrf_token(auth_client, "/")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    after = auth_client.get("/", follow_redirects=False)
    assert after.status_code == 200
    assert "Citywide survey state" not in after.text
    assert 'name="email"' in after.text


def test_security_headers_are_present(client):
    response = client.get("/login")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_repeated_failures_are_rate_limited(client):
    """The failure window is in-process; exercise it directly and reset after."""
    from app import views_auth

    views_auth._login_failures.clear()
    try:
        for _ in range(views_auth.LOGIN_MAX_FAILURES):
            views_auth._record_failure("testclient")
        blocked = client.post(
            "/login",
            data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            follow_redirects=False,
        )
        assert blocked.status_code == 429
        assert "Too many sign-in attempts" in blocked.text
    finally:
        views_auth._login_failures.clear()

    # With the window cleared the demo operator signs in again.
    ok = client.post(
        "/login",
        data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert ok.status_code == 303
