# Sutra: Autonomous Organization Platform

## Vision Statement

**Build the world's most capable AI agent orchestration platform that enables fully autonomous organizations — where AI agents create, delegate, collaborate, and execute across every business function, with humans providing strategic oversight and final approvals.**

Sutra is not just another agent framework. It is an **organizational operating system** where agents form teams, hold discussions, make decisions, manage budgets, engage customers, and run day-to-day operations — all transparently documented and auditable.

---

## Strategic Objectives

### 1. Autonomous Organizational Intelligence
Agents don't just respond — they **proactively plan, prioritize, and execute**. A CEO agent sets strategy. A PM agent breaks it into tasks. Engineering agents build. Marketing agents promote. Finance agents track spend. All coordinated, all accountable.

### 2. Multi-Agent Deliberation & Consensus
Agents hold structured discussions — brainstorms, debates, reviews, retrospectives. They challenge each other's assumptions, synthesize ideas, and reach consensus before acting. Not just delegation chains, but genuine collaborative reasoning.

### 3. Human-in-the-Loop Governance
Every consequential action (financial, public-facing, destructive) requires human approval. The system surfaces decisions clearly, provides full context, and makes review effortless. Humans steer; agents execute.

### 4. Radical Transparency & Auditability
Every decision, discussion, task, and action is logged, searchable, and reviewable. The organization's entire operational history is a queryable knowledge base. No black boxes.

### 5. Platform Security & Trust
Enterprise-grade security: RBAC, encrypted secrets, sandboxed execution, audit trails, anomaly detection. Agents operate within defined boundaries with clear permission models.

---

## Current State Assessment

### What Sutra Has Today (Strong Foundation)
- Multi-provider LLM abstraction (7 providers) with **purpose-based smart routing & automatic fallback**
- Agent lifecycle management (start/stop/restart, auto-restore)
- Inter-agent communication (ask_agent, control_agent) + org chart
- Tool system with 30+ tools (OS, data, GitHub, scraping, email, RAG, MCP, webhooks)
- Streaming chat (SSE) + WebSocket real-time updates
- Visual workflow builder (React Flow) with conditional/parallel/approval/loop nodes
- Scheduled jobs (cron) with notifications + **Batch Jobs (heartbeat groups)**
- Chat integrations (Slack, Telegram, WhatsApp)
- Usage tracking with per-model rate limits (RPM/RPD/TPM/TPD) + Redis real-time counters + full financial dashboards + budgets
- MCP server integration for extensible tooling
- JWT auth + RBAC + Google OAuth + API key management
- Agent memory (pgvector), RAG pipeline, shared knowledge base
- Multi-agent discussions (brainstorm, debate, review, standup, retro)
- Human-in-the-loop approval system with multi-channel notifications
- Agent goals, check-ins, initiatives, triggers (proactive autonomy)
- Role system, team structure, org chart visualization
- Agent factory + 11 builtin templates + dynamic agent creation tools
- Skill system (attach/detach, role-skill binding, builtin skill library)
- Observability: structured logs, execution traces, audit log, performance metrics
- Security: rate limiting, input guardrails, Fernet secret encryption, security headers
- Social Pulse (trending topic monitoring), Forge (autonomous PR agent)
- Clean architecture (FastAPI + LangGraph + Next.js 14 App Router)

### Remaining Gaps
| Gap | Impact | Planned Phase |
|-----|--------|---------------|
| No tool sandboxing | OS tools run in host process; security risk | 5.6 |
| No per-agent permission scopes | Any agent can use any tool it has enabled | 5.6 |
| No social media posting | Can monitor trends but can't post | 5.5 |
| No skill versioning / conflict detection | Skill composition is manual and unguarded | 3.5 |
| No multi-org / federation | Single-tenant only | 4.3 |
| No organizational learning / playbook gen | Outcomes not linked back to process improvement | 5.3 |
| ~~No self-healing / error recovery~~ | ~~Tool failures crash agent; no retries or circuit breakers~~ | ✅ Done |
| Memory not vectorized | JSON embeddings; O(n) search; no decay or consolidation | 5.1 |
| No browser automation | Agents can scrape but can't interact with websites | 5.7 |
| No prompt optimization | Static system prompts; no A/B testing or success tracking | 5.3 |
| No durable workflow execution | Workflows fail completely on crash; no checkpointing | 5.2 |
| ~~No LLM response caching~~ | ~~Identical prompts re-invoke LLM every time~~ | ✅ Done |

---

## Product Roadmap

### Phase 0: Foundation Hardening (Weeks 1-3)
*Secure the base before building up.*

#### 0.1 Authentication & Authorization ✅
- [x] JWT-based authentication (login/register/refresh)
- [x] Role-Based Access Control (RBAC): Owner, Admin, Operator, Viewer
- [x] API key management for programmatic access
- [x] Session management with secure token rotation
- [x] Google OAuth 2.0 (Gmail integration, email draft tool)
- [ ] Per-agent permission scopes (which tools an agent can use, which agents it can talk to)

#### 0.2 Agent Memory & Context ✅
- [x] **Short-term memory**: Conversation window with smart summarization
- [x] **Long-term memory**: Vector store integration (pgvector initially, Pinecone/Weaviate optional)
- [x] **Episodic memory**: Key events, decisions, outcomes stored as retrievable facts
- [x] **Shared memory**: Organization-wide knowledge base accessible to all agents
- [x] Memory management UI (view, search, delete memories)

#### 0.3 Observability & Logging ✅
- [x] Structured logging with correlation IDs (request → agent → tool chain)
- [x] Agent execution traces (LangSmith-compatible format)
- [x] Performance metrics (latency, token usage, error rates per agent)
- [x] Health dashboard with alerts (agent failures, quota exhaustion, unusual patterns)
- [x] Audit log for all state-changing operations

#### 0.4 Security Hardening ✅
- [ ] Tool sandboxing (Docker-based execution for OS tools)
- [x] Input/output guardrails (content filtering, PII detection)
- [x] Secret management (HashiCorp Vault integration or encrypted DB with rotation)
- [x] Rate limiting per agent and per user
- [ ] Network isolation for agent-to-external communications

---

### Phase 1: Organizational Intelligence (Weeks 4-8)
*Give agents the ability to think, plan, and work as a team.*

#### 1.1 Task & Project Management System ✅
- [x] **Task model**: title, description, status, priority, assignee (agent or human), parent task, dependencies, due date, artifacts, discussion thread
- [x] **Project model**: collection of tasks with milestones and status tracking
- [x] **Board views**: Kanban, list, timeline (Gantt)
- [x] **Auto-assignment**: Agents can create tasks and assign to other agents or flag for human assignment
- [x] **Progress tracking**: Agents update task status as they work; humans see real-time progress
- [x] **Task decomposition**: Given a high-level goal, a planning agent breaks it into subtasks automatically

