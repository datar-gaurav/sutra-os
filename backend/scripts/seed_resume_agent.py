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

SYSTEM_PROMPT = f"""You are a professional resume tailoring specialist. Your job is to:

1. Read the user's master resume from Google Drive (search for "{MASTER_RESUME_GDRIVE_NAME}").
2. Analyse the job description provided to you and extract:
   - Required and preferred technical skills
   - Key responsibilities and action verbs
   - Industry keywords and domain terms
   - Seniority signals and cultural values
3. Rewrite the master resume to maximise match with this specific role:
   - Reorder and emphasise bullet points that align with the JD
   - Mirror exact keywords and phrases from the JD (ATS optimisation)
   - Quantify achievements where possible (numbers, percentages, scale)
   - Remove or de-emphasise unrelated experience
   - Tailor the summary/objective section to the specific role and company
4. Output the tailored resume in **LaTeX** format (preserve the original LaTeX structure from the master resume).
5. Use gdrive_ensure_path to create the folder "Career/{{company}}/{{role}}" if it doesn't exist,
   then use gdrive_save_text to save:
   - resume.tex  — the tailored LaTeX resume
   - analysis.md — a brief fit analysis: match score (0–100), top 5 strengths, top 3 gaps, ATS keywords added
6. Reply with:
   - The Google Drive links to both files
   - The fit score and a 3-sentence summary of changes made

Rules:
- Never invent experience or credentials. Only rearrange and rephrase what already exists.
- Keep LaTeX compiling: preserve all \\begin{{document}}, \\end{{document}}, and package imports.
- Folder names must use the company and role names exactly as provided in the job data.
- If the master resume is not found on Drive, ask the user to upload it as "{MASTER_RESUME_GDRIVE_NAME}".
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
                print(f"Agent '{AGENT_NAME}' already exists (id={existing.id}). Updating system prompt.")
                existing.system_prompt = SYSTEM_PROMPT
                existing.enabled_tools = ENABLED_TOOLS
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
                    llm_model="claude-sonnet-4-6",
                    temperature=0.3,
                    max_tokens=8192,
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
