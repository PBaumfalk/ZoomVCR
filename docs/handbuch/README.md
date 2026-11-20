# ZoomVCR – Handbuch

Willkommen im Handbuch von **ZoomVCR**, dem Rekorder für Zoom-Fortbildungen. Teil A richtet sich an alle, die Aufnahmen planen und ansehen; technische Vorkenntnisse sind nicht nötig. Teil B ist für Admins, Teil C für die IT, die ZoomVCR installiert und betreibt.

## Wo fange ich an?

| Sie sind … | Lesen Sie zuerst | Danach |
| --- | --- | --- |
| **neu im Team** | [Erste Schritte](02-erste-schritte.md): Anmelden, Oberfläche, [Ihr erster Ablauf mit einer Testaufnahme](02-erste-schritte.md#ihr-erster-ablauf-eine-testaufnahme) | [Was ist ZoomVCR?](01-was-ist-zoomvcr.md) |
| **ReFa, Sekretariat** – Sie planen Aufnahmen | [Aufnahme planen](03-aufnahme-planen.md) | [Während der Aufnahme](04-waehrend-der-aufnahme.md), [Fehler](05-mediathek-und-auswertung.md#fehler) |
| **Rechtsanwältin, Rechtsanwalt** – Sie arbeiten mit dem Ergebnis | [Mediathek und Auswertung](05-mediathek-und-auswertung.md), besonders [Ergebnis prüfen und weiterverwenden](05-mediathek-und-auswertung.md#ergebnis-prüfen-und-weiterverwenden) | [Datenschutz und Recht](08-datenschutz-und-recht.md) |
| **Admin** – Sie verwalten Konten und Dienste | [Benutzer und Rechte](06-benutzer-und-rechte.md) | [KI und Benachrichtigung](07-ki-und-benachrichtigung.md) |
| **IT** – Sie installieren und betreiben | [Installation](09-installation.md) oder [Installation mit Claude Code](09a-installation-mit-claude-code.md) | [Zoom-Desktop](10-zoom-desktop.md), [Betrieb](13-betrieb.md) |

Jede Funktion mit Rolle, Fundstelle und Kapitel: **[Funktionsliste](anhang-funktionsliste.md)**.

## Inhalt

**Teil A – Arbeiten mit ZoomVCR**

| Kapitel | Inhalt |
| --- | --- |
| [1 – Was ist ZoomVCR?](01-was-ist-zoomvcr.md) | Wofür, wie eine Aufnahme abläuft, Grundbegriffe |
| [2 – Erste Schritte](02-erste-schritte.md) | Anmelden, die Oberfläche, erster Ablauf mit einer Testaufnahme, hell und dunkel, Smartphone |
| [3 – Aufnahme planen](03-aufnahme-planen.md) | Zoom-Link, Uhrzeit, Name in Zoom, Berechtigung, Beispiel |
| [4 – Während der Aufnahme](04-waehrend-der-aufnahme.md) | Status, Tonwächter, Warteraum, Live-Bild, Stoppen |
| [5 – Mediathek und Auswertung](05-mediathek-und-auswertung.md) | Video, Schnitt, Folien, Transkript, KI-Auswertung, Ergebnis prüfen, Herunterladen, Löschen |

**Teil B – Administration**

| Kapitel | Inhalt |
| --- | --- |
| [6 – Benutzer und Rechte](06-benutzer-und-rechte.md) | Rollen, Konten, Zwei-Faktor, Auditprotokoll |
| [7 – KI und Benachrichtigung](07-ki-und-benachrichtigung.md) | KI-Dienst, Transkription, Auswertung, Mail-Warnung |
| [8 – Datenschutz und Recht](08-datenschutz-und-recht.md) | Was gespeichert wird, Berechtigung, Aufbewahrung |

**Teil C – Installation und Betrieb (IT)**

| Kapitel | Inhalt |
| --- | --- |
| [9 – Installation](09-installation.md) | Plattformen, Installationsskript, Handinstallation, erste Anmeldung |
| [9a – Installation mit Claude Code](09a-installation-mit-claude-code.md) | Vorbereitung, Installationsprompt, Erfolgskontrolle |
| [10 – Der Zoom-Desktop](10-zoom-desktop.md) | Zoom-Anmeldung über VNC, Zoom bei Bedarf, Ressourcen |
| [11 – Konfiguration](11-konfiguration.md) | Alle Umgebungsvariablen |
| [12 – Anmeldung über OIDC](12-anmeldung-oidc.md) | Kanzlei-Login über authentik, Keycloak & Co. |
| [13 – Betrieb](13-betrieb.md) | Kommandozeile, Updates, Sicherung, Wiederherstellung, Fehlerbilder |
| [14 – Architektur](14-architektur.md) | Dienste, Ablauf einer Aufnahme, Datenablage, API |
| [15 – Tests](15-tests.md) | Backend-Tests, CI, Bildschirmfotos |
| [16 – Bekannte Einschränkungen](16-einschraenkungen.md) | Was ZoomVCR bewusst nicht kann |
| [Anhang – Funktionsliste](anhang-funktionsliste.md) | Alle Funktionen mit Rolle, Fundstelle und Kapitel |

## Schnelleinstieg in 5 Minuten

1. ZoomVCR im Browser öffnen und **Mit Kanzlei-Login anmelden** ([Kapitel 2](02-erste-schritte.md)).
2. **Aufnahme planen**: Titel, Zoom-Einladungslink, Beginn und Dauer eintragen ([Kapitel 3](03-aufnahme-planen.md)).
3. Berechtigung wählen, den Haken „Die Aufzeichnung ist erlaubt …“ setzen, **Planen**.
4. Nichts weiter tun. Der Rekorder tritt fünf Minuten vor Beginn bei und nimmt bis 15 Minuten nach dem Ende auf ([Kapitel 4](04-waehrend-der-aufnahme.md)).
5. Nach der Verarbeitung liegt die Aufnahme in der **Mediathek**: geschnitten, mit Folien, Transkript und KI-Auswertung ([Kapitel 5](05-mediathek-und-auswertung.md)). Aussagen vor der Verwendung per Zeitstempel prüfen ([Kapitel 5](05-mediathek-und-auswertung.md#ergebnis-prüfen-und-weiterverwenden)).

Geht etwas schief (kein Beitritt, kein Ton, Verarbeitung gescheitert), kommt eine E-Mail ([Kapitel 7](07-ki-und-benachrichtigung.md#mail-warnung)).

## Für die IT in einem Satz

Repository klonen, `scripts/install.sh --domain vcr.example.com --zoom` ausführen, einmal per SSH-Tunnel und VNC in Zoom anmelden, fertig; Datenbank, Redis und VNC bleiben intern ([Kapitel 9](09-installation.md), mit Claude Code: [Kapitel 9a](09a-installation-mit-claude-code.md)).
