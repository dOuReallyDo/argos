"""Embedding engine — text, image, and audio embeddings with optional Gemini 2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal, Protocol

import numpy as np

from core.config import get_settings
from core.logging import logger

settings = get_settings()


# ── Base Embedder Protocol ────────────────────────────────────

class Embedder(ABC):
    """Base class for all embedding models."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts → (N, dim) array."""
        ...

    @abstractmethod
    async def embed_images(self, image_paths: list[Path]) -> np.ndarray:
        """Embed a list of images → (N, dim) array."""
        ...

    @abstractmethod
    async def embed_audio(self, audio_paths: list[Path]) -> np.ndarray:
        """Embed a list of audio files → (N, dim) array."""
        ...

    @property
    @abstractmethod
    def embedding_dim(self) -> int:
        """Output vector dimensionality."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model."""
        ...


# ── Sentence-Transformers (Text) ───────────────────────────────

class TextEmbedder(Embedder):
    """Text embedding via sentence-transformers (multilingual-e5-large by default).

    Multilingual E5 supports 100+ languages including Italian.
    """

    def __init__(self):
        self._model = None
        self._model_name = settings.text_embedding_model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name, device=settings.embedding_device
            )
        return self._model

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        import asyncio

        # E5 models need "query: " prefix for retrieval, "passage: " for indexing
        prefixed = [f"passage: {t}" for t in texts]

        def _embed():
            model = self._get_model()
            return model.encode(prefixed, normalize_embeddings=True)

        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, _embed)
        return np.array(embeddings, dtype=np.float32)

    async def embed_queries(self, queries: list[str]) -> np.ndarray:
        """Embed search queries (uses 'query:' prefix)."""
        prefixed = [f"query: {q}" for q in queries]

        def _embed():
            model = self._get_model()
            return model.encode(prefixed, normalize_embeddings=True)

        import asyncio

        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, _embed)
        return np.array(embeddings, dtype=np.float32)

    async def embed_images(self, image_paths: list[Path]) -> np.ndarray:
        raise NotImplementedError(
            "Text embedder does not support images. Use CLIP or Gemini."
        )

    async def embed_audio(self, audio_paths: list[Path]) -> np.ndarray:
        raise NotImplementedError(
            "Text embedder does not support audio. Use CLAP or Gemini."
        )


# ── CLIP (Image + Text) ────────────────────────────────────────

