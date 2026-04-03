"""Public config API — no auth required — and log cleanup utilities."""
import json
from datetime import datetime, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from utils.database import get_db
from models.schemas import PublicStateResponse, ConfigVersionResponse

router = APIRouter(prefix="/api/config", tags=["public-config"])


def _parse_config_datetime(value: str | None, timezone_name: str = "UTC") -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        try:
            return parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception:
            return parsed.replace(tzinfo=timezone.utc)
    return parsed


@router.get("/public-state", response_model=PublicStateResponse)
async def public_state():
    """Return all public configuration consumed by the frontend."""
    async with await get_db() as db:
        cfg = await (await db.execute("SELECT * FROM admin_config WHERE id=1")).fetchone()
        banner = await (await db.execute("SELECT * FROM notice_banner WHERE id=1")).fetchone()

        active_theme_id = cfg["active_theme_id"] if cfg else "T02"
        theme_row = await (await db.execute(
            "SELECT definition FROM themes WHERE id=?", (active_theme_id,)
        )).fetchone()

    theme_def: Dict[str, Any] = {}
    if theme_row:
        try:
            theme_def = json.loads(theme_row["definition"])
        except Exception:
            pass

    banner_timezone = banner["timezone"] if banner else "America/Toronto"
    banner_now = datetime.now(ZoneInfo(banner_timezone))

    # Determine banner visibility: enabled AND within time window.
    banner_enabled = bool(banner["enabled"]) if banner else False
    if banner_enabled and banner:
        banner_start = _parse_config_datetime(banner["start_time"], banner_timezone)
        banner_end = _parse_config_datetime(banner["end_time"], banner_timezone)
        if banner_start and banner_start > banner_now:
            banner_enabled = False
        if banner_end and banner_end < banner_now:
            banner_enabled = False

    return PublicStateResponse(
        default_language=cfg["default_language"] if cfg else "en",
        active_theme_id=active_theme_id,
        theme_definition=theme_def,
        config_version=cfg["config_version"] if cfg else 1,
        maintenance_mode=bool(cfg["maintenance_mode"]) if cfg else False,
        maintenance_title=cfg["maintenance_title"] if cfg else "",
        maintenance_message=cfg["maintenance_message"] if cfg else "",
        maintenance_start=cfg["maintenance_start"] if cfg else None,
        maintenance_end=cfg["maintenance_end"] if cfg else None,
        banner_enabled=banner_enabled,
        banner_title=banner["title"] if banner else "",
        banner_content=banner["content"] if banner else "",
        banner_start=banner["start_time"] if banner else None,
        banner_end=banner["end_time"] if banner else None,
        banner_timezone=banner_timezone,
        banner_severity=banner["severity"] if banner else "info",
        banner_version=banner["version"] if banner else 1,
    )


@router.get("/version", response_model=ConfigVersionResponse)
async def config_version():
    """Lightweight endpoint polled by the frontend every 30 seconds."""
    async with await get_db() as db:
        row = await (await db.execute("SELECT config_version FROM admin_config WHERE id=1")).fetchone()
    return ConfigVersionResponse(config_version=row["config_version"] if row else 1)


# ──────────────────────────────────────────────────────────────────
# Log retention cleanup (called periodically from lifespan)
# ──────────────────────────────────────────────────────────────────

async def cleanup_old_logs() -> None:
    """Delete error debug logs older than 30 days and summary logs older than 90 days."""
    async with await get_db() as db:
        # Error debug logs (is_error=1): 30 days
        await db.execute("""
            DELETE FROM chat_logs
            WHERE is_error=1 AND requested_at < datetime('now', '-30 days')
        """)
        # Summary logs (is_error=0): 90 days
        await db.execute("""
            DELETE FROM chat_logs
            WHERE is_error=0 AND requested_at < datetime('now', '-90 days')
        """)
        await db.commit()
