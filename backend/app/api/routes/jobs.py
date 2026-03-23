from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import JobCreate, JobResponse, JobUpdate
from app.db.session import get_db
from app.models.job import Job
from app.core.scheduler import sync_jobs

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.get("/scripts")
async def list_available_scripts():
    """List all available python scripts in the /scripts folder."""
    import os
    scripts_dir = os.path.join(os.getcwd(), "scripts")
    if not os.path.exists(scripts_dir):
        return []
    
    scripts = [f for f in os.listdir(scripts_dir) if f.endswith(".py")]
    return sorted(scripts)

@router.get("/", response_model=List[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    """List all scheduled jobs."""
    result = await db.execute(select(Job).order_by(Job.created_at.desc()))
    return result.scalars().all()

@router.post("/", response_model=JobResponse)
async def create_job(job_in: JobCreate, db: AsyncSession = Depends(get_db)):
    """Create a new job."""
    job = Job(**job_in.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    # Sync jobs with scheduler
    await sync_jobs()
    
    return job

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific job."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.put("/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, job_in: JobUpdate, db: AsyncSession = Depends(get_db)):
    """Update a specific job."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    update_data = job_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)
        
    await db.commit()
    await db.refresh(job)
    
    # Sync jobs with scheduler
    await sync_jobs()
    
    return job

@router.delete("/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a specific job."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    await db.delete(job)
    await db.commit()
    
    # Sync jobs with scheduler
    await sync_jobs()
    
    return {"message": "Job deleted successfully"}

@router.post("/{job_id}/run")
async def trigger_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger a job execution."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    # We trigger the manual run in the background (fire and forget)
    from app.core.scheduler import execute_job
    import asyncio
    asyncio.create_task(execute_job(job_id))
    
    return {"message": "Job triggered manually"}