#### 1.2 Multi-Agent Discussion Framework ✅
- [x] **Discussion rooms**: Named channels where multiple agents participate
- [x] **Discussion types**:
  - **Brainstorm**: All agents contribute ideas, then synthesize
  - **Debate**: Agents argue for/against with structured rounds
  - **Review**: One agent presents, others critique
  - **Standup**: Each agent reports status, blockers, plans
  - **Retrospective**: Analyze what worked, what didn't
- [x] **Moderation**: A designated moderator agent (or human) guides the discussion
- [x] **Consensus protocol**: Voting, weighted scoring, or moderator decision
- [x] **Discussion artifacts**: Auto-generated summaries, action items, decisions log
- [x] **Human participation**: Humans can join discussions, override, or just observe

#### 1.3 Advanced Workflow Engine ✅
- [x] **New node types**:
  - Conditional (if/else based on output)
  - Loop (repeat until condition)
  - Parallel (fan-out/fan-in)
  - Human Approval Gate (pause until human approves)
  - Discussion (trigger multi-agent discussion)
  - Task Creation (create and assign tasks)
  - Notification (alert stakeholders)
  - Timer/Delay (wait for duration or schedule)
  - Code/Script (run arbitrary code in sandbox)
- [x] **Error handling**: Per-node retry policies, fallback paths, error notification
- [x] **Workflow templates**: Pre-built templates for common organizational patterns
- [x] **Sub-workflows**: Compose workflows from reusable sub-workflows
- [x] **Execution history**: Full audit trail with node-by-node results and timing

#### 1.4 Agent Roles & Organizational Structure ✅
- [x] **Role system**: Predefined roles (CEO, PM, Engineer, Marketing, Finance, HR, Security, etc.)
- [x] **Role templates**: Pre-configured system prompts, tools, and permissions per role
- [x] **Org chart**: Visual hierarchy showing reporting lines and communication paths
- [x] **Team composition**: Group agents into teams with shared context
- [x] **Capability matching**: Route tasks to agents based on their role, skills, and current workload

---

### Phase 2: Autonomous Operations (Weeks 9-14)
*Enable the organization to run itself.*

#### 2.1 Proactive Agent Behavior ✅
- [x] **Goal-driven agents**: Agents have persistent goals they work toward, not just reactive responses
- [x] **Scheduled check-ins**: Agents periodically review their goals, tasks, and environment
- [x] **Event-driven triggers**: Agents react to external events (webhook, email, calendar, file changes)
- [x] **Self-monitoring**: Agents detect when they're stuck and escalate or pivot
- [x] **Initiative system**: Agents can propose new tasks/projects; queued for human review

#### 2.2 Human-in-the-Loop Approval System ✅
- [x] **Approval queue**: Centralized dashboard for pending human decisions
- [x] **Approval categories**: Financial, External (public communications), Destructive (deletions, deployments), Strategic (new initiatives), General
- [x] **Context packaging**: Each approval request includes full reasoning chain, alternatives considered, risk assessment, and recommended action
- [x] **Approval channels**: Web UI with real-time WebSocket push notifications
- [x] **Delegation rules**: Risk-level sorting (critical → high → medium → low); expiry with auto-expire background job
- [x] **SLA tracking**: Per-request expiry countdown timer with auto-expiry after configurable minutes
- [x] **Approval audit trail**: Who approved what, when, with what context
- [x] **Agent tool**: `request_approval` tool agents can call to pause and submit for human review
- [x] **Action execution**: Deferred action (action_payload) executed automatically on approval

#### 2.3 Financial Management ✅
- [x] **Budget system**: Per-agent, per-team, and org-wide budgets with daily/weekly/monthly periods
- [x] **Cost tracking**: Real-time token-based cost attribution per agent and provider/model (stored in ExecutionTrace)
- [x] **Model pricing**: Built-in pricing defaults for 20+ models (OpenAI, Anthropic, Google, Groq); overrideable via UI
- [x] **Financial reports**: Period breakdowns (today/week/month/all-time) by agent and provider
- [x] **Spend trends**: 30-day daily cost chart
- [x] **Alerts**: Budget threshold warnings and over-budget alerts surfaced in UI banner
- [x] **Token capture**: UsageCallbackHandler now captures token counts from LLM responses via on_llm_end

#### 2.4 Dynamic Agent Creation & Management ✅
- [x] **Agent factory**: Agents can call `create_agent_from_template`, `list_agent_templates`, `archive_agent` tools
- [x] **Template library**: 11 builtin templates seeded on startup; users can create custom templates or save agents as templates
- [x] **Agent evaluation**: Performance scoring endpoint (invocations, error rate, latency, task completion rate, 0-100 score)
- [ ] **Auto-scaling**: Spin up additional agent instances for parallel workload (future)
- [x] **Agent retirement**: Archive/unarchive endpoints + archive agent factory tool; history fully preserved

#### 2.5 Batch Jobs (Heartbeat) ✅
- [x] **BatchJob model**: name, cron schedule, member job list, parallel/sequential execution mode, notifications
- [x] **BatchJobRun model**: per-run log with per-job status, duration_ms, error fields
- [x] **APScheduler integration**: `sync_batch_jobs()` + `execute_batch_job()` with `asyncio.gather` for parallel mode
- [x] **Shared execution core**: `_execute_job_core()` reused by both individual jobs and batch jobs
- [x] **Full CRUD API**: `/api/batch-jobs/` with manual trigger and run history endpoints
- [x] **Frontend**: list page with inline run history drawer, new/edit forms with job picker, schedule builder, execution mode toggle, notifications

#### 2.6 Forge — Autonomous Platform Engineer ✅
- [x] **Forge agent**: Seeded system agent backed by Gemini 2.5 Flash; clones repos, implements features, opens PRs
- [x] **Forge tools**: `forge_start`, `forge_generate_plan`, `forge_execute_plan`, `forge_create_pr`, `forge_request_review`, `forge_merge_pr`, `forge_cancel`
- [x] **Human-in-the-loop review**: Plan approval and merge approval gates via `forge_request_review`
- [x] **UI**: Forge page with request queue and status tracking

#### 2.7 Smart AI Insights & Mission Control ✅
- [x] **AI Insights**: Kimi K2-backed analysis of agent performance, task patterns, and organizational health
- [x] **Mission Control dashboard**: Immersive ops-center view with real-time metrics and agent status

---

