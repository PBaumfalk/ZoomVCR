from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import json
import os
import re
import shutil
import zipfile
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from redis import Redis
from rq import Queue
from .db import init_db, db_session
from .models import Recording, Slide
from .schemas import CreateRecording, UpdateParticipantName
from .config import settings, origin_allowed
from .security import Principal, require_role, log_event, bootstrap_admin
from .media import recording_dir
from .tasks import aware, utcnow
from .scheduler import enqueue_capture
from .users_api import router as users_router
from .oidc import router as oidc_router
from .ai_settings import router as ai_settings_router
from starlette.middleware.sessions import SessionMiddleware
from .db import SessionLocal

@asynccontextmanager
async def lifespan(_app):
    config = settings()
    if (len(config.secret_key) < 32 or len(config.api_token) < 24
            or config.secret_key == "CHANGE_TO_64_RANDOM_HEX_CHARACTERS"
            or config.api_token == "CHANGE_TO_A_SEPARATE_LONG_RANDOM_TOKEN"):
        raise RuntimeError("Set unique strong ZOOMVCR_SECRET_KEY and API_TOKEN in .env")
    if not origin_allowed(config.public_origin):
        raise RuntimeError("Use HTTPS for ZOOMVCR_PUBLIC_ORIGIN except on local development hosts")
    config.storage_root.mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as session:
        bootstrap_admin(session)
    yield

app = FastAPI(title="ZoomVCR", version="0.3.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings().secret_key or "not-configured",
                   session_cookie="zoomvcr_oidc_state",
                   https_only=settings().public_origin.startswith("https://"),
                   same_site="lax", max_age=600)
app.include_router(users_router)
app.include_router(oidc_router)
app.include_router(ai_settings_router)

@app.get("/health")
def health():
    from .db import engine
    from sqlalchemy import text
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        Redis.from_url(settings().redis_url, socket_connect_timeout=2).ping()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(503, "Storage or worker queue unavailable")

def serialize(obj: Recording):
    return {"id": obj.id, "title": obj.title, "source": obj.source, "participant_name": obj.participant_name, "scheduled_at": aware(obj.scheduled_at).isoformat(), "ends_at": aware(obj.ends_at).isoformat(), "status": obj.status, "duration_seconds": obj.duration_seconds, "error": obj.error, "processing_notes": obj.processing_notes, "created_at": aware(obj.created_at).isoformat(), "disclosure_acknowledged": obj.disclosure_acknowledged, "permission_confirmed": obj.permission_confirmed, "metadata": obj.metadata_json or {}}

