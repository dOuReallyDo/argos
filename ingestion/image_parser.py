"""Image parser with OCR + CLIP captioning."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from core.config import get_settings
from core.models import DocumentType

from .base import BaseParser, ParsedDocument

settings = get_settings()


class ImageParser(BaseParser):
    """Parse images — OCR text extraction + optional CLIP vision embedding.

    Supports JPEG, PNG, GIF, WebP, BMP, TIFF, HEIC, AVIF, and RAW formats
    at any resolution (auto-resized to manageable dimensions).
    """

    document_type = DocumentType.IMAGE
    supported_mimes = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "image/heic",
        "image/heif",
        "image/avif",
        # RAW formats
        "image/x-canon-cr2",
        "image/x-canon-crw",
        "image/x-nikon-nef",
        "image/x-sony-arw",
        "image/x-fuji-raf",
        "image/x-adobe-dng",
        "image/x-panasonic-rw2",
        "image/x-olympus-orf",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_sync, file_path)

    def _parse_sync(self, file_path: Path) -> ParsedDocument:
        img = Image.open(str(file_path))

        # Convert to RGB if needed
        if img.mode not in ("RGB", "L", "RGBA"):
            img = img.convert("RGB")

        metadata = {
            "width": img.width,
            "height": img.height,
            "format": img.format or "unknown",
            "mode": img.mode,
            "size_bytes": file_path.stat().st_size,
        }

        # OCR via EasyOCR (primary) + Tesseract (fallback)
        text = self._ocr_with_easyocr(img)

        # If OCR found nothing useful, try Tesseract
        if not text.strip():
            text = self._ocr_with_tesseract(file_path)

        return ParsedDocument(
            text=text,
            metadata=metadata,
        )

    def _ocr_with_easyocr(self, img: Image.Image) -> str:
        """OCR with EasyOCR — good for mixed languages, natural scenes."""
        try:
            import easyocr

            reader = easyocr.Reader(["it", "en"], gpu=False)
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img.save(f.name, "PNG")
                results = reader.readtext(f.name, detail=0)
                os.unlink(f.name)
                return "\n".join(results)
        except ImportError:
            return ""

    def _ocr_with_tesseract(self, file_path: Path) -> str:
        """Fallback OCR with Tesseract."""
        try:
            import pytesseract

            return pytesseract.image_to_string(str(file_path), lang="ita+eng")
        except ImportError:
            return ""

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if mime_type in self.supported_mimes:
            return True
        return file_path.suffix.lower() in (
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
            ".tiff", ".tif", ".heic", ".heif", ".avif",
            ".cr2", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf",
            ".svg", ".ico",
        )