### Phase 3: External Engagement & Intelligence (Weeks 15-20)
*Connect the organization to the outside world.*

#### 3.1 Social & Communication Engagement
- [x] **Social Pulse**: Real-time trending topic monitoring across platforms; niche tracking, keyword alerts, scheduled refresh
- [x] **Email management**: SMTP/IMAP config per agent, send_email + read_emails tools, whitelist enforcement, test endpoint
- [ ] **Social media posting**: Agents draft, schedule, and (with approval) post to Twitter/X, LinkedIn, etc.
- [ ] **Customer support**: Agents handle inbound queries across channels with escalation
- [ ] **Content creation**: Blog posts, newsletters, documentation — drafted by agents, approved by humans
- [ ] **Community management**: Monitor forums, Discord, GitHub discussions; respond or escalate

#### 3.2 Knowledge & Research ✅
- [x] **RAG pipeline**: Ingest documents (PDF, web, code repos) into searchable knowledge base
- [ ] **Research agents**: Continuously monitor industry news, competitors, regulatory changes
- [ ] **Report generation**: Automated daily/weekly briefings for human review
- [ ] **Competitive intelligence**: Track competitor products, pricing, positioning
- [ ] **Trend analysis**: Identify emerging patterns from aggregated data

#### 3.3 Integration Ecosystem
- [x] **Native integrations**: Generic integration model + Google Drive (list/read/upload tools), Slack, Telegram, WhatsApp
- [x] **Webhook framework**: Inbound triggers (AgentTrigger with token-protected public endpoint) + outbound webhooks (HMAC-signed fan-out, delivery log, retry)
- [x] **Outbound webhook subscriptions**: Per-event, per-agent or global; test + retry UI
- [ ] **OAuth2 provider**: Allow external apps to integrate with Sutra
- [ ] **Plugin marketplace**: Community-built tools, agents, workflows
- [ ] **API gateway**: Rate-limited, authenticated API for external consumers

#### 3.4 Advanced Security
- [ ] **Threat detection**: Monitor agent behavior for anomalies (prompt injection attempts, data exfiltration patterns)
- [ ] **Security agent**: Dedicated agent that reviews other agents' actions for policy violations
- [ ] **Compliance framework**: GDPR, SOC2, HIPAA compliance tooling
- [ ] **Penetration testing**: Regular automated security assessments
- [ ] **Incident response**: Automated containment (disable agent, revoke permissions) on threat detection

---

### Phase 3.5: Agent Skills System (Weeks 19-20)
*Give agents composable, shareable capabilities.*

#### 3.5.1 Skill Framework ✅
- [x] **Skill model**: name, description, version, category, configuration schema, system prompt fragment, required tools, parameters
- [x] **Skill registry**: Central catalog of all available skills (built-in + community + custom)
- [ ] **Skill packaging**: Standardized skill definition format (YAML/JSON manifest + prompt templates + tool configs)
- [ ] **Skill versioning**: Semantic versioning; agents pin to a version, upgradeable per-agent or org-wide

#### 3.5.2 Skill Attachment & Composition ✅
- [x] **Agent-skill binding**: Attach/detach skills to individual agents (many-to-many); skill prompts and tools merge into agent config
- [x] **Role-skill binding**: Attach skills to role templates; agents inheriting the role get the skills automatically
- [x] **Skill parameters**: Per-attachment configuration (e.g., a "Code Review" skill parameterized with language=Python, strictness=high)
- [ ] **Skill conflicts**: Detect and warn when two attached skills define overlapping tools or contradictory prompt instructions
- [ ] **Skill priorities**: Ordering/weight when multiple skills contribute to the same agent context

#### 3.5.3 Skill Marketplace & Distribution
- [x] **Built-in skills**: Default skills seeded on startup (Code Review, Research, Email Drafting, Data Analysis, Report Writing, Meeting Notes, etc.)
- [x] **Custom skill creation**: UI to author new skills (prompt editor + tool picker + parameter schema builder)
- [ ] **Skill import/export**: Download skills as portable packages; import from file or URL
- [ ] **Skill marketplace**: Browse, search, rate, and install community-contributed skills
- [ ] **Skill analytics**: Track which skills are used most, success rates, and cost per skill invocation

#### 3.5.4 Skill-Aware Orchestration
- [ ] **Skill-based routing**: Route tasks to agents based on their equipped skills (enhances capability matching from 1.4)
- [ ] **Skill recommendations**: Suggest skills to attach based on agent role, team needs, or failed task patterns
- [ ] **Dynamic skill activation**: Temporarily activate a skill for a single task without permanent attachment

---

### Phase 4: Intelligence & Optimization (Weeks 21-26)
*Make the organization smarter over time.*

#### 4.1 Organizational Learning
- [ ] **Outcome tracking**: Link decisions → actions → results; learn what works
- [ ] **Playbook generation**: Auto-generate SOPs from successful task patterns
- [ ] **Knowledge distillation**: Compress agent experiences into reusable guidelines
- [ ] **Cross-agent learning**: When one agent solves a problem, share the solution with relevant peers
- [ ] **Continuous improvement**: Retrospective workflows that refine processes

#### 4.2 Analytics & Reporting
- [ ] **Executive dashboard**: High-level KPIs (tasks completed, cost, quality, speed)
- [ ] **Agent performance**: Individual agent scorecards with efficiency metrics
- [ ] **Team analytics**: Cross-functional collaboration patterns and bottlenecks
- [ ] **Cost-benefit analysis**: ROI per agent, per workflow, per initiative
- [ ] **Custom reports**: Natural language queries against operational data

#### 4.3 Advanced Orchestration
- [ ] **Multi-org support**: Run multiple autonomous organizations from one Sutra instance
- [ ] **Federation**: Connect multiple Sutra instances for cross-organization collaboration
- [ ] **Agent marketplace**: Share and import agent configurations across organizations
- [ ] **Custom LLM fine-tuning**: Fine-tune models on org-specific data for better performance
- [ ] **Hybrid execution**: Some agents run locally, others in cloud, seamless coordination

---

### Phase 5: Self-Improving Autonomous Platform (Weeks 27-38)
*Make the platform self-healing, self-improving, and publicly autonomous.*

#### 5.1 Memory Revolution
*Learn from Letta/MemGPT's three-tier self-editing memory model.*

