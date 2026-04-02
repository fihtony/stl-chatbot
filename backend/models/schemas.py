from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List


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
