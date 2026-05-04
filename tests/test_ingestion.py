"""Tests for Ingestion Pipeline — integration tests with real files."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.models import DocumentSource, SourceType
from ingestion.base import ParserRegistry
from ingestion.pipeline import IngestionPipeline
from ingestion.pdf_parser import PDFParser
from ingestion.text_parser import TextParser, MarkdownParser


class TestParserRegistry:
    """Parser registry: discovery and matching."""

    def test_registry_has_parsers(self):
        """All parsers are registered at import time."""
        from ingestion.pipeline import _register_all
        from ingestion.base import registry

        # At least 9 parsers registered
        assert len(registry._parsers) >= 9
        assert registry.get_parser_by_type(registry.supported_types[0]) is not None

    def test_text_parser_handles_txt(self):
        parser = TextParser()
        assert parser.can_handle(Path("test.txt"), "text/plain")
        assert parser.can_handle(Path("test.csv"), "text/csv")
        assert parser.can_handle(Path("test.log"), "text/plain")

    def test_markdown_parser_handles_md(self):
        parser = MarkdownParser()
        assert parser.can_handle(Path("doc.md"), "text/plain")
        assert parser.can_handle(Path("doc.markdown"), "text/markdown")
        assert not parser.can_handle(Path("doc.pdf"), "application/pdf")


class TestTextParsing:
    """Integration: actual file parsing."""

    @pytest.mark.asyncio
    async def test_parse_text_file(self):
        parser = TextParser()
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("Hello World\nThis is a test file.\nCiao mondo!")
            tmp = Path(f.name)

        try:
            result = await parser.parse(tmp)
            assert "Hello World" in result.text
            assert "Ciao mondo" in result.text
            assert result.metadata["lines"] == 3
        finally:
            tmp.unlink()

    @pytest.mark.asyncio
    async def test_parse_markdown_file(self):
        parser = MarkdownParser()
        content = "# Title\n\n## Section\n\nSome text here.\n\n```python\nprint('hello')\n```"
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write(content)
            tmp = Path(f.name)

        try:
            result = await parser.parse(tmp)
            assert result.markdown == content
            assert result.metadata["header_count"] == 2
            assert result.metadata["code_blocks"] == 1
        finally:
            tmp.unlink()


class TestIngestionPipeline:
    """End-to-end ingestion flow."""

    @pytest.mark.asyncio
    async def test_process_text_file(self):
        pipeline = IngestionPipeline()
        source = DocumentSource(
            source_type=SourceType.EMAIL,
            source_value="test@example.com",
        )

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("This is a document about artificial intelligence and machine learning.\n" * 20)
            tmp = Path(f.name)

        try:
            record = await pipeline.process_file(tmp, source)
            assert record.document_type.value == "text"
            assert record.parsed_chunks is not None
            assert record.parsed_chunks > 0
            assert record.source_id == source.id
        finally:
            tmp.unlink()

    @pytest.mark.asyncio
    async def test_chunking(self):
        pipeline = IngestionPipeline()
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three.\n\n" * 50
        chunks = pipeline._chunk_text(text, chunk_size=256)

        assert len(chunks) > 0
        # Each chunk should have required fields
        for c in chunks:
            assert "text" in c
            assert "index" in c
            assert "token_count" in c
            assert len(c["text"]) > 0


class TestPDFParser:
    """PDF parser basic validation."""

    def test_pdf_detection(self):
        parser = PDFParser()
        assert parser.can_handle(Path("doc.pdf"), "application/pdf")
        assert not parser.can_handle(Path("doc.txt"), "text/plain")

    def test_mime_detection(self):
        from ingestion.base import BaseParser

        # Test with non-existent file (graceful fallback)
        mime = BaseParser.detect_mime(Path("/nonexistent/file.pdf"))
        assert mime == "application/pdf"  # mimetypes guesses by extension


class TestEmbeddingManager:
    """Embedding manager: model switching."""

    def test_default_is_local(self):
        from embeddings.embedders import embedding_manager
        assert embedding_manager._current == "local"

    def test_switch_to_gemini(self):
        from embeddings.embedders import embedding_manager
        embedding_manager.use_gemini()
        assert embedding_manager._current == "gemini"
        assert embedding_manager.active_dimension == 3072
        # Restore
        embedding_manager.use_local()

    def test_active_model_names(self):
        from embeddings.embedders import embedding_manager
        assert "sentence-transformers" in embedding_manager.active_model
        embedding_manager.use_gemini()
        assert "gemini" in embedding_manager.active_model
        embedding_manager.use_local()
