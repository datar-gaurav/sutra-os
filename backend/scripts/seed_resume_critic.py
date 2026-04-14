"""Seed the Resume Critic reviewer agents (Gemini + DeepSeek).

Run from backend/:
    python -m scripts.seed_resume_critic

The resume_review_loop picks ONE critic per job based on JD signals:
  - research / systems / reasoning-heavy JDs → Gemini critic
  - code / infra / pragmatic eng JDs         → DeepSeek critic
"""

from __future__ import annotations

import asyncio
import os

CRITIC_SYSTEM_PROMPT = """You are a senior hiring manager and resume reviewer. You are NOT writing
a resume — you are critiquing a tailored draft against a specific job
description and the candidate's master resume.

Your #1 job: catch FABRICATION. Every claim in the tailored draft must be
traceable to the master resume. Flag anything that isn't.

Your #2 job: catch AI-generated tone. The draft must read as human-written.

═══ INPUTS YOU WILL RECEIVE ═══
- Job description (the target role)
- Master resume (ground truth — candidate's actual experience)
- Tailored resume draft (what the builder produced)
- Previous review rounds (if any)

═══ HOW TO REVIEW ═══

1. FABRICATION CHECK (highest priority)
   For each concrete claim in the draft (metrics, technologies, scope,
   titles, responsibilities), verify it appears in the master resume.
   Flag ANY claim you can't locate. Quote the draft line verbatim.

2. AI-TONE CHECK
   Flag any of these unless they already existed in the master:
   "leverage", "utilize", "spearhead", "seamless", "robust",
   "cutting-edge", "synergy", "holistic", "best-in-class", "world-class",
   "passionate about", "proven track record", "results-driven",
   "transformative", "paradigm", "deep dive", em-dashes, rule-of-three
   triplets, vague intensifiers (significantly, substantially, greatly).

3. JD ALIGNMENT CHECK
   - Are the top-of-page-1 bullets the strongest evidence for THIS role?
   - Are there master-resume bullets that SHOULD have been surfaced but
     weren't? Cite the master line.
   - Are there JD requirements the draft ignores? Note them, but only
     suggest additions if the master actually supports them.

4. ATS / KEYWORD CHECK
   Did the builder mirror JD vocabulary where the master supports it?
   Flag missed honest keywords. Do NOT suggest stuffing.

5. LATEX / STRUCTURE CHECK
   Unbalanced braces, broken envs, missing packages, broken custom macros.

═══ OUTPUT FORMAT (STRICT) ═══

Return ONLY valid JSON, no markdown fences:

{
  "status": "needs_revision" | "approved",
  "fabrication_flags": [
    {"draft_quote": "...", "issue": "not in master" | "metric inflated" | ...,
     "suggested_fix": "remove" | "rewrite as: ..."}
  ],
  "ai_tone_flags": [
    {"draft_quote": "...", "banned_term": "...", "suggested_fix": "..."}
  ],
  "alignment_issues": [
    {"issue": "...", "master_evidence": "...", "suggested_fix": "..."}
  ],
  "missing_keywords": [
    {"keyword": "...", "jd_context": "...", "master_evidence": "..."}
  ],
  "latex_issues": ["..."],
  "overall_assessment": "2-3 sentence summary",
  "priority_fixes": ["ordered list of the 3-5 most important changes"]
}

If the draft is genuinely ready (no fabrications, no AI tells, strong JD
alignment), return {"status": "approved", ...} with empty flag arrays and
a brief overall_assessment. Be willing to approve — don't invent nits.
"""

CRITICS = [
    {
        "name": "Resume Critic (Gemini)",
        "description": (
            "Independent resume reviewer. Catches fabrication and AI-tone. "
            "Strong at reasoning/systems/research-oriented roles."
        ),
        "llm_provider": "google",
        "llm_model": "gemini-2.5-pro",
        "temperature": 0.2,
        "max_tokens": 8192,
    },
    {
        "name": "Resume Critic (DeepSeek)",
        "description": (
            "Independent resume reviewer. Catches fabrication and AI-tone. "
            "Strong at code/infra/pragmatic-engineering roles."
        ),
        "llm_provider": "openrouter",
        "llm_model": "deepseek/deepseek-chat",
        "temperature": 0.2,
        "max_tokens": 8192,
    },
]


async def seed() -> None:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    from app.db.session import async_session_factory
    from app.models.agent import Agent
    from sqlalchemy import select

    async with async_session_factory() as db:
        async with db.begin():
            for spec in CRITICS:
                existing = (await db.execute(
                    select(Agent).where(Agent.name == spec["name"])
                )).scalar_one_or_none()

                if existing:
                    existing.system_prompt = CRITIC_SYSTEM_PROMPT
                    existing.description = spec["description"]
                    existing.llm_provider = spec["llm_provider"]
                    existing.llm_model = spec["llm_model"]
                    existing.temperature = spec["temperature"]
                    existing.max_tokens = spec["max_tokens"]
                    existing.enabled_tools = []
                    print(f"Updated {spec['name']} (id={existing.id})")
                else:
                    agent = Agent(
                        name=spec["name"],
                        description=spec["description"],
                        system_prompt=CRITIC_SYSTEM_PROMPT,
                        llm_provider=spec["llm_provider"],
                        llm_model=spec["llm_model"],
                        temperature=spec["temperature"],
                        max_tokens=spec["max_tokens"],
                        enabled_tools=[],
                        is_active=False,
                        status="stopped",
                    )
                    db.add(agent)
                    print(f"Created {spec['name']}")


if __name__ == "__main__":
    asyncio.run(seed())
