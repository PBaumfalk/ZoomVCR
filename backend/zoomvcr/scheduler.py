"""Persistent DB-backed scheduler; Redis lock prevents duplicate starts."""
import logging
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from redis import Redis
from rq import Queue
from .db import SessionLocal, init_db
from .models import Recording
from .config import settings
from .tasks import aware

LOG = logging.getLogger("zoomvcr.scheduler")

def enqueue_capture(recording_id: str, redis=None) -> bool:
    conn = redis or Redis.from_url(settings().redis_url)
    lock = "zoomvcr:enqueue:" + recording_id
    if not conn.set(lock, "1", nx=True, ex=120):
        return False
    try:
        Queue("capture", connection=conn).enqueue("zoomvcr.tasks.capture_job", recording_id, job_timeout=33000, result_ttl=3600)
        return True
    except Exception:
        conn.delete(lock)
        raise

def schedule_due(now=None):
    now = now or datetime.now(timezone.utc)
    conn = Redis.from_url(settings().redis_url)
    with SessionLocal() as db:
        candidates = db.scalars(select(Recording).where(Recording.status == "planned")).all()
    lead = timedelta(minutes=max(0, settings().join_lead_minutes))
    for job in candidates:
        start_at = aware(job.scheduled_at) - (lead if job.source == "desktop_manual" else timedelta(0))
        if start_at > now:
            continue
        if aware(job.ends_at) <= now:
            with SessionLocal.begin() as db:
                obj = db.get(Recording, job.id)
                if obj.status == "planned":
                    obj.status = "error"
                    obj.error = "Recording window elapsed before capture could begin"
            continue
        with SessionLocal.begin() as db:
            obj = db.get(Recording, job.id)
            if obj.status != "planned":
                continue
            obj.status = "connecting"
        try:
            enqueue_capture(job.id, conn)
        except Exception as err:
            with SessionLocal.begin() as db:
                obj = db.get(Recording, job.id)
                obj.status = "error"
                obj.error = "Could not enqueue recording: " + str(err)[:250]
    # Lost capture process: never pretend unfinished segments are a completed recording.
    with SessionLocal() as db:
        running = db.scalars(select(Recording).where(Recording.status.in_(["connecting", "waiting_room", "recording"]))).all()
    for job in running:
        heartbeat = aware(job.heartbeat_at) if job.heartbeat_at else aware(job.scheduled_at)
        if (now - heartbeat).total_seconds() > 150:
            with SessionLocal.begin() as db:
                obj = db.get(Recording, job.id)
                if obj.status in {"connecting", "waiting_room", "recording"}:
                    obj.status = "interrupted"
                    obj.error = "Capture heartbeat lost; existing segments retained. Manual recovery required."

def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    while True:
        try:
            schedule_due()
        except Exception:
            LOG.exception("Scheduler iteration failed")
        time.sleep(3)

if __name__ == "__main__":
    main()
