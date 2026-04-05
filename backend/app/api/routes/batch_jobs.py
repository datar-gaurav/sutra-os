import asyncio
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import BatchJobCreate, BatchJobResponse, BatchJobRunResponse, BatchJobUpdate
from app.db.session import get_db
from app.models.batch_job import BatchJob, BatchJobRun
from app.core.scheduler import sync_batch_jobs

router = APIRouter(prefix="/batch-jobs", tags=["Batch Jobs"])


@router.get("/", response_model=List[BatchJobResponse])
async def list_batch_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BatchJob).order_by(BatchJob.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=BatchJobResponse)
async def create_batch_job(job_in: BatchJobCreate, db: AsyncSession = Depends(get_db)):
    batch = BatchJob(**job_in.model_dump())
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    await sync_batch_jobs()
    return batch


@router.get("/{batch_job_id}", response_model=BatchJobResponse)
async def get_batch_job(batch_job_id: str, db: AsyncSession = Depends(get_db)):
    batch = await db.get(BatchJob, batch_job_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return batch


@router.put("/{batch_job_id}", response_model=BatchJobResponse)
async def update_batch_job(batch_job_id: str, job_in: BatchJobUpdate, db: AsyncSession = Depends(get_db)):
    batch = await db.get(BatchJob, batch_job_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")

    for field, value in job_in.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)

    await db.commit()
    await db.refresh(batch)
    await sync_batch_jobs()
    return batch


@router.delete("/{batch_job_id}")
async def delete_batch_job(batch_job_id: str, db: AsyncSession = Depends(get_db)):
    batch = await db.get(BatchJob, batch_job_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")

    await db.delete(batch)
    await db.commit()
    await sync_batch_jobs()
    return {"message": "Batch job deleted successfully"}


@router.post("/{batch_job_id}/run")
async def trigger_batch_job(batch_job_id: str, db: AsyncSession = Depends(get_db)):
    batch = await db.get(BatchJob, batch_job_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")

    from app.core.scheduler import execute_batch_job
    asyncio.create_task(execute_batch_job(batch_job_id))
    return {"message": "Batch job triggered manually"}


@router.get("/{batch_job_id}/runs", response_model=List[BatchJobRunResponse])
async def list_batch_job_runs(batch_job_id: str, db: AsyncSession = Depends(get_db)):
    batch = await db.get(BatchJob, batch_job_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch job not found")

    result = await db.execute(
        select(BatchJobRun)
        .where(BatchJobRun.batch_job_id == batch_job_id)
        .order_by(BatchJobRun.started_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/{batch_job_id}/runs/{run_id}", response_model=BatchJobRunResponse)
async def get_batch_job_run(batch_job_id: str, run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(BatchJobRun, run_id)
    if not run or run.batch_job_id != batch_job_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
