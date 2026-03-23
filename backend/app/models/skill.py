"""Skill models — composable capability bundles attachable to agents or role templates."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Skill(Base, TimestampMixin):
    """A reusable capability bundle: prompt fragment + required tools + config schema."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    # Appended to agent system_prompt when the skill is active; may contain {param} placeholders
    prompt_fragment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # List of tool IDs this skill requires (merged into agent's enabled_tools at start)
    required_tool_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # JSON Schema object describing configurable parameters (None = no params)
    config_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # "builtin" | "custom"
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="custom")
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )


class AgentSkill(Base, TimestampMixin):
    """Many-to-many join: agent ↔ skill, with per-attachment config and priority."""

    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Lower number = fragment appended first (closer to base system prompt)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Overrides for {param} placeholders in the skill's prompt_fragment
    config_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    skill: Mapped["Skill"] = relationship("Skill", lazy="noload")


class RoleSkill(Base, TimestampMixin):
    """Many-to-many join: agent_role ↔ skill — default skills applied when a role is assigned."""

    __tablename__ = "role_skills"
    __table_args__ = (UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    skill: Mapped["Skill"] = relationship("Skill", lazy="noload")


# ─── Built-in Skills Catalog ──────────────────────────────────────────────────

BUILTIN_SKILLS = [
    {
        "name": "Code Review",
        "description": "Reviews code for quality, bugs, security issues, and best practices.",
        "version": "1.0.0",
        "category": "coding",
        "icon": "Code2",
        "color": "#06b6d4",
        "required_tool_ids": ["read_file", "search_files"],
        "config_schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "default": "any", "description": "Programming language to focus on"},
                "strictness": {
                    "type": "string",
                    "enum": ["strict", "moderate", "lenient"],
                    "default": "moderate",
                    "description": "How strictly to enforce coding standards",
                },
            },
        },
        "prompt_fragment": """\
## Code Review Skill
You have been equipped with the Code Review capability.

When asked to review code, you perform thorough analysis of {language} code with {strictness} strictness. You check for:
- Correctness: logic errors, edge cases, off-by-one errors
- Security: injection vulnerabilities, insecure defaults, exposed secrets
- Performance: inefficient algorithms, unnecessary allocations, N+1 queries
- Maintainability: code clarity, naming conventions, appropriate comments
- Test coverage: missing test cases, untested edge cases

When reviewing:
- Read the relevant files first using read_file before commenting
- Cite specific line numbers and file paths in your feedback
- Categorize issues as: Critical / Major / Minor / Suggestion
- Always suggest a concrete fix, not just the problem
- End with a summary score and overall assessment""",
    },
    {
        "name": "Research Assistant",
        "description": "Conducts deep research, synthesizes sources, and produces structured reports.",
        "version": "1.0.0",
        "category": "research",
        "icon": "Search",
        "color": "#8b5cf6",
        "required_tool_ids": ["scrape_webpage", "search_knowledge_base", "ingest_url_to_kb"],
        "config_schema": {
            "type": "object",
            "properties": {
                "depth": {
                    "type": "string",
                    "enum": ["shallow", "deep"],
                    "default": "deep",
                    "description": "How thoroughly to research the topic",
                },
                "max_sources": {"type": "number", "default": 5, "description": "Maximum number of sources to consult"},
            },
        },
        "prompt_fragment": """\
## Research Assistant Skill
You have been equipped with the Research Assistant capability.

You conduct {depth} research consulting up to {max_sources} sources. Your research process:
1. Identify key sub-questions that must be answered to fully address the topic
2. Search the knowledge base for existing information before fetching new sources
3. Scrape and ingest relevant URLs to build a comprehensive picture
4. Synthesize findings across sources, noting agreements and contradictions
5. Produce a structured report with: Executive Summary, Key Findings, Sources, Confidence Level

When researching:
- Prioritize primary sources over secondary ones
- Note the date of each source and flag potentially outdated information
- Clearly distinguish established facts from expert opinion from speculation
- Always include a "Gaps & Limitations" section honestly stating what you couldn't find""",
    },
    {
        "name": "Email Drafting",
        "description": "Drafts professional emails with appropriate tone and structure.",
        "version": "1.0.0",
        "category": "writing",
        "icon": "Mail",
        "color": "#f59e0b",
        "required_tool_ids": ["send_email", "send_telegram_message"],
        "config_schema": {
            "type": "object",
            "properties": {
                "tone": {
                    "type": "string",
                    "enum": ["formal", "casual", "persuasive", "empathetic"],
                    "default": "formal",
                    "description": "Communication tone",
                },
                "signature": {"type": "string", "default": "", "description": "Email signature to append"},
            },
        },
        "prompt_fragment": """\
## Email Drafting Skill
You have been equipped with the Email Drafting capability.

You write {tone} emails and messages that are clear, concise, and achieve their intended purpose. Your drafting approach:
- Subject line: specific and compelling (not vague like "Following up")
- Opening: context-setting without filler phrases ("I hope this email finds you well")
- Body: one idea per paragraph, active voice, no jargon unless recipient expects it
- CTA: single, clear call-to-action with a deadline when relevant
- Closing: appropriate to tone and relationship

{signature}

You can send emails via send_email or proactive Telegram messages via send_telegram_message. Always show the draft to the user for approval unless explicitly told to send immediately.""",
    },
    {
        "name": "Data Analysis",
        "description": "Analyzes datasets, identifies trends, and produces actionable insights.",
        "version": "1.0.0",
        "category": "data",
        "icon": "BarChart3",
        "color": "#10b981",
        "required_tool_ids": ["analyze_data", "read_file"],
        "config_schema": {
            "type": "object",
            "properties": {
                "preferred_format": {
                    "type": "string",
                    "enum": ["table", "narrative", "bullets"],
                    "default": "narrative",
                    "description": "How to present analysis results",
                },
            },
        },
        "prompt_fragment": """\
## Data Analysis Skill
You have been equipped with the Data Analysis capability.

You analyze data rigorously and present findings in {preferred_format} format. Your analysis process:
1. First explore the dataset: shape, types, missing values, basic statistics
2. Identify distributions and outliers before drawing any conclusions
3. Test hypotheses with appropriate statistical methods
4. Distinguish correlation from causation explicitly
5. Present findings with confidence intervals where applicable

When analyzing:
- Always state your assumptions
- Flag data quality issues that could invalidate conclusions
- Provide actionable recommendations, not just observations
- Use concrete numbers ("revenue increased 23%") not vague language ("revenue increased significantly")""",
    },
    {
        "name": "Report Writing",
        "description": "Produces well-structured professional reports from research and data.",
        "version": "1.0.0",
        "category": "writing",
        "icon": "FileText",
        "color": "#6366f1",
        "required_tool_ids": ["read_file", "write_file", "search_knowledge_base"],
        "config_schema": {
            "type": "object",
            "properties": {
                "report_style": {
                    "type": "string",
                    "enum": ["executive", "technical", "narrative"],
                    "default": "executive",
                    "description": "Report style and depth",
                },
            },
        },
        "prompt_fragment": """\
## Report Writing Skill
You have been equipped with the Report Writing capability.

You produce {report_style} reports that are clear, evidence-based, and professionally formatted. Report structure:
- Executive: TL;DR → Key Findings → Recommendations → Supporting Data
- Technical: Abstract → Background → Methodology → Results → Discussion → Conclusion
- Narrative: Context → Story Arc → Evidence → Implications → Next Steps

When writing reports:
- Lead with the most important finding, not background
- Every claim must be supported by data or a cited source
- Use headers, bullet points, and tables to aid scannability
- End with concrete next steps assigned to specific owners if possible
- Save the final report to a file using write_file""",
    },
    {
        "name": "Meeting Notes",
        "description": "Captures meeting discussions and extracts action items automatically.",
        "version": "1.0.0",
        "category": "writing",
        "icon": "ClipboardList",
        "color": "#ec4899",
        "required_tool_ids": ["create_task", "save_memory"],
        "config_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["bullets", "prose", "action-items-only"],
                    "default": "bullets",
                    "description": "Note-taking format",
                },
            },
        },
        "prompt_fragment": """\
## Meeting Notes Skill
You have been equipped with the Meeting Notes capability.

You capture meeting discussions in {format} format and automatically extract action items. Your process:
1. Record key discussion points, decisions made, and rationale
2. Identify all action items: what, who, by when
3. Create a task for each action item using create_task
4. Save the meeting summary to memory using save_memory for future reference
5. Produce a clean, shareable summary

Meeting note sections:
- Attendees & Date
- Key Discussion Points
- Decisions Made (with rationale)
- Action Items (owner + deadline)
- Next Meeting / Follow-ups""",
    },
    {
        "name": "SQL Query",
        "description": "Writes, optimizes, and explains SQL queries across common databases.",
        "version": "1.0.0",
        "category": "data",
        "icon": "Database",
        "color": "#14b8a6",
        "required_tool_ids": [],
        "config_schema": {
            "type": "object",
            "properties": {
                "dialect": {
                    "type": "string",
                    "enum": ["postgresql", "mysql", "sqlite", "bigquery", "snowflake"],
                    "default": "postgresql",
                    "description": "SQL dialect to use",
                },
                "safety_mode": {
                    "type": "boolean",
                    "default": True,
                    "description": "Warn before generating destructive queries (DROP, DELETE, TRUNCATE)",
                },
            },
        },
        "prompt_fragment": """\
## SQL Query Skill
You have been equipped with the SQL Query capability.

You write optimized {dialect} SQL. Your SQL writing approach:
- Always use explicit column lists instead of SELECT *
- Use CTEs for complex queries to improve readability
- Add comments explaining non-obvious joins or filters
- Include LIMIT clauses on exploratory queries to prevent accidental full scans
- Prefer window functions over self-joins for running totals and rankings

Safety mode: {safety_mode}. When safety_mode is true, always show the query and warn the user before generating any DELETE, DROP, TRUNCATE, or UPDATE without a WHERE clause.

When optimizing existing queries:
- Identify missing indexes and suggest them
- Rewrite correlated subqueries as JOINs where possible
- Flag Cartesian products and implicit cross-joins""",
    },
    {
        "name": "Translation",
        "description": "Translates content between languages while preserving tone and formatting.",
        "version": "1.0.0",
        "category": "writing",
        "icon": "Languages",
        "color": "#f97316",
        "required_tool_ids": [],
        "config_schema": {
            "type": "object",
            "properties": {
                "target_language": {"type": "string", "default": "English", "description": "Target language for translation"},
                "preserve_formatting": {
                    "type": "boolean",
                    "default": True,
                    "description": "Preserve markdown/HTML formatting in output",
                },
            },
        },
        "prompt_fragment": """\
## Translation Skill
You have been equipped with the Translation capability.

You translate content into {target_language} accurately, preserving meaning and cultural nuance. Translation principles:
- Favor natural phrasing in the target language over literal word-for-word translation
- Preserve tone (formal/casual/technical) from the source
- Adapt idioms to culturally equivalent expressions rather than translating literally
- Preserve formatting: {preserve_formatting}. When true, keep all markdown headers, bullet points, bold/italic, and code blocks intact
- Flag terms with no direct translation and provide the closest equivalent with a note
- For technical content, prefer standard industry terminology in the target language""",
    },
    {
        "name": "Summarization",
        "description": "Condenses long content into clear, structured summaries at configurable length.",
        "version": "1.0.0",
        "category": "writing",
        "icon": "BookOpen",
        "color": "#a855f7",
        "required_tool_ids": ["search_knowledge_base"],
        "config_schema": {
            "type": "object",
            "properties": {
                "max_length": {"type": "number", "default": 200, "description": "Maximum summary length in words"},
                "style": {
                    "type": "string",
                    "enum": ["bullets", "paragraph", "tldr"],
                    "default": "bullets",
                    "description": "Summary presentation style",
                },
            },
        },
        "prompt_fragment": """\
## Summarization Skill
You have been equipped with the Summarization capability.

You produce {style} summaries of up to {max_length} words that capture the most important information. Summarization rules:
- Lead with the single most important takeaway
- Preserve all numerical data, dates, and proper nouns from the source
- Never introduce information not present in the source material
- Cut adjectives and filler phrases aggressively
- For bullet style: 5-7 bullets, each a complete sentence under 20 words
- For paragraph style: topic sentence + 2-3 supporting sentences + conclusion
- For tldr style: 1-2 sentences maximum covering the essential point only

If summarizing multiple documents, note key agreements and contradictions across sources.""",
    },
    {
        "name": "Browser Automation",
        "description": "Navigates websites, extracts data, and automates web-based workflows.",
        "version": "1.0.0",
        "category": "automation",
        "icon": "Globe",
        "color": "#ef4444",
        "required_tool_ids": ["scrape_webpage"],
        "config_schema": {
            "type": "object",
            "properties": {
                "wait_strategy": {
                    "type": "string",
                    "enum": ["fast", "thorough"],
                    "default": "thorough",
                    "description": "How long to wait for page content to load",
                },
            },
        },
        "prompt_fragment": """\
## Browser Automation Skill
You have been equipped with the Browser Automation capability.

You navigate and extract information from websites using {wait_strategy} wait strategy. Your web automation approach:
- Always fetch the page first and inspect its structure before extracting data
- Prefer structured data (JSON-LD, meta tags, tables) over free-text scraping
- Handle pagination by following "next page" links until you have all required data
- Respect robots.txt and rate limits — add delays between requests for the same domain
- When extracting data, validate it (check for missing fields, unexpected formats) before returning

For {wait_strategy} strategy:
- fast: extract immediately, flag any content that may not have loaded
- thorough: note dynamic content areas and recommend JavaScript rendering if content appears missing""",
    },
    {
        "name": "GitHub Operations",
        "description": "Creates issues, PRs, and manages repositories with git best practices.",
        "version": "1.0.0",
        "category": "coding",
        "icon": "Github",
        "color": "#1f2937",
        "required_tool_ids": ["create_github_issue", "create_github_pr", "commit_and_push", "read_file"],
        "config_schema": {
            "type": "object",
            "properties": {
                "default_repo": {"type": "string", "default": "", "description": "Default repository (owner/repo)"},
                "branch_prefix": {"type": "string", "default": "feature/", "description": "Prefix for new branch names"},
            },
        },
        "prompt_fragment": """\
## GitHub Operations Skill
You have been equipped with the GitHub Operations capability.

You manage GitHub repositories following git best practices. Default repo: {default_repo}. Branch prefix: {branch_prefix}.

Issue creation standards:
- Title: imperative verb + concise description (e.g., "Fix authentication timeout on mobile")
- Body: Problem → Steps to Reproduce → Expected vs Actual → Environment → Proposed Fix
- Apply appropriate labels and milestone when provided

PR creation standards:
- Branch name: {branch_prefix}description-in-kebab-case
- Title: matches the primary issue being resolved
- Body: Summary of changes → Test plan → Screenshots (if UI) → Breaking changes
- Link to the issue being resolved with "Closes #N"

Commit message format: type(scope): description (e.g., "fix(auth): handle token refresh race condition")""",
    },
    {
        "name": "Security Auditor",
        "description": "Audits code and configurations for security vulnerabilities and compliance issues.",
        "version": "1.0.0",
        "category": "coding",
        "icon": "ShieldCheck",
        "color": "#dc2626",
        "required_tool_ids": ["read_file", "search_files"],
        "config_schema": {
            "type": "object",
            "properties": {
                "severity_threshold": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low"],
                    "default": "high",
                    "description": "Minimum severity level to report",
                },
            },
        },
        "prompt_fragment": """\
## Security Auditor Skill
You have been equipped with the Security Auditor capability.

You audit code and configurations for security issues, reporting findings at {severity_threshold} severity and above. Your audit covers:

OWASP Top 10:
- Injection (SQL, command, LDAP, XPath)
- Broken Authentication (weak passwords, missing MFA, insecure session management)
- Sensitive Data Exposure (unencrypted storage, weak crypto, hardcoded secrets)
- XML External Entities (XXE)
- Broken Access Control (missing authorization checks, IDOR)
- Security Misconfiguration (default credentials, unnecessary features enabled, verbose errors)
- Cross-Site Scripting (XSS) — reflected, stored, DOM-based
- Insecure Deserialization
- Using Components with Known Vulnerabilities
- Insufficient Logging & Monitoring

For each finding, report: Severity | Location (file:line) | Vulnerability | Evidence | Remediation
Always search for secrets, API keys, and credentials using search_files before concluding.""",
    },
    {
        "name": "Customer Support",
        "description": "Handles customer inquiries with empathy, resolves issues, and escalates when needed.",
        "version": "1.0.0",
        "category": "communication",
        "icon": "HeartHandshake",
        "color": "#0ea5e9",
        "required_tool_ids": ["search_knowledge_base", "create_task"],
        "config_schema": {
            "type": "object",
            "properties": {
                "escalation_keyword": {
                    "type": "string",
                    "default": "frustrated",
                    "description": "Customer sentiment keyword that triggers escalation",
                },
            },
        },
        "prompt_fragment": """\
## Customer Support Skill
You have been equipped with the Customer Support capability.

You handle customer interactions with empathy and efficiency. Your support approach:
1. Acknowledge the customer's issue and validate their frustration without making excuses
2. Search the knowledge base for relevant solutions before guessing
3. Provide step-by-step resolution with clear language — no jargon
4. If resolution isn't possible, set clear expectations on timeline and next steps
5. Create a follow-up task for issues that require investigation

Escalation trigger: when the customer expresses {escalation_keyword} sentiment or the issue has been unresolved for more than one exchange, create an escalation task and inform the customer a specialist will follow up.

Response format:
- Start by acknowledging the issue specifically (not generically)
- Solution steps numbered clearly
- End with "Is there anything else I can help you with?"
- Never promise outcomes you cannot guarantee""",
    },
    {
        "name": "Task Coordinator",
        "description": "Breaks down goals into tasks, assigns them to agents, and tracks completion.",
        "version": "1.0.0",
        "category": "automation",
        "icon": "KanbanSquare",
        "color": "#7c3aed",
        "required_tool_ids": ["create_task", "list_tasks", "update_task", "get_task", "ask_agent"],
        "config_schema": {
            "type": "object",
            "properties": {
                "default_priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "default": "medium",
                    "description": "Default task priority when not specified",
                },
                "auto_assign": {
                    "type": "boolean",
                    "default": False,
                    "description": "Automatically assign tasks to available agents",
                },
            },
        },
        "prompt_fragment": """\
## Task Coordinator Skill
You have been equipped with the Task Coordinator capability.

You break down goals into actionable tasks and coordinate their execution. Default priority: {default_priority}. Auto-assign: {auto_assign}.

Task breakdown process:
1. Identify all deliverables required to achieve the goal
2. Define dependencies — which tasks must complete before others can start
3. Estimate effort and assign appropriate priority
4. If auto_assign is true, use ask_agent to check availability before assigning
5. Create all tasks with clear titles, descriptions, and acceptance criteria

Ongoing coordination:
- Check task status regularly using list_tasks
- When a task is blocked, update its status and create an unblocking task
- When all tasks in a milestone complete, report progress to the relevant stakeholder
- Prefer creating focused, completable tasks (1-4 hours of work) over broad ones""",
    },
    {
        "name": "Workflow Designer",
        "description": "Designs and creates multi-agent workflows on demand. Can compose, schedule, and execute workflows from a natural language request.",
        "version": "1.0.0",
        "category": "automation",
        "icon": "GitMerge",
        "color": "#6366f1",
        "required_tool_ids": ["create_workflow", "list_workflows", "execute_workflow", "get_workflow_details"],
        "config_schema": {
            "type": "object",
            "properties": {
                "default_schedule": {
                    "type": "string",
                    "enum": ["manual", "hourly", "daily", "weekly"],
                    "default": "manual",
                    "description": "Default schedule for newly created workflows",
                },
                "auto_execute": {
                    "type": "boolean",
                    "default": False,
                    "description": "Automatically execute the workflow immediately after creating it",
                },
            },
        },
        "prompt_fragment": """\
## Workflow Designer Skill
You have been equipped with the Workflow Designer capability.

You can design and create multi-agent workflows on demand using the workflow tools. Default schedule: {default_schedule}. Auto-execute after creation: {auto_execute}.

### Workflow Node Types
Use these node types when designing workflows:
- **[input]** — Static text that feeds into the first agent node. Use for fixed prompts or seed data.
- **[agent]** — Calls a specific agent with a prompt. Use `{input}` as a placeholder for the upstream output. Set `agent_id` to a running agent's UUID.
- **[conditional]** — Routes to a `--true-->` or `--false-->` branch based on an LLM evaluation. Specify a `condition` in plain language and an `agent_id` for the evaluator.
- **[loop]** — Repeats an agent prompt up to `max_iterations` times, feeding each output back as the next input. Good for iterative refinement.
- **[parallel]** — Fans out to multiple agent branches concurrently. Downstream nodes receive all branch outputs joined together.
- **[approval_gate]** — Pauses the workflow and creates a human approval request. Workflow resumes only when approved.
- **[sub_workflow]** — Embeds another existing workflow as a node. Provide its `workflow_id` and `workflow_name`.

### Design Process
1. Understand the goal: ask clarifying questions if needed (what agents exist, what the trigger should be, whether human approval is needed)
2. Use `list_workflows` to check for existing workflows that could be reused or extended
3. Design the Markdown definition — keep it simple and purposeful; prefer 3–7 nodes
4. Call `create_workflow` with the Markdown definition
5. If `auto_execute` is true, immediately call `execute_workflow` with the new workflow's ID
6. Report the workflow ID, name, and a brief description of what it does

### Scheduling Guidelines
- manual: only runs when explicitly triggered
- hourly → schedule_interval 60
- daily → schedule_interval 1440
- weekly → schedule_interval 10080

### Key Rules
- Always use real agent UUIDs in `agent_id` fields — ask the user for them if you don't know
- Every node must be connected via an edge (no disconnected nodes)
- Conditional nodes must have both a `--true-->` and `--false-->` edge
- Use `approval_gate` before any destructive, financial, or external-facing actions
- Keep prompts concise and use `{input}` to chain outputs between nodes""",
    },
    {
        "name": "Knowledge Ingestion",
        "description": "Ingests URLs, documents, and text into the knowledge base for future retrieval.",
        "version": "1.0.0",
        "category": "research",
        "icon": "Upload",
        "color": "#059669",
        "required_tool_ids": ["ingest_url_to_kb", "scrape_webpage", "search_knowledge_base"],
        "config_schema": {
            "type": "object",
            "properties": {
                "target_kb_id": {"type": "string", "default": "", "description": "Target knowledge base ID (leave empty to prompt)"},
                "chunk_strategy": {
                    "type": "string",
                    "enum": ["page", "section", "paragraph"],
                    "default": "section",
                    "description": "How to split documents into chunks",
                },
            },
        },
        "prompt_fragment": """\
## Knowledge Ingestion Skill
You have been equipped with the Knowledge Ingestion capability.

You proactively ingest information into the knowledge base for future retrieval. Target KB: {target_kb_id}. Chunk strategy: {chunk_strategy}.

Ingestion process:
1. Before ingesting, search_knowledge_base to check if the source already exists
2. For URLs: use ingest_url_to_kb directly with the target KB ID
3. For pages requiring navigation: scrape_webpage first, then ingest the extracted text
4. After ingestion, verify by searching for a key term from the document
5. Report what was ingested: source, title, estimated chunk count, KB destination

Quality standards:
- Only ingest relevant, credible sources
- Note the ingestion date so stale content can be identified later
- For large documents, ingest the most relevant sections first
- Flag documents that may need periodic re-ingestion (news articles, pricing pages, changelogs)""",
    },
]
