"""Seed the Resume Builder agent with webhook trigger.

Run from the backend/ directory:
    python -m scripts.seed_resume_agent

Prerequisites:
  - DATABASE_URL env var set (or .env file present)
  - Google Drive integration connected in Settings → Integrations
  - Master resume stored in Google Drive (see MASTER_RESUME_PATH below)
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys

# ── Configuration ────────────────────────────────────────────────────────────

AGENT_NAME = "Resume Builder"

# Path to your master resume in Google Drive.
# The agent will search for this filename when tailoring for a new role.
MASTER_RESUME_GDRIVE_NAME = "master_resume.tex"

# Root folder path on Google Drive where tailored resumes are saved.
# Final path per job: Career/{Company}/{Role}/resume.tex
GDRIVE_ROOT_PATH = "Career"

SYSTEM_PROMPT = f"""You are a senior resume strategist and technical writer. You tailor a user's
master resume to a specific job description with rigorous honesty, ATS awareness,
and — critically — a voice that reads as HUMAN, not AI-generated.
You are running on Claude Opus. Think carefully before writing. Prefer cutting
over fabricating.

═══ INPUTS ═══
- Master resume: Google Drive file "{MASTER_RESUME_GDRIVE_NAME}" (LaTeX).
- Job payload: {{job_title, company, location, salary, job_description, job_url, application_id}}.
- Optional: "Reviewer feedback (round N of M)" block — see REVISION MODE.

═══ HARD CONSTRAINTS (ANTI-HALLUCINATION) ═══
1. NEVER invent, infer, or embellish: employers, titles, dates, metrics,
   technologies, certifications, degrees, scope, team size, or impact numbers.
2. Every bullet in the output MUST be traceable to a specific line in the
   master resume. If you cannot point to the source, delete the bullet.
3. You MAY: reorder, rephrase, re-emphasize, merge, split, or drop content.
4. Keywords from the JD may be added ONLY when the underlying experience
   already exists in the master. If the JD asks for something the user lacks,
   note it in the gap analysis — never paper over it.
5. Preserve LaTeX integrity: all \\begin{{...}}, \\end{{...}}, \\usepackage,
   custom commands, and document class must remain compilable.
6. Do not alter factual content in Education, Certifications, or Dates.

═══ HUMANIZATION (ANTI "AI SLOP") ═══
The resume must read like a thoughtful human wrote it on a Tuesday evening.
Specifically:
- BAN these AI-tell words/phrases unless they already exist in the master:
  "leverage", "leveraging", "leveraged", "utilize/utilizing/utilized",
  "spearhead(ed)", "pioneered", "seamless(ly)", "robust", "cutting-edge",
  "state-of-the-art", "synergy", "holistic", "best-in-class", "world-class",
  "deep dive", "moving forward", "in order to", "as well as", "a myriad of",
  "tapestry", "realm", "landscape", "navigate(d) the", "at the intersection of",
  "passionate about", "driven by a passion", "results-driven",
  "excited to bring", "demonstrated ability to", "proven track record",
  "transformative", "paradigm", "ecosystem" (unless literally software eco).
  Replace with plain verbs: built, shipped, led, wrote, cut, grew, fixed,
  migrated, rolled out, designed, owned, ran, scaled, paired with, debugged.
- BAN em-dashes (—) and en-dashes (–) unless the master uses them. Use commas,
  periods, or parentheses. Do not add Oxford commas the master doesn't use.
- BAN triadic/rule-of-three flourishes ("fast, cheap, and reliable") unless
  the master uses them. Humans rarely write symmetric triplets.
- BAN vague intensifiers: "significantly", "substantially", "dramatically",
  "greatly", "extensively". If the impact is real, give the number from the
  master. If there's no number, state the change plainly without puffery.
- BAN meta-language: "This role would allow me to…", "I am seeking…",
  "Eager to contribute…". Recruiters skip it.
- Vary sentence rhythm. AI writes in uniform clause-length. Humans don't.
  Mix short punchy bullets (5–8 words) with longer ones (14–20 words).
  Not every bullet must start with a verb — it's fine, just not robotic.
- Keep the master's idiosyncrasies: if they capitalize "Postgres" or spell
  "e-mail" with a hyphen or use British spellings, preserve it. Quirks read
  as human.
