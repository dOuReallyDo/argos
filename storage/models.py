"""Database models — SQLAlchemy ORM for document storage and metadata."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Source ─────────────────────────────────────────────────────

class SourceModel(Base):
    """Persistent source attribution — ties documents to a verified identity."""

    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12]
    )
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # email | phone | alias | system
    source_value: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="source"
    )
    encryption_keys: Mapped[list["EncryptionKeyModel"]] = relationship(
        back_populates="source"
    )


# ── Document ───────────────────────────────────────────────────

class DocumentModel(Base):
    """Main document record — one row per ingested document."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    document_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="uploaded", nullable=False, index=True
    )

    # Source attribution (foreign key — always enforced)
    source_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Storage
    storage_path: Mapped[str] = mapped_column(
        String(1024), nullable=False
    )
    storage_backend: Mapped[str] = mapped_column(
        String(20), default="local", nullable=False
    )

    # Parsing metadata
    parsed_text: Mapped[Optional[str]] = mapped_column(Text)
    parsed_chunks: Mapped[Optional[int]] = mapped_column(Integer)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    language: Mapped[Optional[str]] = mapped_column(String(10))

    # Embedding metadata
    embedding_model: Mapped[Optional[str]] = mapped_column(String(127))
    vector_count: Mapped[Optional[int]] = mapped_column(Integer)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer)

    # Encryption
    encrypted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    encryption_key_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("encryption_keys.id"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Error
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    source: Mapped[SourceModel] = relationship(back_populates="documents")
    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="document")
    encryption_key: Mapped[Optional["EncryptionKeyModel"]] = relationship(
        back_populates="documents"
    )


# ── Chunk ──────────────────────────────────────────────────────

class ChunkModel(Base):
    """Reference to a chunk in the vector store."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    document_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    qdrant_point_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    collection: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # Relationship
    document: Mapped[DocumentModel] = relationship(back_populates="chunks")


# ── Encryption Key ─────────────────────────────────────────────

class EncryptionKeyModel(Base):
    """Encryption key metadata — the actual key never touches the DB."""

    __tablename__ = "encryption_keys"

    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12]
    )
    key_alias: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    algorithm: Mapped[str] = mapped_column(
        String(20), default="AES-256-GCM", nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    source: Mapped[SourceModel] = relationship(back_populates="encryption_keys")
    documents: Mapped[list[DocumentModel]] = relationship(
        back_populates="encryption_key"
    )
