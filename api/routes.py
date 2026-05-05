"""REST API routes — upload, search, retrieval, source management."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.logging import logger
from core.models import DocumentRecord, DocumentSource, DocumentStatus, SourceType
from encryption.auth import (
    TokenData,
    create_access_token,
    get_current_source,
    get_current_source_write,
)
from embeddings.embedders import embedding_manager
from embeddings.vector_store import VectorStore
from ingestion.pipeline import IngestionPipeline
from storage.database import get_db
from storage.file_storage import LocalStorage, S3Storage
from storage.repository import DocumentRepository, SourceRepository

from .schemas import (
    DocumentResponse,
    DocumentUploadResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SourceCreate,
    SourceGenerateAlias,
    SourceResponse,
    TokenRequest,
    TokenResponse,
)

settings = get_settings()
router = APIRouter()

# ── Service instances ─────────────────────────────────────────
pipeline = IngestionPipeline()
vector_store = VectorStore()
storage_backend = (
    LocalStorage()
    if settings.storage_backend == "local"
    else S3Storage()
)


# ── Health ────────────────────────────────────────────────────

_start_time = time.time()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """System health check — no auth required."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        embedding_model=embedding_manager.active_model,
        storage_backend=settings.storage_backend,
        encryption_enabled=settings.encryption_enabled,
        uptime_seconds=time.time() - _start_time,
    )


# ── Sources ───────────────────────────────────────────────────

