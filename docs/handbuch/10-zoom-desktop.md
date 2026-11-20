# 10 – Der Zoom-Desktop

Der Container `desktop` ist ein kleiner Linux-Desktop ohne Bildschirm: Ubuntu 24.04 mit dem offiziellen Zoom-Client, Xvfb als virtuellem Bildschirm, Fluxbox als Fenstermanager, PulseAudio mit einem virtuellen Lautsprecher und einem stummen Mikrofon. Ein kleiner Agent (Port 8765, nur intern) startet Zoom, tritt bei, prüft Namen und Ton und verlässt das Meeting wieder.

## Zoom einmalig anmelden

Der Rekorder braucht ein angemeldetes Zoom-Konto. Die Anmeldung bleibt im Volume `zoom_profile` erhalten, auch über Updates.

1. Auf dem eigenen Rechner einen SSH-Tunnel öffnen:

   ```bash
   ssh -N -L 5901:127.0.0.1:5900 admin@SERVER
   ```

2. Mit einem VNC-Viewer `localhost:5901` öffnen. Das Kennwort ist `ZOOMVCR_VNC_PASSWORD` aus `.env` (dort nachsehen, nicht weitergeben).
3. **Rechtsklick auf den Desktop → Zoom starten.**
4. In Zoom anmelden. Bei „Mit Google/SSO anmelden“ öffnet sich Firefox im selben Desktop; danach springt die Anmeldung zurück in Zoom.
5. In den Zoom-Einstellungen Kamera und Mikrofon beim Beitritt ausschalten und „Mit Computeraudio verbinden“ automatisch zulassen.
6. Zoom wieder schließen. Für Aufnahmen startet der Agent Zoom selbst.

Die Sicherheit hängt am SSH-Tunnel; VNC allein ist kein ausreichender Schutz. Port 5900 nie ins Netz freigeben.

Ist Zoom später abgemeldet, scheitert der nächste Beitritt, und eine Mail weist darauf hin. Dann diesen Ablauf wiederholen.

## Zoom bei Bedarf

Zoom läuft **nur während einer Aufnahme**:

- Vor dem Beitritt startet der Agent den Client, wartet, bis er bereit ist, und übergibt den Link (`zoommtg://…`).
- Nach der Aufnahme beendet er Zoom und ein ggf. offenes Firefox.

Für die Anmeldung gibt es im Rechtsklickmenü **Zoom starten** und **Firefox**.

## Was der Agent tut

| Aufgabe | Wie |
| --- | --- |
| Beitreten | Wandelt den geprüften `https://…zoom.us/j/…`-Link in `zoommtg://zoom.us/join?…` um. Nur offizielle Zoom-Adressen. |
| Zustand erkennen | Texterkennung auf dem Bildschirm: Warteraum, Meeting läuft, Kennwortabfrage, Fehler. Bei Zweifel wartet er auf eine Bestätigung ([Kapitel 4](04-waehrend-der-aufnahme.md)). |
| Namen prüfen | Liest die eigene Zeile der Teilnehmerliste und benennt bei Bedarf vorsichtig um. |
| Ton halten | Der Tonwächter: Stream „ZOOM VoiceEngine“ in PulseAudio vorhanden? Wenn nicht, Hinweise bestätigen und Computeraudio verbinden. |
| Aufnehmen | ffmpeg nimmt den virtuellen Bildschirm und den Ton des virtuellen Lautsprechers auf. |

## Ressourcen

Ohne Grafikkarte zeichnet Zoom seine Oberfläche per Software (Mesa llvmpipe). Unbegrenzt belegte das im Leerlauf rund drei Kerne. Deshalb setzt `compose.yml` `LP_NUM_THREADS=1` und `QSG_RENDER_LOOP=basic`. `QT_QUICK_BACKEND=software` funktioniert nicht (schwarzes Fenster).

Gemessen auf einem Server mit 4 vCPU: im Leerlauf (Zoom beendet) etwa 0,4 % CPU, während einer Aufnahme in 720p mit 15 Bildern pro Sekunde ein bis zwei Kerne. Auflösung und Bildrate stellen `ZOOMVCR_DESKTOP_WIDTH`, `_HEIGHT` und `_FPS` ein ([Kapitel 11](11-konfiguration.md)).
