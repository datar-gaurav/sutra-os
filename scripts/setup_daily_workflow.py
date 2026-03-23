import asyncio
import os
import sys

# Add the backend directory to sys.path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.db.session import async_session_factory
from app.models.agent import Agent
from sqlalchemy import select
from app.tools.workflow_tools import _parse_workflow_markdown

async def get_agent_id(db, fallback_role: str, possible_names: list[str]) -> str:
    """Find an agent ID by checking a list of possible names, or fallback to the first active agent."""
    for name in possible_names:
        result = await db.execute(select(Agent).where(Agent.name.ilike(name)))
        agent = result.scalars().first()
        if agent:
            return agent.id
            
    # Fallback: get any active agent
    print(f"Warning: Could not find agents with names {possible_names} for role {fallback_role}. Using fallback.")
    result = await db.execute(select(Agent).limit(1))
    agent = result.scalars().first()
    if agent:
        return agent.id
    
    import uuid
    dummy_id = str(uuid.uuid4())
    print(f"Warning: No agents exist in the database. Using dummy UUID {dummy_id} for {fallback_role}. Please update this workflow in the UI after creating agents.")
    return dummy_id

async def setup():
    from app.core.db_migrations import run_migrations
    async with async_session_factory() as db:
        print("Running schema migrations...")
        await run_migrations(db)
        
        # Find necessary agents
        ceo_id = await get_agent_id(db, "CEO", ["Nova", "CEO", "Director"])
        evolve_id = await get_agent_id(db, "Evolve", ["Evolve", "System", "Platform Health"])
        sec_id = await get_agent_id(db, "Security", ["Groot", "Security Specialist", "Security"])
        
        # Build the markdown string
        workflow_md = f"""# Workflow: Daily Operating Cycle
Automated daily rhythm for the organization.
**Schedule:** Every 1440 minutes
**Active:** true

## Nodes
### 1. [input] Start
- id: input-001
- value: Triggering daily operating cycle.

### 2. [discussion] Morning Standup
- id: disc-standup
- discussion_type: standup
- topic: Daily Standup. What did you do yesterday? What are you doing today? Any blockers?
- participant_names: Nova, Engineer, Groot
- moderator_name: Nova
- max_rounds: 1

### 3. [agent] CEO Triage
- id: agent-triage
- agent_id: {ceo_id}
- prompt: Analyze the standup output:\\n\\n{{input}}\\n\\nIdentify any blockers, cross-agent dependencies, or high-priority issues. Provide a clear triage summary, and state explicitly if there are critical blockers that need immediate resolution by answering at the end with 'BLOCKERS: YES' or 'BLOCKERS: NO'.
- max_retries: 1

### 4. [conditional] Check Blockers
- id: cond-blockers
- condition: The triage summary ends with 'BLOCKERS: YES'
- agent_id: {ceo_id}

### 5. [agent] Resolve Blockers
- id: agent-resolve
- agent_id: {ceo_id}
- prompt: The following blockers were identified:\\n\\n{{input}}\\n\\nDetermine the best plan to resolve them and instruct the appropriate agents. (In a fully expanded workflow, this would be a parallel node).
- max_retries: 1

### 6. [agent] Platform Health
- id: agent-health
- agent_id: {evolve_id}
- prompt: Run a quick health check of the platform and current active goals. Identify one area for improvement today.
- max_retries: 1

### 7. [discussion] Strategic Discussion
- id: disc-strategy
- discussion_type: brainstorm
- topic: Based on the platform health check:\\n\\n{{input}}\\n\\nLet's brainstorm a concrete action plan to address this improvement today.
- participant_names: Nova, Engineer
- moderator_name: Nova
- max_rounds: 2

### 8. [agent] Security Sweep
- id: agent-security
- agent_id: {sec_id}
- prompt: Perform your daily security sweep. Review recent operations and standup notes for potential risks.
- max_retries: 1

### 9. [agent] Daily Report
- id: agent-report
- agent_id: {ceo_id}
- prompt: Compile all the findings from the daily operating cycle into a concise daily report.\\n\\nInput context:\\n{{input}}\\n\\nFormat well with markdown.
- max_retries: 1


## Edges
Start --> Morning Standup
Morning Standup --> CEO Triage
CEO Triage --> Check Blockers
Check Blockers --true--> Resolve Blockers
Resolve Blockers --> Platform Health
Check Blockers --false--> Platform Health
Platform Health --> Strategic Discussion
Strategic Discussion --> Security Sweep
Security Sweep --> Daily Report
"""

        # Parse and save
        name, description, schedule_interval, is_active, definition = _parse_workflow_markdown(workflow_md)
        
        from app.models.workflow import Workflow

        workflow = Workflow(
            name=name,
            description=description,
            schedule_interval=schedule_interval,
            is_active=is_active,
            definition=definition,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        
        print(f"Successfully created master workflow: '{workflow.name}' (ID: {workflow.id})")
        print("Note: The scheduler normally picks these up automatically on its sync cycle.")

if __name__ == "__main__":
    asyncio.run(setup())
