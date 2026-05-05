#!/bin/bash
# Argos minimal RunPod launcher - installs & starts in <4 min
set -e
exec > /workspace/argos_setup.log 2>&1
echo "=== Argos Setup $(date) ==="

# 1. Quick system deps (only what we absolutely need)
echo "[1/5] System deps..."
apt-get update -qq && apt-get install -y -qq ffmpeg tesseract-ocr libgl1 redis-server curl git 2>/dev/null
echo "OK"

# 2. Qdrant (download binary, no Docker needed)
echo "[2/5] Qdrant..."
curl -sL https://github.com/qdrant/qdrant/releases/download/v1.13.0/qdrant-x86_64-unknown-linux-gnu.tar.gz -o /tmp/qd.tar.gz
cd /tmp && tar xzf qd.tar.gz && mv qdrant /usr/local/bin/
mkdir -p /workspace/qdrant_data
/usr/local/bin/qdrant --storage-path /workspace/qdrant_data & 
sleep 3
echo "OK"

# 3. Redis
echo "[3/5] Redis..."
redis-server --daemonize yes
echo "OK"

# 4. Python deps (minimum for Argos to run)
echo "[4/5] Python deps..."
pip install --quiet --no-cache-dir fastapi uvicorn[standard] qdrant-client pydantic-settings python-multipart loguru pillow aiofiles httpx python-jose passlib argon2-cffi cryptography sqlalchemy aiosqlite 2>/dev/null
echo "OK"

# 5. Clone and launch Argos
echo "[5/5] Argos..."
cd /workspace
git clone https://github.com/doureallydo/argos.git 2>/dev/null || (cd argos && git pull)
cd argos
export ARGOS_ENV=production
export QDRANT_URL=http://localhost:6333
export EMBEDDING_DEVICE=cuda
export ENCRYPTION_KEY=$(openssl rand -hex 32)
export JWT_SECRET_KEY=$(openssl rand -hex 64)
export CORS_ORIGINS='["*"]'
python -c 'import asyncio; from storage.database import init_db; asyncio.run(init_db())' 2>/dev/null
echo "=== Starting API ==="
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
