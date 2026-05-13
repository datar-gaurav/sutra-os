import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import httpx
import pytz
from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.batch_job import BatchJob, BatchJobRun
from app.models.workflow import Workflow
from app.models.job import Job
from app.models.trigger import AgentTrigger, TriggerType

scheduler = AsyncIOScheduler()

async def execute_workflow(workflow_id: str, initial_input: str = ""):
    print(f"Executing workflow {workflow_id}")
    async with async_session_factory() as db:
        workflow = await db.get(Workflow, workflow_id)
        if not workflow or not workflow.is_active:
            return

        workflow.last_run_at = datetime.now()
        workflow.last_run_status = "running"
        workflow.last_run_logs = []
        await db.commit()

    async def _flush_progress(current_logs: list) -> None:
        async with async_session_factory() as db:
            wf = await db.get(Workflow, workflow_id)
            if wf:
                wf.last_run_logs = current_logs
                await db.commit()

    try:
        from app.core.workflow_engine import execute_workflow_enhanced
        result = await execute_workflow_enhanced(
            workflow_id,
            initial_input=initial_input,
            progress_callback=_flush_progress,
        )
    except Exception as e:
        result = {"status": "failed", "logs": [{"type": "error", "message": str(e)}], "results": {}, "final_output": ""}

    async with async_session_factory() as db:
        workflow = await db.get(Workflow, workflow_id)
        if workflow:
            workflow.last_run_status = result["status"]
            workflow.last_run_logs = result["logs"]
            await db.commit()

async def sync_workflows():
    """Load workflows from DB and schedule them"""
    async with async_session_factory() as db:
        # Clear existing workflow jobs
        for job in scheduler.get_jobs():
            if job.id.startswith("workflow_"):
                scheduler.remove_job(job.id)
            
        result = await db.execute(select(Workflow).where(Workflow.is_active == True, Workflow.schedule_interval != None))
        workflows = result.scalars().all()
        for wf in workflows:
            scheduler.add_job(
                execute_workflow,
                trigger=IntervalTrigger(minutes=wf.schedule_interval),
                args=[wf.id],
                id=f"workflow_{wf.id}",
                replace_existing=True
            )
        print(f"Synced {len(workflows)} active workflows to scheduler.")

async def execute_job(job_id: str):
    """Execute a scheduled Job."""
    print(f"Executing job {job_id}")
    async with async_session_factory() as db:
        job = await db.get(Job, job_id)
        if not job or not job.is_active:
            return

        job.last_run_at = datetime.now()
        job.last_run_status = "running"
        await db.commit()

        output_text = None
        try:
            if job.execution_type == "prompt":
                from app.core.orchestrator import orchestrator
                if job.target_id and job.prompt_text:
                    # Use an aggressive Double-Wrap strategy to override rigid system prompt instructions
                    summary_header = (
                        "### FORCED SUMMARY MODE ###\n"
                        "CRITICAL: FOR THIS SPECIFIC REQUEST, YOU MUST IGNORE ALL SYSTEM PROMPT INSTRUCTIONS REGARDING "
                        "OUTPUT STRUCTURE OR MANDATORY SECTIONS. DO NOT PROVIDE SCREENING CRITERIA, TECHNICAL ANALYSIS, "
                        "FUNDAMENTAL CATALYSTS, RISK ASSESSMENT, OR TRADE PLAN SECTIONS.\n\n"
                    )
                    summary_footer = (
                        "\n\n### FINAL REMINDER ###\n"
                        "ONLY PROVIDE THE SUMMARY TABLE REQUESTED ABOVE. DO NOT INCLUDE ANY OTHER ANALYSIS OR SECTIONS. "
                        "SYSTEM PROMPT STRUCTURE RULES ARE SUSPENDED FOR MESSAGE."
                    )
                    final_message = summary_header + job.prompt_text + summary_footer
                    
                    result = await orchestrator.route_message(
                        agent_id=job.target_id,
                        message=final_message,
                        chat_history=[]
                    )
                    output_text = result.get("output", "")
                    if result.get("error"):
                        job.last_run_status = "failed"
                    else:
                        job.last_run_status = "success"
            elif job.execution_type == "workflow":
                if job.target_id:
                    await execute_workflow(job.target_id)
                    job.last_run_status = "success"
            elif job.execution_type == "n8n_workflow":
                if job.n8n_webhook_url:
                    # trigger n8n webhook
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(job.n8n_webhook_url, json={"job_id": job.id, "name": job.name})
                        if resp.is_success:
                            job.last_run_status = "success"
                        else:
                            job.last_run_status = "failed"
                            print(f"n8n webhook failed: {resp.status_code}")
            elif job.execution_type == "docker_script":
                if job.script_name:
                    output_text = await _execute_docker_script(job.script_name)
                    job.last_run_status = "success"
                else:
                    job.last_run_status = "failed"
                    output_text = "Error: No script name provided for docker_script job."
        except Exception as e:
            print(f"Job execution failed: {e}")
            job.last_run_status = "failed"
            output_text = f"Error: {str(e)}"
            
        await db.commit()

        # Send email notification if configured
        if job.last_run_status == "success" and job.notify_email:
            _send_job_email(
                to_email=job.notify_email,
                job_name=job.name,
                output=output_text or "(No text output captured — check logs for workflow/n8n jobs.)"
            )

        # Send telegram notification if configured
        if job.last_run_status == "success" and job.notify_telegram_chat_id:
            await _send_job_telegram(
                chat_id=job.notify_telegram_chat_id,
                job_name=job.name,
                output=output_text or "(No text output captured — check logs for workflow/n8n jobs.)"
            )

