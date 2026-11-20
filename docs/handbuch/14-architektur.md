# 14 – Architektur

## Dienste

```
Browser ──HTTPS──▶ Caddy ─┬─ /api ──▶ api (FastAPI) ──┬── PostgreSQL
                          └─ /    ──▶ web (Next.js)    ├── Redis ◀── scheduler
                                                        │     │
                                                        │     ├──▶ capture   (RQ-Worker „capture“)
                                                        │     └──▶ processor (RQ-Worker „processing“)
                                                        │
                                   desktop (Zoom, Xvfb, PulseAudio, Agent :8765) ◀── capture
                                   Volume recordings ◀── api, capture, processor, desktop
```

| Dienst | Aufgabe |
| --- | --- |
| `web` | Next.js 15 (React 19) im Standalone-Modus. Nur Oberfläche; alle Daten kommen von `/api`. |
| `api` | FastAPI: Anmeldung, Rechte, Aufnahmen, Exporte, Einstellungen, Audit. Legt beim Start fehlende Tabellen und Spalten an. |
| `scheduler` | Sieht in der Datenbank nach fälligen Aufnahmen und legt Aufträge in Redis an. Ein Redis-Lock verhindert Doppelstarts. Übersteht Neustarts, weil die Termine in der Datenbank stehen. |
| `capture` | Führt Aufnahmen aus: Agent ansteuern, ffmpeg in Stücken von 60 s, Heartbeat, Ende zur Sollzeit. Ein Worker, also eine Aufnahme gleichzeitig. |
| `processor` | Verarbeitung: Stücke zusammenfügen, Schnitt, Folien, Transkription, Auswertung, Berichte. |
| `desktop` | Zoom-Client mit Agent ([Kapitel 10](10-zoom-desktop.md)). Nur im Profil `zoom`. |
| `postgres`, `redis` | Daten und Warteschlangen. Nur im internen Netz. |
| `proxy` | Caddy mit automatischem HTTPS. Entfällt hinter einem vorhandenen Proxy. |

`api`, `scheduler`, `capture` und `processor` teilen ein Image (`backend/`, Python 3.12).

## Ablauf einer Aufnahme

1. **Planen**: `POST /api/recordings` prüft Link, Name und Berechtigung und schreibt `authorization.json` in den Aufnahmeordner.
2. **Fällig**: Der Scheduler legt fünf Minuten vor Beginn einen Auftrag in die Queue `capture`.
3. **Beitritt**: `capture` ruft am Agenten `/join` auf. Der Agent startet Zoom, tritt bei und meldet den Zustand (Warteraum, im Meeting, unklar). Nach der Namensprüfung beginnt die Aufnahme.
4. **Aufnahme**: ffmpeg nimmt X11-Bild und PulseAudio-Ton auf (H.264/AAC, Matroska-Stücke). Der Tonwächter läuft parallel und meldet `audio_missing_seconds`.
5. **Ende**: zur Sollzeit plus 15 Minuten oder auf **Stoppen**. `/leave` beendet Zoom.
6. **Verarbeitung** in der Queue `processing`: Zusammenfügen zu `original.mp4`, Schnitt per `silencedetect` und Stream-Copy zu `recording.mp4`, Folien per Szenenwechsel (OpenCV, dHash gegen Doppelte) und Tesseract, Transkription in Stücken, KI-Auswertung je Transkriptabschnitt.
7. **Fertig**: Status `ready`, Video und Berichte stehen bereit.

## Datenablage

Je Aufnahme ein Ordner im Volume `recordings`:

| Datei | Inhalt |
| --- | --- |
| `segments/` | Rohstücke der Aufnahme |
| `original.mp4` | Zusammengefügt, ungeschnitten |
| `recording.mp4` | Geschnittene Fassung |
| `slides/`, `slides.json` | Folienbilder und Index |
| `transcript.json`, `transcript.txt` | Transkript |
| `summary.json`, `legal_sources.json` | KI-Auswertung, erkannte Rechtsquellen |
| `authorization.json` | Berechtigungsangabe |
| `inspection.json` | Prüfung des fertigen Videos mit `ffprobe` |
| `ffmpeg.log` | Protokoll der Aufnahme |

## API

Alle Endpunkte unter `/api`, Anmeldung per Cookie (Browser) oder `Authorization: Bearer <ZOOMVCR_API_TOKEN>` (Kommandozeile).

| Endpunkt | Rolle |
| --- | --- |
| `GET /status`, `GET /recordings`, `GET /recordings/{id}`, `…/transcript`, `…/summary`, `…/slides`, `…/video`, `…/export/{kind}` | Betrachter |
| `POST /recordings`, `…/start`, `…/stop`, `…/process`, `…/admit`, `…/confirm-name`, `PATCH …/participant-name`, `GET …/logs`, `GET /desktop/health` | Rekorder |
| `DELETE /recordings/{id}`, `GET /desktop/snapshot`, `/users…`, `/audit`, `/settings/ai…`, `/settings/mail…` | Administrator |
| `GET /me`, `POST /login`, `POST /logout`, `/auth/oidc/…`, `/me/…` | angemeldet bzw. öffentlich |

## Sicherheit in Kürze

- Konten in PostgreSQL, Passwörter als Argon2id-Hash, Sitzungen serverseitig widerrufbar (acht Stunden). Cookies `HttpOnly`, `SameSite=Strict`, bei HTTPS `Secure`.
- Rollen werden bei jedem Aufruf gegen die Datenbank geprüft.
- TOTP nach RFC 6238 mit Schutz gegen Wiederverwendung, Schlüssel verschlüsselt.
- Anmeldeversuche werden in Redis gebremst (je IP und je IP plus Benutzer, 15 Minuten).
- Der KI-Key liegt verschlüsselt in der Datenbank und wird nie ausgegeben.
- Nur offizielle Zoom-Links (`https`, Host `zoom.us` bzw. Subdomain), keine beliebigen Befehle an den Agenten.
- VNC, Agent, Datenbank und Redis sind nicht von außen erreichbar.

Ältere Notizen: [Sicherheitskonzept v3](../SECURITY_V3.md), [Testbericht der Alpha](../TEST_REPORT.md).
