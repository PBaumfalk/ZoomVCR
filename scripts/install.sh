#!/usr/bin/env bash
# ZoomVCR installieren, starten und prüfen.
#
#   scripts/install.sh --lokal [--port 8080]      Probelauf auf diesem Rechner (http://localhost:8080)
#   scripts/install.sh --domain vcr.example.com    Server mit dem mitgelieferten Caddy (automatisches HTTPS)
#   scripts/install.sh --origin https://vcr.example.com
#                                                  Server hinter einem vorhandenen Reverse Proxy
#   scripts/install.sh [--zoom]                    erneut ausführen: bauen, starten, prüfen (auch nach Updates)
#
# Wiederholbar: Eine vorhandene .env bleibt erhalten. Das Skript ersetzt dort nur Platzhalter
# (CHANGE_…) durch Zufallswerte und ändert Adresse/Ports nur, wenn --lokal, --domain oder --origin
# angegeben ist. Geheimnisse werden nie ausgegeben. Datenbank und Aufnahmen (Docker-Volumes) bleiben unberührt.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
ENV_FILE="$ROOT/.env"

MODE=""; PORT=8080; DOMAIN=""; ORIGIN=""; ZOOM=0; WAIT=300

say()  { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nFEHLER: %s\n' "$1" >&2; [ $# -gt 1 ] && printf '%s\n' "${@:2}" >&2; exit 1; }

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --lokal|--local) MODE=lokal ;;
    --port)   [ $# -ge 2 ] || usage 1; PORT="$2"; shift ;;
    --domain) [ $# -ge 2 ] || usage 1; MODE=domain; DOMAIN="$2"; shift ;;
    --origin) [ $# -ge 2 ] || usage 1; MODE=origin; ORIGIN="${2%/}"; shift ;;
    --zoom)   ZOOM=1 ;;
    --wait)   [ $# -ge 2 ] || usage 1; WAIT="$2"; shift ;;
    -h|--help) usage 0 ;;
    *) say "Unbekannte Option: $1"; usage 1 ;;
  esac
  shift
done

case "$PORT" in ''|*[!0-9]*) fail "--port erwartet eine Zahl, z. B. --port 8080." ;; esac

# ---------------------------------------------------------------- Voraussetzungen
step "Voraussetzungen prüfen"
command -v docker >/dev/null 2>&1 || fail "Docker ist nicht installiert." \
  "Linux: https://docs.docker.com/engine/install/  ·  Mac/Windows: Docker Desktop."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 fehlt (Befehl 'docker compose')." \
  "Unter Linux das Paket docker-compose-plugin installieren."
docker info >/dev/null 2>&1 || fail "Docker läuft nicht oder dieser Benutzer darf Docker nicht verwenden." \
  "Docker starten bzw. Benutzer in die Gruppe 'docker' aufnehmen (danach neu anmelden)."
command -v curl >/dev/null 2>&1 || fail "curl fehlt (wird für die Erfolgskontrolle gebraucht)."
ARCH=$(docker info --format '{{.Architecture}}' 2>/dev/null || uname -m)
say "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null), Compose $(docker compose version --short 2>/dev/null), Architektur $ARCH"
[ -f "$ROOT/compose.yml" ] && [ -f "$ROOT/.env.example" ] || fail "compose.yml oder .env.example fehlt. Bitte im ZoomVCR-Ordner ausführen."

# ---------------------------------------------------------------- .env
env_get() { # Wert einer Variable aus .env (ohne Ausgabe ins Terminal verwenden)
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}
env_set() { # setzt KEY=VALUE, ersetzt eine vorhandene Zeile oder hängt an; Dateirechte bleiben erhalten
  local key="$1" value="$2" tmp
  tmp=$(mktemp "$ROOT/.env.tmp.XXXXXX")
  awk -v k="$key" -v v="$value" 'BEGIN{done=0} $0 ~ "^"k"=" {print k"="v; done=1; next} {print} END{if(!done) print k"="v}' \
    "$ENV_FILE" > "$tmp"
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}
random_secret() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 48 || true; }