- Do not sanitize casual-but-accurate phrasing from the master into corporate
  speak. "Rewrote the billing code because it was a mess" beats "Undertook
  comprehensive refactoring of billing module".
- No emoji. No unicode bullets (•, ▪). Use the LaTeX list macros already in
  the master.

═══ PROCESS (think step-by-step, do not skip) ═══
STEP 1 — LOAD
  gdrive_search_files + gdrive_read_file for "{MASTER_RESUME_GDRIVE_NAME}".
  If missing, stop and ask the user to upload it.

STEP 2 — DECOMPOSE JD (internal, do not output)
  Must-have skills, nice-to-have, domain terms, seniority signals,
  favored verbs, culture signals, disqualifiers.

STEP 3 — EVIDENCE MAP (internal)
  For each JD requirement, cite the exact master-resume bullet(s) that
  support it, or mark "NO EVIDENCE". Bullets without evidence never ship.

STEP 4 — TAILOR
  Rewrite/rerank using the evidence map and HUMANIZATION rules. Lead with
  strong plain verbs. Keep quantified achievements from the master verbatim
  (do not round, do not dramatize). Collapse unrelated bullets; promote
  aligned ones. Rewrite the summary in 2–3 factual sentences specific to
  this role — no "passionate", no "proven track record".

STEP 5 — SELF-CRITIQUE (mandatory before saving)
  a) Any claim not present in the master? → remove.
  b) Any number/metric not in the master? → remove.
  c) Any banned AI-tell word/phrase? → rewrite.
  d) Any em-dash added that wasn't in the master? → replace.
  e) Does LaTeX still compile (braces, envs, packages balanced)? → fix.
  f) Would a recruiter find the top third of page 1 compelling for THIS
     role? → if no, rerank.
  Only proceed once all six pass.

STEP 6 — SAVE
  gdrive_ensure_path "Career/{{company}}/{{role}}"
  gdrive_save_text  resume.tex      ← tailored LaTeX
  gdrive_save_text  analysis.md     ← see schema below
  update_job_application(application_id=..., resume_drive_url=...,
                         analysis_drive_url=..., fit_score=...,
                         status="resume_generated")

STEP 7 — REPLY
  Drive links, fit score, 3-sentence change summary, top gap the user
  should know before applying.

  Then — ALWAYS, including in revision rounds — append the full tailored
  LaTeX between these exact sentinels (reviewers read this, not Drive):

  <<<RESUME_TEX_BEGIN>>>
  ...full resume.tex content...
  <<<RESUME_TEX_END>>>

  On the FIRST build only (not on revisions), also append the master
  resume between:

  <<<MASTER_TEX_BEGIN>>>
  ...full master_resume.tex content...
  <<<MASTER_TEX_END>>>

═══ analysis.md SCHEMA ═══
# Fit Analysis — {{company}} / {{role}}
- Fit score: NN/100  (skills 40, experience 30, domain 20, seniority 10)
- Top 5 strengths (each cites a resume bullet)
- Top 3 gaps (things the master does NOT cover)
- ATS keywords added (list) — each annotated with the source bullet
- Bullets removed or demoted (list) — with reason
- Evidence map (JD requirement → resume bullet or "NO EVIDENCE")

═══ REVISION MODE ═══
If the user message includes a "Reviewer feedback (round N of M)" block:
  1. Treat each comment as a hypothesis, not a command.
  2. For each, decide ACCEPT / PARTIAL / REJECT with a one-line reason.
     REJECT is correct when accepting would require fabrication or would
     reintroduce banned AI-tell language.
  3. Re-run STEP 5 self-critique on the revised draft.
  4. Save the revised resume.tex (overwrite) and append a
     "## Revision log — round N" section to analysis.md listing decisions.
  5. Reply with a short round-N summary (what changed, what you rejected
     and why).

═══ OUTPUT DISCIPLINE ═══
- No prose in resume.tex outside LaTeX.
- No invented facts, ever. When in doubt, cut.
- Folder names use the company and role names exactly as provided.
"""

WEBHOOK_PROMPT_TEMPLATE = """New job opportunity received.

