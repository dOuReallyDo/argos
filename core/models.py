"""Domain models shared across modules."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Processing status of an ingested document."""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    """Supported document types."""

    PDF = "pdf"
    WORD = "word"
    MARKDOWN = "markdown"
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"


class SourceType(str, Enum):
    """Source identifier type for document attribution."""

    EMAIL = "email"
    PHONE = "phone"
    ALIAS = "alias"
    SYSTEM = "system"


class DocumentSource(BaseModel):
    """Fixed source attribution for a session of documents."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_type: SourceType
    source_value: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentRecord(BaseModel):
    """A document ingested into Argos."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    filename: str
    original_filename: str
    document_type: DocumentType
    mime_type: str
    file_size_bytes: int
    status: DocumentStatus = DocumentStatus.UPLOADED
    source_id: str
    storage_path: str
    storage_backend: str = "local"

    # Parsing metadata
    parsed_text: Optional[str] = None
    parsed_chunks: Optional[int] = None
    page_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    language: Optional[str] = None

    # Embedding metadata
    embedding_model: Optional[str] = None
    vector_count: Optional[int] = None
    embedding_dim: Optional[int] = None

    # Chunk embedding references (Qdrant point IDs)
    chunk_ids: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Error info
    error_message: Optional[str] = None

    # Encryption
    encrypted: bool = False
    encryption_key_id: Optional[str] = None
