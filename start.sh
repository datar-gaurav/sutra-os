#!/bin/bash
set -e

# ════════════════════════════════════════════════
#  Sutra AI Orchestrator — Start
#  Usage:
#    ./start.sh          # Start (using cached images)
#    ./start.sh --build  # Rebuild images then start
# ════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Starting Sutra AI Orchestrator (production)..."

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Create .env if missing
if [ ! -f backend/.env ]; then
    echo "📝 Creating backend/.env from .env.example..."
    cp backend/.env.example backend/.env
fi

# Render host-path bind mounts (docker-compose.override.yml) from ALLOWED_AGENT_FILE_PATHS
scripts/render-host-mounts.sh

# Start (with optional rebuild)
if [ "$1" = "--build" ]; then
    docker compose up --build -d
else
    docker compose up -d
fi

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║       ⚡ Sutra AI Orchestrator ⚡         ║"
echo "  ╠═══════════════════════════════════════════╣"
echo "  ║                                           ║"
echo "  ║  Backend API   → http://localhost:8000    ║"
echo "  ║  API Docs      → http://localhost:8000/docs║"
echo "  ║  Frontend      → http://localhost:3001    ║"
echo "  ║  PostgreSQL    → localhost:5432           ║"
echo "  ║  Redis         → localhost:6379           ║"
echo "  ║                                           ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1 | grep -v WARN

# Fleet worker status (only if user opted in during install)
PLIST_DEST="$HOME/Library/LaunchAgents/com.sutra.fleet-worker.plist"
if [ -f "$PLIST_DEST" ]; then
    echo ""
    if launchctl list 2>/dev/null | grep -q com.sutra.fleet-worker; then
        # Probe the daemon — KeepAlive should have it up on :7476
        if curl -sf -m 2 http://127.0.0.1:7476/health >/dev/null 2>&1; then
            echo "🛰  Fleet worker:    online at http://127.0.0.1:7476  (logs: ~/Library/Logs/sutra-fleet.log)"
        else
            echo "🛰  Fleet worker:    launchd job loaded but daemon not responding on :7476"
            echo "                    Tail logs: tail -f ~/Library/Logs/sutra-fleet.log"
        fi
    else
        echo "🛰  Fleet worker:    plist present but NOT loaded. Load with:"
        echo "                    launchctl load $PLIST_DEST"
    fi
    if [ ! -f "$HOME/.gemini-fleet-home/.gemini/oauth_creds.json" ]; then
        echo "                    ⚠  Gemini OAuth missing — run:"
        echo "                       HOME=$HOME/.gemini-fleet-home gemini auth login"
    fi
fi

echo ""
echo "💡 ./stop.sh    — Stop all services"
echo "   ./restart.sh — Restart all services"
echo "   docker compose logs -f — Tail logs"
