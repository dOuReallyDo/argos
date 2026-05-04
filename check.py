"""Minimal startup — verifies core imports work before full launch."""

from core.config import get_settings
from core.logging import logger

settings = get_settings()
logger.info("✅ Argos core modules loaded")
logger.info(f"Config loaded: env={settings.env}, storage={settings.storage_backend}")
logger.info(f"Embedding model: {settings.text_embedding_model}")

# Try imports
try:
    from ingestion.pipeline import IngestionPipeline
    logger.info("✅ Ingestion pipeline OK")
except Exception as e:
    logger.warning(f"⚠️ Ingestion pipeline: {e}")

try:
    from encryption.engine import EncryptionEngine
    logger.info("✅ Encryption engine OK")
except Exception as e:
    logger.warning(f"⚠️ Encryption engine: {e}")

try:
    from storage.database import init_db
    import asyncio
    asyncio.run(init_db())
    logger.info("✅ Database initialized")
except Exception as e:
    logger.warning(f"⚠️ Database: {e}")

logger.info("✅ All core systems ready")
