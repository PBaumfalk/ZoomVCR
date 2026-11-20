# 13 – Betrieb

Alle Befehle laufen im Projektordner auf dem Server (dort, wo `compose.yml` liegt).

## Läuft alles?

```bash
docker compose ps                         # api: healthy, alle übrigen: running (desktop nur mit Zoom)
curl -fsS https://vcr.example.com/health  # {"status":"ok"} = Datenbank und Warteschlange erreichbar
./zoomvcr status                          # Aufnahmen je Status, freier Speicher, ob Zoom aktiviert ist
```

`scripts/install.sh` ohne Optionen führt dieselben Prüfungen aus und startet fehlende Dienste neu, ohne etwas an Konfiguration oder Daten zu ändern. Für ein externes Monitoring (z. B. Uptime Kuma) eignet sich `/health`: Antwort `200` heißt betriebsbereit, `503` heißt Datenbank oder Redis nicht erreichbar.

## Kommandozeile

`./zoomvcr` im Projektordner ruft die API im Container `api` mit dem Admin-Token auf.

```bash
./zoomvcr status                     # Dienste, Desktop, Speicher
./zoomvcr recordings [--search TEXT]
./zoomvcr schedule --title 'Fortbildung Arbeitsrecht' --source desktop_manual \
  --url 'https://us06web.zoom.us/j/12345678901?pwd=TOKEN' \
  --participant-name 'ZoomVCR – Aufzeichnung' \
  --at '2026-11-20T09:00:00+01:00' --minutes 180 \
  --authorization written_consent --authorization-reference 'E-Mail vom 05.11.2026' \
  --permission-confirmed --disclosure-acknowledged
./zoomvcr schedule --title Installationstest --source synthetic \
  --at '2026-11-20T09:00:00+01:00' --minutes 1        # Testaufnahme ohne Zoom
./zoomvcr start <ID>                 # sofort starten
./zoomvcr admit <ID>                 # Beitritt bestätigen (nur nach Blick per VNC)
./zoomvcr stop <ID>
./zoomvcr process <ID>               # neu verarbeiten
./zoomvcr logs <ID>
./zoomvcr set-name <ID> --name 'Neuer Name'
./zoomvcr confirm-name <ID>          # Namen in Zoom bestätigen (nur nach Blick per VNC)
```

Jeder Befehl gibt JSON aus und steht im Auditprotokoll als `system-cli`.

## Logs

```bash
docker compose logs -f --tail=200 capture    # Aufnahmen
docker compose logs -f --tail=200 processor  # Verarbeitung
docker compose logs -f --tail=200 desktop    # Zoom-Agent, Tonwächter
docker compose logs -f --tail=200 scheduler
docker compose logs -f --tail=200 api        # Anmeldung, Oberfläche, Start
```

Je Aufnahme liegt zusätzlich ein Log im Aufnahmeordner, abrufbar mit `./zoomvcr logs <ID>`.

## Updates

```bash
git pull
scripts/install.sh
```

Das Skript baut geänderte Images neu, startet die Dienste und prüft sie; `.env`, Datenbank und Aufnahmen bleiben erhalten. Fehlende Tabellen und Spalten legt die API beim Start selbst an. Was sich geändert hat, steht im [CHANGELOG](../../CHANGELOG.md).