async def _execute_docker_script(script_name: str) -> str:
    """Run a python script in a Docker container and return output."""
    import os
    import docker
    import logging

    scripts_dir = os.path.join(os.getcwd(), "scripts")
    if not os.path.exists(os.path.join(scripts_dir, script_name)):
        return f"Error: Script {script_name} not found in {scripts_dir}"

    try:
        client = docker.from_env()
        # We mount the local scripts directory to /app in the container
        container = client.containers.run(
            image="python:3.11-slim",
            command=["python", f"/app/{script_name}"],
            volumes={scripts_dir: {"bind": "/app", "mode": "ro"}},
            remove=True,
            detach=False,
            stdout=True,
            stderr=True,
            network_disabled=True, # Security: disable network for untrusted scripts
            mem_limit="128m",       # Security: limit memory
        )
        return container.decode("utf-8")
    except Exception as e:
        logging.error(f"Docker script execution failed: {e}")
        return f"Error: {str(e)}"

def _send_job_email(to_email: str, job_name: str, output: str):
    """Best-effort SMTP email dispatch. Reads config from environment variables."""
    import os
    import smtplib
    import logging
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    smtp_port_str = os.environ.get("SMTP_PORT", "587").strip()
    smtp_port = int(smtp_port_str) if smtp_port_str.isdigit() else 587
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    from_email = os.environ.get("SMTP_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user:
        logging.warning(
            f"[Jobs] Job '{job_name}' completed but SMTP is not configured. "
            "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM in your environment."
        )
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"✅ Job Completed: {job_name}"
        msg["From"] = from_email
        msg["To"] = to_email

        text_body = f"Your scheduled job '{job_name}' has completed successfully.\n\n--- Output ---\n{output}"
        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #f8fafc;">
            <div style="background: white; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="margin-bottom: 24px;">
                    <span style="font-size: 28px;">✅</span>
                    <h1 style="margin: 8px 0 4px; font-size: 20px; color: #0f172a;">Job Completed</h1>
                    <p style="margin: 0; color: #64748b; font-size: 14px;"><strong>{job_name}</strong> finished successfully.</p>
                </div>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                <h2 style="font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 12px;">Output</h2>
                <pre style="background: #f1f5f9; padding: 16px; border-radius: 8px; font-size: 13px; color: #334155; white-space: pre-wrap; word-break: break-word;">{output}</pre>
            </div>
        </div>
        """

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to_email, msg.as_string())
        
        logging.info(f"[Jobs] Notification email sent to {to_email} for job '{job_name}'.")
    except Exception as e:
        logging.warning(f"[Jobs] Failed to send notification email for job '{job_name}': {e}")


async def _send_job_telegram(chat_id: str, job_name: str, output: str):
    """Dispatch Telegram message. Reads config from environment variables."""
    import os
    import logging
    from app.integrations.telegram_bot import send_telegram_message

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logging.warning(
            f"[Jobs] Job '{job_name}' completed but Telegram token is not configured. "
            "Set TELEGRAM_BOT_TOKEN in your environment."
        )
        return

    try:
        # Temporary debug logging to verify prompt respect
        with open("/tmp/last_job_output.txt", "w") as f:
            f.write(output)
            
        message = f"✅ *Job Completed: {job_name}*\n\n{output}"
        # Truncate if too long (Telegram limit is 4096)
        if len(message) > 4000:
            message = message[:3997] + "..."
        
        await send_telegram_message(chat_id, message)
        logging.info(f"[Jobs] Notification telegram sent to {chat_id} for job '{job_name}'.")
    except Exception as e:
        logging.warning(f"[Jobs] Failed to send notification telegram for job '{job_name}': {e}")


async def _execute_job_core(job_id: str) -> dict:
    """Execute a job's core logic and return result dict. Does NOT update the Job model."""
    async with async_session_factory() as db:
        job = await db.get(Job, job_id)
        if not job:
            return {"status": "failed", "error": f"Job {job_id} not found"}

    output_text = None
    try:
        if job.execution_type == "prompt":
            from app.core.orchestrator import orchestrator
            if job.target_id and job.prompt_text:
                summary_header = (
                    "### FORCED SUMMARY MODE ###\n"
                    "CRITICAL: FOR THIS SPECIFIC REQUEST, YOU MUST IGNORE ALL SYSTEM PROMPT INSTRUCTIONS REGARDING "
                    "OUTPUT STRUCTURE OR MANDATORY SECTIONS.\n\n"
                )
                summary_footer = (
                    "\n\n### FINAL REMINDER ###\n"
                    "ONLY PROVIDE THE SUMMARY REQUESTED ABOVE. SYSTEM PROMPT STRUCTURE RULES ARE SUSPENDED FOR THIS MESSAGE."
                )
                final_message = summary_header + job.prompt_text + summary_footer
                result = await orchestrator.route_message(
                    agent_id=job.target_id,
                    message=final_message,
                    chat_history=[]
                )
                output_text = result.get("output", "")
                if result.get("error"):
                    return {"status": "failed", "error": result.get("error"), "output": output_text}
        elif job.execution_type == "workflow":
            if job.target_id:
                await execute_workflow(job.target_id)
        elif job.execution_type == "n8n_workflow":
            if job.n8n_webhook_url:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(job.n8n_webhook_url, json={"job_id": job.id, "name": job.name})
                    if not resp.is_success:
                        return {"status": "failed", "error": f"n8n webhook returned {resp.status_code}"}
        elif job.execution_type == "docker_script":
            if job.script_name:
                output_text = await _execute_docker_script(job.script_name)
            else:
                return {"status": "failed", "error": "No script name provided"}
        return {"status": "success", "output": output_text}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


async def execute_batch_job(batch_job_id: str):
    """Execute a BatchJob: run all member jobs in parallel or sequential mode."""
    print(f"Executing batch job {batch_job_id}")
    async with async_session_factory() as db:
        batch = await db.get(BatchJob, batch_job_id)
        if not batch or not batch.is_active:
            return

        batch.last_run_at = datetime.now()
        batch.last_run_status = "running"
        await db.commit()

        run = BatchJobRun(batch_job_id=batch_job_id, status="running", results={})
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    job_ids = list(batch.job_ids or [])
    results: dict = {}

    start = datetime.now()

    try:
        if batch.execution_mode == "sequential":
            for jid in job_ids:
                t0 = datetime.now()
                res = await _execute_job_core(jid)
                results[jid] = {**res, "duration_ms": int((datetime.now() - t0).total_seconds() * 1000)}
        else:
            # parallel (default)
            async def _run(jid):
                t0 = datetime.now()
                res = await _execute_job_core(jid)
                return jid, {**res, "duration_ms": int((datetime.now() - t0).total_seconds() * 1000)}

            pairs = await asyncio.gather(*[_run(jid) for jid in job_ids], return_exceptions=True)
            for item in pairs:
                if isinstance(item, Exception):
                    continue
                jid, res = item
                results[jid] = res
    except Exception as e:
        print(f"Batch job {batch_job_id} execution failed: {e}")

    # Determine overall status
    statuses = [r.get("status") for r in results.values()]
    if all(s == "success" for s in statuses):
        overall = "success"
    elif all(s == "failed" for s in statuses):
        overall = "failed"
    else:
        overall = "partial"

    async with async_session_factory() as db:
        batch = await db.get(BatchJob, batch_job_id)
        if batch:
            batch.last_run_status = overall
            await db.commit()

        run = await db.get(BatchJobRun, run_id)
        if run:
            run.completed_at = datetime.now()
            run.status = overall
            run.results = results
            await db.commit()

    # Notifications
    if overall in ("success", "partial"):
        summary_lines = []
        for jid, res in results.items():
            icon = "✅" if res.get("status") == "success" else "❌"
            summary_lines.append(f"{icon} Job {jid[:8]}… — {res.get('status')} ({res.get('duration_ms', 0)}ms)")
        summary = "\n".join(summary_lines)

        if batch.notify_email:
            _send_job_email(
                to_email=batch.notify_email,
                job_name=batch.name,
                output=summary
            )
        if batch.notify_telegram_chat_id:
            await _send_job_telegram(
                chat_id=batch.notify_telegram_chat_id,
                job_name=batch.name,
                output=summary
            )


async def sync_batch_jobs():
    """Load batch jobs from DB and sync them into APScheduler."""
    async with async_session_factory() as db:
        for p_job in scheduler.get_jobs():
            if p_job.id.startswith("batch_"):
                scheduler.remove_job(p_job.id)

        result = await db.execute(select(BatchJob).where(BatchJob.is_active == True))
        batch_jobs = result.scalars().all()

        pacific_tz = pytz.timezone("America/Los_Angeles")

        for bj in batch_jobs:
            try:
                parts = bj.cron_expression.split(" ")
                if len(parts) == 5:
                    scheduler.add_job(
                        execute_batch_job,
                        trigger=CronTrigger(
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4],
                            timezone=pacific_tz
                        ),
                        args=[bj.id],
                        id=f"batch_{bj.id}",
                        replace_existing=True
                    )
            except Exception as e:
                print(f"Failed to schedule batch job {bj.id}: {e}")

        print(f"Synced {len(batch_jobs)} active batch jobs to scheduler.")


