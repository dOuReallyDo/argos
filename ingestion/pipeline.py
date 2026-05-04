"""Ingestion Pipeline — orchestrates parsing + chunking for all document types."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Optional

from core.config import get_settings
from core.logging import logger
from core.models import (
    DocumentRecord,
    DocumentSource,
    DocumentStatus,
    DocumentType,
    SourceType,
)

from .base import BaseParser, ParsedDocument, registry
from .audio_parser import AudioParser
from .excel_parser import ExcelParser
from .image_parser import ImageParser
from .pdf_parser import PDFParser
from .powerpoint_parser import PowerPointParser
from .text_parser import MarkdownParser, TextParser
from .video_parser import VideoParser
from .word_parser import WordParser

settings = get_settings()

# ── Register all parsers at import time ────────────────────────
def _register_all():
    registry.register(PDFParser())
    registry.register(WordParser())
    registry.register(TextParser())
    registry.register(MarkdownParser())
    registry.register(ImageParser())
    registry.register(AudioParser())
    registry.register(VideoParser())
    registry.register(ExcelParser())
    registry.register(PowerPointParser())

_register_all()


class IngestionPipeline:
    """Orchestrates document ingestion: detect → parse → chunk → store.

    Usage:
        pipeline = IngestionPipeline()
        records = await pipeline.process_file(
            file_path=Path("/docs/report.pdf"),
            source=DocumentSource(source_type=SourceType.EMAIL, source_value="mario@example.com")
        )
    """

    # ── Chunking Configuration ─────────────────────────────────
    DEFAULT_CHUNK_SIZE = 512   # tokens
    CHUNK_OVERLAP = 64         # tokens overlap
    MAX_CHUNKS = 5000          # safety limit

    async def process_file(
        self,
        file_path: Path,
        source: DocumentSource,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> DocumentRecord:
        """Process a single file through the full ingestion pipeline.

        Steps:
        1. Detect MIME type
        2. Find appropriate parser
        3. Parse document → text + metadata
        4. Chunk text for embedding
        5. Create DocumentRecord

        Returns:
            DocumentRecord ready for embedding and storage.
        """
        start_time = time.monotonic()

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 1. Detect MIME type
        mime_type = BaseParser.detect_mime(file_path)
        original_filename = file_path.name

        logger.info(
            f"Ingesting: {original_filename} ({mime_type}) "
            f"size={file_path.stat().st_size:_d} bytes"
        )

        # 2. Find parser
        parser = registry.get_parser(file_path, mime_type)
        if not parser:
            raise ValueError(
                f"No parser found for {original_filename} (MIME: {mime_type}). "
                f"Supported types: {registry.supported_types}"
            )

        doc_type = parser.document_type

        # 3. Parse
        try:
            parsed: ParsedDocument = await parser.parse(file_path)
        except Exception as e:
            logger.error(f"Parsing failed for {original_filename}: {e}")
            return self._error_record(
                original_filename, doc_type, mime_type, source, str(e)
            )

        logger.debug(
            f"Parsed: {len(parsed.text)} chars, "
            f"{len(parsed.tables)} tables, {len(parsed.images)} images"
        )

        # 4. Chunk
        chunks = self._chunk_text(
            parsed.text,
            chunk_size=chunk_size,
            overlap=self.CHUNK_OVERLAP,
        )

        # 5. Build record
        record = DocumentRecord(
            filename=uuid.uuid4().hex[:8] + "_" + original_filename,
            original_filename=original_filename,
            document_type=doc_type,
            mime_type=mime_type,
            file_size_bytes=file_path.stat().st_size,
            status=DocumentStatus.PARSED,
            source_id=source.id,
            storage_path=str(file_path),
            storage_backend=settings.storage_backend,
            parsed_text=parsed.text,
            parsed_chunks=len(chunks),
            page_count=parsed.metadata.get("page_count"),
            duration_seconds=parsed.metadata.get("duration_seconds"),
            language=parsed.metadata.get("language"),
        )

        elapsed = time.monotonic() - start_time
        logger.success(
            f"Ingested {original_filename}: {len(chunks)} chunks "
            f"in {elapsed:.2f}s"
        )

        return record

    async def process_batch(
        self,
        file_paths: list[Path],
        source: DocumentSource,
        concurrency: int = 4,
    ) -> list[DocumentRecord]:
        """Process multiple files concurrently.

        All files in a batch share the same source attribution.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _process_one(fp: Path) -> DocumentRecord:
            async with sem:
                return await self.process_file(fp, source)

        tasks = [_process_one(fp) for fp in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        records: list[DocumentRecord] = []
        for fp, result in zip(file_paths, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to process {fp.name}: {result}")
                records.append(
                    self._error_record(
                        fp.name, DocumentType.TEXT, "unknown/unknown",
                        source, str(result)
                    )
                )
            else:
                records.append(result)

        return records

    # ── Chunking ────────────────────────────────────────────────

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = CHUNK_OVERLAP,
    ) -> list[dict]:
        """Split text into overlapping chunks for embedding.

        Strategy: semantic chunking by paragraphs, falling back
        to sentence boundaries, with sliding window for long passages.

        Returns list of {"text": str, "index": int, "token_count": int}
        """
        if not text.strip():
            return []

        # Approximate: 1 token ≈ 0.75 words for English, ≈ 0.5 for Italian
        # We split by paragraphs first, then merge short ones
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text]

        chunks = []
        current = ""
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)

            # If a single paragraph is too large, split by sentences
            if para_tokens > chunk_size:
                # Flush current
                if current:
                    chunks.append(current)
                    current = ""
                    current_tokens = 0

                sentences = self._split_sentences(para)
                for sent in sentences:
                    sent_tokens = self._estimate_tokens(sent)
                    if current_tokens + sent_tokens > chunk_size and current:
                        chunks.append(current)
                        # Keep overlap: last sentence(s) of previous chunk
                        overlap_text = self._get_tail(
                            current, overlap
                        )
                        current = overlap_text + " " + sent
                        current_tokens = self._estimate_tokens(current)
                    else:
                        current = (
                            current + " " + sent
                            if current
                            else sent
                        )
                        current_tokens += sent_tokens
            else:
                if current_tokens + para_tokens > chunk_size:
                    chunks.append(current)
                    current = para
                    current_tokens = para_tokens
                else:
                    current = (
                        current + "\n\n" + para if current else para
                    )
                    current_tokens += para_tokens

        # Don't forget the last chunk
        if current:
            chunks.append(current)

        # Format output
        return [
            {
                "text": chunk,
                "index": i,
                "token_count": self._estimate_tokens(chunk),
            }
            for i, chunk in enumerate(chunks[:self.MAX_CHUNKS])
        ]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast token estimation: ~1.3 tokens per word (conservative)."""
        return max(1, int(len(text.split()) * 1.3))

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Simple sentence splitter for Italian/English."""
        import re

        # Split on terminal punctuation followed by space + uppercase/capital
        sentences = re.split(
            r"(?<=[.!?])\s+(?=[A-ZÀ-Ü])", text
        )
        return [s.strip() for s in sentences if s.strip()]

    @staticmethod
    def _get_tail(text: str, max_tokens: int) -> str:
        """Get last ~max_tokens tokens of text for overlap."""
        words = text.split()
        target_words = int(max_tokens / 1.3)
        if len(words) <= target_words:
            return text
        return " ".join(words[-target_words:])

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _error_record(
        filename: str,
        doc_type: DocumentType,
        mime_type: str,
        source: DocumentSource,
        error: str,
    ) -> DocumentRecord:
        return DocumentRecord(
            filename=filename,
            original_filename=filename,
            document_type=doc_type,
            mime_type=mime_type,
            file_size_bytes=0,
            status=DocumentStatus.FAILED,
            source_id=source.id,
            storage_path="",
            error_message=error,
        )
