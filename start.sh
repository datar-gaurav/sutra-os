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

# ── Host bridges (macOS launchd agents) — start with the app ────────────────
# Host-only I/O the containers can't do: Smart Organizer (Mail/Reminders/Notes,
# :7477) and the Fleet worker (Gemini CLI, :7476). Rendered plists live in
# scripts/launchd/ (NOT ~/Library/LaunchAgents), so they do NOT auto-start at
# login — their lifecycle is tied to ./start.sh and ./stop.sh. Loaded by full
# path here; KeepAlive restarts them on crash while the app is up.
LAUNCHD_DIR="$PROJECT_DIR/scripts/launchd"
start_bridge() {
    # $1=label  $2=plist  $3=health-url  $4=name  $5=logpath
    local label="$1" plist="$2" url="$3" name="$4" log="$5"
    [ -f "$plist" ] || return 0
    launchctl list 2>/dev/null | grep -q "$label" || launchctl load "$plist" 2>/dev/null || true
    local up=""
    for _ in 1 2 3 4 5; do
        # any HTTP reply (200 or 401) means the daemon is reachable
        if curl -s -m 2 -o /dev/null "$url"; then up=1; break; fi
        sleep 1
    done
    if [ -n "$up" ]; then
        echo "🔌 $name: online at ${url%/health}  (logs: $log)"
    else
        echo "🔌 $name: loaded but not responding at $url — tail: tail -f $log"
    fi
}

echo ""
start_bridge com.sutra.smart-organizer-bridge \
    "$LAUNCHD_DIR/com.sutra.smart-organizer-bridge.plist" \
    "http://127.0.0.1:7477/health" "Smart Organizer bridge" "~/Library/Logs/sutra-smart-organizer.log"

# Fleet worker (only if user opted in during install)
FLEET_PLIST="$LAUNCHD_DIR/com.sutra.fleet-worker.plist"
if [ -f "$FLEET_PLIST" ]; then
    start_bridge com.sutra.fleet-worker "$FLEET_PLIST" \
        "http://127.0.0.1:7476/health" "Fleet worker" "~/Library/Logs/sutra-fleet.log"
    if [ ! -f "$HOME/.gemini-fleet-home/.gemini/oauth_creds.json" ]; then
        echo "                    ⚠  Gemini OAuth missing — run:"
        echo "                       HOME=$HOME/.gemini-fleet-home gemini auth login"
    fi
fi

echo ""
echo "💡 ./stop.sh    — Stop all services"
echo "   ./restart.sh — Restart all services"
echo "   docker compose logs -f — Tail logs"
