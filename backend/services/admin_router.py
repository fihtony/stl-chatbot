"""Admin router — all /api/admin/* endpoints and Google OAuth callback."""
import asyncio
import json
import uuid
import csv
import io
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import user_agents as ua_parser

from services.admin_auth_service import (
    build_oauth_redirect_url,
    exchange_code_for_email,
    create_admin_jwt,
    is_admin_email,
    COOKIE_NAME,
    COOKIE_MAX_AGE,
    get_frontend_url,
    is_secure_cookie,
)
from services.admin_deps import get_current_admin
from services.notebooklm_skill.scripts.auth_manager import AuthManager
from utils.database import get_db
from utils.logger import logger
from models.schemas import (
    AdminConfigResponse,
    AdminMeResponse,
    UpdateNotebookLMUrlRequest,
    NotebookLMUrlResponse,
    ReauthStartRequest,
    ReauthStatusResponse,
    ThemeRecord,
    CreateThemeRequest,
    SetActiveThemeRequest,
    NoticeBannerRequest,
    MaintenanceModeRequest,
    DefaultLanguageRequest,
    LogDetail,
    AuditLogEntry,
    DashboardResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# In-memory PKCE state store (state -> (verifier, redirect_uri))
# For production scale use Redis or a signed cookie; fine for single-instance MVP.
_pkce_store: dict[str, tuple[str, str]] = {}
_reauth_tasks: dict[str, asyncio.Task] = {}

REAUTH_TIMEOUT_SECONDS = 600


# ──────────────────────────────────────────────────────────────────
# Helper: write an audit log entry
# ──────────────────────────────────────────────────────────────────

async def _audit(
    email: str,
    action: str,
    result: str = "success",
    before: Optional[str] = None,
    after: Optional[str] = None,
    browser: str = "",
    os: str = "",
) -> None:
    async with await get_db() as db:
        await db.execute(
            """INSERT INTO admin_audit_logs
               (admin_email, action, result, before_summary, after_summary, browser, os)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (email, action, result, before, after, browser, os),
        )
        await db.commit()


def _parse_ua(request: Request) -> tuple[str, str]:
    """Return (browser_string, os_string) from User-Agent header."""
    raw = request.headers.get("user-agent", "")
    parsed = ua_parser.parse(raw)
    b = f"{parsed.browser.family} {parsed.browser.version_string}".strip()
    o = f"{parsed.os.family} {parsed.os.version_string}".strip()
    return b, o


def _mask_url(url: str) -> str:
    """Show only first 10 and last 5 characters."""
    if len(url) <= 15:
        return "***"
    return url[:10] + "..." + url[-5:]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_reauth_job(job_id: str):
    async with await get_db() as db:
        return await (await db.execute(
            "SELECT * FROM notebooklm_auth_jobs WHERE id=?", (job_id,)
        )).fetchone()


async def _set_reauth_status(job_id: str, new_status: str) -> None:
    async with await get_db() as db:
        await db.execute(
            "UPDATE notebooklm_auth_jobs SET status=?, updated_at=datetime('now') WHERE id=?",
            (new_status, job_id),
        )
        await db.commit()


async def _run_reauth_job(job_id: str, admin_email: str) -> None:
    started = time.monotonic()
    try:
        ok = await asyncio.to_thread(AuthManager().re_auth, False, REAUTH_TIMEOUT_SECONDS / 60)
        job = await _get_reauth_job(job_id)
        if not job or job["status"] == "cancelled":
            return

        elapsed = time.monotonic() - started
        if ok:
            await _set_reauth_status(job_id, "authenticated")
            await _audit(admin_email, "reauth_authenticated")
        elif elapsed >= REAUTH_TIMEOUT_SECONDS - 1:
            await _set_reauth_status(job_id, "timeout")
            await _audit(admin_email, "reauth_timeout", result="timeout")
        else:
            await _set_reauth_status(job_id, "failed")
            await _audit(admin_email, "reauth_failed", result="failed")
    except Exception as exc:
        logger.warning("NotebookLM re-auth failed: %s", exc)
        job = await _get_reauth_job(job_id)
        if job and job["status"] != "cancelled":
            await _set_reauth_status(job_id, "failed")
            await _audit(admin_email, "reauth_failed", result="failed", after=str(exc))
    finally:
        _reauth_tasks.pop(job_id, None)


def _kickoff_reauth_job(job_id: str, admin_email: str) -> None:
    if job_id in _reauth_tasks:
        return
    _reauth_tasks[job_id] = asyncio.create_task(_run_reauth_job(job_id, admin_email))


# ──────────────────────────────────────────────────────────────────
# OAuth — initiate + callback
# ──────────────────────────────────────────────────────────────────

@router.get("/login/initiate")
async def login_initiate(request: Request):
    """Build Google OAuth URL and redirect admin to Google.

    The redirect_uri is built from FRONTEND_URL so that Google returns to the
    Next.js proxy (e.g. http://localhost:3086/api/admin/login/callback).  This
    ensures the Set-Cookie in the callback response is set for the frontend
    origin, making the admin JWT cookie available for subsequent proxy calls.
    """
    redirect_uri = get_frontend_url().rstrip("/") + "/api/admin/login/callback"
    url, state, verifier = build_oauth_redirect_url(redirect_uri)
    _pkce_store[state] = (verifier, redirect_uri)
    return RedirectResponse(url)


@router.get("/login/callback")
async def login_callback(
    request: Request,
    response: Response,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    """Handle Google OAuth callback, issue admin JWT cookie."""
    frontend = get_frontend_url()

    if error or not code or not state:
        await _audit("unknown", "login", "failed", after=f"OAuth error: {error}")
        return RedirectResponse(f"{frontend}/admin?auth=error")

    pkce = _pkce_store.pop(state, None)
    if not pkce:
        return RedirectResponse(f"{frontend}/admin?auth=error&reason=invalid_state")

    verifier, redirect_uri = pkce
    browser, os_str = _parse_ua(request)

    email = await exchange_code_for_email(code, redirect_uri, verifier)
    if not email:
        await _audit("unknown", "login", "failed", after="Token exchange failed", browser=browser, os=os_str)
        return RedirectResponse(f"{frontend}/admin?auth=error&reason=exchange_failed")

    if not is_admin_email(email):
        await _audit(email, "login", "denied", after="Not in whitelist", browser=browser, os=os_str)
        return RedirectResponse(f"{frontend}/admin?auth=denied")

    token = create_admin_jwt(email)
    await _audit(email, "login", "success", browser=browser, os=os_str)

    redirect = RedirectResponse(f"{frontend}/admin?auth=success", status_code=302)
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=is_secure_cookie(frontend),
        max_age=COOKIE_MAX_AGE,
        path="/",
    )
    return redirect


@router.delete("/logout")
async def logout(request: Request, response: Response, email: str = Depends(get_current_admin)):
    browser, os_str = _parse_ua(request)
    await _audit(email, "logout", browser=browser, os=os_str)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=AdminMeResponse)
async def get_me(email: str = Depends(get_current_admin)):
    return AdminMeResponse(email=email, logged_in=True)


@router.get("/config", response_model=AdminConfigResponse)
async def get_admin_config(email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        cfg = await (await db.execute("SELECT * FROM admin_config WHERE id=1")).fetchone()
        banner = await (await db.execute("SELECT * FROM notice_banner WHERE id=1")).fetchone()

    return AdminConfigResponse(
        notebooklm_url_masked=_mask_url(cfg["notebooklm_url"] if cfg else ""),
        default_language=cfg["default_language"] if cfg else "en",
        active_theme_id=cfg["active_theme_id"] if cfg else "T02",
        config_version=cfg["config_version"] if cfg else 1,
        maintenance_mode=bool(cfg["maintenance_mode"]) if cfg else False,
        maintenance_title=cfg["maintenance_title"] if cfg else "",
        maintenance_message=cfg["maintenance_message"] if cfg else "",
        maintenance_start=cfg["maintenance_start"] if cfg else None,
        maintenance_end=cfg["maintenance_end"] if cfg else None,
        banner_enabled=bool(banner["enabled"]) if banner else False,
        banner_title=banner["title"] if banner else "",
        banner_content=banner["content"] if banner else "",
        banner_start=banner["start_time"] if banner else None,
        banner_end=banner["end_time"] if banner else None,
        banner_timezone=banner["timezone"] if banner else "America/Toronto",
        banner_severity=banner["severity"] if banner else "info",
        banner_version=banner["version"] if banner else 1,
    )


# ──────────────────────────────────────────────────────────────────
# NotebookLM URL
# ──────────────────────────────────────────────────────────────────

@router.get("/config/notebooklm", response_model=NotebookLMUrlResponse)
async def get_notebooklm_url(email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        row = await (await db.execute("SELECT notebooklm_url, config_version FROM admin_config WHERE id=1")).fetchone()
    url = row["notebooklm_url"] if row else ""
    version = row["config_version"] if row else 1
    return NotebookLMUrlResponse(url_masked=_mask_url(url), config_version=version)


@router.put("/config/notebooklm")
async def update_notebooklm_url(
    body: UpdateNotebookLMUrlRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        old = await (await db.execute("SELECT notebooklm_url, config_version FROM admin_config WHERE id=1")).fetchone()
        old_url = old["notebooklm_url"] if old else ""
        old_version = old["config_version"] if old else 1
        new_version = old_version + 1
        await db.execute(
            """UPDATE admin_config SET notebooklm_url=?, config_version=?, updated_at=datetime('now') WHERE id=1""",
            (body.url, new_version),
        )
        await db.commit()

    await _audit(
        email, "update_notebooklm_url",
        before=_mask_url(old_url),
        after=_mask_url(body.url),
        browser=browser, os=os_str,
    )
    return {"ok": True, "config_version": new_version}


# ──────────────────────────────────────────────────────────────────
# NotebookLM re-auth jobs
# ──────────────────────────────────────────────────────────────────

@router.post("/notebooklm/reauth/start", response_model=ReauthStatusResponse)
async def reauth_start(
    body: ReauthStartRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    job_id = str(uuid.uuid4())
    auth_url = None
    if body.method == "copy_url":
        auth_url = f"{str(request.base_url).rstrip('/')}" + f"/api/admin/notebooklm/reauth/launch/{job_id}"

    async with await get_db() as db:
        await db.execute(
            """INSERT INTO notebooklm_auth_jobs (id, status, method, auth_url, admin_email)
               VALUES (?, 'pending', ?, ?, ?)""",
            (job_id, body.method, auth_url, email),
        )
        await db.commit()

    if body.method == "browser":
        _kickoff_reauth_job(job_id, email)

    await _audit(email, f"reauth_start_{body.method}", browser=browser, os=os_str)
    return ReauthStatusResponse(
        job_id=job_id,
        status="pending",
        method=body.method,
        auth_url=auth_url,
        started_at=_utc_now_iso(),
        updated_at=_utc_now_iso(),
    )


@router.get("/notebooklm/reauth/launch/{job_id}", response_class=HTMLResponse)
async def reauth_launch(job_id: str):
    job = await _get_reauth_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] == "pending":
        _kickoff_reauth_job(job_id, job["admin_email"])

    return HTMLResponse(
        """
        <html>
          <body style=\"font-family: sans-serif; padding: 2rem;\">
            <h1>NotebookLM re-authentication started</h1>
            <p>The authentication flow has been launched on the chatbot host.</p>
            <p>Return to the admin panel to monitor status updates.</p>
          </body>
        </html>
        """
    )


@router.get("/notebooklm/reauth/status/{job_id}", response_model=ReauthStatusResponse)
async def reauth_status(job_id: str, email: str = Depends(get_current_admin)):
    row = await _get_reauth_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] == "pending":
        try:
            started_at = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
        except ValueError:
            started_at = datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - started_at).total_seconds() >= REAUTH_TIMEOUT_SECONDS:
            await _set_reauth_status(job_id, "timeout")
            await _audit(email, "reauth_timeout", result="timeout")
            row = await _get_reauth_job(job_id)
    return ReauthStatusResponse(
        job_id=row["id"],
        status=row["status"],
        method=row["method"],
        auth_url=row["auth_url"],
        started_at=row["started_at"],
        updated_at=row["updated_at"],
    )


@router.post("/notebooklm/reauth/cancel/{job_id}")
async def reauth_cancel(job_id: str, request: Request, email: str = Depends(get_current_admin)):
    browser, os_str = _parse_ua(request)
    row = await _get_reauth_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    await _set_reauth_status(job_id, "cancelled")
    await _audit(email, "reauth_cancel", result="cancelled", browser=browser, os=os_str)
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────
# Themes
# ──────────────────────────────────────────────────────────────────

@router.get("/themes")
async def list_themes(email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        rows = await (await db.execute("SELECT * FROM themes ORDER BY is_preset DESC, created_at ASC")).fetchall()
    return [ThemeRecord(
        id=r["id"], name=r["name"], is_preset=bool(r["is_preset"]),
        definition=json.loads(r["definition"]), created_at=r["created_at"]
    ) for r in rows]


@router.post("/themes")
async def create_theme(
    body: CreateThemeRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    # Enforce max 5 custom themes
    async with await get_db() as db:
        count_row = await (await db.execute("SELECT COUNT(*) as cnt FROM themes WHERE is_preset=0")).fetchone()
        if count_row["cnt"] >= 5:
            raise HTTPException(status_code=400, detail="Maximum 5 custom themes allowed")
        # Sanitize definition — reject if it contains script injection
        raw = json.dumps(body.definition)
        if "<script" in raw.lower() or "javascript:" in raw.lower():
            raise HTTPException(status_code=400, detail="Theme definition contains disallowed content")
        await db.execute(
            "INSERT INTO themes (id, name, is_preset, definition) VALUES (?, ?, 0, ?)",
            (body.id, body.name, raw),
        )
        await db.commit()
    await _audit(email, "create_theme", after=body.name, browser=browser, os=os_str)
    return {"ok": True}


@router.put("/themes/active")
async def set_active_theme(
    body: SetActiveThemeRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        theme_row = await (await db.execute("SELECT * FROM themes WHERE id=?", (body.theme_id,))).fetchone()
        if not theme_row:
            raise HTTPException(status_code=404, detail="Theme not found")

        old_row = await (await db.execute("SELECT active_theme_id FROM admin_config WHERE id=1")).fetchone()
        old_id = old_row["active_theme_id"] if old_row else ""

        await db.execute(
            "UPDATE admin_config SET active_theme_id=?, updated_at=datetime('now') WHERE id=1",
            (body.theme_id,),
        )
        # Save snapshot; keep only 3 most recent
        await db.execute(
            "INSERT INTO theme_snapshots (theme_id, definition) VALUES (?, ?)",
            (body.theme_id, theme_row["definition"]),
        )
        # Prune old snapshots
        await db.execute("""
            DELETE FROM theme_snapshots WHERE id NOT IN (
                SELECT id FROM theme_snapshots ORDER BY applied_at DESC LIMIT 3
            )
        """)
        await db.commit()
    await _audit(email, "apply_theme", before=old_id, after=body.theme_id, browser=browser, os=os_str)
    return {"ok": True}


@router.post("/themes/rollback/{snapshot_id}")
async def rollback_theme(snapshot_id: int, request: Request, email: str = Depends(get_current_admin)):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        snap = await (await db.execute("SELECT * FROM theme_snapshots WHERE id=?", (snapshot_id,))).fetchone()
        if not snap:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        await db.execute(
            "UPDATE admin_config SET active_theme_id=?, updated_at=datetime('now') WHERE id=1",
            (snap["theme_id"],),
        )
        await db.commit()
    await _audit(email, "rollback_theme", after=snap["theme_id"], browser=browser, os=os_str)
    return {"ok": True}


@router.get("/themes/snapshots")
async def list_snapshots(email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        rows = await (await db.execute(
            "SELECT * FROM theme_snapshots ORDER BY applied_at DESC LIMIT 3"
        )).fetchall()
    return [{"id": r["id"], "theme_id": r["theme_id"], "applied_at": r["applied_at"]} for r in rows]


# ──────────────────────────────────────────────────────────────────
# Default language
# ──────────────────────────────────────────────────────────────────

@router.put("/default-language")
async def update_default_language(
    body: DefaultLanguageRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        old = await (await db.execute("SELECT default_language FROM admin_config WHERE id=1")).fetchone()
        old_lang = old["default_language"] if old else "en"
        await db.execute(
            "UPDATE admin_config SET default_language=?, updated_at=datetime('now') WHERE id=1",
            (body.language,),
        )
        await db.commit()
    await _audit(email, "update_default_language", before=old_lang, after=body.language, browser=browser, os=os_str)
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────
# Maintenance banner
# ──────────────────────────────────────────────────────────────────

@router.put("/notice-banner")
async def update_notice_banner(
    body: NoticeBannerRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        await db.execute("""
            UPDATE notice_banner SET
                title=?, content=?, start_time=?, end_time=?,
                timezone=?, severity=?, enabled=?,
                version=version+1, updated_at=datetime('now')
            WHERE id=1
        """, (
            body.title, body.content, body.start_time, body.end_time,
            body.timezone, body.severity, 1 if body.enabled else 0,
        ))
        await db.commit()
    await _audit(
        email, "update_notice_banner",
        after=f"enabled={body.enabled} title={body.title}",
        browser=browser, os=os_str,
    )
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────
# Maintenance mode
# ──────────────────────────────────────────────────────────────────

@router.put("/maintenance")
async def set_maintenance_mode(
    body: MaintenanceModeRequest,
    request: Request,
    email: str = Depends(get_current_admin),
):
    browser, os_str = _parse_ua(request)
    async with await get_db() as db:
        old = await (await db.execute("SELECT maintenance_mode FROM admin_config WHERE id=1")).fetchone()
        old_mode = bool(old["maintenance_mode"]) if old else False
        await db.execute("""
            UPDATE admin_config SET
                maintenance_mode=?, maintenance_title=?, maintenance_message=?,
                maintenance_start=?, maintenance_end=?,
                updated_at=datetime('now')
            WHERE id=1
        """, (
            1 if body.enabled else 0,
            body.title, body.message,
            body.start_time, body.end_time,
        ))
        await db.commit()

    action = "enable_maintenance" if body.enabled else "disable_maintenance"
    await _audit(email, action, before=str(old_mode), after=str(body.enabled), browser=browser, os=os_str)
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────
# Logs
# ──────────────────────────────────────────────────────────────────

@router.get("/logs")
async def list_logs(
    email: str = Depends(get_current_admin),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session_id: Optional[str] = None,
    is_error: Optional[bool] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    where = ["1=1"]
    params: list = []
    if session_id:
        where.append("session_id LIKE ?")
        params.append(f"%{session_id}%")
    if is_error is not None:
        where.append("is_error=?")
        params.append(1 if is_error else 0)
    if keyword:
        where.append("(question_summary LIKE ? OR answer_summary LIKE ? OR error_summary LIKE ?)")
        k = f"%{keyword}%"
        params += [k, k, k]
    if date_from:
        where.append("requested_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("requested_at <= ?")
        params.append(date_to)

    where_clause = " AND ".join(where)
    offset = (page - 1) * page_size

    async with await get_db() as db:
        count_row = await (await db.execute(
            f"SELECT COUNT(*) as cnt FROM chat_logs WHERE {where_clause}", params
        )).fetchone()
        total = count_row["cnt"]

        rows = await (await db.execute(
            f"""SELECT id, session_id, requested_at, question_summary, answer_summary,
                       browser_name, os_name, city, country, is_error, error_summary, response_ms
                FROM chat_logs WHERE {where_clause}
                ORDER BY requested_at DESC LIMIT ? OFFSET ?""",
            params + [page_size, offset]
        )).fetchall()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.get("/logs/{log_id}", response_model=LogDetail)
async def get_log_detail(log_id: int, email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        row = await (await db.execute("SELECT * FROM chat_logs WHERE id=?", (log_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Log not found")
    d = dict(row)
    d["is_error"] = bool(d["is_error"])
    return LogDetail(**d)


@router.get("/logs/export/csv")
async def export_logs_csv(
    email: str = Depends(get_current_admin),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    where = ["1=1"]
    params: list = []
    if date_from:
        where.append("requested_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("requested_at <= ?")
        params.append(date_to)

    async with await get_db() as db:
        rows = await (await db.execute(
            f"""SELECT session_id, requested_at, question_summary, answer_summary,
                       browser_name, os_name, city, country, is_error, error_summary, response_ms
                FROM chat_logs WHERE {" AND ".join(where)} ORDER BY requested_at DESC""",
            params
        )).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["session_id", "requested_at", "question_summary", "answer_summary",
                     "browser_name", "os_name", "city", "country", "is_error", "error_summary", "response_ms"])
    for r in rows:
        # Sanitize for formula injection: prefix cells starting with = + - @ with a single quote
        def sanitize(v):
            s = str(v) if v is not None else ""
            if s and s[0] in ("=", "+", "-", "@"):
                s = "'" + s
            return s
        writer.writerow([sanitize(r[k]) for k in [
            "session_id", "requested_at", "question_summary", "answer_summary",
            "browser_name", "os_name", "city", "country", "is_error", "error_summary", "response_ms"
        ]])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=chat_logs.csv"},
    )


# ──────────────────────────────────────────────────────────────────
# Audit logs
# ──────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(
    email: str = Depends(get_current_admin),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    offset = (page - 1) * page_size
    async with await get_db() as db:
        total_row = await (await db.execute("SELECT COUNT(*) as cnt FROM admin_audit_logs")).fetchone()
        rows = await (await db.execute(
            "SELECT * FROM admin_audit_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (page_size, offset)
        )).fetchall()
    return {
        "total": total_row["cnt"],
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


# ──────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(email: str = Depends(get_current_admin)):
    async with await get_db() as db:
        cfg = await (await db.execute("SELECT * FROM admin_config WHERE id=1")).fetchone()
        maintenance_mode = bool(cfg["maintenance_mode"]) if cfg else False
        config_version = cfg["config_version"] if cfg else 1
        latest_reauth = await (await db.execute(
            "SELECT status FROM notebooklm_auth_jobs ORDER BY started_at DESC LIMIT 1"
        )).fetchone()

        # Active sessions (last 10 min)
        active = await (await db.execute("""
            SELECT COUNT(DISTINCT session_id) as cnt FROM chat_logs
            WHERE requested_at >= datetime('now', '-10 minutes')
        """)).fetchone()

        # Today questions
        today = await (await db.execute("""
            SELECT COUNT(*) as cnt FROM chat_logs
            WHERE date(requested_at) = date('now')
        """)).fetchone()

        # Totals
        totals = await (await db.execute("""
            SELECT
                COUNT(DISTINCT session_id) as sessions,
                COUNT(*) as questions,
                AVG(response_ms) as avg_ms,
                SUM(is_error) as errors
            FROM chat_logs
        """)).fetchone()

        sessions = totals["sessions"] or 0
        questions = totals["questions"] or 0
        avg_ms = totals["avg_ms"] or 0.0
        errors = totals["errors"] or 0

    if maintenance_mode:
        notebooklm_status = "maintenance"
    elif latest_reauth and latest_reauth["status"] == "pending":
        notebooklm_status = "authenticating"
    elif latest_reauth and latest_reauth["status"] in ("failed", "timeout"):
        notebooklm_status = "error"
    else:
        notebooklm_status = "connected"
    maint_status = "maintenance_active" if maintenance_mode else "normal"

    return DashboardResponse(
        active_sessions=active["cnt"],
        notebooklm_status=notebooklm_status,
        today_questions=today["cnt"],
        maintenance_status=maint_status,
        total_sessions=sessions,
        total_questions=questions,
        avg_questions_per_session=round(questions / sessions, 2) if sessions else 0.0,
        avg_response_ms=round(avg_ms, 1),
        error_rate=round(errors / questions, 4) if questions else 0.0,
        config_version=config_version,
    )