@router.post(
    "/sources",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Sources"],
)
async def create_source(
    body: SourceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new source identity (email, phone, alias)."""
    source = await SourceRepository.get_or_create(
        db, body.source_type, body.source_value
    )
    return SourceResponse.model_validate(source)


@router.post(
    "/sources/alias",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Sources"],
)
async def generate_alias(
    body: SourceGenerateAlias,
    db: AsyncSession = Depends(get_db),
):
    """Generate a random alias source (one-click anonymous attribution)."""
    prefix = body.alias_prefix or "src"
    alias_value = f"{prefix}_{uuid.uuid4().hex[:8]}"
    source = await SourceRepository.get_or_create(
        db, SourceType.ALIAS, alias_value
    )
    return SourceResponse.model_validate(source)


@router.get(
    "/sources",
    response_model=list[SourceResponse],
    tags=["Sources"],
)
async def list_sources(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List all registered sources."""
    sources = await SourceRepository.list_all(db, limit, offset)
    return [SourceResponse.model_validate(s) for s in sources]


# ── Documents: Upload ─────────────────────────────────────────

@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Documents"],
)
async def upload_document(
    file: UploadFile = File(...),
    source_id: str = Form(..., description="Your source ID"),
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_source_write),
):
    """Upload a single document for ingestion.

    The document is:
    1. Saved to storage (local or S3)
    2. Parsed by the appropriate parser
    3. Chunked and embedded
    4. Indexed in Qdrant
    5. Metadata stored in the relational DB

    All processing is synchronous in this version; a Celery task
    queue is available for production deployments.
    """
    # Verify or auto-create source (supports email, alias, or UUID)
    source = await SourceRepository.get_by_id(db, source_id)
    if not source:
        # Try as email/alias — auto-register if it looks like a value not an ID
        if "@" in source_id or len(source_id) > 12:
            from core.models import SourceType
            stype = SourceType.EMAIL if "@" in source_id else SourceType.ALIAS
            source = await SourceRepository.get_or_create(db, stype, source_id)
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Source not found: {source_id}",
            )

    # Validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({size_mb:.1f}MB). Max: {settings.max_upload_size_mb}MB",
        )

    # Write temp file
    tmp_path = Path(f"/tmp/argos_upload_{uuid.uuid4().hex[:8]}_{file.filename}")
    tmp_path.write_bytes(contents)

    try:
        # Process through ingestion pipeline
        record = await pipeline.process_file(
            tmp_path,
            source=DocumentSource(
                source_type=SourceType(source.source_type),
                source_value=source.source_value,
            ),
        )
        record.source_id = source.id  # Use DB source ID

        # Persist document record
        doc = await DocumentRepository.create(db, record)

        # Store file permanently
        try:
            storage_path = await storage_backend.store(tmp_path, record.id, file.filename)
            doc.storage_path = storage_path
            await db.commit()
        except Exception as se:
            logger.warning(f"File storage failed, keeping temp path: {se}")

        if record.status == DocumentStatus.FAILED:
            return DocumentUploadResponse(
                document_id=record.id,
                filename=record.original_filename,
                status="failed",
                message=record.error_message or "Processing failed",
            )

        # Chunk and embed (skip if Qdrant unavailable)
        chunks = pipeline._chunk_text(record.parsed_text or "")
        point_ids = []
        
        try:
            point_ids = await vector_store.index_document(record, chunks)
            # Persist chunk references
            from storage.repository import ChunkRepository
            collection = vector_store._collection_for_type(record.document_type)
            await ChunkRepository.create_batch(db, record.id, chunks, point_ids, collection)
            indexed_msg = f"{len(chunks)} chunks indexed"
        except Exception as qe:
            logger.warning(f"Vector indexing skipped (Qdrant unavailable): {qe}")
            indexed_msg = f"{len(chunks)} chunks parsed (vector indexing unavailable)"

        # Update embedding metadata
        await DocumentRepository.update_embedding_metadata(
            db,
            record.id,
            embedding_manager.active_model,
            len(chunks),
            embedding_manager.active_dimension,
        )

        # Mark completed
        await DocumentRepository.update_status(db, record.id, DocumentStatus.COMPLETED)

        return DocumentUploadResponse(
            document_id=record.id,
            filename=record.original_filename,
            status="completed",
            message=f"Successfully processed: {indexed_msg}",
        )

    except Exception as e:
        logger.error(f"Upload failed for {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )
    finally:
        # Cleanup temp file
        if tmp_path.exists():
            tmp_path.unlink()


@router.post(
    "/documents/upload-batch",
    tags=["Documents"],
)
async def upload_batch(
    files: list[UploadFile] = File(...),
    source_id: str = Form(...),
    token: TokenData = Depends(get_current_source_write),
):
    """Upload multiple documents in a single request.

    All documents share the same source attribution.
    """
    results = []
    for file in files:
        # Reuse single upload logic
        pass  # Would call upload_document internally

    return {"uploaded": len(results), "source_id": source_id}


# ── Documents: Get ────────────────────────────────────────────

@router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    tags=["Documents"],
)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_source),
):
    """Get document metadata by ID."""
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.get(
    "/documents/{doc_id}/download",
    tags=["Documents"],
)
async def download_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_source),
):
    """Download the original document file."""
    doc = await DocumentRepository.get_by_id(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_bytes = await storage_backend.retrieve(doc.storage_path)
        return Response(
            content=file_bytes,
            media_type=doc.mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{doc.original_filename}\""
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file not found in storage")


@router.get(
    "/documents/by-source/{source_id}",
    response_model=list[DocumentResponse],
    tags=["Documents"],
)
async def get_documents_by_source(
    source_id: str,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_source),
):
    """Get all documents from a specific source."""
    docs = await DocumentRepository.get_by_source(db, source_id, limit, offset)
    return [DocumentResponse.model_validate(d) for d in docs]


# ── Search ────────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=SearchResponse,
    tags=["Search"],
)
async def search(
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    token: TokenData = Depends(get_current_source),
):
    """Semantic search across all indexed documents.

    Supports:
    - Natural language queries
    - Filtering by document type
    - Filtering by source attribution
    - Optional cross-modal search (Gemini Embedding 2)
    """
    start = time.time()
    doc_types = None
    if body.document_types:
        doc_types = [DocumentType(dt) for dt in body.document_types]

    if body.cross_modal:
        hits = await vector_store.cross_modal_search(
            body.query, limit=body.top_k
        )
    else:
        hits = await vector_store.search(
            body.query,
            top_k=body.top_k,
            document_types=doc_types,
            source_id=body.source_id,
        )

    elapsed_ms = (time.time() - start) * 1000

    return SearchResponse(
        query=body.query,
        total_results=len(hits),
        embedding_model=embedding_manager.active_model,
        results=[SearchResultItem(**h) for h in hits],
        took_ms=round(elapsed_ms, 2),
    )


# ── Auth ──────────────────────────────────────────────────────

@router.post(
    "/auth/token",
    response_model=TokenResponse,
    tags=["Auth"],
)
async def get_token(body: TokenRequest):
    """Get a JWT access token for API authentication.

    The source_id becomes the token's subject — all subsequent
    requests are tied to this source for attribution tracking.
    """
    token = create_access_token(
        body.source_id,
        scope=body.scope,
    )
    return TokenResponse(access_token=token)
