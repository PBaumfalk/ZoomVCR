# 9 – Installation

## Voraussetzungen

- Linux-Server x86-64 (den Zoom-Linux-Client gibt es nur dafür), Docker Engine mit Compose v2, `git` und `curl`.
- **4 vCPU und 8 GB RAM** als Startwert. Während einer Aufnahme braucht der Zoom-Desktop etwa einen bis zwei Kerne, im Leerlauf fast nichts ([Kapitel 10](10-zoom-desktop.md#ressourcen)).
- Speicher: Eine dreistündige Aufnahme in 720p belegt grob 1–2 GB, zusätzlich das ungeschnittene Original. Die Images brauchen rund 3 GB.
- Ein Zoom-Konto für den Rekorder.
- Optional: ein OpenAI-kompatibler KI-Dienst, ein Mailpostfach für Warnungen, ein OIDC-Anbieter (z. B. authentik, Keycloak) für die zentrale Anmeldung.

## Plattformen

| Zweck | Plattform | Was geht |
| --- | --- | --- |
| **Betrieb mit Zoom** | Linux x86-64 mit Docker Engine und Compose v2 (z. B. Ubuntu 24.04) | Alles, inklusive echter Zoom-Aufnahmen |
| **Probelauf** | Mac (Apple Silicon oder Intel), Linux, Windows mit Docker Desktop | Oberfläche, Benutzer, Testaufnahmen, Verarbeitung, Export – ohne Zoom-Desktop |

## Das Installationsskript

Der kürzeste Weg ist `scripts/install.sh` im Projektordner. Es führt dieselben Befehle aus, die unten [von Hand](#von-hand) beschrieben sind, und darf beliebig oft laufen:

```bash
git clone https://github.com/PBaumfalk/ZoomVCR.git zoomvcr && cd zoomvcr

scripts/install.sh --lokal                                   # Probelauf: http://localhost:8080 (anderer Port: --port 8081)
scripts/install.sh --domain vcr.example.com --zoom           # Server mit mitgeliefertem Caddy und automatischem HTTPS
scripts/install.sh --origin https://vcr.example.com --zoom   # Server hinter vorhandenem Reverse Proxy
scripts/install.sh                                           # später: neu bauen, starten, prüfen (z. B. nach git pull)
```

| Schritt | Was das Skript tut |
| --- | --- |
| Voraussetzungen | Prüft Docker, Compose v2, laufenden Docker-Dienst, `curl` und die Architektur. Echte Zoom-Aufnahmen verlangen x86-64. |
| `.env` | Legt sie beim ersten Mal aus `.env.example` an (nur für den Besitzer lesbar) und ersetzt alle Platzhalter `CHANGE_…` durch Zufallswerte. Eine vorhandene `.env` bleibt erhalten: Nur noch vorhandene Platzhalter werden ersetzt, Adresse und Ports nur, wenn `--lokal`, `--domain` oder `--origin` angegeben ist. Ein bewusst entferntes `ZOOMVCR_ADMIN_PASSWORD` legt es nicht wieder an. Geheimnisse werden nie angezeigt. |
| Starten | `docker compose config --quiet`, dann `docker compose up -d --build` (mit `--profile zoom`, wenn `ZOOMVCR_ENABLE_DESKTOP=true`). Volumes mit Datenbank und Aufnahmen bleiben unberührt. |
| Erfolgskontrolle | Wartet, bis die API unter `/health` `ok` meldet (Datenbank und Warteschlange erreichbar), prüft, dass alle Dienste laufen, und ruft Gesundheitsprüfung und Anmeldeseite über den Proxy ab. Bei einem Fehler zeigt es die letzten Zeilen des API-Logs. |
| Ergebnis | Nennt Adresse, Benutzername der ersten Anmeldung und wo das Passwort steht. |

Erfolgreich endet es so:

```text
==> Erfolgskontrolle
  API /health: ok (Datenbank und Warteschlange erreichbar)
  Dienste laufen: api capture postgres processor proxy redis scheduler web
  http://localhost:8080/health und Anmeldeseite: erreichbar

==> Fertig
ZoomVCR läuft unter:  http://localhost:8080
Erste Anmeldung:      Benutzer 'admin', Passwort in .env unter ZOOMVCR_ADMIN_PASSWORD
```

Beim ersten Mal dauert das Bauen der Images einige Minuten, danach Sekunden. Mit Claude Code geht dasselbe per Prompt: [Kapitel 9a](09a-installation-mit-claude-code.md).

## Von Hand

```bash
git clone https://github.com/PBaumfalk/ZoomVCR.git zoomvcr && cd zoomvcr
cp .env.example .env
chmod 600 .env
```

Geheimnisse erzeugen, ohne sie anzuzeigen:

```bash
python3 - <<'PY'
from pathlib import Path
import re, secrets
p = Path('.env'); s = p.read_text()
for key in ('ZOOMVCR_ADMIN_PASSWORD', 'ZOOMVCR_SECRET_KEY', 'ZOOMVCR_API_TOKEN', 'POSTGRES_PASSWORD', 'ZOOMVCR_VNC_PASSWORD'):
    s = re.sub(rf'^{key}=.*$', f'{key}={secrets.token_urlsafe(32)}', s, flags=re.M)
p.write_text(s)
PY
```

Dann in `.env` mindestens setzen ([Kapitel 11](11-konfiguration.md)):

- `ZOOMVCR_PUBLIC_ORIGIN=https://vcr.example.com` und `ZOOMVCR_SITE=vcr.example.com` (Probelauf: `ZOOMVCR_PUBLIC_ORIGIN=http://localhost:8080`, `ZOOMVCR_SITE=:80`, `ZOOMVCR_HTTP_PORT=8080`)
- `ZOOMVCR_ENABLE_DESKTOP=true` für echte Zoom-Aufnahmen

Starten und prüfen:

```bash
docker compose config --quiet              # Konfiguration prüfen
docker compose --profile zoom up -d --build
docker compose ps                          # api: healthy, übrige Dienste: running
curl -fsS https://vcr.example.com/health   # {"status":"ok"}
./zoomvcr status
```

Der Zoom-Desktop liegt im Compose-Profil `zoom`. Ohne `--profile zoom` startet alles außer Zoom; dann sind nur Testaufnahmen möglich.

## Erste Anmeldung

1. Die Adresse öffnen (`https://vcr.example.com`, beim Probelauf `http://localhost:8080`) und mit Benutzer `admin` und dem `ZOOMVCR_ADMIN_PASSWORD` aus `.env` anmelden (anzeigen: `grep ^ZOOMVCR_ADMIN_PASSWORD= .env`). Beim ersten Start legt ZoomVCR genau dieses eine Admin-Konto an.
2. Unter **Mein Konto** ein neues Passwort setzen und den Authenticator einrichten.
3. `ZOOMVCR_ADMIN_PASSWORD` aus `.env` entfernen.
4. Zoom-Konto im Rekorder anmelden: [Kapitel 10](10-zoom-desktop.md).
5. Optional: KI-Dienst eintragen ([Kapitel 7](07-ki-und-benachrichtigung.md)), die zentrale Anmeldung (SSO) per OIDC anbinden ([Kapitel 12](12-anmeldung-oidc.md)), Mail einrichten ([Kapitel 11](11-konfiguration.md#mail)).
6. Eine **Testaufnahme** planen und prüfen, ob sie nach wenigen Minuten auf **Fertig** steht ([Kapitel 2](02-erste-schritte.md#ihr-erster-ablauf-eine-testaufnahme)).
7. Konten für das Team anlegen ([Kapitel 6](06-benutzer-und-rechte.md#konten-verwalten)).

## Netz und Reverse Proxy

Das mitgelieferte Compose startet Caddy (`proxy`) auf 80/443 (änderbar mit `ZOOMVCR_HTTP_PORT` und `ZOOMVCR_HTTPS_PORT`). Mit einer Domain in `ZOOMVCR_SITE` holt Caddy automatisch ein Zertifikat; dafür muss der Name öffentlich auflösbar und Port 80 bzw. 443 von außen erreichbar sein. `/api/*` und `/health` gehen an `api:8000`, alles andere an `web:3000`.

Gibt es schon einen zentralen Reverse Proxy, den Caddy-Dienst abschalten und `api` sowie `web` ins Proxy-Netz hängen. Vorlage: `deploy/docker-compose.override.yml`, auf dem Server als `compose.override.yml` abgelegt ([Kapitel 13](13-betrieb.md#hinter-einem-vorhandenen-reverse-proxy)). Dann `scripts/install.sh --origin https://vcr.example.com` verwenden.

**Nicht veröffentlichen:** PostgreSQL, Redis, den Desktop-Agenten (8765) und VNC (5900). VNC ist nur an `127.0.0.1` des Servers gebunden und wird per SSH-Tunnel genutzt.

## Lokales Whisper

Das Standard-Image transkribiert über den KI-Dienst. Für Transkription ohne Übermittlung:

1. In `.env` `ZOOMVCR_LOCAL_ASR=true` setzen (fehlt die Zeile, ergänzen).
2. `scripts/install.sh` ausführen; es baut das Backend-Image mit Whisper neu. Die Einstellung bleibt bei allen späteren Updates erhalten.
3. In der Oberfläche unter **Verwaltung → KI und Benachrichtigung → Transkription** **Lokal mit Whisper** wählen.

Das Image wird deutlich größer, die Verarbeitung langsamer.
