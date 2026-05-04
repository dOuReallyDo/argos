"""Base parser interface and registry for Ingestion Engine.

All document parsers conform to this protocol, making it easy
to add new formats without touching existing code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.models import DocumentType


@dataclass
class ParsedDocument:
    """Output of a parser — structured text + metadata."""

    text: str
    metadata: dict = field(default_factory=dict)
    chunks: list[dict] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)

    # Optional structured output (tables, formulas, etc.)
    tables: list[dict] = field(default_factory=list)
    markdown: Optional[str] = None


class BaseParser(ABC):
    """Base class for all document parsers."""

    # Override in subclass
    document_type: DocumentType
    supported_mimes: list[str] = []

    @abstractmethod
    async def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a single document into structured text and metadata.

        Args:
            file_path: Absolute path to the document file.

        Returns:
            ParsedDocument with text, metadata, chunks, and optional markdown.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is not supported by this parser.
        """
        ...

    @abstractmethod
    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        """Check if this parser can handle the given file."""
        ...

    @staticmethod
    def detect_mime(file_path: Path) -> str:
        """Detect MIME type using magic bytes (libmagic alternative via stdlib)."""
        import mimetypes

        mime, _ = mimetypes.guess_type(str(file_path))
        if mime:
            return mime

        # Fallback: read magic bytes
        magic_map = {
            b"\x25\x50\x44\x46": "application/pdf",
            b"\x50\x4b\x03\x04": "application/vnd.openxmlformats-officedocument",
            b"\xd0\xcf\x11\xe0": "application/msword",
            b"\xff\xd8\xff": "image/jpeg",
            b"\x89PNG\r\n\x1a\n": "image/png",
            b"GIF89a": "image/gif",
            b"GIF87a": "image/gif",
            b"RIFF": "audio/wav",
            b"ID3": "audio/mpeg",
            b"\xff\xfb": "audio/mpeg",
            b"\x00\x00\x00\x18ftyp": "video/mp4",
            b"\x1a\x45\xdf\xa3": "video/webm",
        }

        try:
            with open(file_path, "rb") as f:
                header = f.read(12)
                for magic, mime in magic_map.items():
                    if header.startswith(magic):
                        return mime
        except OSError:
            pass

        return "application/octet-stream"


class ParserRegistry:
    """Registry of all available parsers — extensible via registration."""

    def __init__(self):
        self._parsers: dict[DocumentType, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        """Register a parser for its document type."""
        self._parsers[parser.document_type] = parser

    def get_parser(
        self, file_path: Path, mime_type: str
    ) -> Optional[BaseParser]:
        """Find the first parser that can handle this file."""
        for parser in self._parsers.values():
            if parser.can_handle(file_path, mime_type):
                return parser
        return None

    def get_parser_by_type(
        self, doc_type: DocumentType
    ) -> Optional[BaseParser]:
        """Get parser by explicit document type."""
        return self._parsers.get(doc_type)

    @property
    def supported_types(self) -> list[DocumentType]:
        return list(self._parsers.keys())


# Singleton registry
registry = ParserRegistry()
