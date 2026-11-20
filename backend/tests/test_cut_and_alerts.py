"""Automatic cut of silent start/end/pauses and mail alerts."""
import subprocess

from test_delete_recording import _recording
from test_user_management import client, login_as, post  # noqa: F401  (fixture reuse)
from zoomvcr import config, media, notify
from zoomvcr.models import Recording

ORIGIN = {"Origin": "http://localhost:8000"}


def test_plan_cut_edges_pauses_and_short_silence():
    silences = [(0.0, 30.0), (93.0, 243.0), (150.0, 160.0), (303.0, 330.0)]
    keep = media.plan_cut(330.0, silences, edge=20, pause=120, pad=3)
    assert keep == [(27.0, 96.0), (240.0, 306.0)]
    # short pauses (< pause) and short edges (< edge) stay
    assert media.plan_cut(300.0, [(0.0, 10.0), (100.0, 160.0)], edge=20, pause=120, pad=3) is None
    # all silent
    assert media.plan_cut(300.0, [(0.0, float("inf"))], edge=20, pause=120, pad=3) == []


def _lecture(path, pattern):
    """pattern: list of ("s"|"t", seconds) -> video with silent / tone audio, keyframe every 2 s."""
    inputs, labels = [], []
    for i, (kind, sec) in enumerate(pattern):
        src = f"anullsrc=r=48000:cl=stereo:d={sec}" if kind == "s" else f"sine=frequency=440:sample_rate=48000:duration={sec}"
        inputs += ["-f", "lavfi", "-i", src]
        labels.append(f"[{i}:a]")
    total = sum(sec for _, sec in pattern)
    n = len(pattern)
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *inputs,
           "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=10:duration={total}",
           "-filter_complex", "".join(labels) + f"concat=n={n}:v=0:a=1[a]",
           "-map", f"{n}:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-g", "20",
           "-c:a", "aac", "-ac", "2", str(path)]
    subprocess.run(cmd, check=True)


def test_auto_cut_keeps_original_and_is_repeatable(tmp_path, monkeypatch):
    config.settings.cache_clear()
    _lecture(tmp_path / "recording.mp4", [("s", 30), ("t", 60), ("s", 150), ("t", 60), ("s", 30)])
    result = media.auto_cut(tmp_path)
    assert result["status"] == "cut" and result["cuts"] == 3
    assert (tmp_path / "original.mp4").is_file()
    cut = media.verify_media(tmp_path / "recording.mp4")["duration_seconds"]
    assert 125 < cut < 145, cut
    assert abs(media.verify_media(tmp_path / "original.mp4")["duration_seconds"] - 330) < 1
    again = media.auto_cut(tmp_path)   # re-processing starts again from the original
    assert again["status"] == "cut"
    assert abs(media.verify_media(tmp_path / "recording.mp4")["duration_seconds"] - cut) < 2.5
    assert not (tmp_path / "cut-parts").exists()


def test_auto_cut_mostly_silent_keeps_everything(tmp_path):
    config.settings.cache_clear()
    _lecture(tmp_path / "recording.mp4", [("s", 200), ("t", 5), ("s", 100)])
    result = media.auto_cut(tmp_path)
    assert result["status"] == "mostly_silent"
    assert not (tmp_path / "original.mp4").exists()
    assert abs(media.verify_media(tmp_path / "recording.mp4")["duration_seconds"] - 305) < 1


def test_alert_sent_once_per_kind_without_names(client, monkeypatch):
    http, Session = client
    assert login_as(http, "admin", "first_admin_password_2026").status_code == 200
    rid = _recording(http)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            sent.append({"host": host, "port": port})
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, user, password):
            sent[-1]["login"] = (user, password)
        def send_message(self, msg):
            sent[-1]["msg"] = msg

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    # not configured: stored, nothing sent
    assert notify.alert(rid, "audio_missing", "kein Ton") is False
    with Session() as s:
        assert s.get(Recording, rid).metadata_json["alerts"]["audio_missing"]["sent"] is False
    monkeypatch.setenv("ZOOMVCR_SMTP_URL", "smtps://rekorder%40example.org:p%40ss@mail.example.org:465")
    monkeypatch.setenv("ZOOMVCR_ALERT_EMAIL", "patrick@example.org")
    monkeypatch.setenv("ZOOMVCR_MAIL_FROM", "ZoomVCR <rekorder@example.org>")
    config.settings.cache_clear()
    assert notify.alert(rid, "capture_failed", "Fehler: join failed") is True
    assert notify.alert(rid, "capture_failed", "Fehler: again") is False      # once per kind
    assert len(sent) == 1 and sent[0]["host"] == "mail.example.org" and sent[0]["login"] == ("rekorder@example.org", "p@ss")
    msg = sent[0]["msg"]
    assert msg["To"] == "patrick@example.org" and "Aufnahme fehlgeschlagen" in msg["Subject"]
    body = msg.get_content()
    assert "Alte Fortbildung" in body and "VNC" in body and "p@ss" not in body
    # admin test mail endpoint
    r = http.post("/api/settings/mail/test", headers=ORIGIN)
    assert r.status_code == 200 and r.json()["ok"] is True and len(sent) == 2
    assert http.get("/api/settings/mail").json()["configured"] is True


def test_smtp_url_from_shared_script_key(monkeypatch):
    monkeypatch.setenv("SMTP_URL", "smtp://u:p@host.example:587")
    monkeypatch.delenv("ZOOMVCR_SMTP_URL", raising=False)
    config.settings.cache_clear()
    parts = notify.smtp_parts(config.settings().smtp_url)
    assert parts == {"tls": False, "host": "host.example", "port": 587, "user": "u", "password": "p"}
    config.settings.cache_clear()