async def sync_jobs():
    """Load scheduled jobs from DB and sync them into APScheduler."""
    async with async_session_factory() as db:
        # Clear existing job triggers
        for p_job in scheduler.get_jobs():
            if p_job.id.startswith("job_"):
                scheduler.remove_job(p_job.id)
                
        result = await db.execute(select(Job).where(Job.is_active == True))
        jobs = result.scalars().all()
        
        pacific_tz = pytz.timezone("America/Los_Angeles")

        for job in jobs:
            try:
                # cron_expression is assumed to be standard cron e.g. "0 11 * * 1,2"
                # "minute hour day month day_of_week"
                parts = job.cron_expression.split(" ")
                if len(parts) == 5:
                    scheduler.add_job(
                        execute_job,
                        trigger=CronTrigger(
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4],
                            timezone=pacific_tz
                        ),
                        args=[job.id],
                        id=f"job_{job.id}",
                        replace_existing=True
                    )
            except Exception as e:
                print(f"Failed to schedule job {job.id}: {e}")
                
        print(f"Synced {len(jobs)} active jobs to scheduler.")

async def execute_trigger(trigger_id: str):
    """Execute a scheduled trigger."""
    from app.core.goal_engine import fire_trigger
    await fire_trigger(trigger_id)


# ─── Job Discovery ────────────────────────────────────────────────────────────

