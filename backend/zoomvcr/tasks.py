"""RQ workers. Backend source implementations are explicit, not guessed."""
from datetime import datetime, timezone
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Recording, Slide
from .media import recording_dir, record_synthetic, merge_segments, verify_media, slide_candidates, run_ocr, video_health, auto_cut
from .notify import alert
from .analysis import transcript_from_video, correlate_slides, build_reports, save_json


def utcnow():
    return datetime.now(timezone.utc)

def aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def update(recording_id: str, **changes):
    with SessionLocal.begin() as db:
        obj = db.get(Recording, recording_id)
        if not obj:
            raise LookupError(f"Missing recording {recording_id}")
        for k, v in changes.items():
            setattr(obj, k, v)

def enqueue_processing(recording_id: str):
    from redis import Redis
    from rq import Queue
    redis = Redis.from_url(settings().redis_url)
    Queue("processing", connection=redis).enqueue("zoomvcr.tasks.process_job", recording_id, job_timeout=14400, result_ttl=86400)

def _set_participant_name_status(recording_id: str, status: str, note: str = ""):
    """Store real verification status separately from the requested display name."""
    with SessionLocal.begin() as db:
        obj = db.get(Recording, recording_id)
        if not obj:
            raise LookupError(recording_id)
        obj.metadata_json = {**(obj.metadata_json or {}),
                             "participant_name_status": status,
                             "participant_name_note": note[:300],
                             "participant_name_checked_at": utcnow().isoformat()}
        obj.heartbeat_at = utcnow()


def capture_zoom_desktop(recording_id: str, meeting_url: str, participant_name: str, end_time, redis):
    """Capture a consented Zoom session ONLY after admission and name check.

    Supplying uname to Zoom is not a verification. The actual name has to be
    positively visible on the participant's own Zoom row or separately verified
    over private VNC by the operator. This avoids silently joining as another
    name, which could mislead the organizer.
    """
    import shutil
    import time
    from .desktop_client import DesktopClient, classify_desktop_image
    from .display_name import check_display_name
    participant_name = check_display_name(participant_name)
    agent = DesktopClient()
    info = agent.health()
    if not (info.get("display_socket") and info.get("ffmpeg_installed") and info.get("zoom_installed")):
        raise RuntimeError("Zoom desktop preflight failed: install Zoom and start virtual display")
    _set_participant_name_status(recording_id, "unverified", "Join request carries the requested name; awaiting Zoom confirmation")
    agent.join(meeting_url, participant_name)
    grace_end = time.monotonic() + max(1, settings().join_grace_seconds)
    deadline = time.monotonic() + max(settings().join_grace_seconds + 1, settings().join_timeout_seconds)
    first = time.monotonic()
    admission_confirmed = False
    name_confirmed = False
    last_name_note = ""
    while time.monotonic() < deadline and utcnow() < end_time:
        if redis.get("zoomvcr:stop:" + recording_id):
            raise RuntimeError("Cancelled before Zoom was ready")
        if not agent.status().get("zoom_running"):
            raise RuntimeError("Zoom client exited before the meeting could be recorded")
        if time.monotonic() >= grace_end:
            state = classify_desktop_image(agent.frame())
            if state == "waiting_room" and not admission_confirmed:
                update(recording_id, status="waiting_room", heartbeat_at=utcnow())
                # Waiting for the host is legitimate: keep waiting (until the planned end) instead of timing out.
                deadline = max(deadline, time.monotonic() + max(30, settings().join_timeout_seconds))
            elif (state == "in_meeting_possible" or
                  redis.get("zoomvcr:admitted:" + recording_id) or
                  (settings().assume_joined_after_seconds > 0 and
                   time.monotonic() - first >= settings().assume_joined_after_seconds)):
                admission_confirmed = True
            if admission_confirmed:
                if redis.get("zoomvcr:name-confirm:" + recording_id):
                    name_confirmed = True
                    _set_participant_name_status(recording_id, "operator_confirmed", "Checked by operator in private Zoom desktop")
                elif not name_confirmed:
                    result = agent.ensure_name()
                    if result.get("status") == "verified":
                        name_confirmed = True
                        _set_participant_name_status(recording_id, "verified", result.get("method", "participant_panel_ocr"))
                    elif not getattr(settings(), "require_name_confirmation", True):
                        name_confirmed = True
                        _set_participant_name_status(recording_id, "unverified_accepted",
                                                     "Name not verifiable by OCR; recording started without confirmation (server setting)")
                    else:
                        last_name_note = result.get("note", "Zoom display name could not be verified")
                        _set_participant_name_status(recording_id, "manual_required", last_name_note)
                if name_confirmed:
                    break
                update(recording_id, status="connecting", heartbeat_at=utcnow())
        update(recording_id, heartbeat_at=utcnow())
        time.sleep(4)
    if not admission_confirmed:
        raise RuntimeError("Meeting admission not confirmed; inspect the desktop and use zoomvcr admit <id>")
    if not name_confirmed:
        raise RuntimeError("Zoom participant name not verified: " + last_name_note[:240] + "; use VNC and zoomvcr confirm-name <id>")
    started = False
    try:
        agent.start(recording_id, end_time)
        started = True
        update(recording_id, status="recording", heartbeat_at=utcnow())
        while utcnow() < end_time:
            if redis.get("zoomvcr:stop:" + recording_id):
                break
            state = agent.status()
            if not state.get("recording"):
                raise RuntimeError("FFmpeg capture stopped unexpectedly; remaining segments preserved")
            if not state.get("zoom_running"):
                raise RuntimeError("Zoom process terminated; remaining segments preserved")
            missing = int(state.get("audio_missing_seconds") or 0)
            if missing >= max(30, settings().audio_alert_seconds):
                alert(recording_id, "audio_missing",
                      f"Zoom ist seit {missing // 60} min {missing % 60} s nicht mit dem Computer-Ton verbunden "
                      f"(Tonwächter: {state.get('audio_join')}). Die Aufnahme läuft weiter, aber ohne Ton.")
            if shutil.disk_usage(recording_dir(recording_id)).free < 200 * 1024 * 1024:
                raise RuntimeError("Disk space critically low; recording stopped")
            agent.heartbeat()
            update(recording_id, heartbeat_at=utcnow())
            time.sleep(min(3, max(0.1, (end_time - utcnow()).total_seconds())))
    finally:
        if started:
            agent.stop()
            try:
                agent.leave()
            except RuntimeError:
                pass


