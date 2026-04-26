#!/bin/bash
set -e

# ════════════════════════════════════════════════
#  Sutra AI Orchestrator — Start (Dev Mode)
#  Usage:
#    ./start_dev.sh          # Start with hot-reload (cached images)
#    ./start_dev.sh --build  # Rebuild images then start
# ════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛠  Starting Sutra AI Orchestrator (development)..."

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

# ── Dispatcher bridge ─────────────────────────────────────────────────────────

ENV_FILE="$PROJECT_DIR/backend/.env"
BRIDGE_TOKEN=$(grep "^DISPATCHER_BRIDGE_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
BRIDGE_PORT=$(grep "^DISPATCHER_BRIDGE_PORT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
BRIDGE_PORT="${BRIDGE_PORT:-7475}"
BRIDGE_LOG="/tmp/dispatcher-bridge.log"

# Kill any existing bridge on the port
EXISTING_PID=$(lsof -ti tcp:"$BRIDGE_PORT" 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "   Stopping existing bridge on port $BRIDGE_PORT (pid $EXISTING_PID)..."
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 1
fi

if [ -n "$BRIDGE_TOKEN" ]; then
    python3 "$PROJECT_DIR/scripts/dispatcher_bridge.py" > "$BRIDGE_LOG" 2>&1 &
    BRIDGE_PID=$!
    sleep 1
    if kill -0 "$BRIDGE_PID" 2>/dev/null; then
        echo "   Dispatcher bridge started (pid $BRIDGE_PID, port $BRIDGE_PORT)"
    else
        echo "   ⚠  Dispatcher bridge failed to start — check $BRIDGE_LOG"
    fi
else
    echo "   ⚠  DISPATCHER_BRIDGE_TOKEN not set — bridge skipped. Run ./install.sh to configure."
fi

# ── Docker services ───────────────────────────────────────────────────────────

# Start with dev overrides (with optional rebuild)
if [ "$1" = "--build" ]; then
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
else
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
fi

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║    🛠  Sutra AI Orchestrator (Dev) 🛠     ║"
echo "  ╠═══════════════════════════════════════════╣"
echo "  ║                                           ║"
echo "  ║  Backend API   → http://localhost:8000    ║"
echo "  ║  API Docs      → http://localhost:8000/docs║"
echo "  ║  Frontend      → http://localhost:3001    ║"
echo "  ║  PostgreSQL    → localhost:5432           ║"
echo "  ║  Redis         → localhost:6379           ║"
echo "  ║                                           ║"
echo "  ║  Backend: hot-reload enabled              ║"
echo "  ║  Frontend: Next.js dev server             ║"
echo "  ║  Dispatcher bridge → localhost:$BRIDGE_PORT        ║"
echo "  ║                                           ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

docker compose -f docker-compose.yml -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1 | grep -v WARN

echo ""
echo "💡 ./stop.sh    — Stop all services"
echo "   ./restart.sh — Restart all services"
echo "   docker compose logs -f — Tail logs"
echo "   tail -f $BRIDGE_LOG — Tail bridge log"
