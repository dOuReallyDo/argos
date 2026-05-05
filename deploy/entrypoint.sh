#!/bin/bash
set -e
echo "🚀 Starting Argos on RunPod GPU..."

# ── 1. Start Qdrant ───────────────────────────────────
echo "📦 Starting Qdrant..."
mkdir -p /app/data/qdrant
/usr/local/bin/qdrant --storage-path /app/data/qdrant &
sleep 3
echo "✅ Qdrant ready"

# ── 2. Start Redis ────────────────────────────────────
echo "📦 Starting Redis..."
redis-server --daemonize yes 2>/dev/null || true
echo "✅ Redis ready"

# ── 3. Configure environment ───────────────────────────
cd /app
[ -z "$ENCRYPTION_KEY" ] && export ENCRYPTION_KEY=$(openssl rand -hex 32)
[ -z "$JWT_SECRET_KEY" ] && export JWT_SECRET_KEY=$(openssl rand -hex 64)
export ARGOS_ENV=production
export QDRANT_URL=http://localhost:6333
export REDIS_URL=redis://localhost:6379/0
export EMBEDDING_DEVICE=cuda
export WHISPER_DEVICE=cuda

# ── 4. Initialize database ─────────────────────────────
python -c "
import asyncio
from storage.database import init_db
asyncio.run(init_db())
" 2>/dev/null
echo "✅ DB ready"

# ── 5. Start Argos API ─────────────────────────────────
echo "🚀 Starting Argos API on port 8000..."
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