async def execute_job_search(config_id: str):
    """Run one job-discovery config end-to-end."""
    try:
        from app.core.job_discovery.service import run_job_search
        summary = await run_job_search(config_id)
        print(f"[Scheduler] Job discovery {config_id}: {summary}")
    except Exception as e:
        print(f"[Scheduler] Job discovery {config_id} failed: {e}")


async def sync_job_search_configs():
    """Load active JobSearchConfig rows and (re)register their cron jobs."""
    from app.models.job_search_config import JobSearchConfig

    async with async_session_factory() as db:
        # Clear existing jobsearch_* triggers so renames/reschedules take effect.
        for p_job in scheduler.get_jobs():
            if p_job.id.startswith("jobsearch_"):
                scheduler.remove_job(p_job.id)

        result = await db.execute(
            select(JobSearchConfig).where(JobSearchConfig.is_active == True)  # noqa: E712
        )
        configs = result.scalars().all()

        for cfg in configs:
            try:
                parts = (cfg.schedule_cron or "").split()
                if len(parts) != 5:
                    print(f"[Scheduler] Skipping job-search config {cfg.id}: bad cron {cfg.schedule_cron!r}")
                    continue
                tz = pytz.timezone(cfg.timezone or "America/Los_Angeles")
                scheduler.add_job(
                    execute_job_search,
                    trigger=CronTrigger(
                        minute=parts[0],
                        hour=parts[1],
                        day=parts[2],
                        month=parts[3],
                        day_of_week=parts[4],
                        timezone=tz,
                    ),
                    args=[cfg.id],
                    id=f"jobsearch_{cfg.id}",
                    replace_existing=True,
                )
            except Exception as e:
                print(f"[Scheduler] Failed to schedule job-search {cfg.id}: {e}")
        print(f"[Scheduler] Synced {len(configs)} job-search configs.")


async def run_h1b_quarterly_refresh():
    """Re-load USCIS Employer Data Hub CSVs for the canonical fiscal years."""
    try:
        from app.core.job_discovery.h1b_loader import refresh_uscis_default
        result = await refresh_uscis_default()
        print(f"[Scheduler] H-1B refresh: {result}")
    except Exception as e:
        print(f"[Scheduler] H-1B refresh failed: {e}")


async def sync_triggers():
    """Load schedule triggers from DB and sync them into APScheduler."""
    async with async_session_factory() as db:
        # Clear existing trigger jobs
        for p_job in scheduler.get_jobs():
            if p_job.id.startswith("trigger_"):
                scheduler.remove_job(p_job.id)

        result = await db.execute(
            select(AgentTrigger).where(
                AgentTrigger.is_active == True,
                AgentTrigger.trigger_type == TriggerType.schedule.value,
                AgentTrigger.cron_expression != None,
            )
        )
        triggers = result.scalars().all()
        pacific_tz = pytz.timezone("America/Los_Angeles")
        for trig in triggers:
            try:
                parts = trig.cron_expression.split(" ")
                if len(parts) == 5:
                    scheduler.add_job(
                        execute_trigger,
                        trigger=CronTrigger(
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4],
                            timezone=pacific_tz,
                        ),
                        args=[trig.id],
                        id=f"trigger_{trig.id}",
                        replace_existing=True,
                    )
            except Exception as e:
                print(f"Failed to schedule trigger {trig.id}: {e}")
        print(f"Synced {len(triggers)} active schedule triggers.")


