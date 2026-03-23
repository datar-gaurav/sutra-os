# Sutra — Production Deployment Guide

This document covers every step required to deploy Sutra safely in a production environment. Follow the sections in order.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Server Setup](#2-server-setup)
3. [Generate Security Secrets](#3-generate-security-secrets)
4. [Configure Environment Variables](#4-configure-environment-variables)
   - 4.1 [Post-Deploy Configuration via Settings UI](#41-post-deploy-configuration-via-settings-ui)
5. [Database Setup](#5-database-setup)
6. [Redis Setup](#6-redis-setup)
7. [Docker Compose — Production Overrides](#7-docker-compose--production-overrides)
8. [TLS / HTTPS with a Reverse Proxy](#8-tls--https-with-a-reverse-proxy)
9. [Build and Start Services](#9-build-and-start-services)
10. [Post-Deploy Verification](#10-post-deploy-verification)
11. [Backups](#11-backups)
12. [Monitoring and Alerts](#12-monitoring-and-alerts)
13. [Upgrading](#13-upgrading)
14. [Security Checklist](#14-security-checklist)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Prerequisites

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| Docker | 24+ | With Compose v2 plugin |
| Docker Compose | 2.20+ | `docker compose` (no hyphen) |
| A domain name | — | e.g. `sutra.example.com` |
| SSL certificate | — | Let's Encrypt (Certbot) or cloud-managed |
| Linux server | Ubuntu 22.04+ / Debian 12+ | 2 vCPU, 4 GB RAM minimum |
| Open ports | 80, 443 | 22 for SSH |

---

## 2. Server Setup

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

Clone the repository:

```bash
git clone https://github.com/your-org/sutra.git /opt/sutra
cd /opt/sutra
```

---

## 3. Generate Security Secrets

Run these commands **once** before configuring `.env`. Store the output securely (e.g. in a secrets manager).

### 3.1 SECRET_KEY (JWT signing key)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Example output: a3f1c9e2d7b4083a1e5f2c6d9b8a7e4f...
```

### 3.2 ENCRYPTION_KEY (Fernet key for LLM API keys at rest)

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Example output: abc123XYZ...= (44-char URL-safe base64)
```

> **Critical:** If you lose or rotate `ENCRYPTION_KEY`, all stored LLM provider API keys become unreadable. Back it up securely before deploying.

### 3.3 PostgreSQL password

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

---

## 4. Configure Environment Variables

Sutra uses a **two-layer configuration model**:

| Layer | What goes here | Where it lives |
|-------|---------------|----------------|
| **Bootstrap** | Secrets needed before the DB is reachable | `backend/.env` (4 required keys) |
| **Runtime** | Everything else — API keys, integrations, schedules | **Settings UI → Environment Variables** |

This means your `.env` file is intentionally minimal in production.

### 4a. Create the minimal bootstrap `.env`

```bash
cp backend/.env.example backend/.env  # or create from scratch
```

Edit `backend/.env` — only these values are **required**; everything else can be set in the UI after the server boots:

```dotenv
# ─── Bootstrap Essentials ─────────────────────────────────────────────────────
# These MUST be in .env — they are needed before the database is accessible.

# Required: database connection
DATABASE_URL=postgresql+asyncpg://sutra:<DB_PASSWORD>@db:5432/sutra

# Required: Redis connection
REDIS_URL=redis://:<REDIS_PASSWORD>@redis:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@redis:6379/0
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@redis:6379/1

# Required: JWT signing key (generated in step 3.1)
SECRET_KEY=<generated-hex-64-chars>

# Required: Fernet encryption key for secrets vault (generated in step 3.2)
# WARNING: Never rotate this without re-encrypting all stored secrets.
ENCRYPTION_KEY=<generated-fernet-key>

# ─── Optional overrides (can also be set in Settings UI after boot) ───────────
DEBUG=false
CORS_ORIGINS=https://sutra.example.com
CSP_HEADER=default-src 'none'; frame-ancestors 'none'
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Ollama (if self-hosted, set here; otherwise configure via UI)
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

> **Why only these four?** `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `ENCRYPTION_KEY` must be available at process startup before the database is reachable. Every other setting can be stored in the database and configured via the Settings UI.
>
> **CORS_ORIGINS** and **DEBUG** should also be set in `.env` before first boot so the security startup checks pass.

Set file permissions:

```bash
chmod 600 backend/.env
```

---

### 4.1 Post-Deploy Configuration via Settings UI

After the server is running, all remaining environment variables — API keys, integrations, notification credentials, and scheduled job times — are managed through the Settings page.

Navigate to **`https://sutra.example.com/settings`** → **Environment Variables**.

#### What you can configure in the UI

| Group | Variables |
|-------|-----------|
| **LLM API Keys** | OpenAI, Anthropic, Google, Groq, OpenRouter, Perplexity |
| **Integrations** | GitHub, Slack (bot token, signing secret, app token), Telegram, WhatsApp, Google OAuth |
| **Email (SMTP)** | Host, port, username, password, from address |
| **Scheduler** | Check-in cron, Forge queue cron |
| **Agent Tools** | Allowed file paths |
| **Infrastructure** | Ollama URL, Redis URL (if changed after boot) |

#### Security guarantees

- **Secrets** (any token, password, or API key) are encrypted with AES-256/Fernet before being written to the database — the same `ENCRYPTION_KEY` from your `.env` is used.
- Secret values are **never returned as plaintext** by the API — only a masked hint (`••••••••••••abcd`) is sent to the browser.
- Non-secret values (URLs, cron expressions, chat IDs) are stored as plaintext and displayed in full.
- Values saved in the UI take effect **immediately** and **override** `.env` — no server restart required.
- Each value shows a source badge: **DB** (set via UI) or **.env** (from the file).
- DB-stored values can be cleared to revert to the `.env` fallback.

#### Workflow for adding a new API key

1. Open `Settings → Environment Variables`
2. Find the key (e.g. `GROQ_API_KEY`) in the **LLM API Keys** group
3. Click the input field and type the new key
4. Click the **save icon** (or use **Save N changes** to batch-save)
5. The key is encrypted and stored — immediately available to all agents

> **Tip:** You can leave all integration tokens out of `.env` entirely. Just boot the server with the 4 bootstrap keys, log in, and fill everything else in through the UI.

---


## 5. Database Setup

Sutra uses PostgreSQL. In production, set a strong password and restrict access.

Update `docker-compose.yml` (or use an override file — see section 7) to replace the dev credentials:

```yaml
db:
  environment:
    POSTGRES_USER: sutra
    POSTGRES_PASSWORD: <DB_PASSWORD>   # same as in DATABASE_URL above
    POSTGRES_DB: sutra
```

> For managed databases (AWS RDS, GCP Cloud SQL, Supabase), point `DATABASE_URL` at the managed host instead of the `db` service. Remove the `db` service from docker-compose in that case.

**Database migrations:** Sutra currently uses `create_all` (auto-DDL). Before going fully production, switch to Alembic migrations:

```bash
# Inside the backend container
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

---

## 6. Redis Setup

Redis is used for:
- Celery task broker/backend
- Rate limit counters (slowapi)
- Token blacklist (refresh token revocation)

For production, enable Redis persistence and authentication:

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --requirepass <REDIS_PASSWORD> --appendonly yes
  volumes:
    - redisdata:/data
```

Update `REDIS_URL` in `.env`:

```dotenv
REDIS_URL=redis://:<REDIS_PASSWORD>@redis:6379/0
```

> For managed Redis (ElastiCache, Upstash, Redis Cloud), use the provided connection string.

---

## 7. Docker Compose — Production Overrides

Create a `docker-compose.prod.yml` override that removes dev-only settings:

```yaml
version: "3.9"

services:
  backend:
    command: []                         # Remove --reload flag
    volumes:                            # Remove local bind mounts
      - /opt/sutra/backend/.env:/app/.env:ro
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://sutra:<DB_PASSWORD>@db:5432/sutra
      REDIS_URL: redis://:<REDIS_PASSWORD>@redis:6379/0

  frontend:
    environment:
      NEXT_PUBLIC_API_URL: https://sutra.example.com
      NEXT_PUBLIC_WS_URL: wss://sutra.example.com
    restart: unless-stopped

  db:
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: <DB_PASSWORD>

  redis:
    command: redis-server --requirepass <REDIS_PASSWORD> --appendonly yes
    volumes:
      - redisdata:/data
    restart: unless-stopped

  celery:
    restart: unless-stopped
    command: celery -A app.worker worker --loglevel=warning --concurrency=4

volumes:
  pgdata:
  redisdata:
```

Deploy using both files:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 8. TLS / HTTPS with a Reverse Proxy

**Never** expose the backend or frontend directly on port 80/443 without TLS. Use Nginx or Caddy as a reverse proxy.

### Option A: Caddy (recommended — auto TLS)

```bash
# /etc/caddy/Caddyfile
sutra.example.com {
    reverse_proxy /api/*    localhost:8000
    reverse_proxy /ws       localhost:8000
    reverse_proxy /*        localhost:3001
}
```

```bash
sudo apt install caddy
sudo systemctl enable --now caddy
```

### Option B: Nginx + Certbot

```nginx
# /etc/nginx/sites-available/sutra
server {
    listen 443 ssl http2;
    server_name sutra.example.com;

    ssl_certificate     /etc/letsencrypt/live/sutra.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sutra.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Backend API
    location /api/ {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass         http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
    }

    # SSE (disable buffering for streaming)
    location /api/chat/stream {
        proxy_pass         http://localhost:8000;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_set_header   X-Accel-Buffering no;
    }

    # Frontend
    location / {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
    }
}

server {
    listen 80;
    server_name sutra.example.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo certbot --nginx -d sutra.example.com
sudo systemctl reload nginx
```

---

## 9. Build and Start Services

```bash
cd /opt/sutra

# Pull latest code
git pull origin master

# Build all images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# Start all services (detached)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Watch startup logs
docker compose logs -f backend
```

Expected healthy startup output:

```
INFO  | app.main | 🚀 Starting Sutra AI Orchestrator...
INFO  | app.main | Security startup checks passed.
INFO  | app.main | ✅ Database tables created/verified.
INFO  | app.main | ✅ APScheduler started.
INFO  | app.main | ✅ Agent and MCP restoration complete.
```

> If you see `SECURITY VIOLATION` lines and the server refuses to start, check your `.env` — the startup checks are strict in production (`DEBUG=false`).

---

## 10. Post-Deploy Verification

Run through this checklist after every deploy:

```bash
# 1. All containers healthy
docker compose ps

# 2. Health endpoint
curl -s https://sutra.example.com/api/system/health | python3 -m json.tool

# 3. Verify security headers are present
curl -sI https://sutra.example.com/api/system/health | grep -E "X-Frame|X-Content|CSP|Strict"

# 4. Verify CORS rejects unknown origins
curl -s -H "Origin: https://evil.com" -I https://sutra.example.com/api/system/health
# Should NOT include Access-Control-Allow-Origin: https://evil.com

# 5. Register the first (owner) user via the UI
open https://sutra.example.com/login

# 6. Confirm the first user receives the "owner" role
```

---

## 11. Backups

### PostgreSQL

```bash
# Daily backup script — add to cron
docker exec sutra-db-1 pg_dump -U sutra sutra | gzip > /backups/sutra-$(date +%F).sql.gz

# Restore
gunzip -c /backups/sutra-2026-03-10.sql.gz | docker exec -i sutra-db-1 psql -U sutra sutra
```

### Encryption Key

Back up `ENCRYPTION_KEY` separately from the database. Without it, all stored LLM API keys are permanently unreadable. Store it in:
- A secrets manager (AWS Secrets Manager, HashiCorp Vault, Doppler)
- An encrypted password manager (1Password, Bitwarden)

### Redis

Redis is used for ephemeral data (rate limits, token blacklist) — it does not need long-term backup. AOF persistence (`--appendonly yes`) is sufficient for restarts.

---

## 12. Monitoring and Alerts

Sutra exposes built-in monitoring endpoints (requires authentication):

| Endpoint | Description |
|----------|-------------|
| `GET /api/system/health` | Service health (DB, Redis, Ollama) |
| `GET /api/monitor/metrics` | Today's token usage, request counts |
| `GET /api/monitor/alerts` | Active quota/error/failure alerts |
| `GET /api/traces/agent/{id}` | Per-agent execution traces |
| `GET /api/audit/` | Audit log (auth events, agent changes) |

### Recommended: External Uptime Monitoring

Set up an uptime check on `https://sutra.example.com/api/system/health` using:
- UptimeRobot (free)
- Better Uptime
- AWS CloudWatch Synthetics

### Log Aggregation

Backend logs are structured (JSON-friendly with `rid=` correlation IDs). Pipe to:

```bash
# Example: ship to a log aggregator
docker compose logs -f backend | your-log-shipper
```

---

## 13. Upgrading

```bash
cd /opt/sutra

# 1. Pull latest code
git pull origin master

# 2. Review CHANGELOG for breaking changes

# 3. Rebuild images
docker compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Rolling restart (backend first, then frontend)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps frontend

# 5. Verify health
curl -s https://sutra.example.com/api/system/health
```

---

## 14. Security Checklist

Go through this before going live and after every major change:

### Secrets
- [ ] `SECRET_KEY` is at least 64 hex chars and unique to this deployment
- [ ] `ENCRYPTION_KEY` is a valid Fernet key, backed up securely
- [ ] `ENCRYPTION_KEY` is **not** the same as `SECRET_KEY`
- [ ] Database password is strong and not the default `sutra_dev`
- [ ] Redis password is set (`--requirepass`)
- [ ] `.env` file has `chmod 600` permissions
- [ ] No secrets are committed to git

### Network
- [ ] Backend port 8000 is **not** exposed directly to the internet (reverse proxy only)
- [ ] PostgreSQL port 5432 is **not** exposed to the internet
- [ ] Redis port 6379 is **not** exposed to the internet
- [ ] TLS 1.2+ is enforced; TLS 1.0/1.1 disabled
- [ ] HSTS header is present (`Strict-Transport-Security`)

### Application
- [ ] `DEBUG=false` in production `.env`
- [ ] `CORS_ORIGINS` contains only your actual frontend domain
- [ ] Startup security checks pass with no violations in logs
- [ ] First registered account has `owner` role — register it immediately after deploy
- [ ] LLM API keys, integration tokens, and SMTP credentials are configured via **Settings → Environment Variables** (stored AES-256 encrypted in DB)
- [ ] `.env` contains only the 4 bootstrap keys (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENCRYPTION_KEY`) plus `CORS_ORIGINS`/`DEBUG` — no plaintext API keys or tokens

### Docker
- [ ] `--reload` flag is removed from the backend command
- [ ] Local volume bind mounts (`./backend:/app`) are removed
- [ ] `restart: unless-stopped` is set on all services

---

## 15. Troubleshooting

### Backend won't start — `SECURITY VIOLATION` in logs

```
SECURITY VIOLATION: SECRET_KEY is set to an insecure default value
```

→ `SECRET_KEY` in `.env` is still `change-me-in-production`. Replace it with a generated value (section 3.1).

### Backend won't start — `ModuleNotFoundError`

→ The Docker image is outdated. Run `docker compose build backend` to rebuild with the latest `pyproject.toml`.

### `Failed to decrypt secret — key mismatch`

→ The `ENCRYPTION_KEY` changed since the LLM API keys were stored. Restore the original key from your backup, or re-enter the LLM API keys via the UI (they will be re-encrypted with the new key).

### Rate limit errors (`429 Too Many Requests`) on login

→ You've hit the auth rate limit (20 requests/hour per IP). Wait or temporarily increase `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` to reduce refresh frequency.

### Agents show "stopped" after restart

→ Expected. Agents are in-memory processes. The server automatically attempts to restore agents that had `status=running` in the database at startup. If restoration fails, check backend logs for the agent name and start it manually via the UI.

### CORS errors in browser console

→ Verify `CORS_ORIGINS` in `.env` exactly matches the origin shown in the browser (`https://sutra.example.com` — no trailing slash). Restart the backend after changing.

### WebSocket disconnects frequently

→ Ensure your reverse proxy has a long `proxy_read_timeout` (e.g. `proxy_read_timeout 3600;` in Nginx) and the `Upgrade` / `Connection` headers are forwarded correctly (see section 8).

### Env var change in Settings UI not taking effect

→ For non-secret values (URLs, cron expressions), the backend updates the process environment immediately on save — no restart needed. For secrets, they are read from the encrypted DB store on the next request that uses them (e.g. when an agent makes an LLM call). If a value still seems stale, restart the backend: `docker compose restart backend`.

→ If the UI shows a **`.env`** source badge instead of **DB**, the value has not been saved to the database yet — type it in and click save.

### Re-entering secrets after `ENCRYPTION_KEY` rotation

→ If you rotate `ENCRYPTION_KEY`, all previously encrypted values in the `env_vars` table become unreadable. Clear them by going to **Settings → Environment Variables** and clicking the trash icon on each DB-stored secret, then re-enter them. The new key will be used for the fresh encryptions.
