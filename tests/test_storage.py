"""Tests for storage — repository, models, file storage."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.models import DocumentRecord, DocumentSource, DocumentStatus, SourceType
from storage.models import Base, DocumentModel, SourceModel
from storage.repository import DocumentRepository, SourceRepository
from storage.file_storage import LocalStorage


@pytest.fixture
async def db() -> AsyncSession:
    """In-memory SQLite database for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


class TestSourceRepository:
    """Source creation and retrieval."""

    @pytest.mark.asyncio
    async def test_create_source(self, db):
        source = await SourceRepository.get_or_create(
            db, SourceType.EMAIL, "user@example.com"
        )
        assert source.id is not None
        assert source.source_type == "email"
        assert source.source_value == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_or_create_idempotent(self, db):
        s1 = await SourceRepository.get_or_create(
            db, SourceType.ALIAS, "test_alias"
        )
        s2 = await SourceRepository.get_or_create(
            db, SourceType.ALIAS, "test_alias"
        )
        assert s1.id == s2.id

    @pytest.mark.asyncio
    async def test_list_sources(self, db):
        await SourceRepository.get_or_create(db, SourceType.EMAIL, "a@b.com")
        await SourceRepository.get_or_create(db, SourceType.PHONE, "+39123456")

        sources = await SourceRepository.list_all(db, limit=10)
        assert len(sources) >= 2


class TestDocumentRepository:
    """Document CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, db):
        source = await SourceRepository.get_or_create(
            db, SourceType.EMAIL, "test@argos.dev"
        )

        record = DocumentRecord(
            filename="test_file.txt",
            original_filename="test_file.txt",
            document_type="text",
            mime_type="text/plain",
            file_size_bytes=1024,
            source_id=source.id,
            storage_path="/data/test.txt",
            status=DocumentStatus.UPLOADED,
        )

        doc = await DocumentRepository.create(db, record)
        assert doc.id is not None
        assert doc.source_id == source.id
        assert doc.status == "uploaded"

        # Retrieve
        retrieved = await DocumentRepository.get_by_id(db, doc.id)
        assert retrieved is not None
        assert retrieved.original_filename == "test_file.txt"
        assert retrieved.source is not None  # Relationship loaded
        assert retrieved.source.id == source.id

    @pytest.mark.asyncio
    async def test_update_status(self, db):
        source = await SourceRepository.get_or_create(
            db, SourceType.SYSTEM, "auto"
        )
        record = DocumentRecord(
            filename="doc.pdf",
            original_filename="doc.pdf",
            document_type="pdf",
            mime_type="application/pdf",
            file_size_bytes=5000,
            source_id=source.id,
            storage_path="/data/doc.pdf",
        )
        doc = await DocumentRepository.create(db, record)

        updated = await DocumentRepository.update_status(
            db, doc.id, DocumentStatus.COMPLETED
        )
        assert updated.status == "completed"
        assert updated.completed_at is not None

        # Error case
        await DocumentRepository.update_status(
            db, doc.id, DocumentStatus.FAILED, "Processing crashed"
        )
        error_doc = await DocumentRepository.get_by_id(db, doc.id)
        assert error_doc.status == "failed"
        assert error_doc.error_message == "Processing crashed"

    @pytest.mark.asyncio
    async def test_get_by_source(self, db):
        source = await SourceRepository.get_or_create(db, SourceType.EMAIL, "m@t.co")
        for i in range(3):
            record = DocumentRecord(
                filename=f"file_{i}.txt",
                original_filename=f"file_{i}.txt",
                document_type="text",
                mime_type="text/plain",
                file_size_bytes=100,
                source_id=source.id,
                storage_path=f"/data/file_{i}.txt",
            )
            await DocumentRepository.create(db, record)

        docs = await DocumentRepository.get_by_source(db, source.id)
        assert len(docs) == 3

    @pytest.mark.asyncio
    async def test_delete(self, db):
        source = await SourceRepository.get_or_create(db, SourceType.ALIAS, "tmp")
        record = DocumentRecord(
            filename="tmp.txt", original_filename="tmp.txt",
            document_type="text", mime_type="text/plain",
            file_size_bytes=10, source_id=source.id, storage_path="/tmp"
        )
        doc = await DocumentRepository.create(db, record)

        assert await DocumentRepository.delete(db, doc.id) is True
        assert await DocumentRepository.get_by_id(db, doc.id) is None
        assert await DocumentRepository.delete(db, "nonexistent") is False


class TestFileStorage:
    """Local file storage operations."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, tmp_path):
        import os
        # Override storage path for test
        storage = LocalStorage()
        storage._base = tmp_path / "files"
        storage._base.mkdir(parents=True, exist_ok=True)

        # Create a test file
        src = tmp_path / "original.txt"
        src.write_text("This is a test file content.")

        stored_path = await storage.store(src, doc_id="abc123", filename="stored.txt")
        assert "stored.txt" in stored_path
        assert Path(stored_path).exists()

        # Retrieve
        content = await storage.retrieve(stored_path)
        assert content == b"This is a test file content."

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        storage = LocalStorage()
        storage._base = tmp_path / "files"

        src = tmp_path / "to_delete.txt"
        src.write_text("delete me")
        stored = await storage.store(src, doc_id="xyz", filename="to_delete.txt")

        await storage.delete(stored)
        assert not Path(stored).exists()