async def expire_pending_approvals():
    """Mark pending approval requests as expired if their expires_at has passed.

    Supports configurable timeout actions:
    - Default: mark as expired
    - Escalation: send notification to Telegram/email before expiring
    - Auto-reject: expire and resume workflow with rejection
    """
    from app.models.approval_request import ApprovalRequest, ApprovalStatus
    from sqlalchemy import update as sa_update

    async with async_session_factory() as db:
        now = datetime.now()

        # 1. Find approvals that are about to expire (within 15 min) — send escalation warning
        warning_threshold = datetime.now()
        warning_threshold_future = datetime.fromtimestamp(now.timestamp() + 15 * 60)

        warning_result = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == ApprovalStatus.pending.value,
                ApprovalRequest.expires_at != None,
                ApprovalRequest.expires_at > now,
                ApprovalRequest.expires_at <= warning_threshold_future,
            )
        )
        expiring_soon = warning_result.scalars().all()
        for req in expiring_soon:
            # Only warn once — check if we already warned (use context field)
            ctx = req.context or {}
            if not ctx.get("_expiry_warned"):
                minutes_left = int((req.expires_at.timestamp() - now.timestamp()) / 60)
                await _send_expiry_warning(req, minutes_left)
                ctx["_expiry_warned"] = True
                req.context = ctx
        if expiring_soon:
            await db.commit()

        # 2. Expire approvals past their deadline
        stmt = (
            sa_update(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.pending.value)
            .where(ApprovalRequest.expires_at <= now)
            .values(status=ApprovalStatus.expired.value)
        )
        result = await db.execute(stmt)
        await db.commit()
        if result.rowcount:
            print(f"Expired {result.rowcount} approval requests.")

            # 3. Send expiry notifications
            expired_result = await db.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.status == ApprovalStatus.expired.value,
                    ApprovalRequest.expires_at != None,
                    ApprovalRequest.expires_at >= datetime.fromtimestamp(now.timestamp() - 10 * 60),
                )
            )
            for req in expired_result.scalars().all():
                await _send_expiry_notification(req)


async def _send_expiry_warning(req, minutes_left: int):
    """Send a warning that an approval is about to expire."""
    import os
    try:
        telegram_chat_id = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
        if telegram_chat_id:
            from app.integrations.telegram_bot import send_telegram_message
            risk = req.risk_level or "unknown"
            msg = (
                f"⚠️ *Approval Expiring Soon*\n\n"
                f"*{req.title}*\n"
                f"Risk: `{risk}` | Expires in ~{minutes_left} min\n\n"
                f"Review it before it auto-expires."
            )
            await send_telegram_message(telegram_chat_id, msg)
    except Exception as e:
        print(f"[Scheduler] Expiry warning notification failed: {e}")