- Vor größeren Updates [sichern](#sicherung).
- Nicht während einer Aufnahme aktualisieren: `./zoomvcr status` bzw. die Übersicht zeigen, ob gerade etwas läuft. Ein Neustart von `capture` oder `desktop` bricht eine laufende Aufnahme ab (Status **Unterbrochen**; vorhandene Teile bleiben).
- Nach einem Update eine **Testaufnahme** planen ([Kapitel 2](02-erste-schritte.md#ihr-erster-ablauf-eine-testaufnahme)).

## Sicherung

| Was | Wie |
| --- | --- |
| Datenbank (Aufnahmen, Konten, Einstellungen, Auditprotokoll) | `docker compose exec -T postgres pg_dump -U zoomvcr --clean --if-exists zoomvcr > zoomvcr.sql` |
| Aufnahmen (Videos, Folien, Transkripte, Auswertungen) | Volume `zoomvcr_recordings`, z. B. `docker run --rm -v zoomvcr_recordings:/data:ro -v "$PWD":/backup alpine tar czf /backup/recordings.tar.gz -C /data .` oder mit restic bzw. einer Volume-Sicherung |
| Zoom-Anmeldung des Rekorders | Volume `zoomvcr_zoom_profile` wie oben, sonst nach einer Wiederherstellung neu anmelden |
| Schlüssel und Einstellungen | `.env`, vor allem `ZOOMVCR_SECRET_KEY`, getrennt und verschlüsselt |

Ohne den passenden `ZOOMVCR_SECRET_KEY` lassen sich der gespeicherte KI-Key und die Authenticator-Einrichtungen nach einer Wiederherstellung nicht mehr entschlüsseln. Sicherungen enthalten Aufnahmen mit Bild und Stimme der Teilnehmer: verschlüsselt ablegen ([Kapitel 8](08-datenschutz-und-recht.md)).

Die Volume-Namen beginnen mit dem Compose-Projektnamen (`zoomvcr`); `docker volume ls` zeigt sie.

## Wiederherstellung

Auf einem Server mit installiertem ZoomVCR (ggf. vorher neu installieren, [Kapitel 9](09-installation.md)) und der gesicherten `.env` im Projektordner:

```bash
docker compose stop api scheduler capture processor web proxy     # Postgres läuft weiter
docker compose exec -T postgres psql -q -U zoomvcr -d zoomvcr -v ON_ERROR_STOP=1 < zoomvcr.sql
docker run --rm -v zoomvcr_recordings:/data -v "$PWD":/backup alpine tar xzf /backup/recordings.tar.gz -C /data
scripts/install.sh                                                  # startet alles und prüft
```

Die Sicherung mit `--clean --if-exists` ersetzt den Datenbankinhalt vollständig; alles, was seit der Sicherung geplant oder aufgenommen wurde, ist danach nicht mehr in der Mediathek. Kontrolle: Die Mediathek zeigt die Aufnahmen wieder, Videos lassen sich abspielen, die Anmeldung mit den bisherigen Konten funktioniert.

## Fehlerbilder

| Meldung oder Beobachtung | Ursache und Abhilfe |
| --- | --- |
| Fehler beim Beitritt, Mail „Aufnahme gescheitert“ | Meeting nicht gestartet, Link falsch oder Zoom abgemeldet. Per VNC nachsehen ([Kapitel 10](10-zoom-desktop.md)), ggf. neu anmelden. |
| Status bleibt auf **Tritt bei** mit Hinweis zum Namen | Zoom-Oberfläche nicht eindeutig erkannt. Per VNC prüfen, dann **Beitritt bestätigen**. |
| Mail „kein Zoom-Ton“ | Der Tonwächter kam nicht durch. Per VNC „Join Audio“ klicken; danach im Desktop-Log nachsehen, welches Fenster im Weg war. |
| Mail „fast ohne Ton“ | Aufnahme lief, aber ohne Ton. Ton-Einstellungen in Zoom prüfen. |
| **Wird verarbeitet** hängt | `docker compose logs processor`. Häufig KI-Dienst (Key, Guthaben, Limit). Danach **Neu verarbeiten**. |
| Hinweis „Kein API-Key hinterlegt“ | Kein KI-Dienst eingerichtet; gewollt, wenn nichts übertragen werden soll. Sonst Key eintragen ([Kapitel 7](07-ki-und-benachrichtigung.md)) und **Neu verarbeiten**. |
| Anmeldung scheitert mit „Invalid request origin“ | Die Adresse im Browser weicht von `ZOOMVCR_PUBLIC_ORIGIN` ab (anderer Name, Port oder http statt https). Wert in `.env` korrigieren, `docker compose up -d --force-recreate api`. |
| API startet nicht: „Use HTTPS for ZOOMVCR_PUBLIC_ORIGIN …“ | Ohne HTTPS sind nur `http://localhost` und `http://127.0.0.1` erlaubt ([Kapitel 11](11-konfiguration.md#grundlagen)). |
| Anmeldung über SSO schlägt fehl | Kein Konto mit dieser E-Mail, E-Mail nicht bestätigt oder Redirect URI falsch ([Kapitel 12](12-anmeldung-oidc.md)). |
| `port is already allocated` beim Start | Ein anderer Dienst nutzt Port 80/443 bzw. den Probelauf-Port. Anderen Port wählen (`--port`) oder ZoomVCR hinter den vorhandenen Proxy stellen. |
| Hohe CPU-Last ohne Aufnahme | Zoom läuft noch (z. B. nach einer Anmeldung per VNC). Im VNC Zoom beenden. |

## Hinter einem vorhandenen Reverse Proxy

Läuft auf dem Server schon ein zentraler Reverse Proxy (Caddy, Traefik, nginx) für mehrere Dienste, braucht ZoomVCR keinen eigenen:

1. `deploy/docker-compose.override.yml` als `compose.override.yml` in den Projektordner kopieren. Sie schaltet den mitgelieferten Caddy ab und hängt `api` und `web` in das externe Docker-Netz `proxy` (Namen dort anpassen, falls Ihr Proxy-Netz anders heißt).
2. Im Proxy zwei Ziele eintragen: `/api/*` und `/health` an `zoomvcr-api:8000`, alles andere an `zoomvcr-web:3000`. Der Proxy übernimmt HTTPS und sollte den Zugriff auf Büronetz und VPN beschränken.
3. `scripts/install.sh --origin https://vcr.example.com` (mit `--zoom` für echte Aufnahmen).

`compose.override.yml` ist in `.gitignore` eingetragen und bleibt bei `git pull` unberührt.