step "Konfiguration (.env)"
CREATED=0
if [ ! -f "$ENV_FILE" ]; then
  [ -n "$MODE" ] || fail "Noch keine .env vorhanden. Bitte angeben, wie ZoomVCR erreichbar sein soll:" \
    "  scripts/install.sh --lokal                      Probelauf auf diesem Rechner" \
    "  scripts/install.sh --domain vcr.example.com     Server mit automatischem HTTPS" \
    "  scripts/install.sh --origin https://vcr.example.com   hinter vorhandenem Reverse Proxy"
  ( umask 077; cp "$ROOT/.env.example" "$ENV_FILE" )
  CREATED=1
  say ".env aus .env.example angelegt (nur für den Besitzer lesbar)."
else
  say ".env vorhanden – bleibt erhalten, nur Platzhalter werden ersetzt."
fi
chmod 600 "$ENV_FILE"

for key in ZOOMVCR_SECRET_KEY ZOOMVCR_API_TOKEN POSTGRES_PASSWORD ZOOMVCR_VNC_PASSWORD ZOOMVCR_ADMIN_PASSWORD; do
  current=$(env_get "$key")
  # ZOOMVCR_ADMIN_PASSWORD nach der Ersteinrichtung bewusst entfernt? Dann nicht wieder anlegen.
  if [ "$key" = ZOOMVCR_ADMIN_PASSWORD ] && [ $CREATED -eq 0 ] && ! grep -q "^$key=" "$ENV_FILE"; then continue; fi
  case "$current" in
    ''|CHANGE_*)
      secret=$(random_secret)
      [ ${#secret} -ge 40 ] || fail "Konnte keinen Zufallswert erzeugen (/dev/urandom)."
      env_set "$key" "$secret"; say "  $key: Zufallswert erzeugt" ;;
    *) say "  $key: vorhanden, unverändert" ;;
  esac
done
unset secret current

case "$MODE" in
  lokal)
    env_set ZOOMVCR_PUBLIC_ORIGIN "http://localhost:$PORT"
    env_set ZOOMVCR_SITE ":80"
    env_set ZOOMVCR_HTTP_PORT "$PORT"
    env_set ZOOMVCR_HTTPS_PORT "$((PORT + 363))"
    say "  Adresse: http://localhost:$PORT (nur HTTP, nur für einen Probelauf auf diesem Rechner)" ;;
  domain)
    case "$DOMAIN" in ''|*/*|*:*) fail "--domain erwartet nur den Namen, z. B. --domain vcr.example.com" ;; esac
    env_set ZOOMVCR_PUBLIC_ORIGIN "https://$DOMAIN"
    env_set ZOOMVCR_SITE "$DOMAIN"
    env_set ZOOMVCR_HTTP_PORT 80
    env_set ZOOMVCR_HTTPS_PORT 443
    say "  Adresse: https://$DOMAIN (Caddy holt das Zertifikat; DNS und Ports 80/443 müssen erreichbar sein)" ;;
  origin)
    case "$ORIGIN" in https://?*) ;; *) fail "--origin erwartet eine HTTPS-Adresse, z. B. https://vcr.example.com" ;; esac
    env_set ZOOMVCR_PUBLIC_ORIGIN "$ORIGIN"
    say "  Adresse: $ORIGIN (HTTPS übernimmt der vorhandene Reverse Proxy, siehe deploy/docker-compose.override.yml)" ;;
esac

if [ $ZOOM -eq 1 ]; then env_set ZOOMVCR_ENABLE_DESKTOP true; say "  ZOOMVCR_ENABLE_DESKTOP=true (echte Zoom-Aufnahmen)"; fi

ORIGIN_NOW=$(env_get ZOOMVCR_PUBLIC_ORIGIN)
case "$ORIGIN_NOW" in
  *example.com*) fail "ZOOMVCR_PUBLIC_ORIGIN steht noch auf der Beispieladresse ($ORIGIN_NOW)." \
    "Mit --lokal, --domain oder --origin die echte Adresse setzen." ;;
esac

PROFILE_ARGS=()
if [ "$(env_get ZOOMVCR_ENABLE_DESKTOP)" = true ]; then
  case "$ARCH" in
    x86_64|amd64) PROFILE_ARGS=(--profile zoom) ;;
    *) fail "Echte Zoom-Aufnahmen brauchen einen x86-64-Server (Zoom-Linux-Client), hier: $ARCH." \
       "Ohne Zoom-Desktop: ZOOMVCR_ENABLE_DESKTOP=false in .env – dann sind Testaufnahmen möglich." ;;
  esac
fi

# ---------------------------------------------------------------- Ports
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }
if [ -z "$(docker compose ps -q --status running proxy 2>/dev/null)" ] && ! [ -f "$ROOT/compose.override.yml" ]; then
  for p in "$(env_get ZOOMVCR_HTTP_PORT)" "$(env_get ZOOMVCR_HTTPS_PORT)"; do
    p=${p:-80}
    if port_busy "$p"; then
      fail "Port $p ist auf diesem Rechner schon belegt." \
        "Probelauf: scripts/install.sh --lokal --port 8081 (oder ein anderer freier Port)." \
        "Server: den Dienst auf Port $p beenden oder ZoomVCR hinter den vorhandenen Proxy stellen (--origin)."
    fi
  done
fi

# ---------------------------------------------------------------- Starten
step "Konfiguration prüfen"
docker compose "${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"}" config --quiet || fail "docker compose config meldet einen Fehler (siehe oben)."
say "in Ordnung"

step "Images bauen und Dienste starten (beim ersten Mal mehrere Minuten)"
docker compose "${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"}" up -d --build --remove-orphans \
  || fail "docker compose up ist gescheitert (siehe oben)." "Häufig: Port belegt → mit --lokal --port 8081 erneut versuchen."

# ---------------------------------------------------------------- Erfolgskontrolle
step "Erfolgskontrolle"
deadline=$(( $(date +%s) + WAIT ))
until docker compose exec -T api curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    docker compose ps
    say ""; docker compose logs --tail=40 api >&2 || true
    fail "Die API meldet nach ${WAIT}s nicht 'ok'. Letzte Zeilen des API-Logs stehen oben."
  fi
  sleep 3
done
say "  API /health: ok (Datenbank und Warteschlange erreichbar)"

running=$(docker compose ps --services --status running)
for svc in postgres redis api scheduler capture processor web; do
  printf '%s\n' "$running" | grep -qx "$svc" || fail "Dienst '$svc' läuft nicht." "docker compose logs $svc"
done
say "  Dienste laufen: $(printf '%s ' $running)"

if printf '%s\n' "$running" | grep -qx proxy; then
  if [ "$MODE" = lokal ] || case "$ORIGIN_NOW" in http://localhost*|http://127.0.0.1*) true ;; *) false ;; esac; then
    base="$ORIGIN_NOW"
    deadline=$(( $(date +%s) + 60 ))
    until curl -fsS "$base/health" >/dev/null 2>&1 && curl -fsS -o /dev/null "$base/"; do
      [ "$(date +%s)" -ge "$deadline" ] && fail "$base antwortet nicht. docker compose logs proxy web"
      sleep 2
    done
    say "  $base/health und Anmeldeseite: erreichbar"
  else
    if curl -fsS --max-time 10 "$ORIGIN_NOW/health" >/dev/null 2>&1; then
      say "  $ORIGIN_NOW/health: erreichbar"
    else
      say "  Hinweis: $ORIGIN_NOW ist von hier (noch) nicht erreichbar. DNS, Firewall und Zertifikat prüfen:"
      say "           docker compose logs proxy"
    fi
  fi
else
  say "  Kein eigener Caddy aktiv (vorhandener Reverse Proxy). Prüfen Sie dort: $ORIGIN_NOW/health"
fi

if [ ${#PROFILE_ARGS[@]} -gt 0 ]; then
  if ./zoomvcr status >/dev/null 2>&1; then say "  ./zoomvcr status: ok"; fi
fi

# ---------------------------------------------------------------- Ergebnis
step "Fertig"
say "ZoomVCR läuft unter:  $ORIGIN_NOW"
if grep -q '^ZOOMVCR_ADMIN_PASSWORD=' "$ENV_FILE"; then
  say "Erste Anmeldung:      Benutzer '$(env_get ZOOMVCR_BOOTSTRAP_ADMIN_USERNAME)', Passwort in .env unter ZOOMVCR_ADMIN_PASSWORD"
  say "                      (anzeigen nur am eigenen Bildschirm: grep ^ZOOMVCR_ADMIN_PASSWORD= .env)"
fi
say "Status:               ./zoomvcr status   ·   docker compose ps"
say "Nächste Schritte:     Handbuch, Kapitel 9 „Erste Anmeldung“ (docs/handbuch/09-installation.md)"
[ ${#PROFILE_ARGS[@]} -eq 0 ] && say "Zoom-Desktop:         aus – Testaufnahmen funktionieren, echte Zoom-Aufnahmen mit --zoom (x86-64)."
exit 0