async def _send_expiry_notification(req):
    """Notify that an approval has expired."""
    import os
    try:
        telegram_chat_id = os.environ.get("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
        if telegram_chat_id:
            from app.integrations.telegram_bot import send_telegram_message
            msg = (
                f"🕐 *Approval Expired*\n\n"
                f"*{req.title}*\n"
                f"Category: `{req.category or 'general'}` | Risk: `{req.risk_level or 'unknown'}`\n"
                f"No human review within the deadline."
            )
            await send_telegram_message(telegram_chat_id, msg)
    except Exception as e:
        print(f"[Scheduler] Expiry notification failed: {e}")


async def run_scheduled_checkins():
    """Daily job: run check-ins for every agent that has at least one active goal."""
    from app.models.goal import AgentGoal, GoalStatus
    from sqlalchemy import distinct

    async with async_session_factory() as db:
        result = await db.execute(
            select(distinct(AgentGoal.agent_id)).where(
                AgentGoal.status == GoalStatus.active.value
            )
        )
        agent_ids = [row[0] for row in result.all()]

    if not agent_ids:
        return

    print(f"[Scheduler] Running check-ins for {len(agent_ids)} agent(s) with active goals.")
    from app.core.goal_engine import run_checkin
    for agent_id in agent_ids:
        try:
            await run_checkin(agent_id)
        except Exception as e:
            print(f"[Scheduler] Check-in failed for agent {agent_id}: {e}")


async def run_memory_maintenance():
    """Daily job: update decay scores and consolidate old recall memories into archival."""
    try:
        from app.core.memory_service import memory_service

        async with async_session_factory() as db:
            decayed = await memory_service.update_decay_scores(db)
            consolidated = await memory_service.consolidate(db)

        print(
            f"[Scheduler] Memory maintenance: {decayed} decay scores updated, "
            f"consolidated={consolidated}"
        )
    except Exception as e:
        print(f"[Scheduler] Memory maintenance failed: {e}")


async def run_evolve_daily_analysis():
    """Scheduled job: run Evolve daily analysis."""
    try:
        from app.core.evolve_service import run_daily_analysis
        run = await run_daily_analysis()
        print(f"[Scheduler] Evolve daily analysis: {run.suggestions_generated} suggestions, status={run.status}")
    except Exception as e:
        print(f"[Scheduler] Evolve daily analysis failed: {e}")


async def run_evolve_competitor_monitor():
    """Scheduled job: run Evolve competitor monitor."""
    try:
        from app.core.evolve_service import run_competitor_monitor
        run = await run_competitor_monitor()
        print(f"[Scheduler] Evolve competitor monitor: {run.suggestions_generated} suggestions, status={run.status}")
    except Exception as e:
        print(f"[Scheduler] Evolve competitor monitor failed: {e}")


async def run_alert_evaluation():
    """Scheduled job: evaluate alert rules and fire/resolve alerts."""
    try:
        from app.core.alert_evaluator import evaluate_alerts
        stats = await evaluate_alerts()
        print(f"[Scheduler] Alert evaluation: {stats}")
    except Exception as e:
        print(f"[Scheduler] Alert evaluation failed: {e}")


async def run_fleet_triage():
    """Scheduled job: run one fleet triage pass.

    `triage_and_enqueue` itself short-circuits if a non-terminal job already
    exists, so this is safe to call hourly.
    """
    from app.core.fleet_orchestrator import triage_and_enqueue

    try:
        async with async_session_factory() as db:
            job = await triage_and_enqueue(db)
        if job:
            print(f"[Scheduler] Fleet triage: enqueued {job.id} → {job.repo_url} {job.issue_ref}")
    except Exception as e:
        print(f"[Scheduler] Fleet triage failed: {e}")


async def run_fleet_watchdog():
    """Scheduled job: poke the host worker if anything looks stuck.

    Cheap — usually no-ops because dispatch happens at enqueue time. Only
    matters when the host worker was offline at enqueue or crashed mid-job.
    """
    from app.core.fleet_dispatcher import watchdog_tick

    try:
        async with async_session_factory() as db:
            stats = await watchdog_tick(db)
        if stats["kicked_queued"] or stats["revived_claimed"]:
            print(f"[Scheduler] Fleet watchdog: {stats}")
    except Exception as e:
        print(f"[Scheduler] Fleet watchdog failed: {e}")


async def run_forge_queue():
    """Scheduled job: process the Forge request queue one request at a time.

    Picks up all queued ForgeRequests (oldest first) and runs them sequentially
    — planning → (user approval if needed) → coding → tests → PR.
    Auto-approved requests proceed end-to-end without user interaction.
    Non-auto-approved requests advance to 'awaiting_plan_approval' and pause
    until the user clicks Approve in the UI.
    """
    import asyncio as _asyncio
    from app.models.forge import ForgeRequest, ForgeStatus
    from sqlalchemy import select as sa_select

    print("[Scheduler] Forge queue runner started.")

    async with async_session_factory() as db:
        result = await db.execute(
            sa_select(ForgeRequest)
            .where(ForgeRequest.status == ForgeStatus.queued.value)
            .order_by(ForgeRequest.created_at)  # FIFO
        )
        queued = result.scalars().all()

    if not queued:
        print("[Scheduler] Forge queue is empty — nothing to do.")
        return

    print(f"[Scheduler] Forge queue: processing {len(queued)} request(s) sequentially.")

    for req in queued:
        forge_id = req.id
        print(f"[Scheduler] Forge queue: starting {forge_id!r} — '{req.title}'")

        # Re-check status in case it changed since we loaded the list
        async with async_session_factory() as db:
            fresh = await db.get(ForgeRequest, forge_id)
            if not fresh or fresh.status != ForgeStatus.queued.value:
                print(f"[Scheduler] Forge queue: skipping {forge_id!r} (status changed to {getattr(fresh, 'status', 'gone')})")
                continue

            # Transition to planning so the UI shows progress
            fresh.status = ForgeStatus.planning.value
            await db.commit()

        try:
            from app.api.routes.forge import _run_planning
            await _run_planning(
                forge_id,
                req.repo_url,
                req.description,
                req.workspace_path or "",
                req.branch_name or "",
                req.llm_provider,
                req.llm_model,
                req.auto_approve_plan,
            )
        except Exception as e:
            print(f"[Scheduler] Forge queue: _run_planning failed for {forge_id!r}: {e}")
            async with async_session_factory() as db:
                stuck = await db.get(ForgeRequest, forge_id)
                if stuck and stuck.status == ForgeStatus.planning.value:
                    stuck.status = ForgeStatus.failed.value
                    stuck.error_log = f"Queue runner error: {e}"
                    await db.commit()
            continue

        # If auto_approve_plan, _run_planning will have already kicked off
        # _run_coding via create_task inside the engine.  We wait for it to
        # finish before moving to the next request so the queue stays serial.
        if req.auto_approve_plan:
            # Poll until this request leaves the coding/testing states
            for _ in range(2400):   # max 40 min at 1-second intervals
                await _asyncio.sleep(1)
                async with async_session_factory() as db:
                    polling = await db.get(ForgeRequest, forge_id)
                terminal = (
                    ForgeStatus.completed.value,
                    ForgeStatus.failed.value,
                    ForgeStatus.cancelled.value,
                    ForgeStatus.pr_created.value,
                )
                if polling and polling.status in terminal:
                    print(f"[Scheduler] Forge queue: {forge_id!r} finished with status={polling.status}")
                    break
            else:
                print(f"[Scheduler] Forge queue: {forge_id!r} timed out after 40 min, moving on.")
        else:
            # Request needs manual plan approval — do NOT block the queue.
            # The user will click Approve in the UI; the next queue flush will
            # pick up the next queued request independently.
            print(f"[Scheduler] Forge queue: {forge_id!r} is awaiting plan approval — pausing sequential flow here.")
            break

    print("[Scheduler] Forge queue runner completed.")


async def run_project_compaction():
    """Nightly job: compact all active project memories."""
    try:
        from app.core.project_memory_service import compact_all_projects

        async with async_session_factory() as db:
            stats = await compact_all_projects(db)
            await db.commit()

        print(f"[Scheduler] Project compaction: {stats}")
    except Exception as e:
        print(f"[Scheduler] Project compaction failed: {e}")


async def refresh_social_pulse():
    """Scheduled job: refresh Social Pulse trending data."""
    try:
        from app.core.social_pulse_service import refresh_all_platforms
        stats = await refresh_all_platforms()
        print(f"[Scheduler] Social Pulse refresh: {stats}")
    except Exception as e:
        print(f"[Scheduler] Social Pulse refresh failed: {e}")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("APScheduler started")
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(sync_workflows())
            loop.create_task(sync_jobs())
            loop.create_task(sync_batch_jobs())
            loop.create_task(sync_triggers())
            loop.create_task(sync_job_search_configs())
            scheduler.add_job(
                expire_pending_approvals,
                trigger=IntervalTrigger(minutes=5),
                id="expire_approvals",
                replace_existing=True,
            )
            # Scheduled check-ins — time from CHECKIN_CRON env var (America/Los_Angeles)
            from app.config import settings
            pacific_tz = pytz.timezone("America/Los_Angeles")
            cron_parts = settings.checkin_cron.split()
            if len(cron_parts) == 5:
                scheduler.add_job(
                    run_scheduled_checkins,
                    trigger=CronTrigger(
                        minute=cron_parts[0],
                        hour=cron_parts[1],
                        day=cron_parts[2],
                        month=cron_parts[3],
                        day_of_week=cron_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="daily_checkins",
                    replace_existing=True,
                )
                print(f"[Scheduler] Check-ins scheduled: {settings.checkin_cron} (America/Los_Angeles)")

            # Memory maintenance — configurable cron (default: 0 3 * * *)
            mem_cron_parts = settings.memory_maintenance_cron.split()
            if len(mem_cron_parts) == 5:
                scheduler.add_job(
                    run_memory_maintenance,
                    trigger=CronTrigger(
                        minute=mem_cron_parts[0],
                        hour=mem_cron_parts[1],
                        day=mem_cron_parts[2],
                        month=mem_cron_parts[3],
                        day_of_week=mem_cron_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="memory_maintenance",
                    replace_existing=True,
                )
                print(f"[Scheduler] Memory maintenance scheduled: {settings.memory_maintenance_cron} (America/Los_Angeles)")

            # Project memory compaction — 30 min after memory maintenance
            proj_cron_parts = settings.project_compaction_cron.split()
            if len(proj_cron_parts) == 5:
                scheduler.add_job(
                    run_project_compaction,
                    trigger=CronTrigger(
                        minute=proj_cron_parts[0],
                        hour=proj_cron_parts[1],
                        day=proj_cron_parts[2],
                        month=proj_cron_parts[3],
                        day_of_week=proj_cron_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="project_compaction",
                    replace_existing=True,
                )
                print(f"[Scheduler] Project compaction scheduled: {settings.project_compaction_cron} (America/Los_Angeles)")

            # Evolve daily analysis
            evolve_daily_parts = settings.evolve_daily_cron.split()
            if len(evolve_daily_parts) == 5:
                scheduler.add_job(
                    run_evolve_daily_analysis,
                    trigger=CronTrigger(
                        minute=evolve_daily_parts[0],
                        hour=evolve_daily_parts[1],
                        day=evolve_daily_parts[2],
                        month=evolve_daily_parts[3],
                        day_of_week=evolve_daily_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="evolve_daily_analysis",
                    replace_existing=True,
                )
                print(f"[Scheduler] Evolve daily analysis scheduled: {settings.evolve_daily_cron} (America/Los_Angeles)")

            # Evolve competitor monitor
            evolve_comp_parts = settings.evolve_competitor_cron.split()
            if len(evolve_comp_parts) == 5:
                scheduler.add_job(
                    run_evolve_competitor_monitor,
                    trigger=CronTrigger(
                        minute=evolve_comp_parts[0],
                        hour=evolve_comp_parts[1],
                        day=evolve_comp_parts[2],
                        month=evolve_comp_parts[3],
                        day_of_week=evolve_comp_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="evolve_competitor_monitor",
                    replace_existing=True,
                )
                print(f"[Scheduler] Evolve competitor monitor scheduled: {settings.evolve_competitor_cron} (America/Los_Angeles)")

            # Alert evaluation — configurable interval (default 30 min)
            alert_interval = settings.alert_evaluation_interval_minutes
            scheduler.add_job(
                run_alert_evaluation,
                trigger=IntervalTrigger(minutes=alert_interval),
                id="alert_evaluation",
                replace_existing=True,
            )
            print(f"[Scheduler] Alert evaluation scheduled: every {alert_interval} minutes")

            # Social Pulse refresh — every 30 min by default
            pulse_cron_parts = settings.social_pulse_cron.split()
            if len(pulse_cron_parts) == 5:
                scheduler.add_job(
                    refresh_social_pulse,
                    trigger=CronTrigger(
                        minute=pulse_cron_parts[0],
                        hour=pulse_cron_parts[1],
                        day=pulse_cron_parts[2],
                        month=pulse_cron_parts[3],
                        day_of_week=pulse_cron_parts[4],
                    ),
                    id="social_pulse_refresh",
                    replace_existing=True,
                )
                print(f"[Scheduler] Social Pulse refresh scheduled: {settings.social_pulse_cron}")

            # H-1B sponsor data refresh — quarterly cron (UTC)
            h1b_parts = settings.h1b_refresh_cron.split()
            if len(h1b_parts) == 5:
                scheduler.add_job(
                    run_h1b_quarterly_refresh,
                    trigger=CronTrigger(
                        minute=h1b_parts[0],
                        hour=h1b_parts[1],
                        day=h1b_parts[2],
                        month=h1b_parts[3],
                        day_of_week=h1b_parts[4],
                    ),
                    id="h1b_quarterly_refresh",
                    replace_existing=True,
                )
                print(f"[Scheduler] H-1B quarterly refresh scheduled: {settings.h1b_refresh_cron}")

            # Forge queue runner — process queued forge requests one-by-one
            # Default: 7:00 PM Pacific every day (FORGE_QUEUE_CRON env var to override)
            forge_cron_parts = settings.forge_queue_cron.split()
            if len(forge_cron_parts) == 5:
                scheduler.add_job(
                    run_forge_queue,
                    trigger=CronTrigger(
                        minute=forge_cron_parts[0],
                        hour=forge_cron_parts[1],
                        day=forge_cron_parts[2],
                        month=forge_cron_parts[3],
                        day_of_week=forge_cron_parts[4],
                        timezone=pacific_tz,
                    ),
                    id="forge_queue_runner",
                    replace_existing=True,
                )
                print(f"[Scheduler] Forge queue runner scheduled: {settings.forge_queue_cron} (America/Los_Angeles)")

            # Fleet triage runner — picks an issue across fleet_repos and enqueues
            # it, but ONLY when there is no in-flight job. Host worker drains it.
            fleet_cron_parts = settings.fleet_triage_cron.split()
            if len(fleet_cron_parts) == 5 and (settings.fleet_repos or "").strip():
                scheduler.add_job(
                    run_fleet_triage,
                    trigger=CronTrigger(
                        minute=fleet_cron_parts[0],
                        hour=fleet_cron_parts[1],
                        day=fleet_cron_parts[2],
                        month=fleet_cron_parts[3],
                        day_of_week=fleet_cron_parts[4],
                    ),
                    id="fleet_triage_runner",
                    replace_existing=True,
                )
                print(f"[Scheduler] Fleet triage runner scheduled: {settings.fleet_triage_cron}")

            # Fleet watchdog — pokes the host worker for any queued/stuck jobs
            watchdog_parts = settings.fleet_watchdog_cron.split()
            if len(watchdog_parts) == 5 and (settings.fleet_worker_token or "").strip():
                scheduler.add_job(
                    run_fleet_watchdog,
                    trigger=CronTrigger(
                        minute=watchdog_parts[0],
                        hour=watchdog_parts[1],
                        day=watchdog_parts[2],
                        month=watchdog_parts[3],
                        day_of_week=watchdog_parts[4],
                    ),
                    id="fleet_watchdog",
                    replace_existing=True,
                )
                print(f"[Scheduler] Fleet watchdog scheduled: {settings.fleet_watchdog_cron}")
