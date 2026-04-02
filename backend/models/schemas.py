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

class ChatResponse(BaseModel):
    answer: str = Field(..., description="Answer from NotebookLM")
    language: str = Field(default="auto", description="Response language")
    sources: List[str] = Field(default_factory=list, description="Source documents")
    citations: List[Citation] = Field(default_factory=list, description="Citation references with source info")
    suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HealthResponse(BaseModel):
    status: str = Field(default="healthy")
    notebooklm: str = Field(default="unknown")
    notebook_name: Optional[str] = None
    auth_status: str = Field(default="unknown")