@app.get("/api/status")
def service_status(db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    rows = db.scalars(select(Recording)).all()
    counts = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {"recordings": len(rows), "by_status": counts, "disk_free_bytes": shutil.disk_usage(settings().storage_root).free, "source_modes": {"synthetic": "working test mode", "desktop_manual": "experimental / configurable" if settings().enable_desktop else "disabled"}}

@app.get("/api/recordings")
def list_recordings(q: str = "", db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    stmt = select(Recording).order_by(Recording.scheduled_at.desc()).limit(300)
    if q:
        stmt = stmt.where(Recording.title.ilike("%" + q.replace("%", "\\%")[:100] + "%"))
    return [serialize(r) for r in db.scalars(stmt)]

@app.post("/api/recordings", status_code=201)
def create_recording(item: CreateRecording, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    if item.source == "desktop_manual" and not settings().enable_desktop:
        raise HTTPException(503, "Zoom desktop adapter is disabled in server configuration")
    now = utcnow()
    start = item.scheduled_at.astimezone(timezone.utc)
    if start < now - timedelta(seconds=20):
        raise HTTPException(400, "Start time is in the past")
    buffer = max(0, getattr(settings(), "end_buffer_minutes", 15)) if item.source == "desktop_manual" else 0
    obj = Recording(title=item.title.strip(), source=item.source, meeting_url=item.meeting_url,
                    participant_name=item.participant_name,
                    scheduled_at=start, ends_at=start + timedelta(minutes=item.duration_minutes + buffer),
                    permission_confirmed=item.permission_confirmed, disclosure_acknowledged=item.disclosure_acknowledged, status="planned",
                    metadata_json={"authorization_basis": item.authorization_basis,
                                   "end_buffer_minutes": buffer,
                                   "authorization_reference": item.authorization_reference or "",
                                   "permission_recorded_at": now.isoformat(),
                                   "participant_name_status": "not_checked" if item.source == "desktop_manual" else "not_applicable"})
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # This is an operator attestation, not an independently verified host consent.
    # Store it separately so a ZIP export contains an audit reference as well.
    from .analysis import save_json
    save_json(recording_dir(obj.id) / "authorization.json", {
        "recording_id": obj.id,
        "basis": item.authorization_basis,
        "requested_participant_name": item.participant_name,
        "reference": item.authorization_reference or "",
        "operator_confirmed": item.permission_confirmed,
        "participant_information_confirmed": item.disclosure_acknowledged,
        "attested_at": now.isoformat(),
        "notice": "Operator statement; not Zoom-host verification or proof of attendance",
    })
    log_event(db, user, "recording.create", "recording", obj.id)
    db.commit()
    return serialize(obj)


@app.patch("/api/recordings/{recording_id}/participant-name")
def change_participant_name(recording_id: str, payload: UpdateParticipantName,
                            db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if obj is None:
        raise HTTPException(404, "Recording not found")
    if obj.source != "desktop_manual" or obj.status != "planned":
        raise HTTPException(409, "Display name may be changed only for a planned Zoom recording")
    obj.participant_name = payload.participant_name
    obj.metadata_json = {**(obj.metadata_json or {}), "participant_name_status": "not_checked"}
    db.commit()
    from .analysis import save_json
    folder = recording_dir(recording_id)
    audit = folder / "authorization.json"
    data = json.loads(audit.read_text()) if audit.is_file() else {"recording_id": recording_id}
    data["requested_participant_name"] = payload.participant_name
    data["name_updated_at"] = utcnow().isoformat()
    save_json(audit, data)
    log_event(db, user, "recording.rename", "recording", obj.id)
    db.commit()
    return serialize(obj)


@app.post("/api/recordings/{recording_id}/confirm-name")
def confirm_participant_name(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if obj is None:
        raise HTTPException(404, "Recording not found")
    if obj.source != "desktop_manual" or obj.status not in {"connecting", "waiting_room"}:
        raise HTTPException(409, "Name confirmation requires a Zoom connection in progress")
    if not obj.participant_name:
        raise HTTPException(409, "No requested display name is stored")
    # An operator must inspect their own row in the Zoom participant list by VNC.
    Redis.from_url(settings().redis_url).setex("zoomvcr:name-confirm:" + recording_id, 600, "1")
    log_event(db, user, "recording.confirm_name", "recording", recording_id)
    db.commit()
    return {"status": "operator_confirmed", "participant_name": obj.participant_name,
            "note": "Operator declares that the actual Zoom self name matches the requested name"}

@app.get("/api/recordings/{recording_id}")
def get_recording(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    obj = db.get(Recording, recording_id)
    if obj is None:
        raise HTTPException(404, "Recording not found")
    return serialize(obj)

@app.post("/api/recordings/{recording_id}/start")
def start_recording(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if not obj:
        raise HTTPException(404, "Recording not found")
    if obj.status != "planned":
        raise HTTPException(409, "Recording is not planned")
    if obj.source == "desktop_manual" and not settings().enable_desktop:
        raise HTTPException(503, "Zoom desktop adapter is disabled")
    if aware(obj.ends_at) <= utcnow():
        raise HTTPException(409, "Recording window has elapsed")
    obj.status = "connecting"
    db.commit()
    try:
        enqueue_capture(recording_id)
    except Exception as e:
        obj.status = "error"
        obj.error = "Enqueue failed: " + str(e)[:200]
        db.commit()
        raise HTTPException(503, "Queue unavailable")
    log_event(db, user, "recording.start", "recording", recording_id)
    db.commit()
    return serialize(obj)

@app.post("/api/recordings/{recording_id}/stop")
def stop_recording(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if not obj:
        raise HTTPException(404, "Recording not found")
    if obj.status == "planned":
        obj.status = "error"
        obj.error = "Cancelled by operator before start"
        log_event(db, user, "recording.cancel", "recording", recording_id)
        db.commit()
        return {"status": "cancelled"}
    if obj.status not in {"connecting", "waiting_room", "recording"}:
        raise HTTPException(409, "Recording is not running")
    Redis.from_url(settings().redis_url).setex("zoomvcr:stop:" + recording_id, 600, "1")
    log_event(db, user, "recording.stop", "recording", recording_id)
    db.commit()
    return {"status": "stop_requested"}

@app.post("/api/recordings/{recording_id}/process")
def process_recording(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if not obj:
        raise HTTPException(404, "Recording not found")
    if obj.status not in {"recorded", "ready", "error"}:
        raise HTTPException(409, "Cannot process while capture is active")
    folder = recording_dir(recording_id)
    if not (folder / "recording.mp4").exists() and not list((folder / "segments").glob("*.mkv")):
        raise HTTPException(400, "No captured media to process")
    obj.status = "processing"
    db.commit()
    try:
        Queue("processing", connection=Redis.from_url(settings().redis_url)).enqueue("zoomvcr.tasks.process_job", recording_id, job_timeout=14400, result_ttl=86400)
    except Exception:
        obj.status = "error"
        obj.error = "Processing queue is unavailable"
        db.commit()
        raise HTTPException(503, "Queue unavailable")
    log_event(db, user, "recording.process", "recording", recording_id)
    db.commit()
    return serialize(obj)

@app.get("/api/recordings/{recording_id}/transcript")
def transcript(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    path = recording_dir(recording_id) / "transcript.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

@app.get("/api/recordings/{recording_id}/summary")
def summary(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    path = recording_dir(recording_id) / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"available": False}

@app.get("/api/recordings/{recording_id}/slides")
def slides(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    return [{"id": s.id, "time_seconds": s.time_seconds, "image_name": s.image_name,
             "ocr_text": s.ocr_text, "transcript_excerpt": s.transcript_excerpt,
             "image_url": f"/api/recordings/{recording_id}/slides/{s.id}/image"}
            for s in db.scalars(select(Slide).where(Slide.recording_id == recording_id).order_by(Slide.time_seconds))]

@app.get("/api/recordings/{recording_id}/slides/{slide_id}/image")
def image(recording_id: str, slide_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    obj = db.get(Slide, slide_id)
    if not obj or obj.recording_id != recording_id:
        raise HTTPException(404)
    path = recording_dir(recording_id) / "slides" / obj.image_name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")

@app.get("/api/recordings/{recording_id}/video")
def video(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    path = recording_dir(recording_id) / "recording.mp4"
    if not path.is_file():
        raise HTTPException(404, "Video not yet available")
    return FileResponse(path, media_type="video/mp4", content_disposition_type="inline")

@app.get("/api/recordings/{recording_id}/logs")
def logs(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    file = recording_dir(recording_id) / "ffmpeg.log"
    if not file.exists():
        return {"log": "No FFmpeg logs available"}
    with file.open("rb") as h:
        h.seek(max(0, file.stat().st_size - 50000))
        log = h.read().decode("utf-8", errors="replace")
    return {"log": log}

@app.get("/api/recordings/{recording_id}/export/{kind}")
def download(recording_id: str, kind: str, db: Session = Depends(db_session), user=Depends(require_role("viewer"))):
    if not db.get(Recording, recording_id):
        raise HTTPException(404)
    allowed = {"video": "recording.mp4", "original": "original.mp4", "transcript": "transcript.txt", "transcript_json": "transcript.json", "summary": "summary.json", "slides": "slides.json", "sources": "legal_sources.json", "authorization": "authorization.json"}
    directory = recording_dir(recording_id)
    if kind not in {*allowed, "zip"}:
        raise HTTPException(404)
    log_event(db, user, "recording.export", "recording", recording_id, details={"format": kind})
    db.commit()
    if kind == "zip":
        output = directory / "archive.zip"
        temp = directory / "archive.partial.zip"
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
            for file in directory.rglob("*"):
                if file.is_file() and file not in {output, temp} and "segments" not in file.parts and file.name not in {"audio.wav", "ffmpeg.log", "original.mp4"}:
                    z.write(file, file.relative_to(directory))
        temp.replace(output)
        return FileResponse(output, filename=f"zoomvcr-{recording_id}.zip")
    if kind not in allowed:
        raise HTTPException(404)
    file = directory / allowed[kind]
    if not file.is_file():
        raise HTTPException(404, "Export is not ready")
    return FileResponse(file, filename=file.name)


ACTIVE_STATES = {"connecting", "waiting_room", "recording", "processing"}


@app.delete("/api/recordings/{recording_id}")
def delete_recording(recording_id: str, request: Request, db: Session = Depends(db_session),
                     user=Depends(require_role("admin"))):
    """Permanently delete a recording: database entry, slides, video, transcript, reports and exports."""
    import uuid
    try:
        uuid.UUID(recording_id)
    except ValueError:
        raise HTTPException(404, "Recording not found")
    obj = db.get(Recording, recording_id)
    if obj is None:
        raise HTTPException(404, "Recording not found")
    if obj.status in ACTIVE_STATES:
        raise HTTPException(409, "Recording is running or being processed; stop it first")
    root = settings().storage_root.resolve()
    folder = (root / recording_id).resolve()
    if not folder.is_relative_to(root) or folder == root:
        raise HTTPException(400, "Invalid recording path")
    if folder.exists():
        shutil.rmtree(folder)
    details = {"title": obj.title[:200], "status": obj.status,
               "scheduled_at": aware(obj.scheduled_at).isoformat()}
    db.delete(obj)
    log_event(db, user, "recording.delete", "recording", recording_id, request, details)
    db.commit()
    return {"status": "deleted", "id": recording_id}


@app.get("/api/settings/mail")
def mail_settings(user=Depends(require_role("admin"))):
    from .notify import smtp_parts
    cfg = settings()
    try:
        server = smtp_parts(cfg.smtp_url)["host"] if cfg.smtp_url else ""
    except Exception:
        server = "ungültig"
    return {"configured": bool(cfg.smtp_url and cfg.alert_email), "alert_email": cfg.alert_email,
            "mail_from": cfg.mail_from, "smtp_server": server}


@app.post("/api/settings/mail/test")
def mail_test(request: Request, db: Session = Depends(db_session), user=Depends(require_role("admin"))):
    from .notify import MailNotConfigured, send_mail
    try:
        send_mail("Testnachricht", "Diese Testnachricht bestätigt, dass ZoomVCR Warnungen per E-Mail versenden kann.\n"
                  f"{settings().public_origin.rstrip('/')}/\n")
    except MailNotConfigured as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        return {"ok": False, "detail": f"Versand fehlgeschlagen: {type(exc).__name__}: {str(exc)[:200]}"}
    log_event(db, user, "settings.mail_test", "settings", "mail", request, {})
    db.commit()
    return {"ok": True, "detail": f"Testnachricht an {settings().alert_email} gesendet"}


@app.get("/api/desktop/health")
def desktop_health(user=Depends(require_role("recorder"))):
    if not settings().enable_desktop:
        return {"enabled": False, "status": "disabled"}
    from .desktop_client import DesktopClient
    try:
        return {"enabled": True, **DesktopClient().health()}
    except RuntimeError as e:
        return {"enabled": True, "status": "unavailable", "error": str(e)}


@app.get("/api/desktop/snapshot")
def desktop_snapshot(user=Depends(require_role("admin"))):
    if not settings().enable_desktop:
        raise HTTPException(503, "Desktop adapter is disabled")
    from .desktop_client import DesktopClient
    try:
        content = DesktopClient().frame()
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.post("/api/recordings/{recording_id}/admit")
def confirm_in_meeting(recording_id: str, db: Session = Depends(db_session), user=Depends(require_role("recorder"))):
    obj = db.get(Recording, recording_id)
    if not obj:
        raise HTTPException(404)
    if obj.source != "desktop_manual" or obj.status not in {"connecting", "waiting_room"}:
        raise HTTPException(409, "No Zoom connection awaiting admission")
    Redis.from_url(settings().redis_url).setex("zoomvcr:admitted:" + recording_id, 600, "1")
    log_event(db, user, "recording.admit", "recording", recording_id)
    db.commit()
    return {"status": "operator_confirmed_in_meeting", "note": "Operator confirms desktop meeting view; no proof of personal attendance"}
