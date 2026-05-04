"""Audio parser — Whisper transcription with metadata extraction."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from core.config import get_settings
from core.models import DocumentType

from .base import BaseParser, ParsedDocument

settings = get_settings()


class AudioParser(BaseParser):
    """Parse audio files — transcribe via Whisper, extract metadata via FFmpeg.

    Supports: MP3, WAV, FLAC, AAC, OGG, M4A, WMA, AIFF, ALAC, Opus, and more
    (both consumer and professional formats).
    """

    document_type = DocumentType.AUDIO
    supported_mimes = [
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/flac",
        "audio/aac",
        "audio/ogg",
        "audio/x-m4a",
        "audio/mp4",
        "audio/x-ms-wma",
        "audio/aiff",
        "audio/x-aiff",
        "audio/opus",
        "audio/webm",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        loop = asyncio.get_running_loop()

        # Get metadata via ffprobe
        metadata = await loop.run_in_executor(
            None, self._extract_metadata, file_path
        )

        # Check duration limit
        duration = metadata.get("duration_seconds", 0)
        if duration > settings.max_audio_duration_seconds:
            metadata["truncated"] = True
            metadata["original_duration"] = duration

        # Transcribe via Whisper
        text = await loop.run_in_executor(
            None, self._transcribe, file_path
        )

        return ParsedDocument(
            text=text,
            metadata=metadata,
        )

    def _extract_metadata(self, file_path: Path) -> dict:
        """Extract audio metadata using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            import json
            info = json.loads(result.stdout)

            fmt = info.get("format", {})
            streams = info.get("streams", [])
            audio_streams = [
                s for s in streams if s.get("codec_type") == "audio"
            ]

            metadata = {
                "duration_seconds": float(fmt.get("duration", 0)),
                "format_name": fmt.get("format_name", "unknown"),
                "bitrate_bps": int(fmt.get("bit_rate", 0)),
                "size_bytes": int(fmt.get("size", 0)),
                "codec": (
                    audio_streams[0].get("codec_name", "unknown")
                    if audio_streams
                    else "unknown"
                ),
                "sample_rate_hz": (
                    int(audio_streams[0].get("sample_rate", 0))
                    if audio_streams
                    else 0
                ),
                "channels": (
                    int(audio_streams[0].get("channels", 0))
                    if audio_streams
                    else 0
                ),
            }

            # Tags (artist, album, etc.)
            tags = fmt.get("tags", {})
            if tags:
                metadata["tags"] = tags

            return metadata
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return {"error": "metadata_extraction_failed"}

    def _transcribe(self, file_path: Path) -> str:
        """Transcribe audio using OpenAI Whisper."""
        try:
            import whisper

            model = whisper.load_model(
                settings.whisper_model, device=settings.whisper_device
            )
            result = model.transcribe(str(file_path))
            return result["text"]
        except ImportError:
            # Fallback: try with explicit error about installation
            raise RuntimeError(
                "openai-whisper not installed. Run: pip install openai-whisper"
            )

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if mime_type in self.supported_mimes:
            return True
        audio_exts = {
            ".mp3", ".wav", ".flac", ".aac", ".ogg", ".oga",
            ".m4a", ".wma", ".aiff", ".aif", ".alac",
            ".opus", ".webm", ".ra", ".amr", ".ac3",
            ".dts", ".pcm", ".wv",
        }
        return file_path.suffix.lower() in audio_exts
