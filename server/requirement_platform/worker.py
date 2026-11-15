import os
import time
from datetime import datetime, timedelta, timezone

from .config import settings
from .db import SessionLocal, init_db
from .models import BackgroundJob
from .services import analyze_requirement, sync_batch_milestone, sync_requirement_issue
from .domain.common import retry_at
from .github_sync import reconcile_pull_requests, schedule_pull_request_reconciliation
from .conversations import process_message
from .notifications import claim_email, send_email
from .collaboration_models import AIQuota
from sqlalchemy import and_, or_


HANDLERS = {
    "conversation": process_message,
    "triage": analyze_requirement,
    "github_issue": sync_requirement_issue,
    "github_milestone": sync_batch_milestone,
    "github_pull_requests": reconcile_pull_requests,
}


def claim_job(db):
    now = datetime.now(timezone.utc)
    eligible = and_(
        BackgroundJob.available_at <= now,
        ((BackgroundJob.status == "queued") | ((BackgroundJob.status == "running") & (BackgroundJob.lease_expires_at < now))),
    )
    row = db.query(BackgroundJob).filter(eligible).order_by(BackgroundJob.created_at).first()
    if not row:
        return None
    job_id = row.id
    claimed = db.query(BackgroundJob).filter(BackgroundJob.id == job_id, eligible).update({
        "status": "running", "attempts": BackgroundJob.attempts + 1, "lease_expires_at": now + timedelta(minutes=15),
    }, synchronize_session=False)
    db.commit()
    return job_id if claimed else None


def run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if not job:
            return
        handler = HANDLERS.get(job.job_type)
        if not handler:
            raise RuntimeError(f"Unknown job type: {job.job_type}")
        handler(db, job.object_id)
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        job.status = "completed"
        job.lease_expires_at = None
        job.last_error = None
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.last_error = str(exc)[:4000]
            job.lease_expires_at = None
            if job.job_type == "conversation" or job.attempts >= settings.max_job_attempts:
                job.status = "failed"
            else:
                job.status = "queued"
                job.available_at = retry_at(job.attempts)
            db.commit()
    finally:
        db.close()


def main() -> None:
    init_db()
    once = os.getenv("RP_WORKER_ONCE", "").lower() in {"1", "true", "yes"}
    while True:
        db = SessionLocal()
        try:
            db.query(AIQuota).filter(AIQuota.expires_at < datetime.now(timezone.utc) - timedelta(days=2)).delete(synchronize_session=False)
            schedule_pull_request_reconciliation(db)
            db.commit()
            email_claim = claim_email(db)
            if email_claim:
                send_email(db, *email_claim)
            job_id = claim_job(db)
        finally:
            db.close()
        if job_id:
            run_job(job_id)
        elif once and not email_claim:
            return
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
