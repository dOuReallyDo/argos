"""Text and Markdown parsers."""

from __future__ import annotations

import asyncio
from pathlib import Path

import charset_normalizer

from core.models import DocumentType

from .base import BaseParser, ParsedDocument


class TextParser(BaseParser):
    """Parse plain text files with automatic encoding detection."""

    document_type = DocumentType.TEXT
    supported_mimes = [
        "text/plain",
        "text/csv",
        "application/json",
        "text/xml",
        "application/xml",
        "application/javascript",
        "text/html",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        # Robust encoding detection
        result = charset_normalizer.from_path(file_path)
        text = str(result.best()) if result else file_path.read_text()

        metadata = {
            "encoding": result.best().encoding if result else "utf-8",
            "lines": text.count("\n") + 1,
            "size_bytes": file_path.stat().st_size,
        }

        return ParsedDocument(text=text, metadata=metadata)

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if mime_type in self.supported_mimes:
            return True
        return file_path.suffix.lower() in (
            ".txt", ".csv", ".json", ".xml", ".html", ".htm",
            ".js", ".ts", ".py", ".java", ".rb", ".go", ".rs",
            ".cpp", ".c", ".h", ".sh", ".bash", ".zsh", ".yml",
            ".yaml", ".toml", ".ini", ".cfg", ".conf", ".log",
            ".css", ".scss", ".sql", ".r", ".m",
        )


class MarkdownParser(BaseParser):
    """Parse Markdown files with structure preservation."""

    document_type = DocumentType.MARKDOWN
    supported_mimes = [
        "text/markdown",
        "text/x-markdown",
        "text/plain",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        result = charset_normalizer.from_path(file_path)
        text = str(result.best()) if result else file_path.read_text()

        # Extract structure: headers, code blocks, links
        import re

        headers = re.findall(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE)
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", text, re.DOTALL)

        metadata = {
            "encoding": result.best().encoding if result else "utf-8",
            "lines": text.count("\n") + 1,
            "header_count": len(headers),
            "code_blocks": len(code_blocks),
            "top_headers": [h[1] for h in headers[:5]],
        }

        return ParsedDocument(
            text=text,
            metadata=metadata,
            markdown=text,  # Preserve original markdown
        )

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if file_path.suffix.lower() in (".md", ".markdown", ".mdx", ".rmd"):
            return True
        # Also handle files with MIME text/markdown
        return mime_type in ("text/markdown", "text/x-markdown")
