"""AI settings (UI-managed API key) and OpenAI-compatible transcription/summary."""
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from test_user_management import client, login_as, post  # noqa: F401  (fixture reuse)
from zoomvcr import ai_settings, analysis, openai_api
from zoomvcr.models import AppSetting, AuditEvent

ORIGIN = {"Origin": "http://localhost:8000"}
KEY = "sk-test-0123456789abcdefWXYZ"


def put(http, payload, headers=ORIGIN):
    return http.put("/api/settings/ai", json=payload, headers=headers)


def admin(http):
    assert login_as(http, "admin", "first_admin_password_2026").status_code == 200


def test_defaults_and_admin_only(client):
    http, _ = client
    assert http.get("/api/settings/ai").status_code == 401
    admin(http)
    data = http.get("/api/settings/ai").json()
    assert data["api_key_set"] is False and data["base_url"] == "https://api.openai.com/v1"
    assert data["transcription_provider"] == "openai" and data["transcription_model"] == "gpt-4o-transcribe"
    r = post(http, "/api/users", {"username": "reader", "role": "viewer", "provider": "local",
                                  "password": "viewer_password_long_2026"})
    assert r.status_code == 201
    post(http, "/api/logout")
    assert login_as(http, "reader", "viewer_password_long_2026").status_code == 200
    assert http.get("/api/settings/ai").status_code == 403
    assert put(http, {"api_key": KEY}).status_code == 403


