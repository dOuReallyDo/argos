"""Request/Response Pydantic schemas for Argos API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from core.models import DocumentStatus, DocumentType, SourceType


# ── Source ────────────────────────────────────────────────────

class SourceCreate(BaseModel):
    """Create a new source attribution."""
    source_type: SourceType = Field(
        ..., description="Type of source identifier"
    )
    source_value: str = Field(
        ..., min_length=1, max_length=255,
        description="Email, phone number, or other identifier"
    )


class SourceGenerateAlias(BaseModel):
    """Generate a random alias source."""
    alias_prefix: Optional[str] = Field(
        None, max_length=20,
        description="Optional prefix for the random alias"
    )


class SourceResponse(BaseModel):
    """Source as returned by API."""
    id: str
    source_type: str
    source_value: str
    created_at: datetime
    document_count: Optional[int] = None

    model_config = {"from_attributes": True}


# ── Document ──────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    """Document metadata as returned by API."""
    id: str
    filename: str
    original_filename: str
    document_type: str
    mime_type: str
    file_size_bytes: int
    status: str
    source_id: str
    storage_path: str
    page_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    language: Optional[str] = None
    encrypted: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """Response after document upload (processing starts async)."""
    document_id: str
    filename: str
    status: str
    message: str


# ── Search ────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Semantic/hybrid search query."""
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    document_types: Optional[list[str]] = None
    source_id: Optional[str] = None
    cross_modal: bool = False


class SearchResultItem(BaseModel):
    """Single search result."""
    score: float
    collection: str
    document_id: str
    text: str
    chunk_index: int
    original_filename: str
    document_type: str
    source_id: str


class SearchResponse(BaseModel):
    """Search results."""
    query: str
    total_results: int
    embedding_model: str
    results: list[SearchResultItem]
    took_ms: float


# ── Auth ──────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    """Request an access token."""
    source_id: str = Field(..., description="Your source identifier")
    secret: Optional[str] = Field(None, description="Optional passphrase")
    scope: str = "read"


class TokenResponse(BaseModel):
    """JWT access token."""
    access_token: str
    token_type: str = "bearer"


# ── Health ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """System health."""
    status: str
    version: str
    embedding_model: str
    storage_backend: str
    encryption_enabled: bool
    uptime_seconds: float
