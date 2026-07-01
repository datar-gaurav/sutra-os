#!/bin/bash
set -e

# ════════════════════════════════════════════════
#  Sutra OS — First-Time Setup
#  Run once after cloning to configure and launch
#  Usage: ./install.sh
# ════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── Colours ──────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✔${RESET}  $*"; }
info() { echo -e "${CYAN}ℹ${RESET}  $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✘${RESET}  $*"; exit 1; }
ask()  { echo -e "${BOLD}$*${RESET}"; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║        Sutra OS — First-Time Setup       ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Prerequisites ─────────────────────────────

info "Checking prerequisites..."

# Docker
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed. Get it at https://docs.docker.com/get-docker/"
fi
ok "Docker found: $(docker --version | awk '{print $3}' | tr -d ',')"

# Docker Compose (v2 plugin or standalone)
if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose found: $(docker compose version --short 2>/dev/null || echo 'v2')"
elif command -v docker-compose &>/dev/null; then
    warn "Using legacy docker-compose — consider upgrading to Docker Compose v2"
    COMPOSE_CMD="docker-compose"
else
    fail "Docker Compose is not installed. Get it at https://docs.docker.com/compose/install/"
fi
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"

# Docker daemon running?
if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon is not running. Please start Docker Desktop (or the Docker service) and try again."
fi
ok "Docker daemon is running"

echo ""

# ── 2. Environment file setup ────────────────────

ENV_FILE="$PROJECT_DIR/backend/.env"

if [ -f "$ENV_FILE" ]; then
    warn "backend/.env already exists."
    read -rp "   Overwrite it with a fresh copy from .env.example? [y/N] " overwrite
    if [[ "$overwrite" =~ ^[Yy]$ ]]; then
        cp backend/.env.example "$ENV_FILE"
        ok "backend/.env reset from .env.example"
    else
        ok "Keeping existing backend/.env"
    fi
else
    cp backend/.env.example "$ENV_FILE"
    ok "Created backend/.env from .env.example"
fi

echo ""

# ── 3. Helper Functions ──────────────────────────

# Updates a key in .env whether it already exists or not
set_env() {
    local key="$1" val="$2"
    if [ -n "$val" ]; then
        if grep -q "^${key}=" "$ENV_FILE"; then
            local tmp
            tmp="$(mktemp)"
            sed "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" > "$tmp" && mv "$tmp" "$ENV_FILE"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    fi
}

# ── 4. Generate SECRET_KEY + ENCRYPTION_KEY ─────

# ── Enable debug mode for local development ────
set_env "DEBUG" "true"
ok "DEBUG=true (local development mode)"

EXISTING_SECRET=$(grep "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_SECRET" ]; then
    # Try openssl first, then python3, then fail hard — the app requires a key
    if command -v openssl &>/dev/null; then
        SECRET=$(openssl rand -hex 32)
    elif command -v python3 &>/dev/null; then
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || true)
    fi
    if [ -n "$SECRET" ]; then
        set_env "SECRET_KEY" "$SECRET"
        ok "Generated a secure SECRET_KEY"
    else
        fail "Could not generate SECRET_KEY — install openssl or python3 and try again."
    fi
else
    ok "SECRET_KEY already set — keeping existing value"
fi

EXISTING_ENC_KEY=$(grep "^ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_ENC_KEY" ]; then
    # Try python3 first (produces a valid Fernet key directly)
    ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
    if [ -z "$ENC_KEY" ] && command -v python3 &>/dev/null; then
        # cryptography not installed locally — generate via base64(32 random bytes)
        ENC_KEY=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" 2>/dev/null || true)
    fi
    if [ -z "$ENC_KEY" ] && command -v openssl &>/dev/null; then
        # Last resort: openssl — pad to 32 bytes then url-safe base64 encode
        ENC_KEY=$(openssl rand 32 | base64 | tr '+/' '-_' | tr -d '=')
        # Fernet requires exactly 44 chars of url-safe base64 (32 bytes + padding)
        ENC_KEY=$(python3 -c "import base64; raw=base64.urlsafe_b64decode('${ENC_KEY}'+'=='); print(base64.urlsafe_b64encode(raw[:32]).decode())" 2>/dev/null || true)
    fi
    if [ -n "$ENC_KEY" ]; then
        set_env "ENCRYPTION_KEY" "$ENC_KEY"
        ok "Generated a secure ENCRYPTION_KEY"
    else
        warn "Could not generate ENCRYPTION_KEY — encrypted secrets won't survive restarts."
        info "Set it later: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    fi
else
    ok "ENCRYPTION_KEY already set — keeping existing value (preserves encrypted secrets)"
fi

echo ""

# ── 4b. Dispatcher bridge config ─────────────────

info "Configuring Dispatcher bridge..."

