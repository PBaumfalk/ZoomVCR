# ZoomVCR — Testprotokoll 2026-11-07

Testumgebung: bereitgestellter Python-/Node-/FFmpeg-Container ohne Docker Engine, ohne Zoom-Konto und ohne externen Docker-Server. Kein Live-Zoom-Zugriff.

| Test | Ergebnis | Aussagekraft |
|---|---|---|
| `PYTHONPATH=backend pytest -q backend/tests` | **26 bestanden** | Validierung der Permissions, Zoom-Links, FFmpeg-Quellen, Compose-Struktur, 80-Zeichen-Anzeigenamen, SQL-Migration, Namensänderung vor dem Start, Weitergabe des Namens an den Agenten, konservative OCR-Selbstprüfung und blockierter Aufnahme bei ungeprüftem Namen |
| `python -m compileall -q backend/zoomvcr` | **Bestanden** | Python-Syntax |
| `bash -n desktop/start.sh` | **Bestanden** | Shell-Syntax |
| FFmpeg, synthetisch 9 Sekunden | **Bestanden** | Tatsächliches H.264-MP4 + AAC-Ton, drei unterschiedliche Präsentationsbilder durch OpenCV und Tesseract erkannt |
| FFmpeg-Remux 3 Stunden aus wiederholtem kurzen Testsignal | **Bestanden** | `ffprobe` meldet `10800.082813` Sekunden, Dateigröße 226.594.037 Byte. Prüft long-duration MP4-Verpackung, nicht Zoom-3h-Livecapture oder 3h-ASR. |
| TypeScript JSX-Parsing mit globalem `tsc` | **Keine JSX-Syntaxfehler** | Typecheck / Next-Build wegen fehlender npm-Module nicht vollständig möglich. |
| Zoom-Teilnehmernamen (GUI-Eingabe und API bis Zoom-Agent) | **26 lokale Python-Tests bestanden** | Anforderung, Persistenz, spätere Bearbeitung, URI-Parameter, separate Bestätigung und fail-closed-Verhalten getestet; kein Nachweis einer echten Namensänderung in der Zoom-Linux-GUI |
| Docker Compose boot | **Nicht ausführbar** | Docker Engine in dieser Umgebung nicht vorhanden |
| Zoom-Client in Ubuntu 24.04 Docker | **Nicht ausführbar** | Download und Test der proprietären Zoom-Linux-Binärdatei benötigen Netzwerkzugang und Docker auf Zielserver |
| VNC-/Xvfb-/PulseAudio-Videoaufnahme | **Nicht ausführbar** | Zielserver-GUI benötigt |
| Echte Zoom-Meeting-Teilnahme + UI-Status + 180-Minuten-Stabilität | **Nicht getestet** | Erfordert Testmeeting und Login sowie Zeit für Live-Test |
| Next.js production build | **Nicht ausführbar** | Paketinstallation von npm in dieser Offline-Umgebung nicht möglich |

Für die neuen Namen-Funktionen wurden die TypeScript-TSX-Syntax geparst, ohne Next.js-Abhängigkeitsinstallation. Die eigentliche GUI-Namensänderung und die offizielle Zoom-Join-Preview sind wegen fehlendem Zoom-Client nicht live verifiziert. Eine `uname`-URL-Übergabe kann insbesondere bei eingeloggten Konten ignoriert werden. In solchen Fällen verlangt ZoomVCR eine manuelle Namensprüfung, bevor die Aufnahme startet.

Alle nicht durchgeführten Tests müssen vor produktiver Nutzung nachgeholt werden. Der Aufnahmewatchdog und die optische Zoom-Statusdetektion sind implementiert, aber noch nicht in einer realen GUI-Sitzung validiert.

## v3 – Benutzerverwaltung (07.11.2026)

- 31 lokale Python-Tests bestanden (`PYTHONPATH=backend pytest -q backend/tests`).
- Abgedeckt: Bootstrap-Admin, Argon2id, lokale Anmeldung, Cookie/JWT-Sessions,
  Logout, Passwortwechsel, erzwungene Sitzungsinvalidierung bei Sperre/Reset/Rollenwechsel,
  Admin/Recorder/Viewer-RBAC, TOTP-Aktivierung und Wiederverwendungsschutz,
  OIDC-Zuordnung nur bei vorab genehmigtem Konto mit verifizierter E-Mail (mockierter Provider).
- Die bisherigen Zoom-/Medien-Python-Tests bleiben grün.
- Nicht validiert: tatsächliche authentik Authorization-Code-/PKCE-Integration,
  echte TLS-/Proxy-Umgebung, Next.js-Produktionsbuild (fehlende Abhängigkeiten),
  PostgreSQL-Docker-Deployment und reale Zoom-Aufnahme.
