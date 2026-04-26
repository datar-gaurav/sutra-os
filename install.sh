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
