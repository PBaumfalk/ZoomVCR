"""Tests: input, persisted value, URI forwarding, self-row OCR and guarded capture."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
import sqlite3
from pathlib import Path
import pytest
import sys
import types
# The local unit-test sandbox lacks Redis and RQ. In that case stub only the
# transport imports; deployment installs the real libraries from requirements.txt.
try:
    import redis  # noqa: F401
except ModuleNotFoundError:
    fake_redis = types.ModuleType('redis')
    class Redis:
        @staticmethod
        def from_url(*_args, **_kwargs):
            raise RuntimeError('Redis server unavailable in local unit tests')
    fake_redis.Redis = Redis
    sys.modules['redis'] = fake_redis
try:
    import rq  # noqa: F401
except ModuleNotFoundError:
    fake_rq = types.ModuleType('rq')
    class Queue:
        pass
    fake_rq.Queue = Queue
    sys.modules['rq'] = fake_rq
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from zoomvcr.display_name import check_display_name, name_visible_on_self_row
from zoomvcr.desktop_agent import validate_zoom_meeting_url, JoinRequest
from zoomvcr.models import Recording
from zoomvcr.schemas import CreateRecording, UpdateParticipantName


def payload(**changes):
    original = dict(title="Seminar", source="desktop_manual", participant_name="Kanzlei Muster – Aufzeichnungsdienst",
        meeting_url="https://us06web.zoom.us/j/12345678901?pwd=abc%2Bdef",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=4), duration_minutes=180,
        authorization_basis="host", permission_confirmed=True, disclosure_acknowledged=True)
    original.update(changes)
    return original


@pytest.mark.parametrize('value', [' ', '\nEvil', 'Hey\u202eparticipant', 'A'*81, 'Name\tNext'])
def test_display_name_rejects_unsafe_inputs(value):
    with pytest.raises(ValueError):
        check_display_name(value)
    with pytest.raises(ValueError):
        CreateRecording(**payload(participant_name=value))


def test_zoom_requires_nonempty_name():
    with pytest.raises(ValueError):
        CreateRecording(**payload(participant_name=None))
    assert CreateRecording(**payload(participant_name='  Rechtsanwalt Muster  ')).participant_name == 'Rechtsanwalt Muster'
    assert UpdateParticipantName(participant_name='   Test Recorder   ').participant_name == 'Test Recorder'


def test_zoom_link_passes_name_but_does_not_certify_it():
    name = 'Kanzlei Muster – Aufzeichnungsdienst'
    uri = validate_zoom_meeting_url(payload()['meeting_url'], name)
    assert parse_qs(urlparse(uri).query)['uname'] == [name]
    assert parse_qs(urlparse(uri).query)['pwd'] == ['abc+def']
    assert JoinRequest(meeting_url=payload()['meeting_url'], participant_name=name).participant_name == name


def test_self_name_verification_is_conservative():
    assert name_visible_on_self_row('Participants\nKanzlei Muster – Aufzeichnungsdienst (Me)\nOther participant', 'Kanzlei Muster – Aufzeichnungsdienst')
    assert name_visible_on_self_row('Teilnehmer\nKanzlei Muster - Aufzeichnungsdienst (Ich)', 'Kanzlei Muster – Aufzeichnungsdienst')
    assert not name_visible_on_self_row('Kanzlei Muster – Aufzeichnungsdienst\nAnderer (Ich)', 'Kanzlei Muster – Aufzeichnungsdienst')
    assert not name_visible_on_self_row('Kanzlei Muster – Aufzeichnungsdienst (host)\nOther (Me)', 'Kanzlei Muster – Aufzeichnungsdienst')
    assert not name_visible_on_self_row('Kanzlei Muster – Aufzeichnungsdienst (Me)', 'Fremder Teilnehmer')
    assert not name_visible_on_self_row('Annabelle (Me)', 'Anna')
    assert name_visible_on_self_row('Anna (Host) (Me)', 'Anna')


def test_new_recording_persists_and_edits_name(tmp_path, monkeypatch):
    from zoomvcr import main
    from zoomvcr.db import Base
    db_engine = create_engine('sqlite:///' + str(tmp_path/'db.sqlite'))
    Base.metadata.create_all(db_engine)
    make_session = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(main, 'settings', lambda: SimpleNamespace(enable_desktop=True))
    def local_folder(rec_id):
        folder = tmp_path/'recordings'/rec_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    monkeypatch.setattr(main, 'recording_dir', local_folder)
    with make_session() as db:
        result = main.create_recording(CreateRecording(**payload()), db=db, user='test')
        assert result['participant_name'] == 'Kanzlei Muster – Aufzeichnungsdienst'
        assert result['metadata']['participant_name_status'] == 'not_checked'
        rid = result['id']
    with make_session() as db:
        saved = db.get(Recording, rid)
        assert saved.participant_name == 'Kanzlei Muster – Aufzeichnungsdienst'
        changed = main.change_participant_name(rid, UpdateParticipantName(participant_name=' Eigener Testname '), db=db, user='test')
        assert changed['participant_name'] == 'Eigener Testname'
    with make_session() as db:
        assert db.get(Recording,rid).participant_name == 'Eigener Testname'
        db.get(Recording,rid).status = 'connecting'
        db.commit()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            main.change_participant_name(rid, UpdateParticipantName(participant_name='Zu spät'), db=db, user='test')
        assert exc.value.status_code == 409
    db_engine.dispose()


def test_upgrade_existing_sqlite_database(tmp_path, monkeypatch):
    from zoomvcr import db
    engine = create_engine('sqlite:///' + str(tmp_path/'legacy.sqlite'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE recordings (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200))'))
    monkeypatch.setattr(db, 'engine', engine)
    db.init_db()
    db.init_db()  # idempotent
    with engine.connect() as conn:
        from sqlalchemy import inspect
        assert 'participant_name' in [c['name'] for c in inspect(conn).get_columns('recordings')]
    engine.dispose()


def test_desktop_client_forwards_name(monkeypatch):
    from zoomvcr.desktop_client import DesktopClient
    client = DesktopClient()
    requests = []
    def fake_request(method, path, data=None, timeout=15):
        requests.append((method, path, data))
        return {'status':'launch_requested'}
    monkeypatch.setattr(client, '_request', fake_request)
    client.join('https://zoom.us/j/12345678901', 'Gesonderter Aufnahme-Dienst')
    assert requests == [('POST','/join',{'meeting_url':'https://zoom.us/j/12345678901','participant_name':'Gesonderter Aufnahme-Dienst'})]


def test_operator_name_confirmation_requires_active_zoom_recording(tmp_path, monkeypatch):
    from zoomvcr import main
    from zoomvcr.db import Base
    engine = create_engine('sqlite:///' + str(tmp_path/'x.sqlite'))
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    fake = SimpleNamespace(enable_desktop=True, redis_url='redis://fake:6379/0')
    monkeypatch.setattr(main, 'settings', lambda: fake)
    def local_folder(rid):
        folder = tmp_path/'rec'/rid
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    monkeypatch.setattr(main, 'recording_dir', local_folder)
    with Session() as db:
        rid = main.create_recording(CreateRecording(**payload()), db=db, user='t')['id']
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            main.confirm_participant_name(rid, db=db, user='t')
        assert exc.value.status_code == 409
        obj = db.get(Recording,rid)
        obj.status='connecting'
        db.commit()
        class FakeRedis:
            def setex(self, key, duration, data):
                assert key == 'zoomvcr:name-confirm:' + rid
                assert duration == 600
        from redis import Redis
        monkeypatch.setattr(Redis, 'from_url', lambda *_: FakeRedis())
        result=main.confirm_participant_name(rid, db=db,user='t')
        assert result['status'] == 'operator_confirmed'
    engine.dispose()


def test_capture_does_not_start_when_name_unverified(monkeypatch):
    """A Zoom join request + possible admission is insufficient to start FFmpeg."""
    from zoomvcr import tasks, desktop_client
    import time
    class FakeAgent:
        def __init__(self):
            self.capture_started = False
        def health(self):
            return {'display_socket': True, 'ffmpeg_installed': True, 'zoom_installed': True}
        def join(self, url, name):
            assert name == 'Eigener Zoom-Name'
            return {'participant_name_status':'unverified'}
        def status(self):
            return {'zoom_running':True}
        def frame(self):
            return b''
        def ensure_name(self):
            return {'status':'manual_required','note':'No verifiable self row'}
        def start(self, *args):
            self.capture_started = True
            raise AssertionError('Recording must not be started under an unverified name')
    fake = FakeAgent()
    monkeypatch.setattr(desktop_client,'DesktopClient',lambda:fake)
    monkeypatch.setattr(desktop_client,'classify_desktop_image',lambda _data: 'in_meeting_possible')
    monkeypatch.setattr(tasks,'update',lambda *a,**kw: None)
    monkeypatch.setattr(tasks,'_set_participant_name_status',lambda *a,**kw: None)
    monkeypatch.setattr(tasks,'settings',lambda: SimpleNamespace(join_grace_seconds=0,join_timeout_seconds=3,assume_joined_after_seconds=0))
    seq = iter([i*0.5 for i in range(100)])
    monkeypatch.setattr(time,'monotonic',lambda:next(seq))
    monkeypatch.setattr(time,'sleep',lambda *a: None)
    class EmptyRedis:
        def get(self,*_args):
            return None
    with pytest.raises(RuntimeError,match='Zoom participant name not verified'):
        tasks.capture_zoom_desktop('uuid', 'https://zoom.us/j/12345678901', 'Eigener Zoom-Name',
                                    datetime.now(timezone.utc)+timedelta(hours=1), EmptyRedis())
    assert not fake.capture_started



def _fake_join(monkeypatch, states, require_name, assume_after=0, timeout=3):
    from zoomvcr import tasks, desktop_client
    import time
    class FakeAgent:
        started = False
        def health(self): return {'display_socket': True, 'ffmpeg_installed': True, 'zoom_installed': True}
        def join(self, url, name): return {}
        def status(self): return {'zoom_running': True, 'recording': False}
        def frame(self): return b''
        def ensure_name(self): return {'status': 'manual_required', 'note': 'No verifiable self row'}
        def start(self, *args):
            FakeAgent.started = True
            raise RuntimeError('started')
        def stop(self, *a): return {}
    fake = FakeAgent()
    names = []
    seq_states = iter(states)
    monkeypatch.setattr(desktop_client, 'DesktopClient', lambda: fake)
    monkeypatch.setattr(desktop_client, 'classify_desktop_image', lambda _d: next(seq_states, states[-1]))
    monkeypatch.setattr(tasks, 'update', lambda *a, **kw: None)
    monkeypatch.setattr(tasks, '_set_participant_name_status', lambda rid, status, note='': names.append(status))
    monkeypatch.setattr(tasks, 'settings', lambda: SimpleNamespace(join_grace_seconds=0, join_timeout_seconds=timeout,
                        assume_joined_after_seconds=assume_after, require_name_confirmation=require_name))
    seq = iter([i * 0.5 for i in range(10000)])
    monkeypatch.setattr(time, 'monotonic', lambda: next(seq))
    monkeypatch.setattr(time, 'sleep', lambda *a: None)
    class EmptyRedis:
        def get(self, *_a): return None
        def delete(self, *_a): return None
    return tasks, fake, names, EmptyRedis()


def test_unverified_name_accepted_when_confirmation_disabled(monkeypatch):
    tasks, fake, names, redis = _fake_join(monkeypatch, ['unknown'], require_name=False, assume_after=2)
    with pytest.raises(RuntimeError, match='started'):
        tasks.capture_zoom_desktop('uuid', 'https://zoom.us/j/12345678901', 'Eigener Zoom-Name',
                                   datetime.now(timezone.utc) + timedelta(hours=1), redis)
    assert fake.started and names[-1] == 'unverified_accepted'


def test_waiting_room_does_not_time_out(monkeypatch):
    # 40 polls in the waiting room (far beyond the 3 s timeout), then admitted.
    states = ['waiting_room'] * 40 + ['in_meeting_possible']
    tasks, fake, names, redis = _fake_join(monkeypatch, states, require_name=False)
    with pytest.raises(RuntimeError, match='started'):
        tasks.capture_zoom_desktop('uuid', 'https://zoom.us/j/12345678901', 'Eigener Zoom-Name',
                                   datetime.now(timezone.utc) + timedelta(hours=1), redis)
    assert fake.started
