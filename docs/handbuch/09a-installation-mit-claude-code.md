# 9a – Installation mit Claude Code

Mit [Claude Code](https://code.claude.com/docs/en/setup), dem Kommandozeilen-Assistenten von Anthropic, lässt sich ZoomVCR installieren, ohne jeden Befehl selbst einzutippen. Claude prüft den Rechner, fragt nach der gewünschten Adresse, führt das mitgelieferte Installationsskript aus, kontrolliert den Start mit einer Testaufnahme und nennt Ihnen am Ende Adresse und erste Anmeldung. Die Befehle dahinter stehen [unten](#was-claude-dabei-ausführt); Sie können sie jederzeit auch selbst ausführen ([Kapitel 9](09-installation.md)).

## Was Sie vorab bereitstellen

| Was | Wozu | Woher |
| --- | --- | --- |
| **Rechner oder Server** mit Docker Engine und Docker Compose v2 | ZoomVCR läuft in Containern | Server: Linux x86-64, 4 vCPU, 8 GB RAM ([Kapitel 9](09-installation.md#voraussetzungen)). Für einen Probelauf genügt ein Mac oder Linux-PC mit Docker Desktop. |
| **git** | Repository holen | Linux: Paket `git`; Mac: `xcode-select --install` |
| **Claude Code** | Der Assistent | Installation laut [offizieller Anleitung](https://code.claude.com/docs/en/setup), siehe nächster Abschnitt. Nötig ist ein Claude-Abo (Pro, Max, Team oder Enterprise) oder ein Konto in der Claude Console; das kostenlose Abo enthält Claude Code nicht. |
| Für einen Server: **DNS-Namen** wie `vcr.kanzlei.example` | Adresse im Browser | Ihr DNS. Für automatisches HTTPS müssen die Ports 80 und 443 von außen erreichbar sein; sonst einen vorhandenen Reverse Proxy nutzen. |
| Für echte Zoom-Aufnahmen: **Zoom-Konto** des Rekorders | Der Rekorder tritt damit bei | Wird nach der Installation per VNC angemeldet ([Kapitel 10](10-zoom-desktop.md)); das macht ein Mensch, nicht Claude. |

Optional, später in der Oberfläche: API-Key eines KI-Dienstes ([Kapitel 7](07-ki-und-benachrichtigung.md)), Mailpostfach ([Kapitel 11](11-konfiguration.md#mail)), authentik ([Kapitel 12](12-anmeldung-oidc.md)).

## Claude Code einrichten

Nach der [offiziellen Anleitung von Anthropic](https://code.claude.com/docs/en/setup) (Stand November 2026), im Terminal des Rechners, auf dem ZoomVCR laufen soll:

```bash
# macOS, Linux, WSL
curl -fsSL https://claude.ai/install.sh | bash
# alternativ auf dem Mac: brew install --cask claude-code

claude --version     # zeigt die installierte Version
claude doctor        # prüft Installation und Einstellungen
```

Unter Windows (PowerShell): `irm https://claude.ai/install.ps1 | iex`. ZoomVCR selbst läuft unter Windows nur in Docker Desktop als Probelauf.

Beim ersten Aufruf von `claude` öffnet sich die Anmeldung im Browser. Auf einem Server ohne Browser zeigt Claude Code einen Link, den Sie auf Ihrem eigenen Rechner öffnen.

## Repository holen und Claude Code öffnen

Claude Code wird **im ZoomVCR-Ordner** geöffnet, also dort, wo `compose.yml` und `scripts/install.sh` liegen. Auf einem Server bietet sich z. B. `/opt` als übergeordneter Ordner an.

```bash
cd /opt                                           # Probelauf: ein beliebiger Ordner
git clone https://github.com/PBaumfalk/ZoomVCR.git zoomvcr
cd zoomvcr
claude
```

## Der Installationsprompt

Kopieren Sie den folgenden Text **unverändert** in Claude Code und drücken Sie Enter. Claude fragt nach, was nur Sie entscheiden können (Probelauf oder Server, Adresse, Zoom ja oder nein), und bittet vor Befehlen um Freigabe, sofern Sie das nicht anders eingestellt haben.

```text
Installiere ZoomVCR aus diesem Ordner, starte es und weise nach, dass es funktioniert.
Grundlage sind docs/handbuch/09-installation.md und docs/handbuch/09a-installation-mit-claude-code.md.

1. Umgebung prüfen und kurz berichten: Ist dies der ZoomVCR-Checkout (compose.yml und
   scripts/install.sh vorhanden)? Sind docker, "docker compose" (v2) und curl da, läuft der
   Docker-Dienst, welche Architektur hat er (docker info), wie viel freier Speicher ist da,
   sind die vorgesehenen Ports frei? Gibt es schon eine .env?
2. Bevor du etwas änderst, frag mich, welche Installation ich möchte:
   (a) Probelauf auf diesem Rechner, (b) Server mit eigener Domain und automatischem HTTPS,
   (c) Server hinter einem vorhandenen Reverse Proxy.
   Bei (b) und (c) frag nach der Adresse und ob echte Zoom-Aufnahmen gewünscht sind
   (nur auf x86-64 möglich). Bei (c) richte compose.override.yml nach
   deploy/docker-compose.override.yml ein und frag nach dem Namen des Proxy-Netzes.
3. Führe scripts/install.sh mit den passenden Optionen aus:
   (a) --lokal (bei belegtem Port 8080: --port 8081 usw.), (b) --domain NAME,
   (c) --origin https://NAME, jeweils plus --zoom, wenn Zoom gewünscht ist.
   Eine vorhandene .env bleibt erhalten; das Skript ersetzt nur Platzhalter.
4. Gib niemals Inhalte der .env aus, auch keine einzelnen Werte, und schreibe keine
   Geheimnisse in den Chat. Lösche nichts: kein "docker compose down -v", keine Volumes,
   keine vorhandenen Dateien.
5. Prüfe den Erfolg selbst:
   - docker compose ps: alle Dienste "running", api "healthy"
   - die Adresse aus ZOOMVCR_PUBLIC_ORIGIN liefert unter /health {"status":"ok"}
     und unter / die Anmeldeseite (bei (b) und (c) nur, wenn sie von hier erreichbar ist)
   - ./zoomvcr status antwortet
   - plane mit ./zoomvcr schedule eine Testaufnahme (--source synthetic, Titel
     "Installationstest", --at jetzt als ISO-Zeit mit Zeitzone, --minutes 1); sie
     startet von selbst. Warte, bis ./zoomvcr recordings für sie den Status "ready"
     zeigt (höchstens etwa zwei Minuten), und prüfe, dass drei Folien erkannt wurden.
6. Scheitert ein Schritt, such die Ursache in der Ausgabe und mit docker compose logs,
   behebe sie, soweit das im Rahmen dieser Anleitung möglich ist, und wiederhole den
   Schritt. Wenn du etwas nicht ohne meine Entscheidung lösen kannst, frag mich.
7. Zum Schluss nenne mir knapp:
   - die Adresse, unter der ZoomVCR erreichbar ist,
   - den Benutzernamen für die erste Anmeldung und dass das Passwort in .env unter
     ZOOMVCR_ADMIN_PASSWORD steht (nicht das Passwort selbst),
   - das Ergebnis der Prüfungen aus Schritt 5,
   - die nächsten Schritte aus Kapitel 9 „Erste Anmeldung“ und, falls Zoom aktiviert
     ist, die Zoom-Anmeldung per VNC aus Kapitel 10.
```

## Woran Sie den Erfolg erkennen

Claude meldet am Ende etwa:

```text
ZoomVCR läuft unter http://localhost:8080.
- docker compose ps: postgres, redis, api (healthy), scheduler, capture, processor, web, proxy laufen
- /health: {"status":"ok"} · Anmeldeseite lädt · ./zoomvcr status antwortet
- Testaufnahme "Installationstest": ready, 59 s Video, 3 Folien erkannt
Erste Anmeldung: Benutzer "admin", Passwort in .env unter ZOOMVCR_ADMIN_PASSWORD.
Nächste Schritte: Kapitel 9 „Erste Anmeldung“ …
```

Öffnen Sie die genannte Adresse im Browser und melden Sie sich an ([Kapitel 2](02-erste-schritte.md#anmelden)). Das Passwort lesen Sie selbst am Bildschirm aus:

```bash
grep ^ZOOMVCR_ADMIN_PASSWORD= .env
```

Die Testaufnahme „Installationstest“ steht in der Mediathek; Sie können sie ansehen und danach löschen ([Kapitel 5](05-mediathek-und-auswertung.md#löschen)).

## Was Claude dabei ausführt

Dieselben Schritte von Hand, z. B. für einen Probelauf auf Port 8080:

```bash
docker compose version && docker info --format '{{.Architecture}}'   # Voraussetzungen
scripts/install.sh --lokal --port 8080                              # .env anlegen, bauen, starten, prüfen
docker compose ps                                                   # alle Dienste laufen
curl -fsS http://localhost:8080/health                              # {"status":"ok"}
./zoomvcr status                                                    # Kommandozeile erreicht die API
./zoomvcr schedule --title Installationstest --source synthetic \
  --at "$(date +%Y-%m-%dT%H:%M:%S%z | sed 's/\(..\)$/:\1/')" --minutes 1   # startet sofort von selbst
./zoomvcr recordings                                                # nach etwa einer Minute: "status": "ready"
```

Für einen Server statt `--lokal` die Option `--domain vcr.kanzlei.example` (mitgelieferter Caddy mit automatischem HTTPS) oder `--origin https://vcr.kanzlei.example` (vorhandener Reverse Proxy) verwenden, für echte Zoom-Aufnahmen zusätzlich `--zoom`. Was das Skript im Einzelnen tut: [Kapitel 9](09-installation.md#das-installationsskript).

## Wenn etwas nicht klappt

| Meldung | Ursache und Abhilfe |
| --- | --- |
| `Docker läuft nicht oder dieser Benutzer darf Docker nicht verwenden` | Docker Desktop starten bzw. unter Linux `sudo usermod -aG docker $USER` und neu anmelden. |
| `Port 8080 ist auf diesem Rechner schon belegt.` | Ein anderer Dienst nutzt den Port. Claude wiederholt mit `--port 8081`. |
| `Echte Zoom-Aufnahmen brauchen einen x86-64-Server` | Der Zoom-Linux-Client existiert nur für x86-64. Ohne `--zoom` installieren; Testaufnahmen funktionieren trotzdem. |
| `ZOOMVCR_PUBLIC_ORIGIN steht noch auf der Beispieladresse` | Es gibt eine `.env` aus einer früheren Handinstallation ohne echte Adresse. Skript mit `--lokal`, `--domain` oder `--origin` erneut starten. |
| Server-Adresse „von hier (noch) nicht erreichbar“ | DNS-Eintrag fehlt, Firewall sperrt 80/443 oder das Zertifikat wird noch ausgestellt. `docker compose logs proxy` zeigt den Grund. |

Claude Code arbeitet nur in diesem Ordner und mit Ihrer Freigabe. Zugangsdaten für Zoom, den Kanzlei-Login, Mail oder den KI-Dienst geben Sie selbst in der Oberfläche bzw. in `.env` ein, nicht im Chat.
