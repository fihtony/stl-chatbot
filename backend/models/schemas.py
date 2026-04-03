from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict


class Citation(BaseModel):
    """A single citation/reference source from NotebookLM"""
    id: int = Field(..., description="Citation number")
    source: str = Field(..., description="Source document name")
    original_ids: List[int] = Field(default_factory=list, description="Original citation IDs from NotebookLM")
    excerpt: str = Field(default="", description="Surrounding paragraph text for context")
    content: str = Field(default="", description="Source document excerpt from citation dialog")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    session_id: str = Field(default="default", description="Session ID for conversation isolation")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="Answer from NotebookLM")
    language: str = Field(default="auto", description="Response language")
    sources: List[str] = Field(default_factory=list, description="Source documents")
    citations: List[Citation] = Field(default_factory=list, description="Citation references with source info")
    suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")
    session_id: str = Field(default="default", description="Session ID echoed back for frontend correlation")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthResponse(BaseModel):
    status: str = Field(default="healthy")
    notebooklm: str = Field(default="unknown")
    notebook_name: Optional[str] = None
    auth_status: str = Field(default="unknown")


class CitationRequest(BaseModel):
    citation_id: int = Field(..., description="Citation ID to fetch content for")
    original_ids: List[int] = Field(default_factory=list, description="Original NotebookLM citation IDs to try")
    session_id: str = Field(default="default", description="Session ID to find the right browser state")


class CitationContentResponse(BaseModel):
    content: str = Field(default="", description="Source document excerpt")
    success: bool = Field(default=False, description="Whether content was successfully fetched")
    error: Optional[str] = Field(default=None, description="Error message if fetch failed")
    images: List[str] = Field(default_factory=list, description="Image URLs from citation popup")


# ──────────────────────────────────────────────────────────────────
# Admin schemas
# ──────────────────────────────────────────────────────────────────

class PublicStateResponse(BaseModel):
    default_language: str
    active_theme_id: str
    theme_definition: Dict[str, Any]
    config_version: int
    maintenance_mode: bool
    maintenance_title: str
    maintenance_message: str
    maintenance_start: Optional[str]
    maintenance_end: Optional[str]
    banner_enabled: bool
    banner_title: str
    banner_content: str
    banner_start: Optional[str]
    banner_end: Optional[str]
    banner_timezone: str
    banner_severity: str
    banner_version: int


class ConfigVersionResponse(BaseModel):
    config_version: int


class AdminMeResponse(BaseModel):
    email: str
    logged_in: bool


class UpdateNotebookLMUrlRequest(BaseModel):
    url: str = Field(..., description="New NotebookLM URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("NotebookLM URL must start with https://")
        if "notebooklm.google" not in v:
            raise ValueError("URL does not appear to be a valid NotebookLM URL")
        return v


class NotebookLMUrlResponse(BaseModel):
    url_masked: str
    config_version: int


class AdminConfigResponse(BaseModel):
    notebooklm_url_masked: str
    default_language: str
    active_theme_id: str
    config_version: int
    maintenance_mode: bool
    maintenance_title: str
    maintenance_message: str
    maintenance_start: Optional[str]
    maintenance_end: Optional[str]
    banner_enabled: bool
    banner_title: str
    banner_content: str
    banner_start: Optional[str]
    banner_end: Optional[str]
    banner_timezone: str
    banner_severity: str
    banner_version: int


class ReauthStartRequest(BaseModel):
    method: str = Field(default="browser", description="'browser' or 'copy_url'")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("browser", "copy_url"):
            raise ValueError("Method must be one of: browser, copy_url")
        return v


class ReauthStatusResponse(BaseModel):
    job_id: str
    status: str
    method: str
    auth_url: Optional[str]
    started_at: str
    updated_at: str


class ThemeDefinition(BaseModel):
    primary: str = Field(default="#1D4ED8")
    background: str = Field(default="#EFF6FF")
    headerBg: str = Field(default="from-blue-700 to-blue-800")
    userBubble: str = Field(default="bg-blue-700")
    assistantBubble: str = Field(default="bg-white")


class ThemeRecord(BaseModel):
    id: str
    name: str
    is_preset: bool
    definition: Dict[str, Any]
    created_at: str


class CreateThemeRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=64)
    definition: Dict[str, Any]


class SetActiveThemeRequest(BaseModel):
    theme_id: str


class NoticeBannerRequest(BaseModel):
    title: str = Field(default="")
    content: str = Field(default="")
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timezone: str = Field(default="America/Toronto")
    severity: str = Field(default="info")
    enabled: bool = Field(default=False)


class MaintenanceModeRequest(BaseModel):
    enabled: bool
    title: str = Field(default="System Maintenance")
    message: str = Field(default="The system is currently under maintenance. Please try again later.")
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class DefaultLanguageRequest(BaseModel):
    language: str = Field(..., description="Language code: 'en', 'fr', or 'zh'")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in ("en", "fr", "zh"):
            raise ValueError("Language must be one of: en, fr, zh")
        return v


class LogEntry(BaseModel):
    id: int
    session_id: str
    requested_at: str
    question_summary: str
    answer_summary: str
    browser_name: str
    os_name: str
    city: str
    country: str
    is_error: bool
    error_summary: Optional[str]
    response_ms: int


class LogDetail(LogEntry):
    browser_version: str
    os_version: str
    device_type: str
    province: str
    language_pref: str
    referer: str
    error_detail: Optional[str]
    google_raw_request: Optional[str]
    google_raw_response: Optional[str]
    user_agent: str


class AuditLogEntry(BaseModel):
    id: int
    admin_email: str
    action: str
    result: str
    before_summary: Optional[str]
    after_summary: Optional[str]
    browser: str
    os: str
    created_at: str


class DashboardResponse(BaseModel):
    active_sessions: int
    notebooklm_status: str
    today_questions: int
    maintenance_status: str
    total_sessions: int
    total_questions: int
    avg_questions_per_session: float
    avg_response_ms: float
    error_rate: float
    config_version: int
