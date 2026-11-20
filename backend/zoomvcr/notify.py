"""Mail alerts to the operator when something is wrong with a recording.

At most one mail per recording and alert kind (tracked in metadata_json["alerts"]). The mail carries only
title, planned time, the problem and a link - no transcript, no participant names. Without SMTP
configuration nothing is sent, but the alert is still stored and logged.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from .config import settings
from . import db as dbmod
from .models import Recording

log = logging.getLogger("zoomvcr.notify")

SUBJECTS = {
    "capture_failed": "Aufnahme fehlgeschlagen",
    "audio_missing": "Aufnahme ohne Ton",
    "processing_failed": "Verarbeitung fehlgeschlagen",
    "mostly_silent": "Aufnahme fast ohne Ton",
    "test": "Testnachricht",
}


class MailNotConfigured(RuntimeError):
    pass


def smtp_parts(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("smtp", "smtps") or not parsed.hostname:
        raise MailNotConfigured("SMTP_URL fehlt oder ist ungültig")
    return {"tls": parsed.scheme == "smtps", "host": parsed.hostname,
            "port": parsed.port or (465 if parsed.scheme == "smtps" else 587),
            "user": unquote(parsed.username or ""), "password": unquote(parsed.password or "")}


def mail_configured() -> bool:
    cfg = settings()
    return bool(cfg.smtp_url and cfg.alert_email)


def send_mail(subject: str, body: str) -> None:
    cfg = settings()
    if not cfg.alert_email:
        raise MailNotConfigured("ZOOMVCR_ALERT_EMAIL fehlt")
    smtp = smtp_parts(cfg.smtp_url)
    sender = cfg.mail_from or formataddr(("ZoomVCR", smtp["user"]))
    msg = EmailMessage()
    msg["Subject"] = "ZoomVCR: " + subject
    msg["From"] = sender
    msg["To"] = cfg.alert_email
    msg["Message-ID"] = make_msgid(domain=(parseaddr(sender)[1].split("@")[-1] or "localhost"))
    msg.set_content(body)
    context = ssl.create_default_context()
    if smtp["tls"]:
        client = smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=30, context=context)
    else:
        client = smtplib.SMTP(smtp["host"], smtp["port"], timeout=30)
    with client:
        if not smtp["tls"]:
            client.starttls(context=context)
        if smtp["user"]:
            client.login(smtp["user"], smtp["password"])
        client.send_message(msg)


def _body(rec: Recording, kind: str, detail: str) -> str:
    cfg = settings()
    tz = ZoneInfo(cfg.timezone)
    planned = rec.scheduled_at if rec.scheduled_at.tzinfo else rec.scheduled_at.replace(tzinfo=timezone.utc)
    lines = [f"{SUBJECTS.get(kind, kind)}", "",
             f"Veranstaltung: {rec.title}",
             f"Geplant: {planned.astimezone(tz):%d.%m.%Y %H:%M} Uhr",
             f"Status: {rec.status}", "", detail.strip(), "",
             f"Aufnahme ansehen: {cfg.public_origin.rstrip('/')}/  (ID {str(rec.id)[:8]})"]
    if kind == "capture_failed":
        lines += ["", "Falls Zoom abgemeldet ist: per VNC auf den Zoom-Desktop, Rechtsklick → „Zoom starten“, anmelden."]
    if kind == "audio_missing":
        lines += ["", "Der Rekorder versucht weiter, den Ton zuzuschalten. Bitte per VNC prüfen."]
    return "\n".join(lines) + "\n"


def alert(recording_id: str, kind: str, detail: str) -> bool:
    """Send one alert per recording and kind. Never raises: a failed mail must not break a recording."""
    try:
        with dbmod.SessionLocal.begin() as db:
            rec = db.get(Recording, recording_id)
            if rec is None:
                return False
            meta = dict(rec.metadata_json or {})
            alerts = dict(meta.get("alerts") or {})
            if kind in alerts:
                return False
            entry = {"at": datetime.now(timezone.utc).isoformat(), "detail": detail[:300], "sent": False}
            body = _body(rec, kind, detail)
            try:
                send_mail(SUBJECTS.get(kind, kind) + " – " + rec.title[:80], body)
                entry["sent"] = True
            except MailNotConfigured as exc:
                entry["error"] = str(exc)
            except Exception as exc:  # SMTP down, auth error ...
                entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            alerts[kind] = entry
            meta["alerts"] = alerts
            rec.metadata_json = meta
        log.warning("alert %s for %s: sent=%s %s", kind, recording_id, entry["sent"], entry.get("error", ""))
        return entry["sent"]
    except Exception:
        log.exception("alert %s for %s failed", kind, recording_id)
        return False
