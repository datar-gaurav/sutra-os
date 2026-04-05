#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🔄 Restarting Sutra AI Orchestrator..."
docker compose down
docker compose up -d

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║       ⚡ Sutra AI Orchestrator ⚡         ║"
echo "  ╠═══════════════════════════════════════════╣"
echo "  ║  Backend API   → http://localhost:8000    ║"
echo "  ║  Frontend      → http://localhost:3001    ║"
echo "  ║  API Docs      → http://localhost:8000/docs║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1 | grep -v WARN
