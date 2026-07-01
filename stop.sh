#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Sutra AI Orchestrator..."
docker compose down

# ── Host bridges — stop with the app ────────────────────────────────────────
# Unload the launchd agents so they don't linger after the stack is down.
stop_bridge() {
    # $1=label  $2=plist  $3=name
    local plist="$2"
    [ -f "$plist" ] || return 0
    if launchctl list 2>/dev/null | grep -q "$1"; then
        launchctl unload "$plist" 2>/dev/null || true
        echo "🔌 $3 stopped."
    fi
}
stop_bridge com.sutra.smart-organizer-bridge \
    "$HOME/Library/LaunchAgents/com.sutra.smart-organizer-bridge.plist" "Smart Organizer bridge"
stop_bridge com.sutra.fleet-worker \
    "$HOME/Library/LaunchAgents/com.sutra.fleet-worker.plist" "Fleet worker"

echo "✅ All services stopped."
