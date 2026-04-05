"""Teams API — CRUD for agent teams."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.team import Team
from app.models.agent import Agent

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/")
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).order_by(Team.name))
    return result.scalars().all()


@router.post("/", status_code=201)
async def create_team(data: dict, db: AsyncSession = Depends(get_db)):
    team = Team(
        name=data["name"],
        description=data.get("description"),
        shared_context=data.get("shared_context"),
        lead_agent_id=data.get("lead_agent_id"),
        member_agent_ids=data.get("member_agent_ids", []),
        color=data.get("color"),
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/{team_id}")
async def get_team(team_id: str, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    return team


@router.put("/{team_id}")
async def update_team(team_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    for field in ("name", "description", "shared_context", "lead_agent_id",
                  "member_agent_ids", "color"):
        if field in data:
            setattr(team, field, data[field])
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: str, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    await db.delete(team)
    await db.commit()


@router.get("/{team_id}/members")
async def get_team_members(team_id: str, db: AsyncSession = Depends(get_db)):
    """Return full Agent records for the team's member_agent_ids."""
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, "Team not found")
    if not team.member_agent_ids:
        return []
    result = await db.execute(
        select(Agent).where(Agent.id.in_(team.member_agent_ids))
    )
    return result.scalars().all()
