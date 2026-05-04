"""PDF parser — primary engine with GLM-OCR fallback capability."""

from __future__ import annotations

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Optional

import pdfplumber
import pypdfium2 as pdfium

from core.config import get_settings
from core.models import DocumentType

from .base import BaseParser, ParsedDocument

settings = get_settings()


class PDFParser(BaseParser):
    """Parse PDF documents into structured text.

    Uses pdfplumber as primary engine for table/column awareness,
    with pypdfium2 for fast text extraction.
    GLM-OCR can be enabled for complex layouts via settings.
    """

    document_type = DocumentType.PDF
    supported_mimes = [
        "application/pdf",
        "application/x-pdf",
        "application/acrobat",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a PDF with multi-engine strategy."""

        # Try GLM-OCR first if enabled
        if settings.glm_ocr_enabled:
            try:
                return await self._parse_with_glm_ocr(file_path)
            except Exception:
                pass  # Fall back to pdfplumber

        return await self._parse_with_pdfplumber(file_path)

    async def _parse_with_pdfplumber(self, file_path: Path) -> ParsedDocument:
        """Primary parser: pdfplumber for layout-aware extraction."""
        text_parts = []
        tables = []
        metadata = {}

        loop = asyncio.get_running_loop()

        def _extract():
            with pdfplumber.open(str(file_path)) as pdf:
                meta = {
                    "page_count": len(pdf.pages),
                    "pdf_metadata": pdf.metadata or {},
                }
                texts = []
                tbls = []
                for i, page in enumerate(pdf.pages):
                    t = page.extract_text() or ""
                    texts.append(f"[Page {i + 1}]\n{t}")

                    # Extract tables
                    page_tables = page.extract_tables()
                    for t_idx, table in enumerate(page_tables):
                        if table:
                            tbls.append(
                                {
                                    "page": i + 1,
                                    "index": t_idx,
                                    "headers": table[0] if table else [],
                                    "rows": len(table) - 1 if table else 0,
                                }
                            )
                return "\n\n".join(texts), tbls, meta

        text, tables, metadata = await loop.run_in_executor(
            None, _extract
        )

        # Check page count limit
        page_count = metadata.get("page_count", 0)
        if settings.max_pdf_pages and page_count > settings.max_pdf_pages:
            metadata["truncated"] = True
            metadata["truncated_pages"] = (
                page_count - settings.max_pdf_pages
            )

        return ParsedDocument(
            text=text,
            metadata=metadata,
            tables=tables,
            markdown=None,
        )

    async def _parse_with_glm_ocr(self, file_path: Path) -> ParsedDocument:
        """Use GLM-OCR for complex PDFs with tables, formulas, handwriting.

        Requires: pip install glm-ocr
        """
        try:
            from glm_ocr import GLMOCR  # type: ignore

            ocr = GLMOCR(model_path=settings.glm_ocr_model_path)
            markdown_output = ocr.process(str(file_path))

            return ParsedDocument(
                text=markdown_output,
                metadata={"parser": "glm-ocr", "model": "glm-ocr-0.9b"},
                markdown=markdown_output,
            )
        except ImportError:
            raise RuntimeError(
                "GLM-OCR not installed. Run: pip install -e '.[glm-ocr]'"
            )

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if mime_type in self.supported_mimes:
            return True
        return file_path.suffix.lower() == ".pdf"
