# Änderungen

Alle nennenswerten Änderungen an ZoomVCR. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [Semantic Versioning](https://semver.org/lang/de/). Fehlende Tabellen und Spalten legt die API beim Start selbst an.

## [Unveröffentlicht]

### Neu
- **Veröffentlichung unter MIT-Lizenz**; README und Handbuch beschreiben ZoomVCR als Produkt für beliebige Kanzleien, ohne Bezug auf eine bestimmte Installation.
- **`scripts/install.sh`**: prüft Voraussetzungen und freie Ports, legt `.env` mit Zufallswerten an (eine vorhandene bleibt erhalten, Geheimnisse werden nie angezeigt), baut, startet und prüft `/health`, Dienste und Anmeldeseite. `--lokal` für einen Probelauf auf dem eigenen Rechner (auch Mac/arm64, ohne Zoom), `--domain` bzw. `--origin` für Server, `--zoom` für echte Aufnahmen. Wiederholbar, dient auch für Updates.
- **Handbuch**: Kapitel 9a „Installation mit Claude Code“ mit Installationsprompt, Anhang „Funktionsliste“, erster Ablauf mit einer Testaufnahme (Kapitel 2), Beispiel zum Planen (Kapitel 3), „Ergebnis prüfen und weiterverwenden“ mit dem Datenfluss der KI (Kapitel 5), Wiederherstellung und Betrieb hinter vorhandenem Reverse Proxy (Kapitel 13), Wegweiser nach Zielgruppen.
- `ZOOMVCR_HTTP_PORT`/`ZOOMVCR_HTTPS_PORT` für den mitgelieferten Caddy, `ZOOMVCR_LOCAL_ASR` für das Image mit lokalem Whisper (bleibt über Updates erhalten).

### Geändert
- Standardname in Zoom ist „Kanzlei – Aufzeichnung“; OIDC ist nicht mehr auf authentik zugeschnitten (Bezeichnung „Kanzlei-Login (OIDC)“).
- Hinweis zur Mail-Einrichtung in der Oberfläche nennt die `.env`-Variablen statt eines kanzleieigenen Skripts.

### Behoben
- `ZOOMVCR_PUBLIC_ORIGIN=http://localhost` (ohne Port) und Adressen mit Standardport (`:80`, `:443`) führten zu „Invalid request origin“ bzw. ließen die API nicht starten; Adressen werden jetzt wie im Browser verglichen.
- Hinweise der Verarbeitung nannten noch den alten Menüpunkt „KI-Anbindung“.

## [1.0.0] – 2026-11-15

Erste Fassung im Repository. Sie entspricht dem Stand, der seit dem 09.11.2026 produktiv im Einsatz ist.

### Neu
- **Handbuch** in 16 Kapiteln nach Zielgruppen (Anwender, Administration, IT) mit Schnelleinstieg und 17 Bildschirmfotos aus einer Beispielinstanz (`docs/handbuch/`).
- `npm run docs:check` prüft Links und Anker in README und Handbuch, `npm run docs:screenshots` erzeugt die Bildschirmfotos neu.
- **CI** in GitHub Actions: Backend-Tests im Backend-Image, Typprüfung und Produktionsbuild der Oberfläche, Bau des Desktop-Images, Prüfung des Handbuchs. Dependabot für Actions, pip, npm und Docker.

### Geändert
- Oberfläche: `package-lock.json` eingecheckt, das Image baut mit `npm ci` reproduzierbar; `.dockerignore` für Oberfläche und Backend.
- Hinweis ohne KI-Auswertung verweist auf „KI und Benachrichtigung“ statt auf die alte Bezeichnung „KI-Anbindung“.

## Vorgeschichte (vor dem Repository)

### 09.11.2026
- **Neue Oberfläche** in der Machart von Filum und Tessera: eigene Seitenleiste, Übersicht mit „Läuft gerade“, Mediathek mit Suche und Filtern, Detailansicht mit Video, Folien, Auswertung und Transkript, hell und dunkel, Smartphone.
- **KI-Auswertung lesbar** statt Roh-JSON, Zeitstempel springen ins Video.
- **Automatischer Schnitt** von stillem Anfang, stillem Ende und Pausen über zwei Minuten; Original bleibt erhalten.
- **Mail-Warnung** bei gescheitertem Beitritt, fehlendem Ton, gescheiterter Verarbeitung und fast stummer Aufnahme.
- **Zoom nur bei Bedarf**: Der Client startet zur Aufnahme und wird danach beendet.

### 08.11.2026
- **Tonwächter**: prüft laufend den Zoom-Tonstream und verbindet Computeraudio neu, nachdem an zwei Tagen stundenlang der Ton fehlte.

### 07.11.2026
- **KI-Anbindung** in der Oberfläche: Key verschlüsselt in der Datenbank, Transkription und Auswertung über einen OpenAI-kompatiblen Dienst, lokales Whisper optional.
- Erste produktive Inbetriebnahme hinter einem zentralen Reverse Proxy, 720p, Beitritt fünf Minuten vorher, 15 Minuten Nachlauf, Löschfunktion.

### Version 3 (Alpha)
- Benutzerkonten mit Rollen, TOTP, Anmeldung über OIDC, Auditprotokoll.
