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

# ── 3. Configure API keys ────────────────────────

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

read_key() {
    local prompt="$1" var="$2"
    read -rp "   $prompt: " value
    set_env "$var" "$value"
    if [ -n "$value" ]; then HAS_KEY=true; fi
}

echo -e "${BOLD}LLM API Keys${RESET}"
echo "   Sutra needs at least one LLM provider to run."
echo "   Press Enter to skip any provider you don't have."
echo ""

HAS_KEY=false
read_key "OpenAI API key         (sk-...)" "OPENAI_API_KEY"
read_key "Anthropic API key      (sk-ant-...)" "ANTHROPIC_API_KEY"
read_key "Google Gemini API key" "GOOGLE_API_KEY"
read_key "OpenRouter API key" "OPENROUTER_API_KEY"
read_key "Groq API key" "GROQ_API_KEY"

echo ""

if [ "$HAS_KEY" = false ]; then
    warn "No LLM API key provided."
    info "You can add keys to backend/.env later and run ./restart.sh"
    info "Ollama (local models) works without an API key if configured."
else
    ok "LLM key(s) saved to backend/.env"
fi

echo ""

# ── 4. Generate SECRET_KEY + ENCRYPTION_KEY ─────

EXISTING_SECRET=$(grep "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_SECRET" ]; then
    if command -v openssl &>/dev/null; then
        SECRET=$(openssl rand -hex 32)
        set_env "SECRET_KEY" "$SECRET"
        ok "Generated a secure SECRET_KEY"
    else
        warn "openssl not found — keeping default SECRET_KEY. Change it before production use."
    fi
else
    ok "SECRET_KEY already set — keeping existing value"
fi

EXISTING_ENC_KEY=$(grep "^ENCRYPTION_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
if [ -z "$EXISTING_ENC_KEY" ]; then
    if command -v python3 &>/dev/null; then
        ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
        if [ -n "$ENC_KEY" ]; then
            set_env "ENCRYPTION_KEY" "$ENC_KEY"
            ok "Generated a secure ENCRYPTION_KEY"
        else
            warn "Could not generate ENCRYPTION_KEY — UI-saved secrets won't survive restarts until it is set."
        fi
    else
        warn "python3 not found — ENCRYPTION_KEY not generated. Set it manually in backend/.env."
    fi
else
    ok "ENCRYPTION_KEY already set — keeping existing value (preserves encrypted secrets)"
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
