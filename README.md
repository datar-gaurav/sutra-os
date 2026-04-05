# Sutra

**Open-source AI agent orchestration platform.** Create autonomous organizations where AI agents collaborate, debate, and execute tasks — with humans in the loop.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)

**[Documentation](https://sutra.gauravdatar.com)** · **[Author](https://www.gauravdatar.com)** · **[Community (Facebook Group)](https://www.facebook.com/groups/919745454310655)**

---

## What is Sutra?

Sutra is a full-stack platform for building and managing teams of AI agents. Each agent has a role, tools, memory, and goals — and they can talk to each other, run workflows, and take actions with human approval gates.

**Key capabilities:**

- **Multi-agent discussions** — brainstorm, debate, review, standup, and retro formats where agents collaborate
- **Organizational structure** — roles, teams, org charts, reporting hierarchies, and agent goals
- **Visual workflow builder** — drag-and-drop workflows with 9+ node types including approval gates
- **30+ built-in tools** — GitHub, email, web scraping, RAG/knowledge base, data analysis, Slack, and more
- **Human-in-the-loop governance** — approval queues, risk levels, and budget controls
- **Multi-provider LLM support** — Ollama (local), OpenAI, Anthropic, Google Gemini, Groq, OpenRouter
- **Knowledge base (RAG)** — upload documents, URLs, or text for agent retrieval
- **Agent memory** — three-tier memory system (core, recall, archival) with vector search
- **Streaming chat** — real-time SSE-powered conversations in the browser
- **Self-healing** — automatic retries, circuit breakers, and agent watchdog monitoring
- **Integrations** — Slack, Telegram, WhatsApp, webhooks, MCP servers

## Getting Started

### Option 1: install.sh (Recommended for first-time setup)

The quickest way to go from a fresh clone to a running Sutra. You need [Docker](https://docs.docker.com/get-docker/) installed.

```bash
# 1. Clone the repo
git clone https://github.com/datar-gaurav/sutra-os.git
cd sutra-os

# 2. Run the setup script
./install.sh
```

`install.sh` will:
1. Check that Docker and Docker Compose are installed and running
2. Create `backend/.env` from `.env.example`
3. Prompt you for LLM API keys (OpenAI, Anthropic, Google Gemini, OpenRouter, Groq) — press Enter to skip any
4. Generate a secure `SECRET_KEY`
5. Build Docker images and start all services
6. Wait for the backend to become healthy

Once ready:

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:3001 |
| **Backend API** | http://localhost:8000 |
| **API Docs** | http://localhost:8000/docs |

The first user to register becomes the **owner**. Subsequent users get the **operator** role.

**Useful commands after install:**

```bash
./stop.sh              # Stop all services
./restart.sh           # Restart all services
./start.sh             # Start without rebuilding
docker compose logs -f # Tail logs
```

### Option 2: Docker Compose (manual)

If you've already configured `backend/.env`, you can build and start directly:

```bash
./start.sh --build
```

### Option 3: Local Development

For contributors who want to run services directly.

**Prerequisites:** Python 3.11+, Node.js 20+, PostgreSQL 16+, Redis 7+

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
cp .env.example .env        # Edit .env if your DB/Redis aren't on default ports
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

**Celery worker** (for background jobs):

```bash
cd backend
celery -A app.worker worker --loglevel=info
```

### Adding LLM Providers

Sutra works with local models (Ollama) out of the box. For cloud providers, add API keys in the **Settings** page after logging in, or set them in `backend/.env`:

```bash
# Local models (free)
OLLAMA_BASE_URL=http://localhost:11434

# Cloud providers (optional — add any or all)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
```

## Architecture

```
sutra/
├── backend/                 # FastAPI + LangGraph + SQLAlchemy
│   ├── app/
│   │   ├── api/routes/      # 35+ REST endpoints + WebSocket
│   │   ├── core/            # Orchestrator, agent manager, LLM registry,
│   │   │                    #   memory service, workflow engine, security
│   │   ├── agents/          # LangGraph agent factory (ReAct agents)
│   │   ├── tools/           # 30+ tool modules (GitHub, email, RAG, etc.)
│   │   ├── models/          # SQLAlchemy ORM models (async via asyncpg)
│   │   └── integrations/    # Slack, Telegram, WhatsApp bots
│   └── Dockerfile
├── frontend/                # Next.js 14 App Router + Tailwind CSS
│   ├── app/                 # 30+ pages (dashboard, chat, workflows, org, etc.)
│   ├── components/          # Shared UI components
│   └── lib/                 # Typed API client, WebSocket client
├── docker-compose.yml       # PostgreSQL, Redis, Backend, Frontend, Celery
├── install.sh               # First-time setup: env, API keys, build, launch
├── start.sh / stop.sh       # Convenience scripts
└── docs/                    # Architecture, deployment, and design docs
```

**Tech stack:**

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI, Pydantic, SQLAlchemy (async) |
| Agent framework | LangChain, LangGraph (ReAct agents) |
| Database | PostgreSQL 16 + pgvector |
| Cache / Queue | Redis 7, Celery |
| Frontend | Next.js 14, React 18, Tailwind CSS |
| State management | Zustand + TanStack React Query |
| Workflow UI | React Flow (@xyflow/react) |

**Data flow:**

1. User sends a message in the chat UI
2. `POST /api/chat/{agent_id}` triggers the orchestrator
3. Orchestrator invokes the agent's LangGraph compiled graph
4. Agent calls tools as needed (GitHub, email, scrapers, other agents, etc.)
5. Token usage is tracked per request
6. Streaming tokens are yielded back via SSE

## Features

### Agent Management
Create agents with custom system prompts, assign roles (CEO, Engineer, Marketing, etc.), equip them with tools, and organize them into teams with reporting hierarchies.

### Multi-Agent Discussions
Run structured discussions where multiple agents collaborate — formats include brainstorm, debate, review, standup, and retrospective. Each agent contributes based on their role and expertise.

### Visual Workflows
Build multi-step workflows using a drag-and-drop canvas. Node types include LLM calls, tool execution, conditionals, loops, approval gates, and agent delegation.

### Knowledge Base (RAG)
Upload documents (PDF, text), web URLs, or raw text. Content is chunked, embedded, and stored for retrieval. Agents can search the knowledge base during conversations.

### Human-in-the-Loop
Define approval requirements for high-risk actions. Requests queue in the approval dashboard where humans can approve, reject, or modify before execution proceeds.

### Monitoring & Observability
Execution traces for every agent invocation, audit logs for all mutations, usage metrics by model/agent, and alerting for quota limits and error spikes.

## Configuration

All configuration is done through environment variables (`backend/.env`) or the runtime **Settings** UI after deployment. See [`backend/.env.example`](backend/.env.example) for the full list.

**Required (set automatically by Docker Compose):**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing key |

**Optional:**

| Variable | Description |
|----------|-------------|
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key |
| `SLACK_BOT_TOKEN` | Slack bot integration |

## Production Deployment

See the [Documentation](https://sutra.gauravdatar.com) for the full production deployment guide covering server requirements, TLS/HTTPS, security secrets, backups, and monitoring.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full product roadmap and vision.

## License

[MIT](LICENSE)