def capture_job(recording_id: str):
    from redis import Redis
    redis = Redis.from_url(settings().redis_url)
    with SessionLocal() as db:
        job = db.get(Recording, recording_id)
        if not job:
            raise LookupError(recording_id)
        if job.status not in {"connecting", "interrupted"}:
            return
        source = job.source
        duration = max(1.0, (aware(job.ends_at) - utcnow()).total_seconds())
        approved = job.permission_confirmed and job.disclosure_acknowledged
    try:
        if source == "synthetic":
            update(recording_id, status="recording", heartbeat_at=utcnow())
            def tick():
                update(recording_id, heartbeat_at=utcnow())
            record_synthetic(recording_id, duration, stop_requested=lambda: bool(redis.get("zoomvcr:stop:" + recording_id)), on_tick=tick)
        elif source == "desktop_manual":
            if not settings().enable_desktop or not approved:
                raise PermissionError("Desktop capture requires explicit authorization, participant notice and enabled adapter")
            with SessionLocal() as db:
                meeting_url = db.get(Recording, recording_id).meeting_url
                ends_at = aware(db.get(Recording, recording_id).ends_at)
                participant_name = db.get(Recording, recording_id).participant_name
            capture_zoom_desktop(recording_id, meeting_url, participant_name, ends_at, redis)
        else:
            raise ValueError("Unsupported recording source")
        update(recording_id, status="recorded", heartbeat_at=utcnow())
        enqueue_processing(recording_id)
    except Exception as e:
        update(recording_id, status="error", error=str(e)[:1000], heartbeat_at=utcnow())
        alert(recording_id, "capture_failed", "Fehler: " + str(e)[:500])
        raise
    finally:
        redis.delete("zoomvcr:stop:" + recording_id)

def process_job(recording_id: str):
    with SessionLocal() as db:
        job = db.get(Recording, recording_id)
        if not job:
            raise LookupError(recording_id)
        if job.status not in {"recorded", "processing", "ready", "error"}:
            raise RuntimeError("Invalid processing state")
    update(recording_id, status="processing", error=None, heartbeat_at=utcnow())
    directory = recording_dir(recording_id)
    try:
        final = directory / "recording.mp4"
        if not final.is_file() and not (directory / "original.mp4").is_file():
            details = merge_segments(directory)
        try:
            cut = auto_cut(directory)
        except Exception as exc:  # an uncut recording is better than none
            if not final.is_file() and (directory / "original.mp4").is_file():
                (directory / "original.mp4").replace(final)
            cut = {"status": "failed", "error": str(exc)[:300]}
        details = verify_media(final)
        cut_note = None
        if cut.get("status") == "cut":
            cut_note = (f"Automatisch geschnitten: {cut['cuts']} Stellen, "
                        f"{round(cut['removed_seconds'] / 60)} min Stille entfernt (Original: original.mp4)")
        elif cut.get("status") == "mostly_silent":
            cut_note = "Aufnahme fast ohne Ton – nicht geschnitten"
            alert(recording_id, "mostly_silent",
                  f"Nur etwa {round(cut['audible_seconds'] / 60)} von {round(cut['original_seconds'] / 60)} Minuten "
                  "enthalten hörbaren Ton.")
        elif cut.get("status") == "failed":
            cut_note = "Automatischer Schnitt fehlgeschlagen – ungeschnittene Fassung"
        health = video_health(final)
        slides = slide_candidates(final, directory / "slides", sample_seconds=1.5)
        slides = run_ocr(slides, directory / "slides")
        lines, warning = transcript_from_video(final, directory)
        slides = correlate_slides(slides, lines)
        notices = build_reports(directory, lines, slides)
        if warning:
            notices.insert(0, warning)
        if cut_note:
            notices.insert(0, cut_note)
        if health.get("warning"):
            notices.append(health["warning"])
        save_json(directory / "inspection.json", {"media": details, "video_health": health, "notices": notices})
        with SessionLocal.begin() as db:
            obj = db.get(Recording, recording_id)
            for existing in list(obj.images):
                db.delete(existing)
            db.flush()
            for slide in slides:
                db.add(Slide(recording_id=recording_id, time_seconds=slide["time_seconds"], image_name=slide["image_name"], ocr_text=slide.get("ocr_text", ""), transcript_excerpt=slide.get("transcript_excerpt", "")))
            obj.status = "ready"
            obj.duration_seconds = int(round(details["duration_seconds"]))
            obj.processing_notes = " | ".join(notices)[:2000]
            obj.metadata_json = {**(obj.metadata_json or {}), "media": details, "video_health": health, "cut": cut}
            obj.heartbeat_at = utcnow()
    except Exception as e:
        update(recording_id, status="error", error=str(e)[:1000])
        alert(recording_id, "processing_failed", "Fehler: " + str(e)[:500])
        raise
