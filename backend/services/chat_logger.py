"""Chat request logger — writes per-request summary to chat_logs table."""
import asyncio
import time
from typing import Optional

import user_agents as ua_parser
import httpx

from utils.database import get_db
from utils.logger import logger

# Free IP geolocation service (no API key required for basic city-level data)
_GEO_URL = "http://ip-api.com/json/{ip}?fields=country,regionName,city,status"
_GEO_TIMEOUT = 3.0


async def _geolocate(ip: str) -> tuple[str, str, str]:
    """Return (country, province, city) — silently returns empty strings on failure."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return "", "", ""
    try:
        async with httpx.AsyncClient(timeout=_GEO_TIMEOUT) as client:
            resp = await client.get(_GEO_URL.format(ip=ip))
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    return data.get("country", ""), data.get("regionName", ""), data.get("city", "")
    except Exception:
        pass
    return "", "", ""


def _parse_ua(ua_string: str) -> tuple[str, str, str, str, str, str]:
    """Return (browser_name, browser_version, os_name, os_version, device_type, raw_ua)."""
    parsed = ua_parser.parse(ua_string)
    browser_name = parsed.browser.family or ""
    browser_ver = parsed.browser.version_string or ""
    os_name = parsed.os.family or ""
    os_ver = parsed.os.version_string or ""
    if parsed.is_mobile:
        device = "mobile"
    elif parsed.is_tablet:
        device = "tablet"
    else:
        device = "desktop"
    return browser_name, browser_ver, os_name, os_ver, device, ua_string


def _summarize(text: str, max_len: int = 200) -> str:
    if not text:
        return ""
    cleaned = text.replace("\n", " ").strip()
    return cleaned[:max_len] + ("…" if len(cleaned) > max_len else "")


async def log_chat_request(
    *,
    session_id: str,
    question: str,
    answer: Optional[str],
    user_agent_str: str,
    real_ip: str,
    language_pref: str,
    referer: str,
    response_ms: int,
    is_error: bool,
    error_summary: Optional[str] = None,
    error_detail: Optional[str] = None,
    google_raw_request: Optional[str] = None,
    google_raw_response: Optional[str] = None,
) -> None:
    """Persist one row to chat_logs.  All geo / UA parsing happens server-side."""
    try:
        browser_name, browser_ver, os_name, os_ver, device, ua_raw = _parse_ua(user_agent_str)
        country, province, city = await _geolocate(real_ip)

        async with await get_db() as db:
            await db.execute(
                """INSERT INTO chat_logs (
                    session_id, question_summary, answer_summary,
                    user_agent, browser_name, browser_version,
                    os_name, os_version, device_type,
                    country, province, city,
                    language_pref, referer, response_ms,
                    is_error, error_summary, error_detail,
                    google_raw_request, google_raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    _summarize(question),
                    _summarize(answer) if answer else "",
                    ua_raw,
                    browser_name, browser_ver,
                    os_name, os_ver,
                    device,
                    country, province, city,
                    language_pref, referer, response_ms,
                    1 if is_error else 0,
                    error_summary, error_detail,
                    google_raw_request, google_raw_response,
                ),
            )
            await db.commit()
    except Exception as exc:
        # Never let logging errors break the chat flow
        logger.warning("chat log write failed: %s", exc)