def test_key_is_sealed_never_returned_and_not_audited(client):
    http, Session = client
    admin(http)
    r = put(http, {"api_key": KEY, "summary_model": "gpt-5-mini"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key_set"] is True and body["api_key_hint"] == "…WXYZ" and body["api_key_source"] == "ui"
    assert KEY not in r.text and KEY not in http.get("/api/settings/ai").text
    with Session() as s:
        stored = s.get(AppSetting, "ai.api_key").value
        assert stored and KEY not in stored
        assert ai_settings.resolve(s).api_key == KEY
        audit = " ".join(json.dumps(e.details) for e in s.scalars(select(AuditEvent)))
        assert KEY not in audit and "api_key" in audit


def test_origin_required_for_changes(client):
    http, _ = client
    admin(http)
    assert put(http, {"api_key": KEY}, headers={}).status_code == 403


def test_endpoint_change_clears_key_and_rejects_plain_http(client):
    http, _ = client
    admin(http)
    put(http, {"api_key": KEY})
    assert put(http, {"base_url": "http://evil.example/v1"}).status_code == 422
    assert put(http, {"base_url": "https://user:pw@evil.example/v1"}).status_code == 422
    r = put(http, {"base_url": "https://other.example/v1"}).json()
    assert r["base_url"] == "https://other.example/v1" and r["api_key_set"] is False
    r = put(http, {"base_url": "https://api.openai.com/v1", "api_key": KEY}).json()
    assert r["api_key_set"] is True
    assert put(http, {"clear_api_key": True}).json()["api_key_set"] is False


def test_test_endpoint_requires_key(client):
    http, _ = client
    admin(http)
    assert post(http, "/api/settings/ai/test").status_code == 409


def test_env_key_is_fallback(client, monkeypatch):
    http, Session = client
    monkeypatch.setenv("ZOOMVCR_AI_API_KEY", "sk-env-key-0123456789abcd")
    from zoomvcr import config
    config.settings.cache_clear()
    with Session() as s:
        cfg = ai_settings.resolve(s)
    assert cfg.api_key == "sk-env-key-0123456789abcd" and cfg.key_source == "env"


def test_chunk_plan_and_parse():
    assert openai_api.chunk_plan(1250.0, 600) == [(0.0, 600.0), (600.0, 600.0), (1200.0, 50.0)]
    assert openai_api.chunk_plan(0.1, 600) == []
    lines = openai_api.parse_transcription(
        {"segments": [{"start": 1.0, "end": 2.5, "text": " Hallo "}, {"start": 3, "end": 4, "text": " "}]}, 600, 600)
    assert lines == [{"start": 601.0, "end": 602.5, "text": "Hallo"}]
    assert openai_api.parse_transcription({"text": "Satz"}, 30, 30) == [{"start": 30, "end": 60, "text": "Satz"}]


def _cfg(**over):
    base = dict(base_url="https://api.example/v1", api_key=KEY, transcription_provider="openai",
                transcription_model="whisper-1", summary_enabled=True, summary_model="m", key_source="ui")
    base.update(over)
    return ai_settings.AIConfig(**base)


_REAL_CLIENT = httpx.Client


def _mock_client(monkeypatch, handler):
    real = _REAL_CLIENT
    monkeypatch.setattr(openai_api.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(openai_api.time, "sleep", lambda s: None)


def test_retry_on_429_and_key_masked_in_errors(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + KEY
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json={"data": [{"id": "whisper-1"}, {"id": "m"}]})
    _mock_client(monkeypatch, handler)
    assert openai_api.list_models(_cfg()) == ["m", "whisper-1"] and len(calls) == 2

    _mock_client(monkeypatch, lambda r: httpx.Response(401, json={"error": {"message": f"Incorrect API key {KEY}"}}))
    with pytest.raises(openai_api.ProviderError) as err:
        openai_api.list_models(_cfg())
    assert KEY not in str(err.value) and "401" in str(err.value)


def _tone(path: Path, seconds: int):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-c:a", "aac", str(path)], check=True)


def test_transcribe_video_chunks_offsets_and_cleanup(tmp_path, monkeypatch):
    video = tmp_path / "recording.m4a"
    _tone(video, 70)
    monkeypatch.setattr(openai_api, "CHUNK_SECONDS_SEGMENTS", 30)
    seen = []
    def handler(request):
        body = request.read()
        assert b'name="model"' in body and b"whisper-1" in body and b"verbose_json" in body
        assert b'filename="chunk_' in body
        seen.append(1)
        return httpx.Response(200, json={"segments": [{"start": 0.5, "end": 1.5, "text": "Teil"}]})
    _mock_client(monkeypatch, handler)
    lines = openai_api.transcribe_video(_cfg(), video, tmp_path, workers=2)
    assert len(seen) == 3
    assert [l["start"] for l in lines] == [0.5, 30.5, 60.5]
    assert not (tmp_path / "asr-chunks").exists()


def test_text_only_model_uses_short_chunks(tmp_path, monkeypatch):
    video = tmp_path / "recording.m4a"
    _tone(video, 65)
    def handler(request):
        body = request.read()
        assert b"verbose_json" not in body and b"timestamp_granularities" not in body
        return httpx.Response(200, json={"text": "Satz"})
    _mock_client(monkeypatch, handler)
    lines = openai_api.transcribe_video(_cfg(transcription_model="gpt-4o-mini-transcribe"), video, tmp_path)
    assert [l["start"] for l in lines] == [0, 30, 60]


def test_analysis_respects_settings_without_transfer(client, tmp_path, monkeypatch):
    http, _ = client
    admin(http)
    def forbidden(*a, **k):
        raise AssertionError("no network call expected")
    monkeypatch.setattr(openai_api, "_request", forbidden)
    put(http, {"transcription_provider": "off"})
    lines, note = analysis.transcript_from_video(tmp_path / "x.mp4", tmp_path)
    assert lines == [] and "ausgeschaltet" in note
    result, note = analysis.optional_ai_analysis([{"start": 0, "end": 1, "text": "x"}])
    assert result is None and "Kein API-Key" in note
    put(http, {"api_key": KEY, "summary_enabled": False})
    result, note = analysis.optional_ai_analysis([{"start": 0, "end": 1, "text": "x"}])
    assert result is None and "ausgeschaltet" in note


def test_summary_via_chat(client, monkeypatch):
    http, _ = client
    admin(http)
    put(http, {"api_key": KEY, "summary_model": "gpt-5-mini"})
    def handler(request):
        payload = json.loads(request.read())
        assert request.url.path.endswith("/chat/completions") and payload["model"] == "gpt-5-mini"
        assert "temperature" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"zusammenfassung\": \"ok\"}"}}]})
    _mock_client(monkeypatch, handler)
    result, note = analysis.optional_ai_analysis([{"start": 0, "end": 1, "text": "Vortrag"}])
    assert note is None and result["parts"] == [{"zusammenfassung": "ok"}]


def test_phantom_and_no_speech_segments_dropped():
    payload = {"segments": [
        {"start": 0, "end": 30, "text": "Untertitel der Amara.org-Community", "no_speech_prob": 0.2},
        {"start": 30, "end": 40, "text": "Hintergrundrauschen", "no_speech_prob": 0.9},
        {"start": 40, "end": 50, "text": "Paragraph 626 BGB", "no_speech_prob": 0.1}]}
    assert [l["text"] for l in openai_api.parse_transcription(payload, 0, 60)] == ["Paragraph 626 BGB"]
    assert openai_api.parse_transcription({"text": "Untertitel der Amara.org-Community"}, 0, 30) == []


def test_silent_chunks_are_not_uploaded(tmp_path, monkeypatch):
    video = tmp_path / "recording.m4a"
    # 30 s digital silence, then 35 s tone
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono:d=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=35", "-filter_complex", "[0][1]concat=n=2:v=0:a=1",
                    "-c:a", "aac", str(video)], check=True)
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"text": "Satz"})
    _mock_client(monkeypatch, handler)
    lines = openai_api.transcribe_video(_cfg(transcription_model="gpt-4o-transcribe"), video, tmp_path)
    assert len(calls) == 2 and [l["start"] for l in lines] == [30, 60]
