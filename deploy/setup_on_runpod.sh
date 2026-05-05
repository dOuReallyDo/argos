#!/bin/bash
set -e
echo "🔧 Setting up Argos on RunPod..."

# Install system deps
apt-get update -qq
apt-get install -y -qq ffmpeg tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng libgl1 redis-server curl > /dev/null 2>&1
echo "✅ System deps"

# Install Qdrant
echo "📦 Installing Qdrant..."
cd /tmp
curl -sL https://github.com/qdrant/qdrant/releases/download/v1.13.0/qdrant-x86_64-unknown-linux-gnu.tar.gz -o qd.tar.gz
tar xzf qd.tar.gz
mv qdrant /usr/local/bin/
mkdir -p /workspace/qdrant_storage

# Start Qdrant
echo "🚀 Starting Qdrant..."
/usr/local/bin/qdrant --storage-path /workspace/qdrant_storage &
sleep 4
echo "✅ Qdrant ready"

# Start Redis
echo "🚀 Starting Redis..."
redis-server --daemonize yes
echo "✅ Redis ready"

# Clone and install Argos
echo "📦 Installing Argos..."
cd /workspace
git clone https://github.com/doureallydo/argos.git 2>/dev/null || (cd argos && git pull)
cd argos
pip install -e "." --quiet 2>&1 | tail -3

# Generate keys
export ENCRYPTION_KEY=$(openssl rand -hex 32)
export JWT_SECRET_KEY=$(openssl rand -hex 64)
export ARGOS_ENV=production
export QDRANT_URL=http://localhost:6333
export REDIS_URL=redis://localhost:6379/0
export EMBEDDING_DEVICE=cuda
export WHISPER_DEVICE=cuda

# Initialize DB
python -c "import asyncio; from storage.database import init_db; asyncio.run(init_db())" 2>/dev/null
echo "✅ DB ready"

# Start Argos API
echo "🚀 Starting Argos API..."
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