- [ ] **pgvector migration**: True vector columns with HNSW indexing for O(log n) semantic search
- [ ] **Three-tier memory**: Core (always in context, like RAM) / Recall (searchable history) / Archival (long-term, compressed)
- [ ] **Self-editing memory tools**: `memory_write`, `memory_update`, `memory_forget` — agents manage their own context
- [ ] **Memory decay**: Importance scores decay over time; boost on access (recency × frequency weighting)
- [ ] **Memory consolidation**: Periodic job that merges related memories, removes duplicates, summarizes old episodes
- [ ] **Cross-agent knowledge sharing**: When one agent solves a problem, relevant agents inherit the learning
- [ ] **Memory analytics**: Dashboard showing memory growth, access patterns, most-used facts per agent

#### 5.2 Self-Healing & Resilience ✅ (partial)
*Learn from Devin's debug loop and LangGraph's durable execution.*

- [x] **Tool retry with backoff**: Exponential backoff + jitter for failed tool calls (configurable per-tool, max 3 retries)
- [x] **Circuit breaker**: After N failures in window, disable tool/provider temporarily; auto-recover after cooldown
- [x] **Agent auto-restart**: Watchdog process that detects crashed agents and restarts with state recovery
- [ ] **Durable workflow execution**: Checkpoint workflow state at each node; resume from last successful node on failure
- [ ] **Self-diagnosis tool**: Agent can inspect its own error history and adjust strategy
- [x] **Approval gate timeouts**: Configurable TTL with auto-escalation or auto-reject on expiry
- [x] **Health probes**: Periodic ping to each running agent; auto-restart if unresponsive
- [x] **Graceful degradation**: If external tool fails, fall back to simpler alternative (e.g., cached data)
- [x] **Purpose-based LLM routing**: Smart router with 5-priority fallback slots per purpose; automatic model switching on runtime errors (429, quota, deprecated, etc.)
- [x] **Token guard**: Context window management with 3-phase trimming + emergency trim for 413 recovery
- [x] **Rate limit tracking**: Redis-backed RPM/RPD/TPM/TPD counters with pre-reserve + finalize pattern

#### 5.3 Self-Improvement Engine
*The key differentiator — no competitor does this well.*

- [ ] **Outcome tracking**: Link goal → tasks → actions → results; score effectiveness
- [ ] **Agent performance scoring**: Auto-grade: task completion rate, error rate, cost efficiency, human override frequency
- [ ] **Prompt optimization**: A/B test system prompts; track success rate per variant; auto-promote winners
- [x] **Model selection intelligence**: Purpose-based routing with priority slots; auto-fallback to cheaper/available models when primary exhausted
- [ ] **Pattern mining**: Analyze ExecutionTrace data: common tool sequences, failure patterns, optimal conversation lengths
- [ ] **Playbook generation**: Auto-extract strategies from successful complex tasks as reusable playbooks
- [ ] **Feedback tool**: `record_feedback(task_id, outcome, notes)` agents call post-completion; feeds into learning loop
- [ ] **Regression detection**: Alert when an agent's performance score drops over time

#### 5.4 Performance & Speed ✅ (partial)
*Faster interactions, lower costs.*

- [x] **Prompt caching layer**: Cache LLM responses for identical/similar prompts (Redis, TTL-based)
- [x] **Conversation windowing**: Load only last N messages + summary of older context (not entire history)
- [ ] **Batch embedding**: Queue embedding requests and process in batches
- [ ] **Database indexes**: Add indexes on (agent_id, created_at) for traces, memories, messages
- [ ] **Connection pool tuning**: Explicit asyncpg pool size based on concurrent agent count
- [ ] **Streaming compression**: gzip SSE responses
- [ ] **Precomputed agent context**: Cache assembled system prompt + tools + recent memory; invalidate on config change
- [ ] **Lazy tool loading**: Load tool implementations on first use, not at agent startup

#### 5.5 Public-Facing Autonomous Agent ("Sutra Ambassador")
*An agent that represents and markets the platform on social media.*

- [ ] **Twitter/X integration**: Post, reply, quote, like, follow; respect rate limits and content policies
- [ ] **LinkedIn integration**: Share posts, comment on relevant discussions
- [ ] **Content pipeline**: Trend detection (Social Pulse) → Content drafting → Human approval gate → Scheduled posting
- [ ] **Persona engine**: Configurable voice/tone/style per social channel
- [ ] **Engagement analytics**: Track reach, impressions, engagement rate; feed back into content strategy
- [ ] **Comment/DM handling**: Auto-respond to mentions and DMs; escalate complex ones to humans
- [ ] **Community management**: Monitor GitHub Discussions, Discord, forums; answer questions, redirect to docs
- [ ] **Ambassador template**: Pre-built agent template combining Social Pulse + Email + Twitter + Approval tools

#### 5.6 Sandbox & Security Hardening
*Required before any public-facing agent goes live.*

- [ ] **Docker-based tool execution**: OS tools, code execution, and scraping run in ephemeral containers
- [ ] **Resource limits**: CPU/memory/time caps per tool execution
- [ ] **Network policies**: Agents can only reach whitelisted external services
- [ ] **Output guardrails pipeline**: PII detection, content policy, format validation as a pipeline stage
- [ ] **Anomaly detection**: Flag unusual patterns: cost spikes, repeated failures, unexpected tool usage
- [ ] **Input/output guardrails**: Structured validation (inspired by OpenAI Agents SDK Guardrails primitive)
- [ ] **Security agent**: Dedicated agent that reviews other agents' actions for policy violations

#### 5.7 Browser Automation (Web Autonomy)
*Learn from MultiOn — agents that act on any website.*

- [ ] **Interactive Playwright**: Extend scraper to support clicks, form fills, navigation, screenshots
- [ ] **Browser-use agent tool**: `browse_web(url, instruction)` interprets visual page and takes actions
- [ ] **Session management**: Persistent browser sessions with cookies/auth for repeated site access
- [ ] **Screenshot + vision**: Take screenshots, send to multimodal LLM for understanding page state
- [ ] **Rate limiting**: Respect robots.txt, implement per-domain request throttling

---

## Implementation Architecture

### Core Architecture Principles

