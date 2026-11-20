# 15 – Tests

## Backend

Rund 75 Tests mit pytest unter `backend/tests/`:

| Datei | Prüft |
| --- | --- |
| `test_user_management.py` | Konten, Rollen, Anmeldung, Sperre, Sitzungswiderruf, Passwortwechsel, TOTP, OIDC-Zuordnung (mit Attrappe) |
| `test_zoom_adapter.py` | Zoom-Links und Abwehr manipulierter Links, Pflichtangaben zur Berechtigung, ffmpeg-Aufruf, unklare Bildschirme gelten nicht als Beitritt, Ton-Schaltfläche |
| `test_participant_name.py` | Name in Zoom: Prüfen, Ändern, Bestätigen |
| `test_scheduler.py` | Beitritt fünf Minuten vorher, 15 Minuten Nachlauf |
| `test_media_pipeline.py` | Testaufnahme mit Ton und drei Folien durch die ganze Verarbeitung |
| `test_cut_and_alerts.py` | Schnitt nach Stille, Schutz vor „alles weg“, Mail-Anlässe, höchstens eine Mail je Anlass |
| `test_ai_settings.py` | KI-Einstellungen nur für Admins, Key verschlüsselt und nie ausgegeben, Adresswechsel verwirft den Key, `.env` als Rückfall |
| `test_delete_recording.py` | Löschen inklusive aller Dateien, nur für Admins, nicht während der Aufnahme |
| `test_compose.py` | `compose.yml`: alle Dienste da, VNC nur an `127.0.0.1` |
| `test_origin.py` | Erlaubte Werte für `ZOOMVCR_PUBLIC_ORIGIN`, Vergleich mit dem Origin des Browsers (Standardports) |

Die Tests brauchen ffmpeg und Tesseract. Am einfachsten im Backend-Image:

```bash
docker build -t zoomvcr-backend backend
docker run --rm -u root -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=/repo/backend zoomvcr-backend \
  sh -c 'pip install -q -r requirements-dev.txt && python -m pytest -q -p no:cacheprovider'
```

## Oberfläche

```bash
cd frontend && npm ci
npx tsc --noEmit      # Typen
npm run build         # Produktionsbuild
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) läuft bei jedem Push und Pull Request:

1. **Backend**: Image bauen, pytest darin.
2. **Oberfläche**: `npm ci`, Typprüfung, Produktionsbuild.
3. **Desktop**: Image des Zoom-Desktops bauen (prüft, dass der Zoom-Client noch installierbar ist).
4. **Handbuch**: Links und Anker in README und Handbuch.

Dependabot hält Actions, Python- und npm-Pakete und die Basis-Images monatlich aktuell.

## Handbuch und Bildschirmfotos

```bash
npm install && npm --prefix frontend install   # einmalig
npm run docs:check         # Links und Anker prüfen
npm run docs:screenshots   # Bildschirmfotos neu erzeugen
```

`docs:screenshots` startet die Oberfläche im Entwicklungsmodus gegen eine Beispiel-API mit erfundenen Daten (`scripts/docs/mock-api.mjs`) und fotografiert sie mit Playwright, hell, dunkel und auf dem Smartphone. **Nie Bildschirmfotos echter Aufnahmen** ins Repository legen: Sie zeigen Referenten und Teilnehmer.

## Installation

`scripts/install.sh` lässt sich ohne Zoom auf jedem Rechner mit Docker prüfen, isoliert von einer vorhandenen Installation:

```bash
git clone https://github.com/PBaumfalk/ZoomVCR.git /tmp/zoomvcr-test && cd /tmp/zoomvcr-test
COMPOSE_PROJECT_NAME=zoomvcr-test scripts/install.sh --lokal --port 8090   # erster Lauf
COMPOSE_PROJECT_NAME=zoomvcr-test scripts/install.sh                        # zweiter Lauf: .env bleibt, alles läuft
COMPOSE_PROJECT_NAME=zoomvcr-test docker compose down -v                    # Testumgebung samt Daten entfernen
```

## Was nur echt getestet werden kann

Beitritt, Warteraum, Tonwächter und Namensprüfung hängen an der echten Zoom-Oberfläche. Nach Zoom-Updates eine kurze Aufnahme eines eigenen Testmeetings machen, dabei die Zoom-Aufnahme starten (das löst den Hinweis aus, an dem der Ton früher abriss) und prüfen, ob der Ton durchgehend ankommt.
