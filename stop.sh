#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Sutra AI Orchestrator..."
docker compose down
echo "✅ All services stopped."