```
┌─────────────────────────────────────────────────────────────────┐
│                        HUMAN LAYER                              │
│  Approval Queue │ Dashboards │ Chat │ Mobile │ Slack/Telegram   │
├─────────────────────────────────────────────────────────────────┤
│                     GOVERNANCE LAYER                            │
│  RBAC │ Approval Gates │ Budget Controls │ Audit Log │ Guards   │
├─────────────────────────────────────────────────────────────────┤
│                   ORCHESTRATION LAYER                           │
│  Agent Manager │ Discussion Engine │ Workflow Engine │ Scheduler │
├─────────────────────────────────────────────────────────────────┤
│                   INTELLIGENCE LAYER                            │
│  Smart Router │ LLM Purposes │ Rate Limits │ Token Guard       │
│  LLM Registry │ Memory (Vector+Episodic) │ RAG │ Analytics     │
├─────────────────────────────────────────────────────────────────┤
│                      AGENT LAYER                                │
│  Agent Factory │ Role Templates │ Skill Registry │ Tool Registry │ MCP │
├─────────────────────────────────────────────────────────────────┤
│                   INTEGRATION LAYER                             │
│  Slack │ Telegram │ WhatsApp │ Email │ Social │ Webhooks │ APIs │
├─────────────────────────────────────────────────────────────────┤
│                   INFRASTRUCTURE LAYER                          │
│  PostgreSQL │ Redis │ pgvector │ S3/MinIO │ Docker │ Celery     │
└─────────────────────────────────────────────────────────────────┘
```

### Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent framework | LangGraph (keep) | Already integrated; supports complex agent graphs |
| Vector store | pgvector (start) → Pinecone (scale) | pgvector avoids new infra; migrate when needed |
| Task queue | Celery + Redis (keep) | Already in place; reliable for background work |
| Real-time | WebSocket + SSE (keep) | Already working; add Redis pub/sub for scale |
| Discussion engine | Custom on LangGraph | Multi-agent conversations need custom orchestration |
| Approval system | Custom + integrations | Must work across Web, Slack, Telegram, email |
| File storage | S3/MinIO | Artifacts, documents, generated content |
| Search | PostgreSQL FTS → Elasticsearch (scale) | Start simple; add dedicated search when needed |
| Auth | JWT + OAuth2 | Industry standard; supports API keys too |

### New Database Models (Phase 1-2)

```
── Organization
   ├── Team[]
   │   ├── Agent[] (members)
   │   └── shared_memory_namespace
   ├── Project[]
   │   ├── Task[]
   │   │   ├── assignee (Agent | Human)
   │   │   ├── status (backlog/todo/in_progress/review/done)
   │   │   ├── priority (critical/high/medium/low)
   │   │   ├── parent_task_id (subtask support)
   │   │   ├── dependencies[] (task IDs)
   │   │   ├── artifacts[] (files, links)
   │   │   └── discussion_id (linked discussion)
   │   └── Milestone[]
   ├── Discussion[]
   │   ├── type (brainstorm/debate/review/standup/retro)
   │   ├── participants[] (Agent | Human)
   │   ├── moderator (Agent | Human)
   │   ├── messages[]
   │   ├── status (active/concluded)
   │   ├── summary (auto-generated)
   │   └── action_items[]
   ├── ApprovalRequest[]
   │   ├── requester (Agent)
   │   ├── category (financial/external/destructive/strategic)
   │   ├── context (full reasoning chain)
   │   ├── recommended_action
   │   ├── risk_level (low/medium/high/critical)
   │   ├── status (pending/approved/rejected/expired)
   │   ├── reviewer (Human)
   │   └── decided_at
   ├── Budget[]
   │   ├── scope (agent/team/org)
   │   ├── amount / spent / remaining
   │   └── period (daily/weekly/monthly)
   ├── Memory[]
   │   ├── agent_id (null = shared)
   │   ├── type (fact/episode/procedure)
   │   ├── content + embedding
   │   ├── importance_score
   │   └── last_accessed_at
   ├── Skill[]
   │   ├── name, description, version, category
   │   ├── prompt_fragment (system prompt addition)
   │   ├── required_tool_ids[] (tools the skill needs)
   │   ├── config_schema (JSON Schema for parameters)
   │   ├── source (builtin/custom/marketplace)
   │   └── AgentSkill[] (join: agent_id + skill_id + config + priority)
   └── AuditLog[]
       ├── actor (agent/human/system)
       ├── action
       ├── resource_type + resource_id
       ├── details (JSON)
       └── timestamp
```

---

## Tactical Implementation Plan

### Sprint 1 (Week 1-2): Auth + Memory Foundation
**Goal**: Secure the platform and give agents persistent memory.

| Task | Effort | Priority |
|------|--------|----------|
| JWT auth (register/login/refresh) | 3d | P0 |
| RBAC middleware (Owner/Admin/Operator/Viewer) | 2d | P0 |
| User model + migration | 1d | P0 |
| pgvector extension + Memory model | 2d | P0 |
| Memory storage/retrieval API | 2d | P0 |
| Inject relevant memories into agent context | 1d | P0 |
| Auth UI (login/register pages) | 2d | P0 |

### Sprint 2 (Week 3): Observability + Security
**Goal**: See what's happening and lock things down.

| Task | Effort | Priority |
|------|--------|----------|
| Structured logging with correlation IDs | 2d | P0 |
| Execution trace storage (per conversation) | 2d | P0 |
| Audit log model + middleware | 2d | P0 |
| Tool sandboxing (Docker executor for OS tools) | 3d | P1 |
| Input guardrails (basic content filtering) | 1d | P1 |
| Health/metrics dashboard improvements | 1d | P1 |

### Sprint 3-4 (Week 4-5): Task Management
**Goal**: Agents can create, assign, and track work.

| Task | Effort | Priority |
|------|--------|----------|
| Task + Project models + migrations | 2d | P0 |
| Task CRUD API endpoints | 2d | P0 |
| Task management tools (for agents) | 3d | P0 |
| Kanban board UI | 3d | P0 |
| Task decomposition prompt engineering | 2d | P1 |
| Task dependency resolution | 2d | P1 |

### Sprint 5-6 (Week 6-8): Multi-Agent Discussions
**Goal**: Agents can brainstorm and debate.

| Task | Effort | Priority |
|------|--------|----------|
| Discussion model + API | 2d | P0 |
| Discussion orchestrator (turn management, moderation) | 5d | P0 |
| Discussion types (brainstorm, debate, review) | 3d | P0 |
| Auto-summary generation | 2d | P0 |
| Discussion UI (real-time, multi-participant) | 4d | P0 |
| Consensus protocol implementation | 2d | P1 |
| Discussion → Task creation pipeline | 2d | P1 |

### Sprint 7-8 (Week 9-10): Approval System + Advanced Workflows
**Goal**: Humans can gate agent actions; workflows get powerful.

| Task | Effort | Priority |
|------|--------|----------|
| ApprovalRequest model + API | 2d | P0 |
| Approval queue UI | 3d | P0 |
| Approval tool (agents request approval) | 2d | P0 |
| Slack/Telegram approval integration | 3d | P0 |
| Workflow: conditional nodes | 2d | P0 |
| Workflow: parallel execution | 3d | P0 |
| Workflow: human approval gate node | 2d | P0 |
| Workflow: loop nodes | 2d | P1 |

