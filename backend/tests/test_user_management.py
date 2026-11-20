"""End-to-end RBAC/API tests without external Redis or Zoom; SQLite is real."""
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Local test environment may not have redis/rq Python packages. Stubs are used only
# in tests and never packaged into the application's production image.
try:
    import redis  # noqa: F401
except ImportError:
    module = types.ModuleType("redis")
    module.Redis = object
    sys.modules["redis"] = module
try:
    import rq  # noqa: F401
except ImportError:
    module = types.ModuleType("rq")
    module.Queue = object
    sys.modules["rq"] = module

from zoomvcr import db, config
from zoomvcr.models import User, LoginSession
from zoomvcr.security import (bootstrap_admin, generate_totp_secret, hash_password,
                               seal_secret, totp_code, unseal_secret, verify_password,
                               verify_totp)
from zoomvcr.user_schemas import UserCreate

class FakeRedis:
    store = {}
    @classmethod
    def from_url(cls, *args, **kwargs): return cls()
    def get(self, key): return self.store.get(key)
    def incr(self, key): self.store[key] = int(self.store.get(key, 0)) + 1
    def expire(self, key, ttl): return True
    def delete(self, key): self.store.pop(key, None)
    def ping(self): return True
    def setex(self, key, ttl, value): self.store[key] = value

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZOOMVCR_SECRET_KEY", "k" * 64)
    monkeypatch.setenv("ZOOMVCR_API_TOKEN", "cli-secret-token-test-123456789012345")
    monkeypatch.setenv("ZOOMVCR_ADMIN_PASSWORD", "first_admin_password_2026")
    monkeypatch.setenv("ZOOMVCR_PUBLIC_ORIGIN", "http://localhost:8000")
    monkeypatch.setenv("ZOOMVCR_STORAGE_ROOT", str(tmp_path / 'recordings'))
    monkeypatch.setenv("ZOOMVCR_DATABASE_URL", "sqlite:///" + str(tmp_path / "security.sqlite3"))
    config.settings.cache_clear()
    from zoomvcr import users_api, main
    from zoomvcr import security
    old_engine, old_session = db.engine, db.SessionLocal
    old_main_session = main.SessionLocal
    new_engine = create_engine("sqlite:///" + str(tmp_path / 'security.sqlite3'), connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=new_engine, expire_on_commit=False)
    db.engine, db.SessionLocal, main.SessionLocal = new_engine, Session, Session
    def local_db():
        with Session() as session:
            yield session
    main.app.dependency_overrides[db.db_session] = local_db
    monkeypatch.setattr(users_api, 'Redis', FakeRedis)
    monkeypatch.setattr(main, 'Redis', FakeRedis)
    FakeRedis.store = {}
    try:
        with TestClient(main.app, base_url="http://localhost:8000") as http:
            yield http, Session
    finally:
        main.app.dependency_overrides.clear()
        db.engine, db.SessionLocal, main.SessionLocal = old_engine, old_session, old_main_session
        new_engine.dispose()
        config.settings.cache_clear()


def post(http, url, json=None):
    return http.post(url, json=json, headers={"Origin": "http://localhost:8000"})

def patch(http, url, json=None):
    return http.patch(url, json=json, headers={"Origin": "http://localhost:8000"})


def login_as(http, name, password, code=""):
    return post(http, '/api/login', {"username": name, "password": password, "totp": code})


def test_first_start_creates_hashed_admin_once(client):
    http, Session = client
    with Session() as session:
        users = session.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].username == 'admin' and users[0].role == 'admin'
        assert users[0].password_hash != "first_admin_password_2026"
        assert verify_password('first_admin_password_2026', users[0].password_hash)
        bootstrap_admin(session)
        assert len(session.scalars(select(User)).all()) == 1
    assert login_as(http, 'admin', 'first_admin_password_2026').status_code == 200
    assert http.get('/api/me').json()['user']['role'] == 'admin'


def test_role_permissions_revocation_password_reset_and_audit(client):
    http, Session = client
    assert login_as(http, 'admin', 'first_admin_password_2026').status_code == 200
    u = post(http, '/api/users', {"username": "reader", "email": "reader@example.org", "role":"viewer", "provider":"local", "password":"viewer_password_long_2026"})
    assert u.status_code == 201, u.text
    user_id = u.json()['id']
    r = post(http, '/api/users', {"username": "recorder", "role":"recorder", "provider":"local", "password":"recorder_password_long_2026"})
    assert r.status_code == 201, r.text
    r_id = r.json()['id']
    oidc = post(http, '/api/users', {"username": "sso_only", "provider": "oidc", "email":"sso@example.org", "role":"viewer"})
    assert oidc.status_code == 201 and oidc.json()['provider'] == 'oidc'
    # Authentication secrets are never returned.
    assert 'password_hash' not in str(http.get('/api/users').json())
    assert 'mfa_secret' not in str(http.get('/api/users').json())
    assert http.get('/api/audit').status_code == 200
    assert len(http.get('/api/audit').json()) >= 3
    assert patch(http, '/api/users/' + user_id, {"role":"viewer"}).status_code == 200
    # Browser origin required for mutating authenticated requests.
    assert http.post('/api/users', json={"username":"bad"}).status_code == 403
    reader = TestClient(http.app, base_url='http://localhost:8000')
    assert login_as(reader, 'reader', 'viewer_password_long_2026').status_code == 200
    assert reader.get('/api/recordings').status_code == 200
    assert reader.get('/api/users').status_code == 403
    assert reader.get('/api/audit').status_code == 403
    scheduled = {"title":"Synthetic", "source":"synthetic", "scheduled_at":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),"duration_minutes":30}
    assert post(reader,'/api/recordings',scheduled).status_code == 403
    assert reader.get('/api/desktop/snapshot').status_code == 403
    # The recorder may create a schedule but cannot perform administration.
    worker=TestClient(http.app,base_url='http://localhost:8000')
    assert login_as(worker, 'recorder', 'recorder_password_long_2026').status_code == 200
    assert post(worker,'/api/recordings',scheduled).status_code == 201
    assert worker.get('/api/users').status_code == 403
    assert worker.get('/api/desktop/snapshot').status_code == 403
    # Reset password revokes all sessions and clears MFA.
    result = post(http, f'/api/users/{user_id}/reset-password', {"new_password": "renewed_password_long_2026"})
    assert result.status_code == 200
    assert reader.get('/api/me').status_code == 401
    assert login_as(reader, 'reader', 'viewer_password_long_2026').status_code == 401
    assert login_as(reader, 'reader', 'renewed_password_long_2026').status_code == 200
    assert patch(http, f'/api/users/{user_id}', {"active":False}).status_code == 200
    assert reader.get('/api/recordings').status_code == 401
    assert login_as(reader, 'reader', 'renewed_password_long_2026').status_code == 401
    assert patch(http, f'/api/users/{user_id}', {"active":True}).status_code == 200
    assert patch(http, f'/api/users/{r_id}', {"role": "viewer"}).status_code == 200
    assert worker.get('/api/recordings').status_code == 401
    # Last administrator must not be disabled.
    admin_id=http.get('/api/me').json()['user']['id']
    assert patch(http, f'/api/users/{admin_id}', {"active":False}).status_code == 409
    assert patch(http, f'/api/users/{admin_id}', {"role":"viewer"}).status_code == 409