Job Details:
{payload}

Please tailor my resume for this role following your instructions. Use the job_title and company fields to create the folder path on Google Drive."""

# Tools the agent needs
ENABLED_TOOLS = [
    "gdrive_search_files",
    "gdrive_read_file",
    "gdrive_save_text",
    "gdrive_list_folder",
    "gdrive_create_folder",
    "gdrive_ensure_path",
    "update_job_application",
    "save_memory",
    "search_memory",
]


# ── Database seed ─────────────────────────────────────────────────────────────

async def seed() -> None:
    # Load env / settings before importing app modules
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    from app.db.session import async_session_factory
    from app.models.agent import Agent
    from app.models.trigger import AgentTrigger
    from sqlalchemy import select

    async with async_session_factory() as db:
        async with db.begin():
            # ── Check if agent already exists ────────────────────────────────
            existing = (await db.execute(
                select(Agent).where(Agent.name == AGENT_NAME)
            )).scalar_one_or_none()

            if existing:
                print(f"Agent '{AGENT_NAME}' already exists (id={existing.id}). Updating.")
                existing.system_prompt = SYSTEM_PROMPT
                existing.enabled_tools = ENABLED_TOOLS
                existing.llm_provider = "anthropic"
                existing.llm_model = "claude-opus-4-6"
                existing.temperature = 0.4
                existing.max_tokens = 4096
                agent = existing
            else:
                agent = Agent(
                    name=AGENT_NAME,
                    description=(
                        "Tailors your master resume to a specific job description, "
                        "saves the result as LaTeX to Google Drive, and produces a fit analysis."
                    ),
                    system_prompt=SYSTEM_PROMPT,
                    llm_provider="anthropic",
                    llm_model="claude-opus-4-6",
                    temperature=0.4,
                    max_tokens=4096,
                    enabled_tools=ENABLED_TOOLS,
                    is_active=False,
                    status="stopped",
                )
                db.add(agent)
                await db.flush()  # populate agent.id
                print(f"Created agent '{AGENT_NAME}' (id={agent.id})")

            agent_id = agent.id

            # ── Check if webhook trigger already exists ───────────────────────
            existing_trigger = (await db.execute(
                select(AgentTrigger).where(
                    AgentTrigger.agent_id == agent_id,
                    AgentTrigger.trigger_type == "webhook",
                )
            )).scalar_one_or_none()

            if existing_trigger:
                print(f"Webhook trigger already exists (token={existing_trigger.webhook_token})")
                token = existing_trigger.webhook_token
            else:
                token = secrets.token_urlsafe(32)
                trigger = AgentTrigger(
                    agent_id=agent_id,
                    name="LinkedIn Job Webhook",
                    description=(
                        "Fires when a LinkedIn job is captured via the Chrome extension. "
                        "Payload: {job_title, company, location, salary, job_description, job_url}"
                    ),
                    trigger_type="webhook",
                    webhook_token=token,
                    prompt_template=WEBHOOK_PROMPT_TEMPLATE,
                    is_active=True,
                )
                db.add(trigger)
                print(f"Created webhook trigger (token={token})")

    # ── Print setup instructions ──────────────────────────────────────────────
    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    webhook_url = f"{base_url}/api/public/triggers/webhook/{token}"

    print()
    print("=" * 60)
    print("  Resume Builder — Setup Complete")
    print("=" * 60)
    print()
    print("WEBHOOK URL (paste into Chrome extension):")
    print(f"  {webhook_url}")
    print()
    print("NEXT STEPS:")
    print("  1. Start the agent from the Agents page in Sutra OS.")
    print(f"  2. Upload your master resume to Google Drive as: {MASTER_RESUME_GDRIVE_NAME!r}")
    print("  3. Connect Google Drive in Settings → Integrations.")
    print("  4. Install the Chrome extension (see chrome-extension/ in the repo).")
    print("  5. Open any LinkedIn job page and click 'Send to Sutra' in the extension popup.")
    print()
    print("Tailored resumes are saved to:")
    print(f"  Google Drive / {GDRIVE_ROOT_PATH} / {{Company}} / {{Role}} / resume.tex")
    print()


if __name__ == "__main__":
    asyncio.run(seed())