### Sprint 9-10 (Week 11-12): Financial Controls + Proactive Agents
**Goal**: Budget management and goal-driven behavior.

| Task | Effort | Priority |
|------|--------|----------|
| Budget model + API | 2d | P0 |
| Cost attribution per agent/task | 3d | P0 |
| Spending approval workflow | 2d | P0 |
| Financial dashboard | 2d | P0 |
| Goal model for agents | 2d | P0 |
| Scheduled goal check-in system | 3d | P0 |
| Event-driven trigger framework | 3d | P1 |

### Sprint 11-12 (Week 13-14): Agent Factory + Org Structure
**Goal**: Agents can create other agents; org chart takes shape.

| Task | Effort | Priority |
|------|--------|----------|
| Role template system | 2d | P0 |
| Agent factory meta-agent | 3d | P0 |
| Org chart model + visualization | 3d | P0 |
| Team model + shared context | 2d | P0 |
| Agent performance scoring | 2d | P1 |
| Agent template marketplace (local) | 2d | P1 |

### Sprint 13-16 (Week 15-20): External Engagement
**Goal**: Connect to the outside world.

| Task | Effort | Priority |
|------|--------|----------|
| RAG pipeline (document ingestion + retrieval) | 5d | P0 |
| Email integration (read/send) | 3d | P0 |
| Social media tools (draft + approve + post) | 4d | P1 |
| Webhook framework (inbound/outbound) | 3d | P0 |
| Research agent template | 2d | P1 |
| Report generation system | 3d | P1 |
| Plugin/tool marketplace architecture | 4d | P1 |

### Sprint 15-16 (Week 19-20): Agent Skills System
**Goal**: Composable, shareable agent capabilities.

| Task | Effort | Priority |
|------|--------|----------|
| Skill model + registry + CRUD API | 2d | P0 |
| Agent-skill + Role-skill binding (attach/detach) | 3d | P0 |
| Skill prompt/tool merging into agent build | 2d | P0 |
| Built-in skills (10-15 defaults) | 3d | P0 |
| Skill management UI (browse, attach, configure) | 3d | P0 |
| Custom skill creation UI | 2d | P1 |
| Skill import/export (portable packages) | 2d | P1 |
| Skill-based task routing | 2d | P1 |
| Skill marketplace (browse, rate, install) | 3d | P2 |

### Sprint 17-20 (Week 21-26): Intelligence + Scale
**Goal**: Learn, optimize, scale.

| Task | Effort | Priority |
|------|--------|----------|
| Outcome tracking (decision → result) | 3d | P1 |
| Playbook auto-generation | 3d | P1 |
| Executive analytics dashboard | 4d | P1 |
| Multi-org support | 5d | P2 |
| Agent marketplace | 4d | P2 |
| Federation protocol | 5d | P2 |

### Sprint 21-22 (Week 27-28): Self-Healing & Performance [Phase 5.2 + 5.4]
**Goal**: Make the platform resilient and fast.

| Task | Effort | Priority |
|------|--------|----------|
| Tool retry with exponential backoff + circuit breaker | 3d | P0 |
| Agent auto-restart watchdog + health probes | 3d | P0 |
| Durable workflow checkpointing | 4d | P0 |
| Database indexes + connection pool tuning | 1d | P0 |
| Conversation windowing (last N + summary) | 2d | P0 |
| Prompt caching layer (Redis) | 2d | P0 |
| Streaming compression + lazy tool loading | 1d | P1 |

### Sprint 23-24 (Week 29-31): Memory Revolution [Phase 5.1]
**Goal**: Give agents self-managing, vectorized memory.

| Task | Effort | Priority |
|------|--------|----------|
| pgvector migration + HNSW indexing | 3d | P0 |
| Three-tier memory model (core/recall/archival) | 4d | P0 |
| Self-editing memory tools (write/update/forget) | 3d | P0 |
| Memory decay + importance re-scoring | 2d | P1 |
| Memory consolidation background job | 2d | P1 |
| Cross-agent knowledge sharing | 2d | P1 |

### Sprint 25-26 (Week 32-33): Sandbox & Security [Phase 5.6]
**Goal**: Isolate execution and harden for public-facing use.

| Task | Effort | Priority |
|------|--------|----------|
| Docker-based tool execution sandbox | 4d | P0 |
| Resource limits (CPU/mem/time per tool) | 2d | P0 |
| Output guardrails pipeline (PII, policy, format) | 3d | P0 |
| Network policies for agent external access | 2d | P1 |
| Anomaly detection (cost spikes, failure patterns) | 2d | P1 |

### Sprint 27-28 (Week 34-35): Self-Improvement Engine [Phase 5.3]
**Goal**: Agents that get smarter over time.

| Task | Effort | Priority |
|------|--------|----------|
| Outcome tracking (goal → task → action → result) | 3d | P0 |
| Agent performance scoring + regression detection | 3d | P0 |
| Prompt A/B testing framework | 3d | P1 |
| Model selection intelligence | 2d | P1 |
| Pattern mining on ExecutionTrace data | 2d | P1 |
| Playbook auto-generation from successful tasks | 3d | P1 |

### Sprint 29-30 (Week 36-37): Browser Automation [Phase 5.7]
**Goal**: Agents that can interact with any website.

| Task | Effort | Priority |
|------|--------|----------|
| Interactive Playwright (click, fill, navigate) | 3d | P0 |
| browse_web agent tool with vision | 3d | P0 |
| Persistent browser sessions | 2d | P1 |
| Rate limiting + robots.txt compliance | 1d | P1 |

### Sprint 31-32 (Week 37-38): Public-Facing Agent [Phase 5.5]
**Goal**: Launch the Sutra Ambassador.

| Task | Effort | Priority |
|------|--------|----------|
| Twitter/X integration (post, reply, like, follow) | 4d | P0 |
| LinkedIn integration (share, comment) | 3d | P0 |
| Content pipeline (trend → draft → approve → publish) | 3d | P0 |
| Persona engine (voice/tone per channel) | 2d | P1 |
| Engagement analytics + feedback loop | 2d | P1 |
| Ambassador agent template | 1d | P1 |
| Community management (GitHub, Discord, forums) | 3d | P2 |

---

## Key Design Patterns

### 1. Discussion Protocol
```
Discussion Flow:
1. INITIATE: Agent or human creates discussion with type + topic + participants
2. MODERATE: Moderator sets agenda, invites opening statements
3. ROUNDS: Each participant contributes (structured by discussion type)
   - Brainstorm: Free association → clustering → prioritization
   - Debate: Proposition → Opposition → Rebuttal → Counter
   - Review: Presentation → Questions → Feedback → Score
4. SYNTHESIZE: Moderator summarizes positions, identifies consensus/disagreements
5. CONCLUDE: Decision recorded, action items created as Tasks
6. ARCHIVE: Full transcript + summary stored for organizational memory
```

