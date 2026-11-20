"""Zoom recordings start early (join lead time), synthetic ones exactly on time."""
from datetime import datetime, timedelta, timezone

from test_user_management import client  # noqa: F401  (fixture reuse)
from zoomvcr import scheduler
from zoomvcr.models import Recording


def _add(Session, source, start):
    with Session.begin() as s:
        obj = Recording(title=source, source=source, scheduled_at=start, ends_at=start + timedelta(minutes=30),
                        status="planned", permission_confirmed=True, disclosure_acknowledged=True,
                        meeting_url="https://zoom.us/j/12345678901" if source == "desktop_manual" else None)
        s.add(obj)
        s.flush()
        return obj.id


def test_zoom_joins_five_minutes_early(client, monkeypatch):
    _, Session = client
    now = datetime.now(timezone.utc)
    zoom_soon = _add(Session, "desktop_manual", now + timedelta(minutes=4))
    zoom_later = _add(Session, "desktop_manual", now + timedelta(minutes=6))
    synth_soon = _add(Session, "synthetic", now + timedelta(minutes=4))
    enqueued = []
    monkeypatch.setattr(scheduler, "SessionLocal", Session)
    monkeypatch.setattr(scheduler, "enqueue_capture", lambda rid, conn=None: enqueued.append(rid) or True)
    monkeypatch.setattr(scheduler.Redis, "from_url", classmethod(lambda cls, *a, **k: None))
    scheduler.schedule_due(now)
    assert enqueued == [zoom_soon]
    with Session() as s:
        assert s.get(Recording, zoom_soon).status == "connecting"
        assert s.get(Recording, zoom_later).status == "planned"
        assert s.get(Recording, synth_soon).status == "planned"



def test_zoom_recording_gets_end_buffer(client, monkeypatch):
    http, Session = client
    from zoomvcr import config
    from test_user_management import login_as, post
    monkeypatch.setenv("ZOOMVCR_ENABLE_DESKTOP", "true")
    config.settings.cache_clear()
    assert login_as(http, "admin", "first_admin_password_2026").status_code == 200
    start = datetime.now(timezone.utc) + timedelta(hours=2)
    body = {"title": "Fortbildung", "source": "desktop_manual", "meeting_url": "https://us06web.zoom.us/j/12345678901?pwd=abc",
            "participant_name": "Muster GmbH", "scheduled_at": start.isoformat(), "duration_minutes": 180,
            "permission_confirmed": True, "disclosure_acknowledged": True, "authorization_basis": "host"}
    r = post(http, "/api/recordings", body)
    assert r.status_code == 201, r.text
    ends = datetime.fromisoformat(r.json()["ends_at"])
    assert round((ends - start).total_seconds() / 60) == 195
    assert r.json()["metadata"]["end_buffer_minutes"] == 15
    body.update(source="synthetic", meeting_url=None, participant_name=None)
    r = post(http, "/api/recordings", body)
    assert round((datetime.fromisoformat(r.json()["ends_at"]) - start).total_seconds() / 60) == 180