# Token (generate once, never rotate automatically)
EXISTING_BRIDGE_TOKEN=$(grep "^DISPATCHER_BRIDGE_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_BRIDGE_TOKEN" ]; then
    BRIDGE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || true)
    if [ -n "$BRIDGE_TOKEN" ]; then
        set_env "DISPATCHER_BRIDGE_TOKEN" "$BRIDGE_TOKEN"
        ok "Generated DISPATCHER_BRIDGE_TOKEN"
    else
        warn "Could not generate DISPATCHER_BRIDGE_TOKEN — set it manually in backend/.env"
    fi
else
    ok "DISPATCHER_BRIDGE_TOKEN already set — keeping existing value"
fi

# Port (default 7475, only write if absent)
EXISTING_BRIDGE_PORT=$(grep "^DISPATCHER_BRIDGE_PORT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_BRIDGE_PORT" ]; then
    set_env "DISPATCHER_BRIDGE_PORT" "7475"
    ok "Set DISPATCHER_BRIDGE_PORT=7475"
else
    ok "DISPATCHER_BRIDGE_PORT already set to ${EXISTING_BRIDGE_PORT}"
fi

# Base path (prompt once; re-use existing if already set)
EXISTING_BASE_PATH=$(grep "^DISPATCHER_BASE_PATH=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_BASE_PATH" ]; then
    echo ""
    ask "Enter the absolute path to your runtime_scripts repo on this host:"
    read -rp "   (leave blank to skip and set manually later): " RUNNER_PATH
    if [ -n "$RUNNER_PATH" ]; then
        set_env "DISPATCHER_BASE_PATH" "$RUNNER_PATH"
        ok "Set DISPATCHER_BASE_PATH=${RUNNER_PATH}"
    else
        warn "DISPATCHER_BASE_PATH not set — add it to backend/.env before starting the bridge."
    fi
else
    ok "DISPATCHER_BASE_PATH already set to ${EXISTING_BASE_PATH}"
fi

echo ""

# ── 4b-2. Smart Organizer bridge (macOS mail/reminders/notes) ─────

info "Configuring Smart Organizer bridge..."
echo "    A host daemon (launchd, 127.0.0.1:7477) that reads Apple Mail and"
echo "    writes Reminders/Notes for the smart_organizer extension. The"
echo "    Dockerized backend reaches it via http://host.docker.internal:7477."

# Token (generate once, never rotate automatically)
EXISTING_SO_TOKEN=$(grep "^SMART_ORGANIZER_BRIDGE_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_SO_TOKEN" ]; then
    SO_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || true)
    if [ -n "$SO_TOKEN" ]; then
        set_env "SMART_ORGANIZER_BRIDGE_TOKEN" "$SO_TOKEN"
        ok "Generated SMART_ORGANIZER_BRIDGE_TOKEN"
    else
        warn "Could not generate SMART_ORGANIZER_BRIDGE_TOKEN — set it manually in backend/.env"
    fi
else
    SO_TOKEN="$EXISTING_SO_TOKEN"
    ok "SMART_ORGANIZER_BRIDGE_TOKEN already set — keeping existing value"
fi

# Port (default 7477, only write if absent)
EXISTING_SO_PORT=$(grep "^SMART_ORGANIZER_BRIDGE_PORT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_SO_PORT" ]; then
    set_env "SMART_ORGANIZER_BRIDGE_PORT" "7477"
    ok "Set SMART_ORGANIZER_BRIDGE_PORT=7477"
else
    ok "SMART_ORGANIZER_BRIDGE_PORT already set to ${EXISTING_SO_PORT}"
fi