### 2. Approval Flow
```
Agent Action → Risk Assessment → Route:
  LOW risk (internal, reversible): Auto-approve, log
  MEDIUM risk (cost < threshold, internal comms): Queue for batch review
  HIGH risk (external comms, significant spend): Immediate human approval required
  CRITICAL risk (security, legal, financial): Multi-human approval + cooling period
```

### 3. Agent Autonomy Levels
```
Level 0 - Tool:     Agent only responds when asked. No initiative.
Level 1 - Assistant: Agent can suggest actions, human must approve all.
Level 2 - Operator:  Agent executes routine tasks, escalates exceptions.
Level 3 - Manager:   Agent plans and executes, human reviews outcomes.
Level 4 - Director:  Agent sets goals for other agents, human sets strategy.
Level 5 - Executive: Agent operates fully autonomously within policy bounds.
```

### 4. Purpose-Based LLM Routing & Automatic Fallback

Agents no longer hardcode a provider/model. Instead, each agent is assigned a **Purpose** (e.g., Reasoning, Summarization, Generic), and the system automatically selects the best available model at request time.

```
┌──────────────────────────────────────────────────────────────────┐
│  Agent Request (purpose_id + message)                            │
│                                                                  │
│  1. Token Guard                                                  │
│     estimate_messages_tokens() → ~4 chars/token heuristic        │
│     get_context_limit(provider, model) → window × 0.80 margin    │
│     trim_messages_to_fit() → 3-phase: history → memory → stub    │
│                                                                  │
│  2. LLM Queue (asyncio.Lock — serialized)                        │
│     acquire_model(purpose_id, est_tokens, db, exclude)           │
│         ↓                                                        │
│  3. Smart Router                                                 │
│     resolve_model() → walk priority slots P1→P5                  │
│         ├─ Skip models in exclude set (failed at runtime)        │
│         ├─ check_capacity(provider, model, est_tokens)           │
│         │    ├─ RPM: sutra:usage:{p}:{m}:rpm:{HHMM} < limit     │
│         │    ├─ RPD: sutra:usage:{p}:{m}:rpd:{YYYYMMDD} < limit │
│         │    ├─ TPM: current + est_tokens ≤ limit                │
│         │    └─ TPD: current + est_tokens ≤ limit                │
│         ├─ First with capacity → pre_reserve() → return          │
│         └─ All exhausted → SmartRouterError (with reasons)       │
│                                                                  │
│  4. Orchestrator Fallback Loop (up to 5 attempts)                │
│     ├─ Build fresh executor for resolved (provider, model)       │
│     ├─ Invoke LLM (via circuit breaker + retry_with_backoff)     │
│     ├─ On success → finalize_usage(actual_tokens) → return       │
│     ├─ On retriable error (429, quota, deprecated, 503, etc.)    │
│     │   → add (provider, model) to exclude set → continue loop   │
│     ├─ On CircuitOpenError → same: exclude + continue            │
│     ├─ On 413/context_length → emergency_trim() → retry once     │
│     └─ On non-retriable error → return error                     │
│                                                                  │
│  5. Usage Tracking (Redis)                                       │
│     pre_reserve: INCRBY rpm/rpd/tpm/tpd with estimated tokens   │
│     finalize: adjust tpm/tpd by (actual - estimated) diff        │
│     TTLs: minute=120s, day=refresh_hours×3600+300s               │
└──────────────────────────────────────────────────────────────────┘
```

**Data Model:**
```
LLMPurpose                          ModelRateLimit
├─ id, name, description            ├─ id, provider, model (unique pair)
├─ is_default                       ├─ requests_per_minute (nullable)
├─ priority_1: {provider, model}    ├─ requests_per_day (nullable)
├─ priority_2: {provider, model}    ├─ tokens_per_minute (nullable)
├─ priority_3: {provider, model}    ├─ tokens_per_day (nullable)
├─ priority_4: {provider, model}    ├─ refresh_interval_hours (default 24)
└─ priority_5: {provider, model}    └─ label (e.g., "Text-out")

Agent.purpose_id → LLMPurpose.id   (null = unlimited)
```

**Retriable Error Patterns** (trigger auto-fallback):
`429`, `rate limit`, `quota`, `resource_exhausted`, `too many requests`,
`model not found`, `deprecated`, `does not exist`, `not available`,
`insufficient_quota`, `billing`, `overloaded`, `503`, `capacity`

**Token Guard — 3-Phase Trimming:**
```
Phase 1: Remove oldest chat history messages (keep system + last user msg)
Phase 2: Truncate memory/system message to 50%
Phase 3: Aggressive stub — system message to 500 chars
Emergency: On 413 → keep system (2000 chars) + last 5 messages + user msg
```

**Key Files:**
- `backend/app/models/llm_purpose.py` — LLMPurpose model (5 priority slots)
- `backend/app/models/rate_limit.py` — ModelRateLimit model (RPM/RPD/TPM/TPD)
- `backend/app/core/smart_router.py` — resolve_model() with exclude set
- `backend/app/core/llm_queue.py` — acquire_model() with asyncio.Lock
- `backend/app/core/usage_tracker.py` — Redis counters, check_capacity, pre_reserve, finalize
- `backend/app/core/token_guard.py` — estimate, trim, emergency_trim, context limits
- `backend/app/core/orchestrator.py` — fallback loop (route_message + stream_message)
- `backend/app/api/routes/purposes.py` — Purpose CRUD + live capacity status
- `backend/app/api/routes/rate_limits.py` — Rate limit CRUD + usage + sync from provider

**API Endpoints:**
```
GET/POST       /api/purposes/              — List/create purposes
GET/PUT/DELETE  /api/purposes/{id}          — Get/update/delete purpose
GET             /api/purposes/{id}/status   — Live capacity per slot (green/yellow/red)

GET/POST        /api/rate-limits/           — List/create rate limits
PUT/DELETE      /api/rate-limits/{id}       — Update/delete rate limit
GET             /api/rate-limits/usage      — Live Redis counters for all models
POST            /api/rate-limits/sync/{provider} — Auto-sync limits from Groq/Google APIs
```

