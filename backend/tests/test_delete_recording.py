"""Permanent deletion of recordings: admin only, files removed, audited, running ones protected."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from test_user_management import client, login_as, post  # noqa: F401  (fixture reuse)
from zoomvcr.models import AuditEvent, Recording, Slide

ORIGIN = {"Origin": "http://localhost:8000"}


def _recording(http):
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    r = post(http, "/api/recordings", {"title": "Alte Fortbildung", "source": "synthetic", "scheduled_at": start.isoformat(),
                                       "duration_minutes": 5, "permission_confirmed": True, "disclosure_acknowledged": True,
                                       "authorization_basis": "host"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_admin_deletes_recording_with_files(client, tmp_path):
    http, Session = client
    assert login_as(http, "admin", "first_admin_password_2026").status_code == 200
    rid = _recording(http)
    folder = tmp_path / "recordings" / rid
    (folder / "slides").mkdir(parents=True, exist_ok=True)
    (folder / "recording.mp4").write_bytes(b"video")
    with Session.begin() as s:
        s.get(Recording, rid).status = "ready"
        s.add(Slide(recording_id=rid, time_seconds=1.0, image_name="slide_0001.jpg"))
    assert http.delete(f"/api/recordings/{rid}", headers={}).status_code == 403          # origin required
    r = http.delete(f"/api/recordings/{rid}", headers=ORIGIN)
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    assert not folder.exists()
    with Session() as s:
        assert s.get(Recording, rid) is None
        assert s.scalars(select(Slide).where(Slide.recording_id == rid)).first() is None
        event = s.scalars(select(AuditEvent).where(AuditEvent.action == "recording.delete")).one()
        assert event.target_id == rid and event.details["title"] == "Alte Fortbildung"
    assert http.delete(f"/api/recordings/{rid}", headers=ORIGIN).status_code == 404
    assert http.delete("/api/recordings/../../etc", headers=ORIGIN).status_code in (404, 405)


def test_running_recording_cannot_be_deleted_and_recorder_role_cannot_delete(client):
    http, Session = client
    assert login_as(http, "admin", "first_admin_password_2026").status_code == 200
    rid = _recording(http)
    with Session.begin() as s:
        s.get(Recording, rid).status = "recording"
    assert http.delete(f"/api/recordings/{rid}", headers=ORIGIN).status_code == 409
    assert post(http, "/api/users", {"username": "rekorder", "role": "recorder", "provider": "local",
                                     "password": "recorder_password_long_2026"}).status_code == 201
    post(http, "/api/logout")
    assert login_as(http, "rekorder", "recorder_password_long_2026").status_code == 200
    with Session.begin() as s:
        s.get(Recording, rid).status = "ready"
    assert http.delete(f"/api/recordings/{rid}", headers=ORIGIN).status_code == 403
