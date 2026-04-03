"""Admin authentication service — Google OAuth 2.0 + PKCE + JWT cookie."""
import os
import uuid
import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlencode, urlparse

import httpx
from jose import jwt, JWTError

from utils.logger import logger


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8
COOKIE_NAME = "admin_token"

# Loaded once at startup from environment
_ADMIN_EMAILS: Optional[set] = None
_JWT_SECRET: Optional[str] = None
_GOOGLE_CLIENT_ID: Optional[str] = None
_GOOGLE_CLIENT_SECRET: Optional[str] = None
_FRONTEND_URL: Optional[str] = None


def reset_admin_auth_config_cache() -> None:
    """Reset cached auth config values. Intended for tests."""
    global _ADMIN_EMAILS, _JWT_SECRET, _GOOGLE_CLIENT_ID, _GOOGLE_CLIENT_SECRET, _FRONTEND_URL
    _ADMIN_EMAILS = None
    _JWT_SECRET = None
    _GOOGLE_CLIENT_ID = None
    _GOOGLE_CLIENT_SECRET = None
    _FRONTEND_URL = None


def _load_config() -> None:
    global _ADMIN_EMAILS, _JWT_SECRET, _GOOGLE_CLIENT_ID, _GOOGLE_CLIENT_SECRET, _FRONTEND_URL
    raw = os.getenv("ADMIN_EMAILS", "")
    _ADMIN_EMAILS = {e.strip().lower() for e in raw.split(",") if e.strip()}
    _JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "")
    _GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    _GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    _FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3086")


def get_admin_emails() -> set:
    if _ADMIN_EMAILS is None:
        _load_config()
    return _ADMIN_EMAILS  # type: ignore[return-value]


def get_jwt_secret() -> str:
    if _JWT_SECRET is None:
        _load_config()
    return _JWT_SECRET or ""  # type: ignore[return-value]


def get_google_client_id() -> str:
    if _GOOGLE_CLIENT_ID is None:
        _load_config()
    return _GOOGLE_CLIENT_ID or ""


def get_google_client_secret() -> str:
    if _GOOGLE_CLIENT_SECRET is None:
        _load_config()
    return _GOOGLE_CLIENT_SECRET or ""


def get_frontend_url() -> str:
    if _FRONTEND_URL is None:
        _load_config()
    return _FRONTEND_URL or "http://localhost:3086"


# ──────────────────────────────────────────────────────────────────
# PKCE helpers
# ──────────────────────────────────────────────────────────────────

def _generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ──────────────────────────────────────────────────────────────────
# OAuth flow
# ──────────────────────────────────────────────────────────────────

def build_oauth_redirect_url(redirect_uri: str) -> Tuple[str, str, str]:
    """Build Google OAuth URL.  Returns (url, state, code_verifier)."""
    state = secrets.token_urlsafe(16)
    verifier = _generate_code_verifier()
    challenge = _generate_code_challenge(verifier)

    params = {
        "client_id": get_google_client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    query = urlencode(params)
    url = f"{GOOGLE_AUTH_URL}?{query}"
    return url, state, verifier


def is_secure_cookie(frontend_url: Optional[str] = None) -> bool:
    """Only mark cookies secure when the configured frontend origin uses HTTPS."""
    parsed = urlparse(frontend_url or get_frontend_url())
    return parsed.scheme == "https"


async def exchange_code_for_email(
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> Optional[str]:
    """Exchange authorization code for user email.  Returns email or None."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": get_google_client_id(),
                    "client_secret": get_google_client_secret(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
            )
            if resp.status_code != 200:
                logger.warning("Token exchange failed: %s", resp.text)
                return None
            tokens = resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return None

            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code != 200:
                return None
            return info_resp.json().get("email")
        except Exception as exc:
            logger.warning("OAuth exchange error: %s", exc)
            return None


# ──────────────────────────────────────────────────────────────────
# JWT helpers
# ──────────────────────────────────────────────────────────────────

def create_admin_jwt(email: str) -> str:
    """Create a signed JWT for an authenticated admin."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_admin_jwt(token: str) -> Optional[str]:
    """Decode and validate an admin JWT.  Returns the admin email or None."""
    try:
        secret = get_jwt_secret()
        if not secret:
            return None
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def is_admin_email(email: str) -> bool:
    """Check whether an email is in the ADMIN_EMAILS whitelist."""
    emails = get_admin_emails()
    if not emails:
        return False
    return email.strip().lower() in emails


# ──────────────────────────────────────────────────────────────────
# Cookie helper
# ──────────────────────────────────────────────────────────────────

COOKIE_MAX_AGE = JWT_EXPIRY_HOURS * 3600
