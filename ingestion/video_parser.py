"""Video parser — audio track extraction + frame extraction + Whisper transcription."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from core.config import get_settings
from core.models import DocumentType

from .base import BaseParser, ParsedDocument

settings = get_settings()


class VideoParser(BaseParser):
    """Parse video files — extract audio for transcription + keyframes.

    Supports: MP4, MOV, AVI, MKV, WebM, FLV, WMV, M4V, MPEG, 3GP, and more
    (consumer and professional formats with any resolution).
    """

    document_type = DocumentType.VIDEO
    supported_mimes = [
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
        "video/x-flv",
        "video/x-ms-wmv",
        "video/mpeg",
        "video/3gpp",
        "video/3gpp2",
        "video/x-m4v",
        "video/mp2t",
    ]

    async def parse(self, file_path: Path) -> ParsedDocument:
        loop = asyncio.get_running_loop()

        # Extract metadata
        metadata = await loop.run_in_executor(
            None, self._extract_metadata, file_path
        )

        duration = metadata.get("duration_seconds", 0)
        if duration > settings.max_video_duration_seconds:
            metadata["truncated"] = True
            metadata["original_duration"] = duration
            duration = settings.max_video_duration_seconds

        # 1. Extract audio track → transcribe
        audio_path = await loop.run_in_executor(
            None, self._extract_audio, file_path, duration
        )
        transcription = ""
        if audio_path:
            transcription = await loop.run_in_executor(
                None, self._transcribe_audio, audio_path
            )

        # 2. Extract keyframes (1 frame every 30 seconds) → extract text from slides/charts
        frames = await loop.run_in_executor(
            None, self._extract_keyframes, file_path, duration
        )

        # Combine: audio transcription is the primary text
        text = transcription
        metadata["frame_count"] = len(frames)
        metadata["has_audio_transcription"] = bool(transcription.strip())

        return ParsedDocument(
            text=text,
            metadata=metadata,
            images=frames,
        )

    def _extract_metadata(self, file_path: Path) -> dict:
        """Extract video metadata via ffprobe."""
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
                timeout=60,
            )
            import json
            info = json.loads(result.stdout)

            fmt = info.get("format", {})
            streams = info.get("streams", [])
            video_streams = [
                s for s in streams if s.get("codec_type") == "video"
            ]
            audio_streams = [
                s for s in streams if s.get("codec_type") == "audio"
            ]

            metadata = {
                "duration_seconds": float(fmt.get("duration", 0)),
                "format_name": fmt.get("format_name", "unknown"),
                "bitrate_bps": int(fmt.get("bit_rate", 0)),
                "size_bytes": int(fmt.get("size", 0)),
                "has_audio": len(audio_streams) > 0,
                "video_codec": (
                    video_streams[0].get("codec_name", "unknown")
                    if video_streams
                    else "unknown"
                ),
                "width": (
                    int(video_streams[0].get("width", 0))
                    if video_streams
                    else 0
                ),
                "height": (
                    int(video_streams[0].get("height", 0))
                    if video_streams
                    else 0
                ),
                "fps": self._parse_fps(
                    video_streams[0].get("r_frame_rate", "0/1")
                    if video_streams
                    else "0/1"
                ),
            }

            tags = fmt.get("tags", {})
            if tags:
                metadata["tags"] = tags

            return metadata
        except Exception:
            return {"error": "metadata_extraction_failed"}

    @staticmethod
    def _parse_fps(frame_rate: str) -> float:
        """Parse '30000/1001' → 29.97."""
        try:
            num, den = frame_rate.split("/")
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return 0.0

    def _extract_audio(
        self, file_path: Path, duration: float
    ) -> Path | None:
        """Extract audio track to a temp WAV file."""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", str(file_path),
                    "-t", str(duration),
                    "-vn",  # No video
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",  # 16kHz for Whisper
                    "-ac", "1",     # Mono
                    "-y",
                    tmp.name,
                ],
                capture_output=True,
                timeout=120,
                check=True,
            )
            return Path(tmp.name)
        except subprocess.CalledProcessError:
            return None

    def _transcribe_audio(self, audio_path: Path) -> str:
        """Transcribe extracted audio with Whisper."""
        try:
            import whisper

            model = whisper.load_model(
                settings.whisper_model, device=settings.whisper_device
            )
            result = model.transcribe(str(audio_path))
            return result["text"]
        except Exception:
            return ""

    def _extract_keyframes(
        self, file_path: Path, duration: float
    ) -> list[Path]:
        """Extract keyframes: 1 frame every 30 seconds, max 20 frames."""
        frames = []
        interval = max(30, duration / 20)  # Aim for ~20 frames max
        timestamps = [
            i for i in range(0, int(duration), int(interval))
        ]

        for ts in timestamps[:20]:
            try:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=f"_t{ts}.jpg", delete=False
                )
                tmp.close()
                subprocess.run(
                    [
                        "ffmpeg",
                        "-ss", str(ts),
                        "-i", str(file_path),
                        "-frames:v", "1",
                        "-q:v", "2",
                        "-y",
                        tmp.name,
                    ],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                frames.append(Path(tmp.name))
            except subprocess.CalledProcessError:
                continue

        return frames

    def can_handle(self, file_path: Path, mime_type: str) -> bool:
        if mime_type in self.supported_mimes:
            return True
        video_exts = {
            ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
            ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".3g2",
            ".ts", ".m2ts", ".mts", ".vob", ".ogv", ".divx",
            ".xvid", ".rm", ".rmvb", ".asf",
        }
        return file_path.suffix.lower() in video_exts