def test_session_logout_and_password_change(client):
    http, Session=client
    assert login_as(http,'admin','first_admin_password_2026').status_code==200
    original = http.cookies.get('zoomvcr_session')
    assert post(http,'/api/me/change-password',{"current_password":"bad","new_password":"another_password_2026"}).status_code==401
    change=post(http,'/api/me/change-password',{"current_password":"first_admin_password_2026","new_password":"another_password_2026"})
    assert change.status_code==200
    assert http.get('/api/me').status_code==401
    assert login_as(http,'admin','first_admin_password_2026').status_code==401
    assert login_as(http,'admin','another_password_2026').status_code==200
    assert post(http,'/api/logout').status_code==200
    assert http.get('/api/me').status_code==401
    # The previous cookie cannot be replayed after a password change.
    with TestClient(http.app,base_url='http://localhost:8000') as other:
        other.cookies.set('zoomvcr_session',original)
        assert other.get('/api/me').status_code==401


def test_totp_and_secret_encryption(client):
    http, Session = client
    assert login_as(http,'admin','first_admin_password_2026').status_code==200
    setup = post(http,'/api/me/mfa/setup')
    assert setup.status_code==200,setup.text
    secret=setup.json()['secret']
    assert setup.json()['otpauth_uri'].startswith('otpauth://')
    with Session() as dbsession:
        admin=dbsession.scalar(select(User).where(User.username=='admin'))
        assert admin.mfa_pending != secret
        assert unseal_secret(admin.mfa_pending)==secret
    import time
    code=totp_code(secret,int(time.time()//30))
    assert post(http,'/api/me/mfa/verify',{"code":"000"}).status_code==422
    assert post(http,'/api/me/mfa/verify',{"code":code}).status_code==200
    assert http.get('/api/me').status_code==401
    assert login_as(http,'admin','first_admin_password_2026').status_code==401
    # The activation code cannot be replayed in the same time step.
    assert login_as(http,'admin','first_admin_password_2026',code).status_code==401
    # Simulate next TOTP period without slowing the test.
    from zoomvcr import security
    from zoomvcr import users_api
    original = users_api.verify_totp
    def future(secret, code, last_step=-1):
        return original(secret,code,last_step,at=int((time.time()//30+1)*30))
    from unittest.mock import patch as mockpatch
    next_code=totp_code(secret,int(time.time()//30+1))
    with mockpatch.object(users_api,'verify_totp',future):
        assert login_as(http,'admin','first_admin_password_2026',next_code).status_code==200


def test_oidc_requires_verified_preapproved_account(client, monkeypatch):
    http,Session = client
    assert http.get('/api/auth/oidc/start').status_code == 503
    assert login_as(http,'admin','first_admin_password_2026').status_code==200
    oidc = post(http,'/api/users',{"username":"external","email":"external@example.org","provider":"oidc","role":"viewer"})
    assert oidc.status_code==201
    from zoomvcr import oidc as oidc_module
    class FakeOIDCProvider:
        def __init__(self, verified=True, email="external@example.org"):
            self.verified=verified;self.email=email
        async def authorize_access_token(self,request):
            return {"userinfo":{"sub":"idp-user-333","email":self.email,"email_verified":self.verified}}
    monkeypatch.setattr(oidc_module,'_provider',lambda:FakeOIDCProvider(verified=False))
    assert http.get('/api/auth/oidc/callback',follow_redirects=False).status_code == 401
    monkeypatch.setattr(oidc_module,'_provider',lambda:FakeOIDCProvider(email="other@example.org"))
    assert http.get('/api/auth/oidc/callback',follow_redirects=False).status_code == 403
    monkeypatch.setattr(oidc_module,'_provider',lambda:FakeOIDCProvider())
    response = http.get('/api/auth/oidc/callback',follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location']=='/'
    assert http.get('/api/me').json()['user']['username']=='external'
    with Session() as dbsession:
        user=dbsession.get(User,oidc.json()['id'])
        assert user.oidc_subject=='idp-user-333'
