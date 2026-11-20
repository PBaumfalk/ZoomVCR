# Anhang – Funktionsliste

Alle Funktionen von ZoomVCR 1.0 mit Rolle bzw. Voraussetzung, Fundstelle und dem Kapitel, das sie erklärt. Rollen: **Betrachter** < **Rekorder** < **Administrator**; jede Rolle darf alles der Rollen davor ([Kapitel 6](06-benutzer-und-rechte.md#rollen)). „Server“ heißt: Zugang zur Kommandozeile im Projektordner.

Stand-Angaben: **stabil** = im Kanzleibetrieb erprobt; **heuristisch** = hängt an der Erkennung der Zoom-Oberfläche und kann nach Zoom-Updates Anpassung brauchen ([Kapitel 16](16-einschraenkungen.md)); **experimentell** = bewusst abgeschaltet, nur nach eigener Abwägung einschalten.

## Anmelden und Oberfläche

| Funktion | Rolle oder Voraussetzung | Fundstelle | Kapitel |
| --- | --- | --- | --- |
| Anmelden mit lokalem Konto (Passwort, ggf. Authenticator-Code) | jedes Konto | Anmeldeseite → **Lokales Konto verwenden** · `POST /api/login` | [2](02-erste-schritte.md#anmelden) |
| Anmelden mit Kanzlei-Login | OIDC eingerichtet, Konto mit gleicher E-Mail | Anmeldeseite → **Mit Kanzlei-Login anmelden** · `backend/zoomvcr/oidc.py` | [2](02-erste-schritte.md#anmelden), [12](12-anmeldung-oidc.md) |
| Abmelden, Sitzung endet nach 8 Stunden | jedes Konto | Seitenleiste unten | [2](02-erste-schritte.md#die-oberfläche) |
| Übersicht: Läuft gerade, Als Nächstes, Zuletzt aufgenommen (aktualisiert alle 5 s) | Betrachter | **Übersicht** | [2](02-erste-schritte.md#die-oberfläche) |
| Hell und dunkel | jedes Konto | Mond-/Sonnensymbol unten links | [2](02-erste-schritte.md#hell-und-dunkel) |
| Smartphone-Ansicht | VPN bzw. Büronetz | automatisch bei schmalem Bildschirm | [2](02-erste-schritte.md#auf-dem-smartphone) |

## Aufnehmen

| Funktion | Rolle oder Voraussetzung | Fundstelle | Kapitel |
| --- | --- | --- | --- |
| Zoom-Aufnahme planen (Titel, Link, Beginn, Dauer, Name in Zoom) | Rekorder; Zoom-Desktop aktiv (`--zoom`, x86-64) | **Aufnahme planen** · `POST /api/recordings` | [3](03-aufnahme-planen.md) |
| Berechtigung und Nachweis erklären (wird protokolliert, `authorization.json`) | Rekorder | Dialog **Aufnahme planen** | [3](03-aufnahme-planen.md#die-felder), [8](08-datenschutz-und-recht.md#vor-der-aufnahme) |
| Testaufnahme ohne Zoom (Testbild, Ton, drei Folien) | Rekorder | **Aufnahme planen → Weitere Optionen → Quelle** | [2](02-erste-schritte.md#ihr-erster-ablauf-eine-testaufnahme), [3](03-aufnahme-planen.md#die-felder) |
| Name in Zoom vor dem Start ändern | Rekorder | Detailansicht einer geplanten Zoom-Aufnahme · `PATCH …/participant-name` | [3](03-aufnahme-planen.md#nach-dem-planen) |
| Jetzt starten | Rekorder | Detailansicht → **Jetzt starten** · `POST …/start` | [3](03-aufnahme-planen.md#nach-dem-planen) |
| Automatischer Start: Beitritt 5 Min. vorher, Ende 15 Min. nach Plan (Hintergrund) | Dienst `scheduler` | `backend/zoomvcr/scheduler.py`, `ZOOMVCR_JOIN_LEAD_MINUTES`, `ZOOMVCR_END_BUFFER_MINUTES` | [1](01-was-ist-zoomvcr.md#wie-eine-aufnahme-abläuft), [11](11-konfiguration.md#zoom-desktop) |
| Eine Aufnahme gleichzeitig, Warteschlange (Hintergrund) | Dienst `capture` | `compose.yml` | [3](03-aufnahme-planen.md#zeiten), [16](16-einschraenkungen.md) |
| Warteraum- und Meeting-Erkennung · *heuristisch* | Zoom-Desktop | Status **Warteraum** / **Tritt bei** · `backend/zoomvcr/desktop_agent.py` | [4](04-waehrend-der-aufnahme.md#status) |
| Namensprüfung in der Teilnehmerliste · *heuristisch* | Zoom-Desktop | `backend/zoomvcr/zoom_name_gui.py` | [4](04-waehrend-der-aufnahme.md#name-in-zoom-und-beitritt-bestätigen) |
| Beitritt bzw. Namen bestätigen | Rekorder; nach Blick per VNC | Detailansicht → **Beitritt bestätigen** · `POST …/admit`, `…/confirm-name` | [4](04-waehrend-der-aufnahme.md#name-in-zoom-und-beitritt-bestätigen) |
| Tonwächter · *heuristisch* (Hintergrund) | Zoom-Desktop | `backend/zoomvcr/desktop_agent.py` | [4](04-waehrend-der-aufnahme.md#der-tonwächter) |
| Live-Bild des Rekorders | Administrator | Detailansicht einer laufenden Aufnahme · `GET /api/desktop/snapshot` | [4](04-waehrend-der-aufnahme.md#live-bild) |
| Stoppen | Rekorder | Detailansicht → **Stoppen** · `POST …/stop` | [4](04-waehrend-der-aufnahme.md#stoppen) |
| Aufnahme auf Verdacht nach X Sekunden · *experimentell, aus* | Server, `.env` | `ZOOMVCR_ASSUME_JOINED_AFTER_SECONDS` | [11](11-konfiguration.md#zoom-desktop) |
| Zoom nur bei Bedarf starten (Hintergrund) | Zoom-Desktop | `desktop/` | [10](10-zoom-desktop.md#zoom-bei-bedarf) |

## Ergebnis ansehen und weiterverwenden

| Funktion | Rolle oder Voraussetzung | Fundstelle | Kapitel |
| --- | --- | --- | --- |
| Mediathek mit Suche und Reitern Alle / Geplant / Fertig / Mit Problemen | Betrachter | **Mediathek** | [5](05-mediathek-und-auswertung.md#mediathek) |
| Video abspielen, Sprung per Zeitstempel | Betrachter | Detailansicht | [5](05-mediathek-und-auswertung.md#die-detailansicht) |
| Automatischer Schnitt von Stille, Original bleibt (Hintergrund) | `ZOOMVCR_CUT_ENABLED=true` (Standard) | Hinweis über dem Video · `backend/zoomvcr/media.py` | [5](05-mediathek-und-auswertung.md#automatischer-schnitt), [11](11-konfiguration.md#schnitt) |
| Folienerkennung mit Texterkennung (lokal) | – | Reiter **Folien** | [5](05-mediathek-und-auswertung.md#folien) |
| Transkript mit Suche | KI-Key oder lokales Whisper | Reiter **Transkript** | [5](05-mediathek-und-auswertung.md#transkript), [7](07-ki-und-benachrichtigung.md#transkription) |
| KI-Auswertung (Zusammenfassung, Gliederung, Argumentation, Praxishinweise, Rechtsquellen) | KI-Key und Haken „per KI erstellen“ | Reiter **Auswertung** | [5](05-mediathek-und-auswertung.md#auswertung), [7](07-ki-und-benachrichtigung.md#auswertung) |
| Ergebnis prüfen und in der Kanzlei weiterverwenden | Betrachter | Detailansicht, **Herunterladen** | [5](05-mediathek-und-auswertung.md#ergebnis-prüfen-und-weiterverwenden) |
| Rechtsquellen-Fundstellen ohne KI (Paragraphen, Aktenzeichen, Gerichte aus dem Transkript) | Transkript vorhanden | `legal_sources.json`, Export `sources` · `backend/zoomvcr/analysis.py` | [5](05-mediathek-und-auswertung.md#ergebnis-prüfen-und-weiterverwenden), [14](14-architektur.md#api) |
| Herunterladen: Video, Original, Transkript, Auswertung, Folienindex, ZIP | Betrachter | Detailansicht → **Herunterladen** · `GET …/export/{kind}` | [5](05-mediathek-und-auswertung.md#herunterladen) |
| Neu verarbeiten | Rekorder | Detailansicht → **Neu verarbeiten** · `POST …/process` | [5](05-mediathek-und-auswertung.md#neu-verarbeiten) |
| Aufnahme endgültig löschen | Administrator; nicht während der Aufnahme | Papierkorbsymbol → **Endgültig löschen** · `DELETE /api/recordings/{id}` | [5](05-mediathek-und-auswertung.md#löschen) |

## Verwaltung

| Funktion | Rolle oder Voraussetzung | Fundstelle | Kapitel |
| --- | --- | --- | --- |
| Konto anlegen (Kanzlei-Login oder lokal), Rolle ändern, sperren, Passwort zurücksetzen | Administrator | **Verwaltung → Benutzer** | [6](06-benutzer-und-rechte.md#konten-verwalten) |
| Eigenes Passwort ändern, Authenticator (TOTP) einrichten oder abschalten | lokales Konto | **Mein Konto** | [6](06-benutzer-und-rechte.md#mein-konto-und-zwei-faktor) |
| Auditprotokoll | Administrator | **Verwaltung → Auditprotokoll** | [6](06-benutzer-und-rechte.md#auditprotokoll) |
| KI-Dienst: Adresse, API-Key, Verbindung testen, Key entfernen | Administrator | **Verwaltung → KI und Benachrichtigung** | [7](07-ki-und-benachrichtigung.md#ki-dienst) |
| Transkription über KI-Dienst, lokal oder aus | Administrator; lokal nur mit Image `LOCAL_ASR=true` | ebenda, **Transkription** | [7](07-ki-und-benachrichtigung.md#transkription), [9](09-installation.md#lokales-whisper) |
| Mail-Warnung bei Problemen, Testmail | Administrator; SMTP in `.env` | ebenda, **Benachrichtigung bei Problemen** | [7](07-ki-und-benachrichtigung.md#mail-warnung), [11](11-konfiguration.md#mail) |

## Installation und Betrieb

| Funktion | Rolle oder Voraussetzung | Fundstelle | Kapitel |
| --- | --- | --- | --- |
| Installationsskript (anlegen, bauen, starten, prüfen; wiederholbar) | Server, Docker | `scripts/install.sh` | [9](09-installation.md#das-installationsskript) |
| Installation mit Claude Code | Server, Claude Code | Installationsprompt | [9a](09a-installation-mit-claude-code.md) |
| Erstes Admin-Konto beim ersten Start | `ZOOMVCR_ADMIN_PASSWORD` | `backend/zoomvcr/security.py` | [9](09-installation.md#erste-anmeldung) |
| Betrieb hinter vorhandenem Reverse Proxy | Server | `deploy/docker-compose.override.yml` | [9](09-installation.md#netz-und-reverse-proxy), [13](13-betrieb.md#hinter-einem-vorhandenen-reverse-proxy) |
| Zoom-Konto des Rekorders per VNC anmelden | Server, SSH-Tunnel | Rechtsklickmenü im Zoom-Desktop | [10](10-zoom-desktop.md#zoom-einmalig-anmelden) |
| Kommandozeile `./zoomvcr` (status, recordings, schedule, start, stop, admit, process, logs, set-name, confirm-name) | Server, `ZOOMVCR_API_TOKEN` | `backend/zoomvcr/cli.py` | [13](13-betrieb.md#kommandozeile) |
| Gesundheitsprüfung (auch für Monitoring) | – | `GET /health`, `./zoomvcr status`, `docker compose ps` | [13](13-betrieb.md#läuft-alles) |
| Protokoll je Aufnahme | Rekorder bzw. Server | `GET …/logs`, `./zoomvcr logs <ID>` | [13](13-betrieb.md#logs) |
| Updates | Server | `git pull` + `scripts/install.sh` | [13](13-betrieb.md#updates) |
| Sicherung und Wiederherstellung | Server | `pg_dump`, Volume-Archiv | [13](13-betrieb.md#sicherung), [13](13-betrieb.md#wiederherstellung) |
| Schnittstelle (REST-API) für eigene Skripte | Token oder Sitzung, je nach Rolle | `/api/…` | [14](14-architektur.md#api) |
| Tests, CI, Bildschirmfotos | Entwicklung | `backend/tests`, `.github/workflows/ci.yml`, `scripts/docs/` | [15](15-tests.md) |

Nicht vorhanden sind u. a.: Trennung der Mediathek nach Personen oder Mandaten, automatisches Löschen nach Frist, Teams/Webex, gleichzeitige Aufnahmen ([Kapitel 16](16-einschraenkungen.md)).
