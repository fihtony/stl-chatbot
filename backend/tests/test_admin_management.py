import asyncio
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.admin_auth_service import (
    build_oauth_redirect_url,
    create_admin_jwt,
    is_admin_email,
    is_secure_cookie,
    reset_admin_auth_config_cache,
    COOKIE_NAME,
)
from services.admin_deps import get_current_admin
from services.admin_router import router as admin_router
from services.public_config_router import router as public_config_router, cleanup_old_logs
from utils import database


def _run(coro):
    return asyncio.run(coro)


async def _insert_chat_log(question_summary: str = "question", answer_summary: str = "answer") -> None:
    async with await database.get_db() as db:
        await db.execute(
            """INSERT INTO chat_logs (
                session_id, question_summary, answer_summary, user_agent,
                browser_name, browser_version, os_name, os_version, device_type,
                country, province, city, language_pref, referer, response_ms, is_error, error_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "session-1",
                question_summary,
                answer_summary,
                "pytest-agent",
                "Chrome",
                "123",
                "macOS",
                "14",
                "desktop",
                "Canada",
                "Quebec",
                "Montreal",
                "en-CA",
                "http://localhost:3086",
                123,
                0,
                None,
            ),
        )
        await db.commit()


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    test_db = tmp_path / "admin.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)
    _run(database.init_db())

    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(public_config_router)
    app.dependency_overrides[get_current_admin] = lambda: "redacted@example.com"

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def no_auth_client(tmp_path, monkeypatch):
    """Client without auth override — uses real JWT validation."""
    test_db = tmp_path / "admin.db"
    monkeypatch.setattr(database, "DB_PATH", test_db)
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret-for-no-auth")
    monkeypatch.setenv("ADMIN_EMAILS", "redacted@example.com")
    reset_admin_auth_config_cache()
    _run(database.init_db())

    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(public_config_router)

    with TestClient(app) as client:
        yield client

    reset_admin_auth_config_cache()


def test_update_notebooklm_url_increments_config_version(admin_client):
    response = admin_client.put(
        "/api/admin/config/notebooklm",
        json={"url": "https://notebooklm.google.com/notebook/REDACTED"},
    )

    assert response.status_code == 200
    assert response.json()["config_version"] == 2

    version_response = admin_client.get("/api/config/version")
    assert version_response.status_code == 200
    assert version_response.json()["config_version"] == 2


def test_admin_config_endpoint_returns_maintenance_and_banner_state(admin_client):
    maintenance_response = admin_client.put(
        "/api/admin/maintenance",
        json={
            "enabled": True,
            "title": "Maintenance Window",
            "message": "The chatbot is being updated.",
            "start_time": "2026-04-02T21:00:00",
            "end_time": "2026-04-02T22:00:00",
        },
    )
    assert maintenance_response.status_code == 200

    banner_response = admin_client.put(
        "/api/admin/notice-banner",
        json={
            "title": "Scheduled maintenance",
            "content": "Expect downtime tonight.",
            "start_time": "2026-04-02T21:00:00",
            "end_time": "2026-04-02T22:00:00",
            "timezone": "America/Toronto",
            "severity": "warning",
            "enabled": True,
        },
    )
    assert banner_response.status_code == 200

    config_response = admin_client.get("/api/admin/config")
    assert config_response.status_code == 200
    payload = config_response.json()
    assert payload["maintenance_mode"] is True
    assert payload["maintenance_title"] == "Maintenance Window"
    assert payload["banner_enabled"] is True
    assert payload["banner_severity"] == "warning"


def test_public_state_hides_future_banner(admin_client):
    response = admin_client.put(
        "/api/admin/notice-banner",
        json={
            "title": "Future maintenance",
            "content": "Not visible yet.",
            "start_time": "2099-04-02T21:00:00",
            "end_time": "2099-04-02T22:00:00",
            "timezone": "America/Toronto",
            "severity": "info",
            "enabled": True,
        },
    )
    assert response.status_code == 200

    public_state = admin_client.get("/api/config/public-state")
    assert public_state.status_code == 200
    assert public_state.json()["banner_enabled"] is False


def test_logs_csv_export_sanitizes_formula_cells(admin_client):
    _run(_insert_chat_log(question_summary="=cmd|' /C calc'!A0", answer_summary="normal"))

    response = admin_client.get("/api/admin/logs/export/csv")
    assert response.status_code == 200
    body = response.text
    assert "'=cmd|' /C calc'!A0" in body


def test_chat_logs_schema_does_not_store_ip_columns(admin_client):
    async def _columns():
        async with await database.get_db() as db:
            rows = await (await db.execute("PRAGMA table_info(chat_logs)")).fetchall()
        return [row[1] for row in rows]

    columns = _run(_columns())
    assert all("ip" not in column.lower() for column in columns)


def test_copy_url_reauth_returns_launch_url_and_can_be_cancelled(admin_client):
    response = admin_client.post("/api/admin/notebooklm/reauth/start", json={"method": "copy_url"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["auth_url"].endswith(f"/api/admin/notebooklm/reauth/launch/{payload['job_id']}")

    cancel_response = admin_client.post(f"/api/admin/notebooklm/reauth/cancel/{payload['job_id']}")
    assert cancel_response.status_code == 200

    status_response = admin_client.get(f"/api/admin/notebooklm/reauth/status/{payload['job_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "cancelled"


def test_oauth_redirect_url_is_encoded_and_local_cookie_security_is_correct(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    reset_admin_auth_config_cache()

    redirect_uri = "http://127.0.0.1:8086/api/admin/login/callback"
    url, state, verifier = build_oauth_redirect_url(redirect_uri)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert state
    assert verifier
    assert params["redirect_uri"] == [redirect_uri]
    assert params["scope"] == ["openid email profile"]
    assert "scope=openid+email+profile" in url
    assert is_secure_cookie("http://127.0.0.1:3086") is False
    assert is_secure_cookie("https://chatbot.example.com") is True


# ──────────────────────────────────────────────────────────────────
# NFR-01: Admin endpoints require authentication
# ──────────────────────────────────────────────────────────────────

def test_admin_endpoints_require_auth(no_auth_client):
    """All protected admin endpoints return 401 when no token is provided."""
    protected = [
        ("GET", "/api/admin/me"),
        ("GET", "/api/admin/config"),
        ("GET", "/api/admin/dashboard"),
        ("GET", "/api/admin/logs"),
        ("GET", "/api/admin/audit-logs"),
        ("GET", "/api/admin/themes"),
        ("PUT", "/api/admin/config/notebooklm"),
        ("PUT", "/api/admin/maintenance"),
        ("PUT", "/api/admin/notice-banner"),
        ("PUT", "/api/admin/default-language"),
    ]
    for method, path in protected:
        resp = no_auth_client.request(method, path, json={})
        assert resp.status_code == 401, f"{method} {path} should return 401 without auth"


# ──────────────────────────────────────────────────────────────────
# NFR-11: Tampered JWT is rejected
# ──────────────────────────────────────────────────────────────────

def test_tampered_jwt_returns_401(no_auth_client, monkeypatch):
    """A JWT with an invalid signature returns 401."""
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret-for-no-auth")
    reset_admin_auth_config_cache()

    token = create_admin_jwt("redacted@example.com")
    # Flip the last character of the signature
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    resp = no_auth_client.get("/api/admin/me", cookies={COOKIE_NAME: tampered})
    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────
# NFR-12: Empty ADMIN_EMAILS whitelist blocks all logins
# ──────────────────────────────────────────────────────────────────

def test_empty_admin_emails_rejects_all_logins(monkeypatch):
    """When ADMIN_EMAILS is empty, no email is allowed through."""
    monkeypatch.setenv("ADMIN_EMAILS", "")
    reset_admin_auth_config_cache()
    try:
        assert is_admin_email("redacted@example.com") is False
        assert is_admin_email("redacted@example.com") is False
    finally:
        reset_admin_auth_config_cache()


# ──────────────────────────────────────────────────────────────────
# NFR-16: NotebookLM URL without https:// scheme is rejected
# ──────────────────────────────────────────────────────────────────

def test_notebooklm_url_without_scheme_rejected(admin_client):
    """Saving a URL without https:// must fail with 422 (validation error)."""
    resp = admin_client.put(
        "/api/admin/config/notebooklm",
        json={"url": "notebooklm.google.com/notebook/12345678-1234-1234-1234-123456789abc"},
    )
    assert resp.status_code == 422


def test_notebooklm_url_must_contain_notebooklm_domain(admin_client):
    """Saving a non-NotebookLM https URL must fail with 422."""
    resp = admin_client.put(
        "/api/admin/config/notebooklm",
        json={"url": "https://google.com/some/path"},
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────
# NFR-17: Fresh database starts with config_version == 1
# ──────────────────────────────────────────────────────────────────

def test_initial_config_version_is_1(admin_client):
    """Freshly initialised database must have config_version = 1."""
    resp = admin_client.get("/api/config/version")
    assert resp.status_code == 200
    assert resp.json()["config_version"] == 1


# ──────────────────────────────────────────────────────────────────
# AUTH-08 / AUTH-09: Logout and audit
# ──────────────────────────────────────────────────────────────────

def test_logout_returns_ok(admin_client):
    """DELETE /api/admin/logout responds with ok=True."""
    resp = admin_client.delete("/api/admin/logout")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_audit_log_entries_written_on_key_actions(admin_client):
    """Modifying URL, language, and maintenance all produce audit entries."""
    admin_client.put(
        "/api/admin/config/notebooklm",
        json={"url": "https://notebooklm.google.com/notebook/REDACTED"},
    )
    admin_client.put("/api/admin/default-language", json={"language": "fr"})
    admin_client.put(
        "/api/admin/maintenance",
        json={"enabled": True, "title": "t", "message": "m"},
    )

    resp = admin_client.get("/api/admin/audit-logs")
    assert resp.status_code == 200
    actions = [item["action"] for item in resp.json()["items"]]
    assert "update_notebooklm_url" in actions
    assert "update_default_language" in actions
    assert "enable_maintenance" in actions


# ──────────────────────────────────────────────────────────────────
# NFR-19 / DASH-19: Dashboard empty-DB state
# ──────────────────────────────────────────────────────────────────

def test_dashboard_empty_db(admin_client):
    """Dashboard metrics are all zero-safe with no chat log records."""
    resp = admin_client.get("/api/admin/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_sessions"] == 0
    assert data["today_questions"] == 0
    assert data["total_questions"] == 0
    assert data["total_sessions"] == 0
    assert data["avg_questions_per_session"] == 0.0
    assert data["error_rate"] == 0.0
    assert data["config_version"] == 1


# ──────────────────────────────────────────────────────────────────
# LOG-09 / LOG-10: Log retention cleanup
# ──────────────────────────────────────────────────────────────────

async def _insert_old_log(is_error: bool, days_ago: int) -> None:
    """Insert a chat log record backdated by `days_ago` days."""
    old_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    async with await database.get_db() as db:
        await db.execute(
            """INSERT INTO chat_logs (
                session_id, question_summary, answer_summary, user_agent,
                browser_name, browser_version, os_name, os_version, device_type,
                country, province, city, language_pref, referer, response_ms,
                is_error, error_summary, requested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"old-session-{days_ago}",
                "old question",
                "" if is_error else "old answer",
                "pytest-agent",
                "Chrome", "123", "macOS", "14", "desktop",
                "Canada", "Quebec", "Montreal", "en-CA",
                "http://localhost:3086", 100,
                1 if is_error else 0,
                "error" if is_error else None,
                old_ts,
            ),
        )
        await db.commit()


def test_log_cleanup_removes_old_error_logs(admin_client):
    """Error debug logs older than 30 days are removed; newer ones are kept."""
    _run(_insert_old_log(is_error=True, days_ago=31))
    _run(_insert_old_log(is_error=True, days_ago=15))

    _run(cleanup_old_logs())

    resp = admin_client.get("/api/admin/logs?is_error=true")
    assert resp.status_code == 200
    ids = [item["session_id"] for item in resp.json()["items"]]
    assert not any("old-session-31" == s for s in ids), "31-day-old error log should be deleted"
    assert any("old-session-15" == s for s in ids), "15-day-old error log should be kept"


def test_log_cleanup_removes_old_summary_logs(admin_client):
    """Summary logs older than 90 days are removed; newer ones are kept."""
    _run(_insert_old_log(is_error=False, days_ago=91))
    _run(_insert_old_log(is_error=False, days_ago=45))

    _run(cleanup_old_logs())

    resp = admin_client.get("/api/admin/logs?is_error=false")
    assert resp.status_code == 200
    ids = [item["session_id"] for item in resp.json()["items"]]
    assert not any("old-session-91" == s for s in ids), "91-day-old summary log should be deleted"
    assert any("old-session-45" == s for s in ids), "45-day-old summary log should be kept"


# ──────────────────────────────────────────────────────────────────
# MAINT-05 / MAINT-08: Maintenance mode visible in public state
# ──────────────────────────────────────────────────────────────────

def test_maintenance_mode_visible_in_public_state(admin_client):
    """Enabling maintenance mode is reflected in the public-state endpoint."""
    admin_client.put(
        "/api/admin/maintenance",
        json={
            "enabled": True,
            "title": "Emergency maintenance",
            "message": "Back soon.",
        },
    )

    resp = admin_client.get("/api/config/public-state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["maintenance_mode"] is True
    assert data["maintenance_title"] == "Emergency maintenance"
    assert data["maintenance_message"] == "Back soon."


def test_disabling_maintenance_mode_restores_public_state(admin_client):
    """Disabling maintenance mode is reflected in the public-state endpoint."""
    admin_client.put(
        "/api/admin/maintenance",
        json={"enabled": True, "title": "t", "message": "m"},
    )
    admin_client.put(
        "/api/admin/maintenance",
        json={"enabled": False, "title": "t", "message": "m"},
    )

    resp = admin_client.get("/api/config/public-state")
    assert resp.status_code == 200
    assert resp.json()["maintenance_mode"] is False


# ──────────────────────────────────────────────────────────────────
# login_initiate uses FRONTEND_URL for the OAuth callback (cookie domain fix)
# ──────────────────────────────────────────────────────────────────

def test_login_initiate_uses_frontend_url_for_redirect_uri(no_auth_client, monkeypatch):
    """login/initiate must build the redirect_uri from FRONTEND_URL so the
    OAuth callback goes through the Next.js proxy and the JWT cookie is set
    for the frontend origin."""
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3086")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    reset_admin_auth_config_cache()

    # The initiate endpoint redirects to Google — follow_redirects=False so we
    # can inspect the Location header instead of fetching Google.
    resp = no_auth_client.get("/api/admin/login/initiate", follow_redirects=False)
    assert resp.status_code in (302, 307)

    location = resp.headers.get("location", "")
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    # redirect_uri in the OAuth URL must point to the frontend proxy, not the
    # raw backend host.
    redirect_uri = params.get("redirect_uri", [""])[0]
    assert redirect_uri.startswith("http://localhost:3086"), (
        f"redirect_uri should use FRONTEND_URL (localhost:3086), got: {redirect_uri!r}"
    )