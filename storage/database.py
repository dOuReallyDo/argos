"""Database session factory and engine — SQLite (dev) / PostgreSQL (prod)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from core.logging import logger

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────
_engine = create_async_engine(
    settings.database_url,
    echo=settings.env == "development",
    echo_pool=False,
    pool_size=5,
    max_overflow=10,
)

# ── Session factory ───────────────────────────────────────────
AsyncSessionLocal = sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Lifecycle ─────────────────────────────────────────────────
async def init_db() -> None:
    """Create all tables (safe to call on startup)."""
    from .models import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables initialized")


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    """Dispose engine on shutdown."""
    await _engine.dispose()
    logger.info("Database connections closed")
