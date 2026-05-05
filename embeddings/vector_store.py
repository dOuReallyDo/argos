"""Qdrant vector store integration — indexing and search."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import numpy as np
from qdrant_client import AsyncQdrantClient, QdrantClient, models

from core.config import get_settings
from core.logging import logger
from core.models import DocumentRecord, DocumentType

from .embedders import embedding_manager

settings = get_settings()


class VectorStore:
    """Manages vector storage and retrieval via Qdrant.

    Each document type gets its own named collection:
        - argos_text       (text chunks, markdown, parsed text)
        - argos_images     (image embeddings + OCR text)
        - argos_audio      (audio transcripts + CLAP embeddings)
        - argos_video      (video transcripts + frame embeddings)

    When Gemini Embedding 2 is activated, a single unified
    collection (argos_unified) is used for cross-modal search.
    """

    # ── Collection configuration ────────────────────────────────
    TEXT_COLLECTION = "argos_text"
    IMAGE_COLLECTION = "argos_images"
    AUDIO_COLLECTION = "argos_audio"
    VIDEO_COLLECTION = "argos_video"
    UNIFIED_COLLECTION = "argos_unified"

    def __init__(self):
        self._client: Optional[AsyncQdrantClient] = None

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
        return self._client

    async def initialize(self) -> None:
        """Create all required collections if they don't exist."""
        await self._ensure_collection(
            self.TEXT_COLLECTION, embedding_manager.active_dimension
        )
        await self._ensure_collection(
            self.IMAGE_COLLECTION, embedding_manager.active_dimension
        )
        await self._ensure_collection(
            self.AUDIO_COLLECTION, 512  # CLAP dimension
        )
        await self._ensure_collection(
            self.VIDEO_COLLECTION, embedding_manager.active_dimension
        )
        logger.info("Vector store initialized — all collections ready")

    async def _ensure_collection(
        self, name: str, vector_size: int
    ) -> None:
        """Create collection if missing."""
        exists = await self.client.collection_exists(name)
        if not exists:
            await self.client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Created collection: {name} (dim={vector_size})")

    # ── Indexing ────────────────────────────────────────────────

    async def index_document(
        self,
        record: DocumentRecord,
        chunks: list[dict],
    ) -> list[str]:
        """Index a document's chunks into the appropriate Qdrant collection.

        Args:
            record: DocumentRecord from ingestion pipeline
            chunks: List of {text, index, token_count} from chunking

        Returns:
            List of Qdrant point IDs for later retrieval.
        """
        if not chunks:
            logger.warning(f"No chunks to index for {record.original_filename}")
            return []

        collection = self._collection_for_type(record.document_type)
        texts = [c["text"] for c in chunks]

        # Generate embeddings
        vectors = await embedding_manager.embed_texts(texts)

        # Build points
        points = []
        point_ids = []

        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            pid = uuid.uuid4().hex
            point_ids.append(pid)

            points.append(
                models.PointStruct(
                    id=pid,
                    vector=vector.tolist(),
                    payload={
                        "document_id": record.id,
                        "chunk_index": chunk["index"],
                        "text": chunk["text"],
                        "token_count": chunk["token_count"],
                        "source_id": record.source_id,
                        "document_type": record.document_type.value,
                        "original_filename": record.original_filename,
                        "mime_type": record.mime_type,
                        "page_count": record.page_count,
                        "duration_seconds": record.duration_seconds,
                    },
                )
            )

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=collection,
                points=batch,
            )

        logger.info(
            f"Indexed {len(points)} chunks in '{collection}' "
            f"for {record.original_filename}"
        )

        return point_ids

    async def index_image(
        self,
        record: DocumentRecord,
        image_path: Path,
        description: str = "",
    ) -> str:
        """Index an image with its CLIP embedding + OCR text."""
        vector = await embedding_manager.embed_images([image_path])
        pid = uuid.uuid4().hex

        await self.client.upsert(
            collection_name=self.IMAGE_COLLECTION,
            points=[
                models.PointStruct(
                    id=pid,
                    vector=vector[0].tolist(),
                    payload={
                        "document_id": record.id,
                        "image_path": str(image_path),
                        "ocr_text": description,
                        "source_id": record.source_id,
                        "original_filename": record.original_filename,
                    },
                )
            ],
        )

        return pid

    async def index_audio(
        self,
        record: DocumentRecord,
        audio_path: Path,
        transcript: str = "",
    ) -> str:
        """Index audio with CLAP embedding + Whisper transcript."""
        vector = await embedding_manager.embed_audio([audio_path])
        pid = uuid.uuid4().hex

        await self.client.upsert(
            collection_name=self.AUDIO_COLLECTION,
            points=[
                models.PointStruct(
                    id=pid,
                    vector=vector[0].tolist(),
                    payload={
                        "document_id": record.id,
                        "audio_path": str(audio_path),
                        "transcript": transcript,
                        "source_id": record.source_id,
                        "original_filename": record.original_filename,
                    },
                )
            ],
        )

        return pid

    # ── Searching ───────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 10,
        document_types: Optional[list[DocumentType]] = None,
        source_id: Optional[str] = None,
    ) -> list[dict]:
        """Semantic search across vector store.

        Args:
            query: Natural language query
            top_k: Number of results per collection
            document_types: Filter to specific types (None = text collections only)
            source_id: Filter to a specific source (for attribution tracking)

        Returns:
            List of {score, text, metadata} sorted by relevance.
        """
        # Embed query
        query_vec = await embedding_manager.embed_texts(
            [query], for_query=True
        )

        collections = self._search_collections(document_types)
        search_filter = self._build_filter(source_id)
        results = []

        for collection in collections:
            try:
                hits = await self.client.search(
                    collection_name=collection,
                    query_vector=query_vec[0].tolist(),
                    limit=top_k,
                    query_filter=search_filter,
                    with_payload=True,
                )

                for hit in hits:
                    results.append({
                        "score": hit.score,
                        "collection": collection,
                        "document_id": hit.payload.get("document_id", ""),
                        "text": hit.payload.get("text", hit.payload.get("transcript", "")),
                        "chunk_index": hit.payload.get("chunk_index", 0),
                        "original_filename": hit.payload.get("original_filename", "unknown"),
                        "document_type": hit.payload.get("document_type", "text"),
                        "source_id": hit.payload.get("source_id", ""),
                    })
            except Exception as e:
                logger.warning(f"Search in {collection} failed: {e}")
                continue

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def cross_modal_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Cross-modal search — requires Gemini Embedding 2 for unified space.

        Finds relevant content regardless of modality.
        Example: "find the graph about Q1 revenue" → returns video frames,
        PDF charts, and image screenshots.
        """
        embedding_manager.use_gemini()
        try:
            return await self.search(query, top_k=limit)
        finally:
            # Restore local models for cost efficiency
            embedding_manager.use_local()

    # ── Helpers ─────────────────────────────────────────────────

    def _collection_for_type(
        self, doc_type: DocumentType
    ) -> str:
        """Map document type to Qdrant collection."""
        mapping = {
            DocumentType.PDF: self.TEXT_COLLECTION,
            DocumentType.WORD: self.TEXT_COLLECTION,
            DocumentType.MARKDOWN: self.TEXT_COLLECTION,
            DocumentType.TEXT: self.TEXT_COLLECTION,
            DocumentType.EXCEL: self.TEXT_COLLECTION,
            DocumentType.POWERPOINT: self.TEXT_COLLECTION,
            DocumentType.IMAGE: self.IMAGE_COLLECTION,
            DocumentType.AUDIO: self.AUDIO_COLLECTION,
            DocumentType.VIDEO: self.VIDEO_COLLECTION,
        }
        return mapping.get(doc_type, self.TEXT_COLLECTION)

    def _search_collections(
        self,
        doc_types: Optional[list[DocumentType]],
    ) -> list[str]:
        """Determine which collections to search."""
        if not doc_types:
            # Default: search text collections only (same dimension)
            return [self.TEXT_COLLECTION]

        collections = set()
        for dt in doc_types:
            collections.add(self._collection_for_type(dt))
        return list(collections)

    @staticmethod
    def _build_filter(
        source_id: Optional[str],
    ) -> Optional[models.Filter]:
        """Build Qdrant filter for source attribution."""
        if not source_id:
            return None

        return models.Filter(
            must=[
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=source_id),
                )
            ]
        )
