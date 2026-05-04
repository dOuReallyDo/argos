#!/bin/bash
# ── Argos Quick Deploy — Start API + Cloudflare Tunnel ──
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/python"
ARGOS_DIR="$SCRIPT_DIR"

echo "🚀 Starting Argos RAG deployment..."
echo ""

# 1. Start API server in background
echo "📡 Starting Argos API on port 8000..."
cd "$ARGOS_DIR"
"$VENV" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
echo "   API PID: $API_PID"

# Wait for API to be ready
sleep 3
echo "✅ API ready"

# 2. Start Cloudflare Tunnel (quick — no login needed)
echo ""
echo "🌐 Starting Cloudflare Tunnel..."
cloudflared tunnel --url http://localhost:8000 2>&1 | while read line; do
    echo "$line"
    if echo "$line" | grep -q "trycloudflare.com"; then
        TUNNEL_URL=$(echo "$line" | grep -o 'https://[^ ]*trycloudflare\.com')
        echo ""
        echo "═══════════════════════════════════════════"
        echo "🔗 ARGOS URL: $TUNNEL_URL"
        echo "📋 Login:    $TUNNEL_URL/api/auth/login"
        echo "📚 API Docs: $TUNNEL_URL/docs"
        echo "🔑 Admin:    $TUNNEL_URL/api/auth/token"
        echo "═══════════════════════════════════════════"
        echo ""
    fi
done

# Cleanup on exit
trap "kill $API_PID 2>/dev/null; echo '🛑 Argos stopped'" EXIT
