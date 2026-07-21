#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🛑 Stopping Sutra AI Orchestrator..."
docker compose down

# ── Host bridges — stop with the app ────────────────────────────────────────
# Unload the launchd agents (rendered under scripts/launchd/) so they don't
# linger after the stack is down. unload matches by Label, so the same file
# start.sh loaded is torn down here.
LAUNCHD_DIR="$PROJECT_DIR/scripts/launchd"
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
    "$LAUNCHD_DIR/com.sutra.smart-organizer-bridge.plist" "Smart Organizer bridge"
stop_bridge com.sutra.fleet-worker \
    "$LAUNCHD_DIR/com.sutra.fleet-worker.plist" "Fleet worker"

echo "✅ All services stopped."
