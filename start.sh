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

echo "🚀 Starting Sutra AI Orchestrator..."

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

echo ""
echo "💡 ./stop.sh    — Stop all services"
echo "   ./restart.sh — Restart all services"
echo "   docker compose logs -f — Tail logs"
