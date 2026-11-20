#!/bin/bash
set -euo pipefail
umask 077
mkdir -p "$HOME/.vnc" "$XDG_RUNTIME_DIR" "$HOME/.config" /data/recordings
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb "$DISPLAY" -screen 0 "${ZOOMVCR_DESKTOP_WIDTH:-1920}x${ZOOMVCR_DESKTOP_HEIGHT:-1080}x24" -nolisten tcp -noreset >"$HOME/xvfb.log" 2>&1 &
for i in $(seq 1 30); do test -S /tmp/.X11-unix/X99 && break; sleep 0.25; done
test -S /tmp/.X11-unix/X99 || { echo 'Xvfb failed'; exit 1; }
# Right-click menu for the private VNC session: Zoom runs only for recordings, sign-in is started by hand.
mkdir -p "$HOME/.fluxbox"
cat >"$HOME/.fluxbox/menu" <<'MENU'
[begin] (ZoomVCR)
  [exec] (Zoom starten) {zoom}
  [exec] (Firefox) {firefox}
  [separator]
  [restart] (Fenster neu laden)
[end]
MENU
fluxbox >"$HOME/fluxbox.log" 2>&1 &
pulseaudio --start --exit-idle-time=-1
for i in $(seq 1 20); do pactl info >/dev/null 2>&1 && break; sleep 0.25; done
pactl load-module module-null-sink sink_name=ZoomVCR sink_properties=device.description=ZoomVCR >/dev/null
pactl load-module module-null-sink sink_name=SilentMicrophone sink_properties=device.description=SilentMicrophone >/dev/null
pactl set-default-sink ZoomVCR
pactl set-default-source SilentMicrophone.monitor
pactl set-source-mute SilentMicrophone.monitor 1
# Browser sign-in: http(s) opens Firefox, the zoommtg:// result link goes back to the Zoom client.
xdg-mime default firefox.desktop x-scheme-handler/http x-scheme-handler/https text/html 2>/dev/null || true
ZOOM_DESKTOP=$(ls /usr/share/applications/ | grep -i -m1 '^zoom.*\.desktop$' || true)
[ -n "$ZOOM_DESKTOP" ] && xdg-mime default "$ZOOM_DESKTOP" x-scheme-handler/zoommtg x-scheme-handler/zoomus 2>/dev/null || true
# Zoom is NOT started here: the agent starts it for each recording and ends it afterwards (an idle client
# costs about one CPU core). For the one-time sign-in use the VNC right-click menu "Zoom starten".
# The VNC socket is only mapped to 127.0.0.1 of the Docker host.
if [ -n "${ZOOMVCR_VNC_PASSWORD:-}" ]; then
    x11vnc -storepasswd "$ZOOMVCR_VNC_PASSWORD" "$HOME/.vnc/passwd" >/dev/null 2>&1
    x11vnc -display "$DISPLAY" -forever -shared -xkb -rfbauth "$HOME/.vnc/passwd" -rfbport 5900 -quiet >"$HOME/vnc.log" 2>&1 &
fi
cd /app
exec /opt/agent/bin/uvicorn desktop_agent:app --host 0.0.0.0 --port 8765
