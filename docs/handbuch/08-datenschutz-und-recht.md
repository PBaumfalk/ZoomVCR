# 8 – Datenschutz und Recht

Dieses Kapitel ist eine technische Beschreibung, keine Rechtsberatung. Ob eine Aufnahme zulässig ist, entscheiden Veranstalter und Betreiber im Einzelfall.

## Vor der Aufnahme

- **Nur mit Erlaubnis aufnehmen.** Entweder Sie sind Veranstalter, oder es liegt eine Freigabe des Veranstalters vor, am besten schriftlich. Den Nachweis beim Planen angeben.
- **Beteiligte informieren.** ZoomVCR zeichnet den Bildschirm des Rekorders auf dem Server auf, nicht über die Aufnahmefunktion von Zoom. Die anderen Teilnehmer sehen deshalb **keinen** Aufnahmehinweis von Zoom, nur einen weiteren Teilnehmer mit dem gewählten Namen. Die Information muss vorab über den Veranstalter laufen.
- **Schutzmaßnahmen nicht umgehen.** Sperrt der Veranstalter Aufnahmen, wird nicht aufgezeichnet. ZoomVCR umgeht weder Warteräume noch Anmeldungen noch Aufnahmesperren.
- **Kein Anwesenheitsnachweis.** Die Aufnahme belegt nicht, dass jemand teilgenommen hat.

Die Angaben zu Berechtigung und Nachweis speichert ZoomVCR mit der Aufnahme, im Auditprotokoll und in `authorization.json` im ZIP-Export. Es ist Ihre Erklärung, keine technische Prüfung.

## Was gespeichert wird

| Daten | Wo | Wie lange |
| --- | --- | --- |
| Video, Original, Folienbilder | Docker-Volume `recordings` auf dem Server | Bis eine Aufnahme gelöscht wird |
| Transkript, Auswertung, Folientext | ebenda, als Dateien | Bis zur Löschung |
| Titel, Termin, Zoom-Link, Name in Zoom, Berechtigung | PostgreSQL | Bis zur Löschung |
| Konten, Sitzungen | PostgreSQL; Passwörter nur als Argon2id-Hash, TOTP-Schlüssel verschlüsselt | Konten werden gesperrt, nicht gelöscht |
| Auditprotokoll | PostgreSQL, mit IP-Adressen | Unbegrenzt, keine automatische Löschung |
| Zoom-Anmeldung des Rekorders | Docker-Volume `zoom_profile` | Bis zur Abmeldung |

Aufnahmen können Bild, Stimme und Namen der Teilnehmer enthalten. Eine **Aufbewahrungsfrist** legt der Betreiber fest; ZoomVCR löscht nichts von selbst. Sicherungen der Volumes verschlüsselt ablegen.

## Übermittlung an Dritte

| Empfänger | Was | Wann |
| --- | --- | --- |
| Zoom | Die Teilnahme des Rekorders wie bei jedem Teilnehmer | Bei jeder Aufnahme |
| KI-Dienst (z. B. OpenAI) | Ton (für die Transkription) und Transkript (für die Auswertung) | Nur, wenn ein Key hinterlegt ist ([Kapitel 7](07-ki-und-benachrichtigung.md)) |
| Mailserver | Titel, Termin und Problembeschreibung | Nur bei Warnungen |

Wer keine Übermittlung an einen KI-Dienst möchte, wählt die lokale Transkription und schaltet die Auswertung ab.

## Zugriff

Die Oberfläche ist nur mit Konto erreichbar. Empfohlen: zusätzlich nur aus dem Büronetz oder über VPN freigeben (am Reverse Proxy oder an der Firewall). Alle Konten sehen alle Aufnahmen. Für Aufnahmen mit Mandatsbezug ist ZoomVCR deshalb nicht gedacht.
