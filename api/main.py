"""FastAPI application — main entrypoint for Argos API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from core.config import get_settings
from core.logging import logger
from storage.database import close_db, init_db

from .routes import router
from .oauth import router as oauth_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"Starting Argos API v0.1.0 ({settings.env})")

    # Initialize database
    await init_db()

    # Create data directories
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)

    logger.info(
        f"API ready — {settings.api_host}:{settings.api_port} | "
        f"embedding: {settings.text_embedding_model} | "
        f"storage: {settings.storage_backend}"
    )

    yield

    # Shutdown
    logger.info("Shutting down Argos API")
    await close_db()


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Argos RAG API",
    description="""Modular RAG system for multimodal document ingestion,
    semantic search, encrypted storage, and cross-modal retrieval.

    ## Features
    - 📄 Multimodal ingestion (PDF, Word, images, audio, video, Markdown, text)
    - 🔍 Semantic + hybrid search with Qdrant
    - 🧠 Multi-model embeddings (E5, CLIP, CLAP, Gemini 2 optional)
    - 🔐 AES-256-GCM encryption with Argon2id key derivation
    - 🔗 Source-attributed document tracking
    - 📦 Pluggable storage (local, S3, MinIO)

    ## Authentication
    Get a token from `/api/auth/token` and use it as `Authorization: Bearer <token>`.
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────
app.include_router(router, prefix="/api")
app.include_router(oauth_router, prefix="/api/auth")


# ── Root endpoint ─────────────────────────────────────────────
# ── Root (SPA) ─────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_spa():
    spa_path = Path(__file__).resolve().parent.parent / "ui" / "spa.html"
    if spa_path.exists():
        return HTMLResponse(content=spa_path.read_text())
    return HTMLResponse(content="<h1>Argos API</h1><p>SPA not built. Visit /docs for API.</p>")


@app.get("/api", tags=["System"])
async def root():
    return {
        "name": "Argos RAG",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health",
    }
