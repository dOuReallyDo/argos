"""Repository layer — CRUD operations for documents and sources."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logging import logger
from core.models import DocumentRecord, DocumentSource, DocumentStatus, SourceType

from .models import ChunkModel, DocumentModel, EncryptionKeyModel, SourceModel


# ── Source Repository ─────────────────────────────────────────

class SourceRepository:
    """CRUD for persistent source identities."""

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        source_type: SourceType,
        source_value: str,
    ) -> SourceModel:
        """Get existing source or create a new one."""
        result = await db.execute(
            select(SourceModel).where(
                SourceModel.source_type == source_type.value,
                SourceModel.source_value == source_value,
            )
        )
        source = result.scalar_one_or_none()
        if source:
            return source

        source = SourceModel(
            source_type=source_type.value,
            source_value=source_value,
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        logger.info(f"Created source: {source_type.value}:{source_value} ({source.id})")
        return source

    @staticmethod
    async def get_by_id(
        db: AsyncSession, source_id: str
    ) -> Optional[SourceModel]:
        result = await db.execute(
            select(SourceModel).where(SourceModel.id == source_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(
        db: AsyncSession, limit: int = 100, offset: int = 0
    ) -> list[SourceModel]:
        result = await db.execute(
            select(SourceModel)
            .order_by(SourceModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


# ── Document Repository ───────────────────────────────────────

class DocumentRepository:
    """CRUD for document records."""

    @staticmethod
    async def create(
        db: AsyncSession,
        record: DocumentRecord,
    ) -> DocumentModel:
        """Persist a DocumentRecord as a DocumentModel."""
        doc = DocumentModel(
            id=record.id,
            filename=record.filename,
            original_filename=record.original_filename,
            document_type=record.document_type.value,
            mime_type=record.mime_type,
            file_size_bytes=record.file_size_bytes,
            status=record.status.value,
            source_id=record.source_id,
            storage_path=record.storage_path,
            storage_backend=record.storage_backend,
            encrypted=record.encrypted,
            encryption_key_id=record.encryption_key_id,
            page_count=record.page_count,
            duration_seconds=record.duration_seconds,
            language=record.language,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def update_status(
        db: AsyncSession,
        doc_id: str,
        status: DocumentStatus,
        error_message: Optional[str] = None,
    ) -> Optional[DocumentModel]:
        doc = await DocumentRepository.get_by_id(db, doc_id)
        if not doc:
            return None

        doc.status = status.value
        if error_message:
            doc.error_message = error_message
        if status == DocumentStatus.COMPLETED:
            doc.completed_at = datetime.utcnow()
        doc.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def update_embedding_metadata(
        db: AsyncSession,
        doc_id: str,
        model_name: str,
        vector_count: int,
        embedding_dim: int,
    ) -> None:
        doc = await DocumentRepository.get_by_id(db, doc_id)
        if doc:
            doc.embedding_model = model_name
            doc.vector_count = vector_count
            doc.embedding_dim = embedding_dim
            doc.updated_at = datetime.utcnow()
            await db.commit()

    @staticmethod
    async def get_by_id(
        db: AsyncSession, doc_id: str
    ) -> Optional[DocumentModel]:
        result = await db.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.source))
            .where(DocumentModel.id == doc_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_source(
        db: AsyncSession,
        source_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentModel]:
        """Get all documents from a specific source."""
        result = await db.execute(
            select(DocumentModel)
            .where(DocumentModel.source_id == source_id)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def search(
        db: AsyncSession,
        query: str,
        doc_type: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[DocumentModel]:
        """Full-text search on parsed text and filenames."""
        conditions = []

        if source_id:
            conditions.append(DocumentModel.source_id == source_id)
        if doc_type:
            conditions.append(DocumentModel.document_type == doc_type)

        # SQLite: use LIKE for FTS (PostgreSQL would use tsvector)
        like_query = f"%{query}%"
        conditions.append(
            func.lower(DocumentModel.original_filename).like(
                func.lower(like_query)
            )
        )

        stmt = (
            select(DocumentModel)
            .where(*conditions)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_by_source(db: AsyncSession) -> list[dict]:
        """Count documents per source."""
        result = await db.execute(
            select(
                DocumentModel.source_id,
                func.count(DocumentModel.id).label("count"),
                func.sum(DocumentModel.file_size_bytes).label("total_bytes"),
            ).group_by(DocumentModel.source_id)
        )
        return [
            {"source_id": r.source_id, "count": r.count, "total_bytes": r.total_bytes}
            for r in result.all()
        ]

    @staticmethod
    async def delete(
        db: AsyncSession, doc_id: str
    ) -> bool:
        doc = await DocumentRepository.get_by_id(db, doc_id)
        if not doc:
            return False
        await db.delete(doc)
        await db.commit()
        return True


# ── Chunk Repository ──────────────────────────────────────────

class ChunkRepository:
    """CRUD for chunk references."""

    @staticmethod
    async def create_batch(
        db: AsyncSession,
        document_id: str,
        chunks: list[dict],
        qdrant_point_ids: list[str],
        collection: str,
    ) -> None:
        """Create chunk records in batch."""
        for chunk, pid in zip(chunks, qdrant_point_ids):
            ch = ChunkModel(
                document_id=document_id,
                chunk_index=chunk["index"],
                qdrant_point_id=pid,
                text=chunk["text"],
                token_count=chunk["token_count"],
                collection=collection,
            )
            db.add(ch)

        await db.commit()
        logger.debug(
            f"Created {len(chunks)} chunk records for doc {document_id}"
        )

    @staticmethod
    async def get_by_document(
        db: AsyncSession, document_id: str
    ) -> list[ChunkModel]:
        result = await db.execute(
            select(ChunkModel)
            .where(ChunkModel.document_id == document_id)
            .order_by(ChunkModel.chunk_index)
        )
        return list(result.scalars().all())
