# Sutra Phase 5: Detailed Implementation Design

> Self-Improving Autonomous Platform — Technical Design Document
> Last updated: 2026-03-17

---

## Table of Contents

1. [Phase 5.1 — Memory Revolution](#phase-51--memory-revolution)
2. [Phase 5.2 — Self-Healing & Resilience](#phase-52--self-healing--resilience)
3. [Phase 5.3 — Self-Improvement Engine](#phase-53--self-improvement-engine)
4. [Phase 5.4 — Performance & Speed](#phase-54--performance--speed)
5. [Phase 5.5 — Public-Facing Autonomous Agent](#phase-55--public-facing-autonomous-agent)
6. [Phase 5.6 — Sandbox & Security Hardening](#phase-56--sandbox--security-hardening)
7. [Phase 5.7 — Browser Automation](#phase-57--browser-automation)
8. [Implementation Priority & Dependencies](#implementation-priority--dependencies)

---

## Phase 5.1 — Memory Revolution

### Problem Statement

Current memory system stores embeddings as JSON strings in TEXT columns. Search is O(n) — all memories loaded into Python, then sorted by cosine similarity. No decay, pruning, or consolidation. Agents don't control what they remember.

### Architecture: Three-Tier Self-Editing Memory

```
┌──────────────────────────────────────────────────────────┐
│                    CORE MEMORY (Tier 1)                   │
│  Always injected into agent context. Like RAM.            │
│  Agent's identity, key facts, active goals, preferences.  │
│  Max ~2000 tokens per agent. Agent edits directly.        │
├──────────────────────────────────────────────────────────┤
│                   RECALL MEMORY (Tier 2)                  │
│  Searchable conversation history + extracted facts.       │
│  Vector-indexed via pgvector HNSW. Semantic search.       │
│  Auto-populated from conversations. Agent can query.      │
├──────────────────────────────────────────────────────────┤
│                  ARCHIVAL MEMORY (Tier 3)                  │
│  Long-term storage. Compressed summaries of old episodes. │
│  Infrequently accessed. Searchable but not in context.    │
│  Consolidation job moves Recall → Archival after N days.  │
└──────────────────────────────────────────────────────────┘
```

### Database Changes

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- New memory table (replaces current Memory model)
ALTER TABLE memories ADD COLUMN embedding vector(1536);
ALTER TABLE memories ADD COLUMN tier VARCHAR(10) DEFAULT 'recall';  -- 'core', 'recall', 'archival'
ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE memories ADD COLUMN last_accessed_at TIMESTAMP;
ALTER TABLE memories ADD COLUMN decay_score FLOAT DEFAULT 1.0;
ALTER TABLE memories ADD COLUMN consolidated_from_ids UUID[];
ALTER TABLE memories ADD COLUMN ttl_days INTEGER;  -- NULL = never expires

-- HNSW index for fast vector search
CREATE INDEX idx_memories_embedding ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Composite index for tier-based queries
CREATE INDEX idx_memories_agent_tier ON memories (agent_id, tier, decay_score DESC);
```

### New Agent Tools

```python
# backend/app/tools/memory_tools.py

MEMORY_TOOL_IDS = {"memory_write", "memory_update", "memory_forget", "memory_search", "memory_promote"}

def memory_write(content: str, tier: str = "recall", importance: float = 0.5) -> str:
    """Write a new memory. Core memories are always in context."""

def memory_update(memory_id: str, new_content: str) -> str:
    """Update an existing memory's content."""

def memory_forget(memory_id: str, reason: str) -> str:
    """Mark a memory as forgotten (soft delete with reason)."""

def memory_search(query: str, tier: str = "all", limit: int = 5) -> str:
    """Search memories by semantic similarity."""

def memory_promote(memory_id: str, target_tier: str) -> str:
    """Move a memory between tiers (e.g., recall → core)."""
```

### Memory Decay Algorithm

```python
def calculate_decay_score(memory) -> float:
    """
    Score = base_importance * recency_factor * frequency_factor

    recency_factor: exponential decay, half-life = 7 days
    frequency_factor: log(access_count + 1)

    Memories with decay_score < 0.1 are candidates for archival.
    Archival memories with decay_score < 0.01 are candidates for deletion.
    """
    days_since_access = (now() - memory.last_accessed_at).days
    recency = 0.5 ** (days_since_access / 7.0)
    frequency = math.log(memory.access_count + 1, 10)
    return memory.importance * recency * max(frequency, 0.1)
```

### Memory Consolidation Job

Runs daily via APScheduler:

1. Find all recall memories with `decay_score < 0.1` and `age > 14 days`
2. Group by agent_id and topic (cluster by embedding similarity, threshold 0.85)
3. For each cluster: LLM-summarize into a single archival memory
4. Set `consolidated_from_ids` on the new memory; soft-delete originals
5. Find archival memories with `decay_score < 0.01` and `age > 90 days` → hard delete

### Context Injection (Modified Orchestrator)

```python
async def _build_agent_context(self, agent_id: str) -> list[SystemMessage]:
    # 1. Always inject ALL core memories (Tier 1)
    core = await memory_service.get_by_tier(agent_id, "core")

    # 2. Retrieve relevant recall memories for current query (Tier 2)
    recall = await memory_service.vector_search(agent_id, query, tier="recall", limit=5)

    # 3. Format and inject
    context = f"## Your Core Memory\n{format_memories(core)}\n\n"
    context += f"## Relevant Past Knowledge\n{format_memories(recall)}"
    return [SystemMessage(content=context)]
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/tools/memory_tools.py` | Create | 5 self-editing memory tools |
| `backend/app/core/memory_service.py` | Rewrite | pgvector search, tier management, decay calculation |
| `backend/app/models/memory.py` | Modify | Add vector column, tier, decay_score, access_count, ttl |
| `backend/app/core/orchestrator.py` | Modify | New context injection using tiered memory |
| `backend/app/tools/registry.py` | Modify | Register MEMORY_TOOL_IDS |
| `backend/app/core/scheduler.py` | Modify | Add daily consolidation + decay jobs |
| `frontend/app/memory/page.tsx` | Modify | Show tiers, decay scores, consolidation stats |

---

## Phase 5.2 — Self-Healing & Resilience

### Problem Statement

Tool failures crash the agent response. No retries, no circuit breakers, no auto-restart. Workflows fail completely on any node error. Approval gates block forever.

### 1. Tool Retry with Exponential Backoff

```python
# backend/app/core/retry.py

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0      # seconds
    max_delay: float = 30.0
    jitter: bool = True
    retryable_errors: set = field(default_factory=lambda: {
        ConnectionError, TimeoutError, httpx.HTTPStatusError
    })

async def retry_with_backoff(func, config: RetryConfig, **kwargs):
    for attempt in range(config.max_retries + 1):
        try:
            return await func(**kwargs)
        except tuple(config.retryable_errors) as e:
            if attempt == config.max_retries:
                raise
            delay = min(config.base_delay * (2 ** attempt), config.max_delay)
            if config.jitter:
                delay *= random.uniform(0.5, 1.5)
            logger.warning(f"Retry {attempt+1}/{config.max_retries} after {delay:.1f}s: {e}")
            await asyncio.sleep(delay)
```

### 2. Circuit Breaker

```python
# backend/app/core/circuit_breaker.py

class CircuitBreaker:
    """
    States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)

    Transition rules:
    - CLOSED → OPEN: when failure_count >= threshold within window
    - OPEN → HALF_OPEN: after cooldown_seconds
    - HALF_OPEN → CLOSED: on success
    - HALF_OPEN → OPEN: on failure
    """
    def __init__(self, name: str, threshold: int = 5, window: int = 60, cooldown: int = 30):
        self.name = name
        self.threshold = threshold
        self.window = window          # seconds
        self.cooldown = cooldown      # seconds
        self.state = "CLOSED"
        self.failures: list[float] = []
        self.last_failure_time: float = 0

    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.cooldown:
                self.state = "HALF_OPEN"
            else:
                raise CircuitOpenError(f"Circuit {self.name} is OPEN, retry after cooldown")

        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures.clear()
            return result
        except Exception as e:
            self._record_failure()
            raise

    def _record_failure(self):
        now = time.time()
        self.failures = [t for t in self.failures if now - t < self.window]
        self.failures.append(now)
        self.last_failure_time = now
        if len(self.failures) >= self.threshold:
            self.state = "OPEN"
            logger.error(f"Circuit {self.name} OPENED after {len(self.failures)} failures")

# Registry of circuit breakers (one per external service / LLM provider)
_breakers: dict[str, CircuitBreaker] = {}

def get_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name)
    return _breakers[name]
```

### 3. Agent Watchdog & Auto-Restart

```python
# backend/app/core/watchdog.py

class AgentWatchdog:
    """
    Runs as a background task. Periodically checks agent health.
    """
    def __init__(self, agent_manager, interval: int = 30):
        self.agent_manager = agent_manager
        self.interval = interval  # seconds
        self.last_heartbeat: dict[str, float] = {}  # agent_id → timestamp

    async def run(self):
        while True:
            await asyncio.sleep(self.interval)
            for agent_id, status in self.agent_manager.agents.items():
                if status.get("status") != "running":
                    continue

                last_beat = self.last_heartbeat.get(agent_id, 0)
                if time.time() - last_beat > self.interval * 3:
                    logger.warning(f"Agent {agent_id} unresponsive, restarting...")
                    try:
                        await self.agent_manager.restart_agent(agent_id)
                        await record_audit("system", "agent.auto_restart", "agent", agent_id,
                                         {"reason": "watchdog_timeout"})
                    except Exception as e:
                        logger.error(f"Failed to restart agent {agent_id}: {e}")

    def heartbeat(self, agent_id: str):
        self.last_heartbeat[agent_id] = time.time()
```

### 4. Durable Workflow Execution

```python
# backend/app/models/workflow.py — New fields

class WorkflowRun(Base):
    """Tracks a single execution of a workflow with per-node checkpointing."""
    id = Column(UUID, primary_key=True)
    workflow_id = Column(UUID, ForeignKey("workflows.id"))
    status = Column(String, default="running")  # running, paused, completed, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    # Per-node checkpoint: {node_id: {status, output, started_at, completed_at}}
    checkpoints = Column(JSON, default={})
    current_node_id = Column(String)
    error = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

# In workflow_engine.py:
async def execute_workflow(self, workflow_id: str, run_id: str = None):
    # If run_id provided, resume from checkpoint
    if run_id:
        run = await self.load_run(run_id)
        start_node = run.current_node_id  # Resume from last incomplete node
    else:
        run = await self.create_run(workflow_id)
        start_node = workflow.definition["nodes"][0]["id"]

    for node in self._traverse_from(start_node, workflow.definition):
        run.current_node_id = node["id"]
        try:
            output = await self._execute_node(node, run)
            run.checkpoints[node["id"]] = {
                "status": "completed", "output": output,
                "completed_at": datetime.utcnow().isoformat()
            }
            await self.save_run(run)  # Checkpoint after each node
        except Exception as e:
            run.checkpoints[node["id"]] = {"status": "failed", "error": str(e)}
            if run.retry_count < run.max_retries:
                run.retry_count += 1
                await self.save_run(run)
                await asyncio.sleep(2 ** run.retry_count)
                return await self.execute_workflow(workflow_id, run.id)  # Resume
            else:
                run.status = "failed"
                run.error = str(e)
                await self.save_run(run)
                raise
```

### 5. Approval Gate Timeout

```python
# In approval handling:
class ApprovalGateConfig:
    timeout_minutes: int = 60 * 24  # 24h default
    on_timeout: str = "escalate"     # "escalate", "auto_reject", "auto_approve_low_risk"
    escalation_channel: str = "telegram"  # Where to escalate

# Scheduler job: check_expired_approvals() runs every 5 minutes
async def check_expired_approvals():
    expired = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == "pending")
        .where(ApprovalRequest.created_at < datetime.utcnow() - timedelta(minutes=config.timeout))
    )
    for approval in expired:
        if config.on_timeout == "escalate":
            await notify_escalation(approval)
        elif config.on_timeout == "auto_reject":
            approval.status = "expired"
            await resume_workflow(approval.workflow_run_id, rejected=True)
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/core/retry.py` | Create | RetryConfig + retry_with_backoff |
| `backend/app/core/circuit_breaker.py` | Create | CircuitBreaker + registry |
| `backend/app/core/watchdog.py` | Create | AgentWatchdog background task |
| `backend/app/models/workflow.py` | Modify | Add WorkflowRun model with checkpoints |
| `backend/app/core/workflow_engine.py` | Modify | Durable execution with checkpoint resume |
| `backend/app/core/orchestrator.py` | Modify | Wrap tool calls in retry + circuit breaker |
| `backend/app/core/agent_manager.py` | Modify | Integrate watchdog heartbeats |
| `backend/app/core/scheduler.py` | Modify | Add expired approval check job |
| `backend/app/main.py` | Modify | Start watchdog on startup |

---

## Phase 5.3 — Self-Improvement Engine

### Problem Statement

ExecutionTrace data is collected but never analyzed. Agents don't learn from past successes or failures. System prompts are static. No feedback loops exist.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    IMPROVEMENT PIPELINE                       │
│                                                               │
│  ExecutionTrace ──→ Pattern Analyzer ──→ Insights Store       │
│       ↑                    ↓                    ↓             │
│  Feedback Tool      Performance Score    Prompt Variants      │
│       ↑                    ↓                    ↓             │
│  Agent completes    Agent Scorecard      A/B Test Runner      │
│  task + records     (auto-graded)        (auto-promote)       │
│  outcome                                                      │
│                                                               │
│  Successful Task ──→ Playbook Generator ──→ Knowledge Base    │
└─────────────────────────────────────────────────────────────┘
```

### 1. Outcome Tracking Model

```python
# backend/app/models/outcome.py

class Outcome(Base):
    """Links goals → tasks → actions → results."""
    __tablename__ = "outcomes"

    id = Column(UUID, primary_key=True, default=uuid4)
    agent_id = Column(UUID, ForeignKey("agents.id"))
    goal_id = Column(UUID, ForeignKey("agent_goals.id"), nullable=True)
    task_id = Column(UUID, ForeignKey("tasks.id"), nullable=True)

    # What happened
    action_summary = Column(Text)           # LLM-generated summary of what the agent did
    tool_sequence = Column(JSON)            # Ordered list of tools used
    trace_ids = Column(JSON)                # List of ExecutionTrace IDs involved
    total_tokens = Column(Integer)
    total_cost_usd = Column(Float)
    total_latency_ms = Column(Integer)

    # How it went
    result = Column(String)                 # "success", "partial", "failure"
    result_details = Column(Text)           # What specifically succeeded/failed
    human_override = Column(Boolean, default=False)  # Did human need to intervene?
    human_feedback = Column(Text)           # Optional human assessment

    # Scoring (auto-calculated)
    effectiveness_score = Column(Float)     # 0-1: did it achieve the goal?
    efficiency_score = Column(Float)        # 0-1: cost/time relative to baseline
    quality_score = Column(Float)           # 0-1: human overrides reduce this

    created_at = Column(DateTime, server_default=func.now())
```

### 2. Agent Performance Scoring

```python
# backend/app/core/performance_scorer.py

class AgentScorer:
    """Auto-calculates agent performance scores from outcomes and traces."""

    async def score_agent(self, agent_id: str, period_days: int = 30) -> AgentScorecard:
        outcomes = await self.get_outcomes(agent_id, period_days)
        traces = await self.get_traces(agent_id, period_days)

        return AgentScorecard(
            agent_id=agent_id,
            period_days=period_days,

            # Task metrics
            tasks_completed=len([o for o in outcomes if o.result == "success"]),
            tasks_failed=len([o for o in outcomes if o.result == "failure"]),
            completion_rate=self._completion_rate(outcomes),

            # Quality metrics
            human_override_rate=self._override_rate(outcomes),
            error_rate=self._error_rate(traces),
            avg_quality_score=self._avg_quality(outcomes),

            # Efficiency metrics
            avg_cost_per_task=self._avg_cost(outcomes),
            avg_latency_per_task=self._avg_latency(outcomes),
            cost_trend=self._cost_trend(outcomes),  # "improving" | "stable" | "degrading"

            # Overall
            overall_score=self._weighted_score(outcomes, traces),  # 0-100
            trend=self._score_trend(agent_id),  # "improving" | "stable" | "degrading"
            regression_alert=self._detect_regression(agent_id),
        )

    def _detect_regression(self, agent_id: str) -> Optional[str]:
        """Compare last 7d vs prior 7d. Alert if score dropped >15%."""
        recent = self._weighted_score_for_period(agent_id, days=7)
        prior = self._weighted_score_for_period(agent_id, days=14, offset=7)
        if prior > 0 and (prior - recent) / prior > 0.15:
            return f"Performance dropped {((prior-recent)/prior*100):.0f}% in last 7 days"
        return None
```

### 3. Prompt A/B Testing

```python
# backend/app/models/prompt_experiment.py

class PromptExperiment(Base):
    """A/B test for agent system prompts."""
    __tablename__ = "prompt_experiments"

    id = Column(UUID, primary_key=True, default=uuid4)
    agent_id = Column(UUID, ForeignKey("agents.id"))
    name = Column(String)
    status = Column(String, default="running")  # running, concluded
    started_at = Column(DateTime, server_default=func.now())
    concluded_at = Column(DateTime)

    # Variants
    variant_a_prompt = Column(Text)  # Control (current prompt)
    variant_b_prompt = Column(Text)  # Challenger
    traffic_split = Column(Float, default=0.5)  # % of requests that get variant B

    # Results (updated incrementally)
    variant_a_invocations = Column(Integer, default=0)
    variant_a_successes = Column(Integer, default=0)
    variant_a_avg_quality = Column(Float, default=0)
    variant_b_invocations = Column(Integer, default=0)
    variant_b_successes = Column(Integer, default=0)
    variant_b_avg_quality = Column(Float, default=0)

    # Decision
    winner = Column(String)  # "a", "b", or null
    auto_promoted = Column(Boolean, default=False)

# In orchestrator.py, before invoking agent:
async def _select_prompt_variant(self, agent_id):
    experiment = await get_active_experiment(agent_id)
    if not experiment:
        return agent.system_prompt  # No experiment running

    if random.random() < experiment.traffic_split:
        return experiment.variant_b_prompt, "b"
    return experiment.variant_a_prompt, "a"
```

### 4. Pattern Mining

```python
# backend/app/core/pattern_miner.py

class PatternMiner:
    """Analyzes ExecutionTrace data to find patterns."""

    async def mine_tool_sequences(self, agent_id: str) -> list[ToolPattern]:
        """Find common tool call sequences that lead to success vs failure."""
        traces = await self.get_traces(agent_id, days=30)
        sequences = [t.tool_calls for t in traces if t.tool_calls]

        # Cluster sequences by similarity
        # Find high-success sequences and high-failure sequences
        patterns = []
        for seq_group in self._cluster_sequences(sequences):
            success_rate = self._success_rate_for_sequences(seq_group, traces)
            patterns.append(ToolPattern(
                tools=seq_group[0],  # Representative sequence
                frequency=len(seq_group),
                success_rate=success_rate,
                avg_latency=self._avg_latency(seq_group, traces),
            ))
        return sorted(patterns, key=lambda p: p.frequency, reverse=True)

    async def mine_failure_patterns(self, agent_id: str) -> list[FailurePattern]:
        """Find recurring failure modes."""
        errors = await self.get_error_traces(agent_id, days=30)
        # Cluster by error message similarity
        clusters = self._cluster_errors(errors)
        return [FailurePattern(
            error_category=c.representative_error,
            count=len(c),
            first_seen=min(c.timestamps),
            last_seen=max(c.timestamps),
            common_trigger=self._find_common_trigger(c),
        ) for c in clusters]
```

### 5. Playbook Generation

```python
# backend/app/core/playbook_generator.py

async def generate_playbook(outcome: Outcome) -> Optional[Playbook]:
    """
    When an agent successfully completes a complex task (>3 tool calls),
    auto-extract the strategy as a reusable playbook.
    """
    if outcome.result != "success" or len(outcome.tool_sequence) < 3:
        return None

    traces = await load_traces(outcome.trace_ids)
    prompt = f"""Analyze this successful task execution and create a reusable playbook.

    Task: {outcome.action_summary}
    Tools used (in order): {outcome.tool_sequence}
    Execution details: {format_traces(traces)}

    Create a playbook with:
    1. A descriptive title
    2. When to use this playbook (trigger conditions)
    3. Step-by-step instructions (referencing specific tools)
    4. Expected outcomes
    5. Common pitfalls to avoid
    """

    playbook_text = await llm.invoke(prompt)
    return Playbook(
        agent_id=outcome.agent_id,
        title=extract_title(playbook_text),
        content=playbook_text,
        source_outcome_id=outcome.id,
        tool_sequence=outcome.tool_sequence,
    )
```

### 6. Feedback Tool

```python
# Added to agent tools
def record_feedback(task_id: str, outcome: str, notes: str) -> str:
    """
    Record the outcome of a completed task. Called by agents post-completion.
    outcome: "success" | "partial" | "failure"
    notes: What worked, what didn't, and what to do differently next time.
    """
    # Creates an Outcome record
    # Triggers playbook generation if successful
    # Updates agent performance score
    # Stores in memory for future reference
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/models/outcome.py` | Create | Outcome model |
| `backend/app/models/prompt_experiment.py` | Create | PromptExperiment model |
| `backend/app/models/playbook.py` | Create | Playbook model |
| `backend/app/core/performance_scorer.py` | Create | Agent scoring engine |
| `backend/app/core/pattern_miner.py` | Create | Trace pattern analysis |
| `backend/app/core/playbook_generator.py` | Create | Auto-playbook from successful tasks |
| `backend/app/tools/feedback_tools.py` | Create | record_feedback agent tool |
| `backend/app/api/routes/insights.py` | Create | API for scorecards, patterns, experiments |
| `backend/app/core/orchestrator.py` | Modify | Prompt variant selection, outcome recording |
| `frontend/app/analytics/page.tsx` | Modify | Agent scorecards, pattern viz, experiment UI |

---

## Phase 5.4 — Performance & Speed

### Problem Statement

Chat history loaded unbounded. Memory search is O(n). No prompt caching. No database indexes on frequently queried columns. Embeddings processed one-by-one.

### 1. Prompt Caching Layer

```python
# backend/app/core/prompt_cache.py

class PromptCache:
    """
    Redis-based cache for LLM responses.
    Key: SHA256(model + system_prompt + last_3_messages)
    TTL: 1 hour for general queries, 5 min for time-sensitive.
    """
    def __init__(self, redis_client):
        self.redis = redis_client
        self.default_ttl = 3600
        self.hit_count = 0
        self.miss_count = 0

    def _cache_key(self, model: str, messages: list) -> str:
        # Only hash the last 3 messages + system prompt for cache key
        relevant = [m for m in messages if m["role"] == "system"]
        relevant += messages[-3:]
        content = f"{model}:{json.dumps(relevant, sort_keys=True)}"
        return f"prompt_cache:{hashlib.sha256(content.encode()).hexdigest()}"

    async def get(self, model: str, messages: list) -> Optional[str]:
        key = self._cache_key(model, messages)
        cached = await self.redis.get(key)
        if cached:
            self.hit_count += 1
            return json.loads(cached)
        self.miss_count += 1
        return None

    async def set(self, model: str, messages: list, response: str, ttl: int = None):
        key = self._cache_key(model, messages)
        await self.redis.setex(key, ttl or self.default_ttl, json.dumps(response))

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0
```

### 2. Conversation Windowing

```python
# backend/app/core/conversation_window.py

class ConversationWindow:
    """
    Instead of loading all messages, load:
    1. System prompt
    2. Summary of older messages (if any)
    3. Last N messages (default 20)
    """
    MAX_RECENT_MESSAGES = 20
    SUMMARY_THRESHOLD = 30  # Summarize when conversation exceeds this

    async def get_windowed_history(self, conversation_id: str) -> list:
        total_count = await self._count_messages(conversation_id)

        if total_count <= self.MAX_RECENT_MESSAGES:
            return await self._get_all_messages(conversation_id)

        # Get or generate summary of older messages
        summary = await self._get_or_create_summary(conversation_id, total_count)

        # Get recent messages
        recent = await self._get_recent_messages(conversation_id, self.MAX_RECENT_MESSAGES)

        return [
            {"role": "system", "content": f"[Summary of earlier conversation]\n{summary}"},
            *recent
        ]

    async def _get_or_create_summary(self, conversation_id: str, total_count: int) -> str:
        """Generate and cache a rolling summary of older messages."""
        cache_key = f"conv_summary:{conversation_id}:{total_count // 10}"
        cached = await redis.get(cache_key)
        if cached:
            return cached

        older_messages = await self._get_messages(
            conversation_id,
            offset=0,
            limit=total_count - self.MAX_RECENT_MESSAGES
        )
        summary = await self._llm_summarize(older_messages)
        await redis.setex(cache_key, 3600, summary)
        return summary
```

### 3. Batch Embedding

```python
# backend/app/core/embedding_batcher.py

class EmbeddingBatcher:
    """
    Queue embedding requests and process in batches.
    Reduces API calls from N to ceil(N/batch_size).
    """
    def __init__(self, embedding_service, batch_size: int = 20, flush_interval: float = 0.5):
        self.service = embedding_service
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: list[tuple[str, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._flush_task = None

    async def embed(self, text: str) -> list[float]:
        future = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._queue.append((text, future))
            if len(self._queue) >= self.batch_size:
                await self._flush()
            elif not self._flush_task:
                self._flush_task = asyncio.create_task(self._delayed_flush())
        return await future

    async def _flush(self):
        if not self._queue:
            return
        batch = self._queue[:self.batch_size]
        self._queue = self._queue[self.batch_size:]
        texts = [t for t, _ in batch]
        embeddings = await self.service.embed_batch(texts)
        for (_, future), embedding in zip(batch, embeddings):
            future.set_result(embedding)

    async def _delayed_flush(self):
        await asyncio.sleep(self.flush_interval)
        async with self._lock:
            await self._flush()
            self._flush_task = None
```

### 4. Database Indexes

```sql
-- High-impact indexes for frequent queries
CREATE INDEX idx_execution_traces_agent_created
  ON execution_traces (agent_id, created_at DESC);

CREATE INDEX idx_memories_agent_created
  ON memories (agent_id, created_at DESC);

CREATE INDEX idx_messages_conversation_created
  ON messages (conversation_id, created_at DESC);

CREATE INDEX idx_usage_records_agent_date
  ON usage_records (agent_id, created_at DESC);

CREATE INDEX idx_tasks_assignee_status
  ON tasks (assignee_agent_id, status);

CREATE INDEX idx_audit_log_created
  ON audit_log (created_at DESC);

CREATE INDEX idx_outcomes_agent_created
  ON outcomes (agent_id, created_at DESC);
```

### 5. Precomputed Agent Context

```python
# backend/app/core/agent_context_cache.py

class AgentContextCache:
    """
    Cache the assembled agent context (system prompt + tools + core memories).
    Invalidate on: agent config change, skill attach/detach, core memory edit.
    """
    CACHE_TTL = 300  # 5 minutes

    async def get_context(self, agent_id: str) -> Optional[dict]:
        key = f"agent_ctx:{agent_id}"
        cached = await redis.get(key)
        return json.loads(cached) if cached else None

    async def set_context(self, agent_id: str, context: dict):
        key = f"agent_ctx:{agent_id}"
        await redis.setex(key, self.CACHE_TTL, json.dumps(context))

    async def invalidate(self, agent_id: str):
        await redis.delete(f"agent_ctx:{agent_id}")
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/core/prompt_cache.py` | Create | Redis-based LLM response cache |
| `backend/app/core/conversation_window.py` | Create | Windowed history with rolling summary |
| `backend/app/core/embedding_batcher.py` | Create | Batch embedding queue |
| `backend/app/core/agent_context_cache.py` | Create | Precomputed agent context cache |
| `backend/app/core/orchestrator.py` | Modify | Use prompt cache, conversation window, context cache |
| `backend/app/core/memory_service.py` | Modify | Use embedding batcher |
| `backend/app/main.py` | Modify | Run index migration on startup (one-time) |

---

## Phase 5.5 — Public-Facing Autonomous Agent

### Problem Statement

Sutra can monitor social trends (Social Pulse) but can't post, reply, or engage. No Twitter/X or LinkedIn integration. No content pipeline from insight to publication.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    CONTENT PIPELINE                            │
│                                                                │
│  Social Pulse ──→ Trend Detector ──→ Content Planner          │
│  (trending data)   (alerts on spikes)  (weekly content cal)   │
│                                           ↓                    │
│                                    Content Drafter              │
│                                    (per-channel format)        │
│                                           ↓                    │
│                                    Approval Gate               │
│                                    (human review)              │
│                                           ↓                    │
│                              ┌─────────┬──────────┐           │
│                              ↓         ↓          ↓           │
│                          Twitter/X  LinkedIn   Telegram        │
│                              ↓         ↓          ↓           │
│                         Engagement  Engagement  Engagement     │
│                         Monitor     Monitor     Monitor        │
│                              ↓         ↓          ↓           │
│                          ┌───┴─────────┴──────────┘           │
│                          ↓                                     │
│                    Analytics Dashboard                         │
│                    (reach, engagement, conversion)             │
└──────────────────────────────────────────────────────────────┘
```

### 1. Twitter/X Integration

```python
# backend/app/integrations/twitter.py

class TwitterClient:
    """Twitter/X API v2 integration."""

    def __init__(self, bearer_token: str, api_key: str, api_secret: str,
                 access_token: str, access_secret: str):
        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=api_key, consumer_secret=api_secret,
            access_token=access_token, access_token_secret=access_secret
        )

    async def post_tweet(self, text: str, reply_to: str = None, media_ids: list = None) -> dict:
        """Post a tweet. Max 280 chars. Returns tweet ID and URL."""

    async def get_mentions(self, since_id: str = None) -> list[dict]:
        """Get recent mentions/replies to our account."""

    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet."""

    async def follow_user(self, user_id: str) -> bool:
        """Follow a user."""

    async def get_tweet_metrics(self, tweet_id: str) -> dict:
        """Get impressions, likes, retweets, replies for a tweet."""

# backend/app/tools/twitter_tools.py

TWITTER_TOOL_IDS = {"post_tweet", "get_mentions", "reply_to_tweet",
                     "like_tweet", "get_tweet_metrics"}

def post_tweet(content: str, reply_to_id: str = None) -> str:
    """Post a tweet. Content must be under 280 characters.
    Requires human approval if this is a new post (not a reply)."""

def reply_to_tweet(tweet_id: str, content: str) -> str:
    """Reply to a specific tweet."""

def get_mentions(count: int = 20) -> str:
    """Get recent mentions of our account."""

def get_tweet_metrics(tweet_id: str) -> str:
    """Get engagement metrics for a tweet."""
```

### 2. LinkedIn Integration

```python
# backend/app/integrations/linkedin.py

class LinkedInClient:
    """LinkedIn API integration via OAuth2."""

    async def create_post(self, text: str, visibility: str = "PUBLIC") -> dict:
        """Create a LinkedIn post. Returns post URN."""

    async def get_post_stats(self, post_urn: str) -> dict:
        """Get impressions, likes, comments, shares."""

    async def comment_on_post(self, post_urn: str, comment: str) -> dict:
        """Comment on a LinkedIn post."""

# backend/app/tools/linkedin_tools.py
LINKEDIN_TOOL_IDS = {"linkedin_post", "linkedin_comment", "linkedin_metrics"}
```

### 3. Persona Engine

```python
# backend/app/models/persona.py

class SocialPersona(Base):
    """Defines voice/tone for social media interactions."""
    __tablename__ = "social_personas"

    id = Column(UUID, primary_key=True, default=uuid4)
    agent_id = Column(UUID, ForeignKey("agents.id"))
    channel = Column(String)  # "twitter", "linkedin", "telegram", "all"

    # Voice configuration
    tone = Column(String, default="professional")      # professional, casual, witty, technical
    topics = Column(JSON)                               # List of topics to engage with
    avoid_topics = Column(JSON)                         # Topics to never engage with
    style_guidelines = Column(Text)                     # Custom style instructions
    max_daily_posts = Column(Integer, default=3)
    posting_hours = Column(JSON, default=[9, 12, 17])   # Preferred hours (UTC)

    # Safety
    require_approval_for = Column(JSON, default=["new_post"])  # Which actions need approval
    blocklist_words = Column(JSON, default=[])           # Words to never use
    content_policy = Column(Text)                        # Additional content rules

    # Templates
    post_templates = Column(JSON)  # Optional structural templates for posts
```

### 4. Content Pipeline Workflow

```python
# Pre-built workflow template for the Ambassador agent

AMBASSADOR_WORKFLOW = {
    "name": "Social Content Pipeline",
    "nodes": [
        {
            "id": "trend_check",
            "type": "agent",
            "config": {"prompt": "Check Social Pulse for trending topics in our niches. "
                                "Pick the most relevant trend for our audience."}
        },
        {
            "id": "draft_content",
            "type": "agent",
            "config": {"prompt": "Draft a tweet and LinkedIn post about this trend. "
                                "Follow persona guidelines. Be insightful, not generic."}
        },
        {
            "id": "review_gate",
            "type": "approval_gate",
            "config": {"category": "external", "timeout_minutes": 240,
                      "context": "Review social media posts before publishing"}
        },
        {
            "id": "publish_twitter",
            "type": "agent",
            "config": {"prompt": "Post the approved tweet using post_tweet tool."}
        },
        {
            "id": "publish_linkedin",
            "type": "agent",
            "config": {"prompt": "Post the approved content to LinkedIn using linkedin_post tool."}
        },
        {
            "id": "schedule_metrics",
            "type": "timer",
            "config": {"delay_minutes": 120}
        },
        {
            "id": "collect_metrics",
            "type": "agent",
            "config": {"prompt": "Collect engagement metrics for today's posts. "
                                "Store insights for future content strategy."}
        }
    ]
}
```

### 5. Engagement Analytics

```python
# backend/app/models/social_post.py

class SocialPost(Base):
    """Tracks all social media posts and their performance."""
    __tablename__ = "social_posts"

    id = Column(UUID, primary_key=True, default=uuid4)
    agent_id = Column(UUID, ForeignKey("agents.id"))
    channel = Column(String)                    # twitter, linkedin, telegram
    external_id = Column(String)                # Platform-specific post ID
    content = Column(Text)
    posted_at = Column(DateTime)
    approval_id = Column(UUID, nullable=True)   # Link to ApprovalRequest

    # Metrics (updated periodically)
    impressions = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    reposts = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0)  # (likes+replies+reposts) / impressions

    # Content analysis
    topic_tags = Column(JSON)                   # Auto-detected topics
    sentiment = Column(String)                  # positive, neutral, negative
    source_trend_id = Column(UUID, nullable=True)  # Which Social Pulse trend inspired this
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/integrations/twitter.py` | Create | Twitter/X API v2 client |
| `backend/app/integrations/linkedin.py` | Create | LinkedIn API client |
| `backend/app/tools/twitter_tools.py` | Create | 5 Twitter agent tools |
| `backend/app/tools/linkedin_tools.py` | Create | 3 LinkedIn agent tools |
| `backend/app/models/persona.py` | Create | SocialPersona model |
| `backend/app/models/social_post.py` | Create | SocialPost tracking model |
| `backend/app/core/content_pipeline.py` | Create | Content pipeline orchestrator |
| `backend/app/api/routes/social.py` | Create | Social management API endpoints |
| `backend/app/tools/registry.py` | Modify | Register Twitter + LinkedIn tools |
| `frontend/app/social-pulse/page.tsx` | Modify | Add publishing + metrics tabs |
| `frontend/app/social-pulse/posts/page.tsx` | Create | Post history + engagement dashboard |

---

## Phase 5.6 — Sandbox & Security Hardening

### Problem Statement

OS tools run on the host machine with full access. No resource limits, no network isolation, no output validation pipeline. Required before any public-facing agent.

### 1. Docker-Based Tool Execution

```python
# backend/app/core/sandbox.py

class Sandbox:
    """
    Executes tool commands in ephemeral Docker containers.
    Each execution gets a fresh container that is destroyed after use.
    """
    IMAGE = "sutra-sandbox:latest"  # Minimal image with Python, Node, common CLI tools
    DEFAULT_TIMEOUT = 30            # seconds
    DEFAULT_MEMORY = "256m"
    DEFAULT_CPU = "0.5"

    def __init__(self, docker_client=None):
        self.client = docker_client or docker.from_env()

    async def execute(self, command: str, config: SandboxConfig = None) -> SandboxResult:
        config = config or SandboxConfig()

        container = self.client.containers.run(
            self.IMAGE,
            command=["sh", "-c", command],
            detach=True,
            mem_limit=config.memory_limit or self.DEFAULT_MEMORY,
            cpu_period=100000,
            cpu_quota=int(float(config.cpu_limit or self.DEFAULT_CPU) * 100000),
            network_mode="none" if not config.allow_network else "bridge",
            read_only=not config.allow_write,
            volumes=config.volumes or {},
            environment=config.env_vars or {},
        )

        try:
            result = container.wait(timeout=config.timeout or self.DEFAULT_TIMEOUT)
            logs = container.logs(stdout=True, stderr=True).decode()
            return SandboxResult(
                exit_code=result["StatusCode"],
                stdout=logs,
                timed_out=False,
            )
        except docker.errors.ContainerError:
            return SandboxResult(exit_code=1, stdout="Container error", timed_out=False)
        except Exception:
            container.kill()
            return SandboxResult(exit_code=-1, stdout="Execution timed out", timed_out=True)
        finally:
            container.remove(force=True)

@dataclass
class SandboxConfig:
    timeout: int = 30
    memory_limit: str = "256m"
    cpu_limit: str = "0.5"
    allow_network: bool = False
    allow_write: bool = False
    volumes: dict = None
    env_vars: dict = None

@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    timed_out: bool
```

### 2. Output Guardrails Pipeline

```python
# backend/app/core/guardrails.py

class GuardrailsPipeline:
    """
    Validates agent outputs before they reach the user or external systems.
    Inspired by OpenAI Agents SDK Guardrails primitive.
    """
    def __init__(self):
        self.validators: list[OutputValidator] = [
            PIIDetector(),
            ContentPolicyChecker(),
            FormatValidator(),
            InjectionDetector(),
        ]

    async def validate(self, output: str, context: GuardrailContext) -> GuardrailResult:
        issues = []
        sanitized = output

        for validator in self.validators:
            result = await validator.check(sanitized, context)
            if not result.passed:
                issues.extend(result.issues)
                if result.sanitized:
                    sanitized = result.sanitized
                if result.block:
                    return GuardrailResult(
                        passed=False, blocked=True,
                        reason=f"Blocked by {validator.name}: {result.issues[0]}",
                        original=output
                    )

        return GuardrailResult(
            passed=len(issues) == 0,
            blocked=False,
            issues=issues,
            sanitized=sanitized,
            original=output,
        )

class PIIDetector(OutputValidator):
    """Detect and redact PII (emails, phone numbers, SSNs, credit cards)."""
    name = "pii_detector"
    PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
    }

class ContentPolicyChecker(OutputValidator):
    """Check output against content policy (hate speech, violence, etc.)."""
    name = "content_policy"

class InjectionDetector(OutputValidator):
    """Detect prompt injection attempts in tool outputs."""
    name = "injection_detector"
```

### 3. Network Policies

```python
# backend/app/core/network_policy.py

class NetworkPolicy:
    """Per-agent network access rules."""

    # Default whitelist for all agents
    DEFAULT_ALLOWED = [
        "api.openai.com", "api.anthropic.com", "api.groq.com",
        "generativelanguage.googleapis.com",
    ]

    def __init__(self, agent_config: dict):
        self.allowed_domains = set(self.DEFAULT_ALLOWED)
        self.allowed_domains.update(agent_config.get("allowed_domains", []))
        self.blocked_domains = set(agent_config.get("blocked_domains", []))

    def is_allowed(self, url: str) -> bool:
        domain = urlparse(url).hostname
        if domain in self.blocked_domains:
            return False
        if self.allowed_domains and domain not in self.allowed_domains:
            return False
        return True
```

### 4. Anomaly Detection

```python
# backend/app/core/anomaly_detector.py

class AnomalyDetector:
    """Detects unusual agent behavior patterns."""

    async def check_agent(self, agent_id: str) -> list[Anomaly]:
        anomalies = []

        # 1. Cost spike: today's cost > 3x 7-day average
        daily_cost = await self._get_today_cost(agent_id)
        avg_cost = await self._get_avg_daily_cost(agent_id, days=7)
        if avg_cost > 0 and daily_cost > avg_cost * 3:
            anomalies.append(Anomaly(
                type="cost_spike", severity="high",
                message=f"Today's cost ${daily_cost:.2f} is {daily_cost/avg_cost:.1f}x the 7-day average"
            ))

        # 2. Error spike: error rate > 50% in last hour
        recent_traces = await self._get_recent_traces(agent_id, hours=1)
        if len(recent_traces) > 5:
            error_rate = sum(1 for t in recent_traces if t.had_error) / len(recent_traces)
            if error_rate > 0.5:
                anomalies.append(Anomaly(
                    type="error_spike", severity="critical",
                    message=f"Error rate {error_rate:.0%} in last hour ({len(recent_traces)} invocations)"
                ))

        # 3. Unusual tool usage: tool used that agent hasn't used in 30 days
        recent_tools = await self._get_recent_tool_usage(agent_id, hours=24)
        historical_tools = await self._get_historical_tool_usage(agent_id, days=30)
        novel_tools = recent_tools - historical_tools
        if novel_tools:
            anomalies.append(Anomaly(
                type="unusual_tool", severity="medium",
                message=f"Agent used unfamiliar tools: {novel_tools}"
            ))

        return anomalies

# Scheduler: runs every 15 minutes
async def anomaly_scan():
    for agent_id in await get_active_agent_ids():
        anomalies = await detector.check_agent(agent_id)
        for a in anomalies:
            if a.severity == "critical":
                await notify_admin(a)
                if AUTO_PAUSE_ON_CRITICAL:
                    await agent_manager.stop_agent(agent_id, reason=f"Anomaly: {a.message}")
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/core/sandbox.py` | Create | Docker-based isolated execution |
| `backend/app/core/guardrails.py` | Create | Output validation pipeline |
| `backend/app/core/network_policy.py` | Create | Per-agent network access rules |
| `backend/app/core/anomaly_detector.py` | Create | Behavioral anomaly detection |
| `backend/Dockerfile.sandbox` | Create | Minimal sandbox container image |
| `backend/app/tools/os_tools.py` | Modify | Route commands through sandbox |
| `backend/app/core/orchestrator.py` | Modify | Apply guardrails to all outputs |
| `backend/app/core/scheduler.py` | Modify | Add anomaly scan job |
| `backend/app/models/agent.py` | Modify | Add network_policy, sandbox_config fields |

---

## Phase 5.7 — Browser Automation

### Problem Statement

Agents can scrape web pages (Playwright) but can't interact — no clicking, form filling, navigation, or visual understanding. This limits agents to API-only interactions.

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  BROWSER AGENT TOOL                       │
│                                                           │
│  Agent calls: browse_web(url, instruction)                │
│       ↓                                                   │
│  BrowserController                                        │
│  ├── Launch/reuse Playwright browser                      │
│  ├── Navigate to URL                                      │
│  ├── Take screenshot                                      │
│  ├── Send screenshot + instruction to vision LLM          │
│  ├── LLM returns action plan (click X, type Y, etc.)      │
│  ├── Execute actions via Playwright                        │
│  ├── Take new screenshot                                  │
│  ├── Repeat until task complete or max_steps reached      │
│  └── Return result (extracted data, confirmation, etc.)   │
└──────────────────────────────────────────────────────────┘
```

### Implementation

```python
# backend/app/tools/browser_tools.py

BROWSER_TOOL_IDS = {"browse_web", "take_screenshot", "browser_click", "browser_type", "browser_extract"}

class BrowserController:
    """Interactive browser control using Playwright + Vision LLM."""

    MAX_STEPS = 10
    SCREENSHOT_WIDTH = 1280
    SCREENSHOT_HEIGHT = 720

    def __init__(self):
        self.sessions: dict[str, BrowserSession] = {}

    async def browse_web(self, url: str, instruction: str, agent_id: str) -> str:
        """
        Navigate to URL and follow instruction using vision-guided actions.
        Returns the result of the interaction.
        """
        session = await self._get_or_create_session(agent_id)
        page = session.page

        await page.goto(url, wait_until="networkidle", timeout=15000)

        for step in range(self.MAX_STEPS):
            # Take screenshot
            screenshot = await page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Ask vision LLM what to do
            action = await self._get_next_action(
                screenshot_b64, instruction, step, session.action_history
            )

            if action["type"] == "done":
                return action.get("result", "Task completed")

            if action["type"] == "click":
                await page.click(action["selector"], timeout=5000)
            elif action["type"] == "type":
                await page.fill(action["selector"], action["text"])
            elif action["type"] == "scroll":
                await page.evaluate(f"window.scrollBy(0, {action.get('pixels', 300)})")
            elif action["type"] == "navigate":
                await page.goto(action["url"], wait_until="networkidle")
            elif action["type"] == "extract":
                content = await page.inner_text(action.get("selector", "body"))
                return content[:2000]  # Limit extracted text
            elif action["type"] == "wait":
                await page.wait_for_timeout(action.get("ms", 2000))

            session.action_history.append(action)

        return "Max steps reached without completing the task"

    async def _get_next_action(self, screenshot_b64: str, instruction: str,
                                step: int, history: list) -> dict:
        """Use multimodal LLM to determine next browser action."""
        messages = [
            {"role": "system", "content": BROWSER_AGENT_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"""
Instruction: {instruction}
Step: {step + 1}/{self.MAX_STEPS}
Previous actions: {json.dumps(history[-3:])}

What should I do next? Respond with a JSON action:
- {{"type": "click", "selector": "CSS selector"}}
- {{"type": "type", "selector": "CSS selector", "text": "text to type"}}
- {{"type": "scroll", "pixels": 300}}
- {{"type": "navigate", "url": "..."}}
- {{"type": "extract", "selector": "CSS selector"}}
- {{"type": "wait", "ms": 2000}}
- {{"type": "done", "result": "summary of what was accomplished"}}
"""},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
            ]}
        ]
        response = await vision_llm.ainvoke(messages)
        return json.loads(extract_json(response.content))

class BrowserSession:
    """Persistent browser session with cookies and state."""
    def __init__(self, browser, context, page):
        self.browser = browser
        self.context = context
        self.page = page
        self.action_history: list[dict] = []
        self.created_at = datetime.utcnow()

BROWSER_AGENT_PROMPT = """You are a browser automation agent. You see a screenshot of a web page
and must determine the next action to accomplish the user's instruction.

Rules:
- Use CSS selectors for click/type actions. Prefer IDs, then classes, then text content.
- If you can't find the right element, try scrolling first.
- Never submit forms with sensitive data unless explicitly instructed.
- If the task is complete, respond with type "done" and a summary.
- Respect robots.txt and rate limits. Do not spam actions.
- If a CAPTCHA appears, respond with type "done" and result "CAPTCHA detected, cannot proceed".
"""
```

### Rate Limiting & Safety

```python
# Per-domain rate limiting
class BrowserRateLimiter:
    """Enforce per-domain request limits to avoid abuse."""
    MAX_REQUESTS_PER_DOMAIN = 10  # per minute

    async def check(self, domain: str) -> bool:
        key = f"browser_rate:{domain}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        return count <= self.MAX_REQUESTS_PER_DOMAIN

# Robots.txt compliance
class RobotsChecker:
    """Check robots.txt before browsing."""
    _cache: dict[str, RobotFileParser] = {}

    async def is_allowed(self, url: str) -> bool:
        domain = urlparse(url).netloc
        if domain not in self._cache:
            parser = RobotFileParser()
            parser.set_url(f"https://{domain}/robots.txt")
            try:
                parser.read()
            except:
                return True  # If robots.txt unavailable, allow
            self._cache[domain] = parser
        return self._cache[domain].can_fetch("SutraBot", url)
```

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `backend/app/tools/browser_tools.py` | Create | BrowserController + 5 tools |
| `backend/app/core/browser_rate_limiter.py` | Create | Per-domain rate limiting |
| `backend/app/tools/registry.py` | Modify | Register BROWSER_TOOL_IDS |
| `frontend/app/settings/page.tsx` | Modify | Browser tool configuration UI |

---

## Implementation Priority & Dependencies

### Dependency Graph

```
                    ┌─────────────┐
                    │  5.2 Self-  │
                    │  Healing    │ ← START HERE (no dependencies)
                    │  (P0)       │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ↓            ↓            ↓
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ 5.4 Perf   │ │ 5.1 Memory│ │ 5.6 Sand-│
     │ & Speed    │ │ Revolution│ │ box      │
     │ (P0)       │ │ (P1)      │ │ (P1)     │
     └──────┬─────┘ └─────┬─────┘ └────┬─────┘
            │              │            │
            └──────┬───────┘            │
                   ↓                    │
          ┌────────────────┐            │
          │ 5.3 Self-      │            │
          │ Improvement    │            │
          │ (P1)           │            │
          └────────────────┘            │
                                        │
              ┌─────────────────────────┘
              ↓
     ┌────────────┐     ┌──────────────┐
     │ 5.7 Browser│     │ 5.5 Public   │
     │ Automation │────→│ Agent        │
     │ (P2)       │     │ (P2)         │
     └────────────┘     └──────────────┘
                              ↑
                  Requires: 5.6 + 5.3 + 5.1
```

### Sprint Calendar

| Sprint | Weeks | Phase | Deliverable |
|--------|-------|-------|-------------|
| 21-22 | 27-28 | **5.2 + 5.4** | Retry, circuit breaker, watchdog, DB indexes, prompt cache, conversation windowing |
| 23-24 | 29-31 | **5.1** | pgvector migration, 3-tier memory, self-editing tools, decay + consolidation |
| 25-26 | 32-33 | **5.6** | Docker sandbox, guardrails pipeline, network policy, anomaly detection |
| 27-28 | 34-35 | **5.3** | Outcome tracking, scoring, prompt A/B, pattern mining, playbook gen |
| 29-30 | 36-37 | **5.7** | Interactive Playwright, vision-guided browsing, session management |
| 31-32 | 37-38 | **5.5** | Twitter/X, LinkedIn, content pipeline, persona engine, ambassador template |

### Estimated Effort

| Phase | Backend Days | Frontend Days | Total |
|-------|-------------|---------------|-------|
| 5.1 Memory | 12 | 3 | 15 |
| 5.2 Self-Healing | 14 | 2 | 16 |
| 5.3 Self-Improvement | 14 | 4 | 18 |
| 5.4 Performance | 8 | 1 | 9 |
| 5.5 Public Agent | 12 | 5 | 17 |
| 5.6 Sandbox | 10 | 2 | 12 |
| 5.7 Browser | 8 | 2 | 10 |
| **Total** | **78** | **19** | **97 days** |

### Key Technical Risks

| Risk | Mitigation |
|------|------------|
| pgvector migration breaks existing memories | Run migration in parallel; dual-write during transition; rollback script ready |
| Docker sandbox adds latency to every tool call | Use container pooling (pre-warm containers); only sandbox untrusted tools |
| Vision LLM browser control is unreliable | Fallback to CSS-selector-only mode; cap max_steps; human escalation on failure |
| Twitter API rate limits / account suspension | Conservative rate limits (well below API caps); approval gate for all posts; content policy checks |
| Self-improvement creates feedback loops | Human review gate for auto-promoted prompts; score changes capped at ±10% per cycle |
| Prompt caching returns stale responses | Short TTL (1h default); cache key includes recent messages; bypass cache for tool-using queries |
