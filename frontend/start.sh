#!/bin/bash
set -e

echo "═══════════════════════════════════════════════"
echo "  🎨 Sutra Frontend — Starting Up"
echo "═══════════════════════════════════════════════"

# ── Install dependencies if needed ───────────────
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# ── Wait for backend API ─────────────────────────
echo "⏳ Waiting for backend API..."
BACKEND_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
MAX_RETRIES=30
RETRY=0
until curl -sf "${BACKEND_URL}/api/system/health" > /dev/null 2>&1; do
    RETRY=$((RETRY + 1))
    if [ $RETRY -ge $MAX_RETRIES ]; then
        echo "  ⚠️  Backend not reachable after ${MAX_RETRIES} attempts, starting anyway..."
        break
    fi
    echo "  ⏳ Backend not ready yet... (${RETRY}/${MAX_RETRIES})"
    sleep 3
done

if [ $RETRY -lt $MAX_RETRIES ]; then
    echo "  ✅ Backend is ready"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  ⚡ Starting Sutra Frontend"
echo "  📍 http://0.0.0.0:3001"
echo "═══════════════════════════════════════════════"
echo ""

# ── Start the dev server ─────────────────────────
exec npm run dev -- -H 0.0.0.0 -p 3001
