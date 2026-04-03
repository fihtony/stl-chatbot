import sys
import time
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from utils.config import config
from utils.logger import logger
from utils.database import init_db
from utils.constants import (
    ResponseKeys,
    NotebookLMStatus,
    HealthStatus,
)
from models.schemas import ChatRequest, ChatResponse, HealthResponse, CitationRequest, CitationContentResponse
from services.auth_service import AuthService
from services.service_factory import get_notebooklm_service, NotebookLMServiceInterface
from services.admin_router import router as admin_router
from services.public_config_router import router as public_config_router, cleanup_old_logs
from services.chat_logger import log_chat_request

# Lazy initialization - services will be created when needed
_auth_service: Optional[AuthService] = None
_notebooklm_services: Dict[str, NotebookLMServiceInterface] = {}  # Session-scoped services
_notebooklm_default: Optional[NotebookLMServiceInterface] = None  # Default service for non-session requests

# Cache for authentication status (updated at startup)
# Type: Optional[NotebookLMStatus] - None indicates not yet initialized
_auth_status_cache: Optional[str] = NotebookLMStatus.MOCK_MODE if config.MOCK_NOTEBOOKLM else None


def get_auth_service() -> AuthService:
    """Lazy initialization of AuthService (only in non-mock mode)"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def get_notebooklm(session_id: str = None) -> NotebookLMServiceInterface:
    """Get session-scoped NotebookLM service.

    Each session gets its own service instance with isolated browser state,
    citation cache, and thread pool. If no session_id is provided, uses default singleton.
    """
    global _notebooklm_default, _notebooklm_services
    if session_id:
        if session_id not in _notebooklm_services:
            _notebooklm_services[session_id] = get_notebooklm_service(session_id=session_id)
        return _notebooklm_services[session_id]
    else:
        if _notebooklm_default is None:
            _notebooklm_default = get_notebooklm_service(session_id="default")
        return _notebooklm_default


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    global _auth_status_cache, _notebooklm_default, _notebooklm_services
    logger.info("=== Starting NotebookLM Chatbot Backend ===")

    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Initialize SQLite database
    await init_db()

    # Skip authentication in mock mode
    if config.MOCK_NOTEBOOKLM:
        logger.info("🎭 MOCK MODE: Using MockNotebookLMService (authentication skipped)")
    else:
        # Initialize auth service only in non-mock mode
        auth = get_auth_service()

        # Check authentication status - start in degraded mode if not authenticated
        # Admin can re-authenticate via the admin panel without restarting the server
        if not auth.is_authenticated():
            logger.warning(
                "⚠️  NotebookLM not authenticated. Chat will be unavailable until re-authenticated. "
                "Use the admin panel to re-authenticate."
            )
            _auth_status_cache = NotebookLMStatus.NOT_AUTHENTICATED
        else:
            logger.info("✅ Authentication found")
            _auth_status_cache = NotebookLMStatus.AUTHENTICATED
            logger.info("✅ Connected to NotebookLM")

    # Schedule daily log cleanup
    async def _log_cleanup_loop():
        while True:
            await asyncio.sleep(86400)  # Run once per day
            try:
                await cleanup_old_logs()
                logger.info("Log cleanup completed")
            except Exception as exc:
                logger.warning("Log cleanup failed: %s", exc)

    cleanup_task = asyncio.create_task(_log_cleanup_loop())

    yield

    # Cancel background task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # Cleanup: shut down all session-scoped services
    logger.info("=== Shutting down ===")
    for sid, svc in list(_notebooklm_services.items()):
        try:
            if hasattr(svc, 'shutdown'):
                svc.shutdown()
        except Exception:
            pass
    _notebooklm_services.clear()
    if _notebooklm_default and hasattr(_notebooklm_default, 'shutdown'):
        _notebooklm_default.shutdown()
        _notebooklm_default = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


# Create FastAPI application
app = FastAPI(
    title="NotebookLM Chatbot API",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Register routers
app.include_router(admin_router)
app.include_router(public_config_router)


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    Returns the status of the application and its services
    """
    global _auth_status_cache

    # Determine auth status (use cache if available)
    if config.MOCK_NOTEBOOKLM:
        auth_status = NotebookLMStatus.MOCK_MODE
    elif _auth_status_cache is not None:
        auth_status = _auth_status_cache
    else:
        auth_status = (
            NotebookLMStatus.AUTHENTICATED
            if get_auth_service().is_authenticated()
            else NotebookLMStatus.NOT_AUTHENTICATED
        )

    return HealthResponse(
        status=HealthStatus.HEALTHY,
        notebooklm=(
            NotebookLMStatus.MOCK_MODE
            if config.MOCK_NOTEBOOKLM
            else NotebookLMStatus.CONNECTED
        ),
        notebook_name=(
            "Saint-Louis (Mock)" if config.MOCK_NOTEBOOKLM else "Saint-Louis"
        ),
        auth_status=auth_status,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """
    Chat endpoint
    Processes user messages and returns responses from NotebookLM (or mock service).
    Blocked during maintenance mode (unless the caller is an authenticated admin).
    """
    # --- Maintenance mode guard ---
    try:
        from utils.database import get_db as _get_db
        async with await _get_db() as _db:
            _cfg = await (await _db.execute(
                "SELECT maintenance_mode FROM admin_config WHERE id=1"
            )).fetchone()
        if _cfg and bool(_cfg["maintenance_mode"]):
            # Allow admins through (check JWT cookie)
            from services.admin_auth_service import decode_admin_jwt, COOKIE_NAME
            token = http_request.cookies.get(COOKIE_NAME)
            if not token or not decode_admin_jwt(token):
                raise HTTPException(
                    status_code=503,
                    detail="System is currently under maintenance. Please try again later."
                )
    except HTTPException:
        raise
    except Exception:
        pass  # DB not yet ready — allow request through

    # --- Collect request metadata for logging ---
    ua_str = http_request.headers.get("user-agent", "")
    lang_pref = http_request.headers.get("accept-language", "")
    referer = http_request.headers.get("referer", "")
    # Extract real IP: respect X-Forwarded-For set by a trusted reverse proxy
    forwarded_for = http_request.headers.get("x-forwarded-for", "")
    real_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        http_request.client.host if http_request.client else ""
    )

    start_ms = int(time.time() * 1000)
    try:
        service = get_notebooklm(request.session_id)
        result = service.query(request.message)

        response_ms = int(time.time() * 1000) - start_ms
        answer = result[ResponseKeys.ANSWER]

        # Fire-and-forget log (don't block the response)
        asyncio.create_task(log_chat_request(
            session_id=request.session_id or "default",
            question=request.message,
            answer=answer,
            user_agent_str=ua_str,
            real_ip=real_ip,
            language_pref=lang_pref[:50],
            referer=referer[:200],
            response_ms=response_ms,
            is_error=False,
        ))

        return ChatResponse(
            answer=answer,
            language=result[ResponseKeys.LANGUAGE],
            sources=result[ResponseKeys.SOURCES],
            citations=result.get("citations", []),
            suggestions=result.get("suggestions", []),
            session_id=request.session_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        response_ms = int(time.time() * 1000) - start_ms
        err_str = str(e)
        logger.error(f"Chat error: {e}", exc_info=True)
        asyncio.create_task(log_chat_request(
            session_id=request.session_id or "default",
            question=request.message,
            answer=None,
            user_agent_str=ua_str,
            real_ip=real_ip,
            language_pref=lang_pref[:50],
            referer=referer[:200],
            response_ms=response_ms,
            is_error=True,
            error_summary=err_str[:300],
            error_detail=err_str,
        ))
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request. Please try again later."
        )


@app.post("/api/citation", response_model=CitationContentResponse)
async def citation(request: CitationRequest):
    """
    Citation content endpoint
    Fetches the source document content for a citation on-demand (lazy loading).
    Uses the browser session kept alive from the previous chat query.
    Non-blocking — delegates to session's dedicated thread pool.
    """
    try:
        service = get_notebooklm(request.session_id)
        if not hasattr(service, 'fetch_citation_content'):
            return CitationContentResponse(
                content="",
                success=False,
                error="Citation loading not supported in this mode"
            )

        result = await service.fetch_citation_content(
            citation_id=request.citation_id,
            original_ids=request.original_ids
        )

        return CitationContentResponse(
            content=result.get("content", ""),
            success=result.get("success", False),
            error=result.get("error"),
            images=result.get("images", []),
        )

    except Exception as e:
        logger.error(f"Citation fetch error: {e}", exc_info=True)
        return CitationContentResponse(
            content="",
            success=False,
            error="Failed to fetch citation content"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.BACKEND_PORT)