### 5. Memory Architecture
```
┌─────────────────────────────────────────┐
│            WORKING MEMORY               │
│  Current conversation + active task     │
├─────────────────────────────────────────┤
│           EPISODIC MEMORY               │
│  Past conversations, decisions, outcomes│
│  (Vector search + recency weighting)    │
├─────────────────────────────────────────┤
│          SEMANTIC MEMORY                │
│  Facts, procedures, organizational      │
│  knowledge (RAG from documents)         │
├─────────────────────────────────────────┤
│          SHARED MEMORY                  │
│  Org-wide knowledge accessible to all   │
│  agents (policies, playbooks, contacts) │
└─────────────────────────────────────────┘
```

---

## Success Metrics

### Platform Health
- Agent uptime > 99.5%
- API latency p95 < 2s (non-LLM operations)
- Zero unauthorized data access incidents

### Organizational Efficiency
- % of routine tasks handled without human intervention
- Time from task creation to completion
- Human review queue clearance time (< 4 hours for HIGH, < 1 hour for CRITICAL)

### Agent Quality
- Task completion rate per agent
- Human override/correction rate (lower = better)
- Cost per completed task (trending down)

### Collaboration Quality
- Discussion-to-action conversion rate
- Cross-agent task success rate
- Knowledge reuse frequency

---

## Competitive Differentiation

### Competitor Analysis (Updated March 2026)

| Platform | Core Differentiator | Memory | Self-Healing | Social/Public |
|----------|-------------------|--------|-------------|---------------|
| **CrewAI** | Role-based crews + hierarchical manager; 2-3x faster execution | Planned (Q1 2026) | Manager re-delegates on failure | None |
| **AutoGen/AG2** | Conversation-centric; cross-language (Python+.NET); framework interop | Shared state across lifecycle | Human-in-the-loop fallback | None |
| **LangGraph** | DAG-based durable execution with checkpoint resume | Short-term + long-term persistence | **Strong** — auto-resume from checkpoints | None |
| **OpenClaw** | Messaging-first (Signal/TG/Discord/WA); 250K+ GitHub stars | Conversation context only | Basic; security concerns | **50+ integrations** |
| **Devin** | Autonomous SWE with sandboxed IDE+terminal+browser | Session-based | **Strong** — debug loop: write→fail→fix→retry | None |
| **Letta/MemGPT** | LLM-as-OS; **self-editing 3-tier memory** (core/recall/archival) | **Gold standard** — agents manage own memory | Basic | None |
| **Composio** | Integration layer; **1000+ tool connectors** with managed OAuth | N/A (tool layer) | Sandboxed execution | Tool connectors for social |
| **OpenAI Agents SDK** | Responses API + Agents SDK; built-in tools; Guardrails primitive | Stateful context via store | Agentic retry loop + guardrails | GPT Store publishing |
| **Relevance AI** | No-code agent teams; SOC2; describe→build UX | Session + team-shared context | Basic retry | Slack, Gmail, CRM |
| **MultiOn** | Autonomous browser agents; navigate any website like a human | Session-based | Proxy + retry for bot protection | **Core capability** — any website |

### Feature Matrix

| Feature | CrewAI | AutoGen | LangGraph | OpenClaw | Devin | Letta | Composio | **Sutra** |
|---------|--------|---------|-----------|----------|-------|-------|----------|-----------|
| Multi-agent orchestration | Yes | Yes | Yes | No | No | No | No | **Yes** |
| Visual workflow builder | No | No | Studio | No | No | No | No | **Yes (React Flow)** |
| Persistent agent memory | No | No | Checkpoints | No | Session | **Self-editing 3-tier** | No | **pgvector + auto-extract** |
| Multi-agent discussions | Limited | Group chat | No | No | No | No | No | **5 structured protocols** |
| Human approval gates | No | Basic | No | No | No | No | No | **Multi-channel + SLA** |
| Financial controls | No | No | No | No | ACU-based | No | No | **Full budget system** |
| Task/Project management | No | No | No | No | No | No | No | **Built-in Kanban** |
| Social engagement | No | No | No | **50+ apps** | No | No | No | **Multi-platform** |
| Org structure & roles | Roles | No | No | No | No | No | No | **Full org chart + teams** |
| Composable skill system | No | No | No | No | No | No | No | **Attach/share/compose** |
| Chat integrations | No | No | No | **Native** | No | No | No | **Slack/TG/WA** |
| Production security | No | No | No | Low | VPC | No | SOC2 | **RBAC + audit + encrypt** |
| Self-hosted | Yes | Yes | Cloud | Yes | VPC option | Yes | Yes | **Yes (Docker)** |
| Browser automation | No | No | No | No | **Full IDE+browser** | No | No | Scraping only |
| Sandboxed execution | No | No | No | No | **Yes** | No | **Yes** | No (planned) |
| Managed OAuth (1000+ tools) | No | No | No | No | No | No | **Yes** | No (planned) |
| Self-improving / learning | Reflection | No | No | No | Dynamic re-plan | **Self-editing memory** | No | Traces only (planned) |
| Durable execution (checkpoint) | No | No | **Yes** | No | Yes | No | No | No (planned) |
| Guardrails (I/O validation) | No | No | No | No | No | No | No | Basic (planned) |

### Sutra's Unique Competitive Moat

1. **Self-hosted + Self-improving** — No competitor combines data sovereignty with organizational learning
2. **Full Organizational Simulation** — Roles, teams, org chart, discussions, budgets, approvals — models an entire company
3. **Transparent Autonomy** — Every decision auditable, every action logged, every spend tracked
4. **Composable Skills** — Plugin-like capabilities that attach/detach to agents; no competitor has this
5. **Integrated Platform** — One system for agents, tasks, workflows, approvals, budgets, chat, social — not a framework requiring assembly

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Runaway agent costs | Per-agent budgets, auto-pause on threshold, purpose-based routing auto-downgrades to cheaper models |
| Agent produces harmful content | Output guardrails, human review for external comms |
| Security breach via tool use | Sandboxed execution, permission scoping, audit logging |
| Agent hallucination in decisions | Require evidence/sources, multi-agent review, human gates |
| System complexity overwhelms users | Progressive disclosure UI, sensible defaults, templates |
| Vendor lock-in (LLM providers) | Multi-provider abstraction + purpose-based routing with automatic fallback across providers |
| Data loss | Automated backups, soft deletes, audit trail |

---

## Getting Started (Recommended First Week)

1. **Day 1-2**: Implement User model + JWT auth + login UI
2. **Day 3**: Add pgvector extension, create Memory model
3. **Day 4**: Build memory storage/retrieval, inject into agent context
4. **Day 5**: Add basic audit logging middleware
5. **Day 6-7**: Implement Task model + CRUD API + basic task board UI

This gives you a secured platform where agents remember context and work gets tracked — the minimum viable autonomous organization.
