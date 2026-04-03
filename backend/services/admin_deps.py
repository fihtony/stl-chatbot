"""Admin API dependency — extract and validate admin JWT from cookie."""
from fastapi import Cookie, HTTPException, status
from typing import Optional

from services.admin_auth_service import decode_admin_jwt, COOKIE_NAME


async def get_current_admin(admin_token: Optional[str] = Cookie(default=None)) -> str:
    """FastAPI dependency: return admin email or raise 401."""
    if not admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    email = decode_admin_jwt(admin_token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return email