class CLIPEmbedder(Embedder):
    """Image and text embeddings via OpenAI CLIP (ViT-L/14 by default)."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._model_name = settings.image_embedding_model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        return 768  # ViT-L/14

    def _get_model(self):
        if self._model is None:
            from transformers import CLIPModel, CLIPProcessor

            self._model = CLIPModel.from_pretrained(self._model_name)
            self._processor = CLIPProcessor.from_pretrained(
                self._model_name
            )
            self._model.eval()
        return self._model, self._processor

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        import asyncio

        def _embed():
            import torch

            model, processor = self._get_model()
            inputs = processor(
                text=texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            with torch.no_grad():
                embeddings = model.get_text_features(**inputs)
            # Normalize
            embeddings = embeddings / embeddings.norm(
                dim=-1, keepdim=True
            )
            return embeddings.numpy()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _embed)

    async def embed_images(self, image_paths: list[Path]) -> np.ndarray:
        import asyncio

        from PIL import Image

        def _embed():
            import torch

            model, processor = self._get_model()

            images = [
                Image.open(str(p)).convert("RGB") for p in image_paths
            ]
            inputs = processor(
                images=images,
                return_tensors="pt",
            )
            with torch.no_grad():
                embeddings = model.get_image_features(**inputs)
            embeddings = embeddings / embeddings.norm(
                dim=-1, keepdim=True
            )
            return embeddings.numpy()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _embed)

    async def embed_audio(self, audio_paths: list[Path]) -> np.ndarray:
        raise NotImplementedError(
            "CLIP does not support audio. Use CLAP or Gemini."
        )


# ── CLAP (Audio) ───────────────────────────────────────────────

class CLAPEmbedder(Embedder):
    """Audio embeddings via CLAP (Contrastive Language-Audio Pretraining)."""

    def __init__(self):
        self._model = None
        self._processor = None
        self._model_name = "laion/clap-htsat-unfused"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        return 512  # CLAP default

    def _get_model(self):
        if self._model is None:
            from transformers import ClapModel, ClapProcessor

            self._model = ClapModel.from_pretrained(self._model_name)
            self._processor = ClapProcessor.from_pretrained(
                self._model_name
            )
            self._model.eval()
        return self._model, self._processor

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        import asyncio

        def _embed():
            import torch

            model, processor = self._get_model()
            inputs = processor(
                text=texts,
                return_tensors="pt",
                padding=True,
            )
            with torch.no_grad():
                embeddings = model.get_text_features(**inputs)
            embeddings = embeddings / embeddings.norm(
                dim=-1, keepdim=True
            )
            return embeddings.numpy()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _embed)

    async def embed_images(self, image_paths: list[Path]) -> np.ndarray:
        raise NotImplementedError("CLAP does not support images.")

    async def embed_audio(self, audio_paths: list[Path]) -> np.ndarray:
        import asyncio

        def _embed():
            import torch

            model, processor = self._get_model()
            # CLAP expects 48kHz; ffmpeg can handle conversion, but here we trust the input
            audio_data = []
            sample_rates = []
            import soundfile as sf

            for p in audio_paths:
                audio, sr = sf.read(str(p))
                audio_data.append(audio)
                sample_rates.append(sr)

            inputs = processor(
                audios=audio_data,
                sampling_rates=sample_rates,
                return_tensors="pt",
            )
            with torch.no_grad():
                embeddings = model.get_audio_features(**inputs)
            embeddings = embeddings / embeddings.norm(
                dim=-1, keepdim=True
            )
            return embeddings.numpy()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _embed)


# ── Gemini Embedding 2 (optional, cloud) ───────────────────────

class GeminiEmbedder(Embedder):
    """Google Gemini Embedding 2 — natively multimodal embedding model.

    Requirements:
        - GOOGLE_API_KEY in .env
        - pip install google-genai
        - Costs apply (check Google pricing)

    Capabilities:
        - Text up to 8192 tokens
        - Images up to 6 per request
        - Video up to 120 seconds
        - Audio natively (no intermediate transcription)
        - PDF up to 6 pages
        - Unified 3072-dim embedding space
    """

    def __init__(self):
        self._model_name = "gemini-embedding-2"
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dim(self) -> int:
        return 3072

    def _get_client(self):
        if self._client is None:
            from google import genai

            if not settings.google_api_key:
                raise ValueError(
                    "GOOGLE_API_KEY not set. Add it to your .env file."
                )
            self._client = genai.Client(api_key=settings.google_api_key)
        return self._client

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Embed texts using Gemini Embedding 2.

        ⚠️ Each text is a separate API call. For cost efficiency,
        batch your texts appropriately.
        """
        import asyncio

        client = self._get_client()

        async def _embed_one(text):
            result = await asyncio.to_thread(
                lambda: client.models.embed_content(
                    model=self._model_name,
                    contents=[text],
                )
            )
            return result.embeddings[0].values

        tasks = [_embed_one(t) for t in texts]
        results = await asyncio.gather(*tasks)
        return np.array(results, dtype=np.float32)

    async def embed_images(self, image_paths: list[Path]) -> np.ndarray:
        import asyncio

        from google.genai import types

        client = self._get_client()
        embeddings = []

        for p in image_paths:
            with open(p, "rb") as f:
                image_bytes = f.read()

            parts = [
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            ]
            result = await asyncio.to_thread(
                lambda: client.models.embed_content(
                    model=self._model_name,
                    contents=parts,
                )
            )
            embeddings.append(result.embeddings[0].values)

        return np.array(embeddings, dtype=np.float32)

    async def embed_audio(self, audio_paths: list[Path]) -> np.ndarray:
        import asyncio

        from google.genai import types

        client = self._get_client()
        embeddings = []

        for p in audio_paths:
            with open(p, "rb") as f:
                audio_bytes = f.read()

            parts = [
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
            ]
            result = await asyncio.to_thread(
                lambda: client.models.embed_content(
                    model=self._model_name,
                    contents=parts,
                )
            )
            embeddings.append(result.embeddings[0].values)

        return np.array(embeddings, dtype=np.float32)