# Render + optionally load the launchd agent
read -rp "$(echo -e ${BOLD}Enable the Smart Organizer bridge on this host?${RESET}) [y/N] " enable_so
if [[ "$enable_so" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/Library/Logs" "$HOME/Library/LaunchAgents"
    SO_PLIST_TEMPLATE="$PROJECT_DIR/scripts/com.sutra.smart-organizer-bridge.plist"
    SO_PLIST_DEST="$HOME/Library/LaunchAgents/com.sutra.smart-organizer-bridge.plist"
    if [ ! -f "$SO_PLIST_TEMPLATE" ]; then
        warn "plist template missing at $SO_PLIST_TEMPLATE — skipping launchd setup."
    else
        sed \
            -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
            -e "s|__HOME__|$HOME|g" \
            -e "s|__SMART_ORGANIZER_BRIDGE_TOKEN__|${SO_TOKEN:-CHANGE_ME}|g" \
            "$SO_PLIST_TEMPLATE" > "$SO_PLIST_DEST"
        chmod 600 "$SO_PLIST_DEST"   # contains the bridge token
        ok "Wrote $SO_PLIST_DEST"
        echo "    NOTE: grant TWO permissions in System Settings > Privacy & Security:"
        echo "      1. Full Disk Access — add python3 (to read ~/Library/Mail)"
        echo "      2. Automation — approve on first Mail/Reminders/Notes use"
        echo "    Check with: curl -H 'Authorization: Bearer <token>' localhost:7477/health"
        read -rp "$(echo -e ${BOLD}Load the launchd agent now?${RESET}) [y/N] " so_load_now
        if [[ "$so_load_now" =~ ^[Yy]$ ]]; then
            launchctl unload "$SO_PLIST_DEST" 2>/dev/null || true
            if launchctl load "$SO_PLIST_DEST"; then
                ok "Loaded com.sutra.smart-organizer-bridge (daemon on 127.0.0.1:7477)"
            else
                warn "launchctl load failed — load manually: launchctl load $SO_PLIST_DEST"
            fi
        else
            info "Load later with: launchctl load $SO_PLIST_DEST"
        fi
    fi
else
    info "Skipped Smart Organizer bridge — re-run ./install.sh to enable later."
fi

echo ""

# ── 4c. Sutra Fleet (cross-repo automation) ─────

info "Configuring Sutra Fleet (Gemini-CLI host worker)..."
echo "    Fleet automates fixes across multiple repos: a Gemini CLI daemon"
echo "    runs on the host (KeepAlive via launchd) listening on 127.0.0.1:7476."
echo "    Sutra triggers it the instant a job is enqueued; a watchdog cron"
echo "    inside sutra re-pokes anything that got stuck."
echo ""

read -rp "$(echo -e ${BOLD}Enable Sutra Fleet on this host?${RESET}) [y/N] " enable_fleet

if [[ "$enable_fleet" =~ ^[Yy]$ ]]; then
    # Token — generate once, reuse on subsequent installs
    EXISTING_FLEET_TOKEN=$(grep "^FLEET_WORKER_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
    if [ -z "$EXISTING_FLEET_TOKEN" ]; then
        FLEET_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || true)
        if [ -z "$FLEET_TOKEN" ]; then
            fail "Could not generate FLEET_WORKER_TOKEN — install python3 and retry."
        fi
        set_env "FLEET_WORKER_TOKEN" "$FLEET_TOKEN"
        ok "Generated FLEET_WORKER_TOKEN"
    else
        FLEET_TOKEN="$EXISTING_FLEET_TOKEN"
        ok "FLEET_WORKER_TOKEN already set — reusing"
    fi

    # Optional: fleet repos list (comma-separated owner/repo)
    EXISTING_FLEET_REPOS=$(grep "^FLEET_REPOS=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
    if [ -z "$EXISTING_FLEET_REPOS" ]; then
        ask "Enter comma-separated repos to triage (e.g. me/proj-a,me/proj-b):"
        read -rp "   (blank to skip and set in Settings UI later): " FLEET_REPOS
        if [ -n "$FLEET_REPOS" ]; then
            set_env "FLEET_REPOS" "$FLEET_REPOS"
            ok "Set FLEET_REPOS=${FLEET_REPOS}"
        else
            warn "FLEET_REPOS empty — triage scheduler will no-op until you set it."
        fi
    else
        ok "FLEET_REPOS already set: ${EXISTING_FLEET_REPOS}"
    fi

    # Need GITHUB_TOKEN — already required for the rest of sutra, but check
    GH_TOKEN_VAL=$(grep "^GITHUB_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
    if [ -z "$GH_TOKEN_VAL" ]; then
        # Try gh's stored token as a fallback
        if command -v gh &>/dev/null && gh auth status &>/dev/null; then
            GH_TOKEN_VAL=$(gh auth token 2>/dev/null || true)
            if [ -n "$GH_TOKEN_VAL" ]; then
                set_env "GITHUB_TOKEN" "$GH_TOKEN_VAL"
                ok "Pulled GITHUB_TOKEN from gh CLI keychain"
            fi
        fi
    fi
    if [ -z "$GH_TOKEN_VAL" ]; then
        warn "GITHUB_TOKEN not set — fleet worker can't clone/push. Set it in backend/.env or run 'gh auth login' before loading the worker."
    fi

    # Host-side dirs
    mkdir -p "$HOME/agent_workspaces"
    ok "Created $HOME/agent_workspaces"
    mkdir -p "$HOME/.gemini-fleet-home"
    ok "Created $HOME/.gemini-fleet-home (isolated HOME for Gemini CLI)"
    mkdir -p "$HOME/Library/Logs"

    # Render the launchd plist
    PLIST_TEMPLATE="$PROJECT_DIR/scripts/com.sutra.fleet-worker.plist"
    PLIST_DEST="$HOME/Library/LaunchAgents/com.sutra.fleet-worker.plist"
    if [ ! -f "$PLIST_TEMPLATE" ]; then
        warn "plist template missing at $PLIST_TEMPLATE — skipping launchd setup."
    else
        mkdir -p "$HOME/Library/LaunchAgents"
        HOSTNAME_SHORT=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
        # Escape sed delimiters in substituted values (token is base64-urlsafe; safe)
        sed \
            -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
            -e "s|__HOME__|$HOME|g" \
            -e "s|__HOSTNAME__|$HOSTNAME_SHORT|g" \
            -e "s|__FLEET_WORKER_TOKEN__|$FLEET_TOKEN|g" \
            -e "s|__GITHUB_TOKEN__|${GH_TOKEN_VAL:-CHANGE_ME}|g" \
            "$PLIST_TEMPLATE" > "$PLIST_DEST"
        chmod 600 "$PLIST_DEST"   # contains the GH + fleet tokens
        ok "Wrote $PLIST_DEST"

        # Check Gemini OAuth has been seated in the isolated HOME
        if [ ! -f "$HOME/.gemini-fleet-home/.gemini/oauth_creds.json" ]; then
            warn "Gemini OAuth not yet set up in fleet HOME."
            info "Run once before loading the worker:"
            echo "      HOME=$HOME/.gemini-fleet-home gemini auth login"
        else
            ok "Gemini OAuth present in fleet HOME"
        fi

        # Offer to load it — don't force, as the user may want to inspect first
        read -rp "$(echo -e ${BOLD}Load the launchd agent now?${RESET}) [y/N] " load_now
        if [[ "$load_now" =~ ^[Yy]$ ]]; then
            launchctl unload "$PLIST_DEST" 2>/dev/null || true
            if launchctl load "$PLIST_DEST"; then
                ok "Loaded com.sutra.fleet-worker (daemon on 127.0.0.1:7476)"
            else
                warn "launchctl load failed — load manually after fixing: launchctl load $PLIST_DEST"
            fi
        else
            info "Load later with: launchctl load $PLIST_DEST"
        fi
    fi
else
    info "Skipped fleet setup — re-run ./install.sh to enable later."
fi

echo ""

# ── 5. Build & start services ────────────────────

echo -e "${BOLD}Building Docker images (this may take a few minutes the first time)...${RESET}"
echo ""
$COMPOSE_CMD build

echo ""
echo -e "${BOLD}Starting services...${RESET}"
$COMPOSE_CMD up -d

echo ""

# ── 6. Wait for backend health ───────────────────

info "Waiting for backend to become healthy..."
MAX_WAIT=120
ELAPSED=0
until curl -sf http://localhost:8000/api/system/health >/dev/null 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        warn "Backend did not respond within ${MAX_WAIT}s."
        info "Check logs with: docker compose logs -f backend"
        break
    fi
    printf "."
    sleep 3
    ELAPSED=$((ELAPSED + 3))
done
echo ""
[ $ELAPSED -lt $MAX_WAIT ] && ok "Backend is healthy"

echo ""

# ── 7. Seed Resume Builder + Critic agents ───────

if [ $ELAPSED -lt $MAX_WAIT ]; then
    info "Seeding Resume Builder + Critic agents..."
    if $COMPOSE_CMD exec -T backend python -m scripts.seed_resume_agent; then
        ok "Resume Builder seeded"
    else
        warn "Resume Builder seed failed — run manually: $COMPOSE_CMD exec backend python -m scripts.seed_resume_agent"
    fi
    if $COMPOSE_CMD exec -T backend python -m scripts.seed_resume_critic; then
        ok "Resume Critic(s) seeded"
    else
        warn "Resume Critic seed failed — run manually: $COMPOSE_CMD exec backend python -m scripts.seed_resume_critic"
    fi
    echo ""
fi

echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║        Sutra OS is ready!                ║${RESET}"
echo -e "${GREEN}${BOLD}╠══════════════════════════════════════════╣${RESET}"
echo -e "${GREEN}${BOLD}║                                          ║${RESET}"
echo -e "${GREEN}${BOLD}║  Frontend   → http://localhost:3001      ║${RESET}"
echo -e "${GREEN}${BOLD}║  Backend    → http://localhost:8000      ║${RESET}"
echo -e "${GREEN}${BOLD}║  API Docs   → http://localhost:8000/docs ║${RESET}"
echo -e "${GREEN}${BOLD}║                                          ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo "  ./stop.sh       — Stop all services"
echo "  ./restart.sh    — Restart all services"
echo "  ./start.sh      — Start without rebuilding"
echo "  docker compose logs -f — Tail live logs"
echo ""
echo -e "${CYAN}Dispatcher bridge (run on host, keeps running in background):${RESET}"
echo "  python3 scripts/dispatcher_bridge.py &"
echo "  See docs/dispatcher.md for launchd/systemd persistence."
echo ""