# ── Embedding Manager ───────────────────────────────────────────

class EmbeddingManager:
    """Coordinates multi-model embeddings for all modalities.

    Usage:
        manager = EmbeddingManager()
        text_vecs = await manager.embed_texts(["doc1", "doc2"])
        img_vecs = await manager.embed_images([Path("img.jpg")])

        # Switch to Gemini for cross-modal search
        manager.use_gemini()
        vec = await manager.embed_texts(["find this image"])

    Architecture note: all embedders produce normalized vectors
    in the same float32 format, but vector dimensions differ by model.
    Qdrant handles mixed-dimension collections via separate namespaces.
    """

    def __init__(self):
        self._text_embedder: TextEmbedder | None = None
        self._clip_embedder: CLIPEmbedder | None = None
        self._clap_embedder: CLAPEmbedder | None = None
        self._gemini_embedder: GeminiEmbedder | None = None
        self._current: Literal["local", "gemini"] = "local"

    def use_gemini(self) -> None:
        """Switch to Gemini Embedding 2 for all modalities."""
        if not self._gemini_embedder:
            self._gemini_embedder = GeminiEmbedder()
        self._current = "gemini"
        logger.info("Switched to Gemini Embedding 2 (multimodal unified)")

    def use_local(self) -> None:
        """Switch to local models (E5 + CLIP + CLAP)."""
        self._current = "local"
        logger.info("Switched to local embedding models")

    @property
    def active_model(self) -> str:
        if self._current == "gemini":
            return "gemini-embedding-2"
        return "sentence-transformers + CLIP + CLAP"

    @property
    def active_dimension(self) -> int:
        if self._current == "gemini":
            return 3072
        # Dynamically get from text embedder
        return self._get_text().embedding_dim

    async def embed_texts(
        self, texts: list[str], for_query: bool = False
    ) -> np.ndarray:
        """Embed text chunks or search queries."""
        if self._current == "gemini":
            return await self._get_gemini().embed_texts(texts)

        embedder = self._get_text()
        if for_query:
            return await embedder.embed_queries(texts)
        return await embedder.embed_texts(texts)

    async def embed_images(
        self, image_paths: list[Path]
    ) -> np.ndarray:
        """Embed images."""
        if self._current == "gemini":
            return await self._get_gemini().embed_images(image_paths)
        return await self._get_clip().embed_images(image_paths)

    async def embed_audio(
        self, audio_paths: list[Path]
    ) -> np.ndarray:
        """Embed audio files."""
        if self._current == "gemini":
            return await self._get_gemini().embed_audio(audio_paths)
        return await self._get_clap().embed_audio(audio_paths)

    # ── Lazy getters ────────────────────────────────────────────

    def _get_text(self) -> TextEmbedder:
        if self._text_embedder is None:
            self._text_embedder = TextEmbedder()
        return self._text_embedder

    def _get_clip(self) -> CLIPEmbedder:
        if self._clip_embedder is None:
            self._clip_embedder = CLIPEmbedder()
        return self._clip_embedder

    def _get_clap(self) -> CLAPEmbedder:
        if self._clap_embedder is None:
            self._clap_embedder = CLAPEmbedder()
        return self._clap_embedder

    def _get_gemini(self) -> GeminiEmbedder:
        if self._gemini_embedder is None:
            self._gemini_embedder = GeminiEmbedder()
        return self._gemini_embedder


# Singleton for app-wide use
embedding_manager = EmbeddingManager()
