# ZoomVCR v3 – Authentifizierung und Berechtigungen

## Architektur

- Lokale Accounts in PostgreSQL, Argon2id-Passwort-Hashes.
- Gesonderte Login-Session-Tabelle mit UUID, Ablaufdatum (8 Stunden) und Widerruf.
- Cookies: HttpOnly, Strict, Secure bei HTTPS. JWT enthält nur Benutzer-ID, Session-ID und Sessionversion; jeder API-Request verifiziert den Datenbankstatus.
- Serverseitige RBAC: Viewer (lesen/exportieren) < Recorder (planen/steuern) < Admin (Benutzer/Audit/Live-Snapshot).
- Kein automatisches SSO-Konto und keine Rollenübernahme aus Browser-Claims. OIDC: vorab provisionierte E-Mail, beim ersten Login mit verifiziertem Subject verknüpft.
- TOTP-RFC6238 (SHA-1, 30 Sekunden, sechs Stellen, ± ein Step) mit Replay-Schutz, verschlüsselt abgelegt. Bei Passwort-Reset wird MFA zurückgesetzt.
- Login-Throttling in Redis nach IP und nach IP/Benutzername (15 Minuten). Auditlog ohne Geheimnisse.
- Privilegierter CLI-API-Token aus Umgebung bleibt bestehen, wird niemals ins Webfrontend eingebettet.

## Rollen

| Endpunkt | Betrachter | Rekorder | Administrator |
|---|---:|---:|---:|
| `GET /api/recordings`, Transkript, Folien, Player, Export | Ja | Ja | Ja |
| `POST /api/recordings`, Start, Stop, Process, Admit, Name | Nein | Ja | Ja |
| `GET /api/recordings/{id}/logs` | Nein | Ja | Ja |
| `GET /api/desktop/health` | Nein | Ja | Ja |
| `GET /api/desktop/snapshot` | Nein | Nein | Ja |
| `GET/POST/PATCH /api/users`, Passwort-Reset | Nein | Nein | Ja |
| `GET /api/audit` | Nein | Nein | Ja |
| `GET /api/me`, Passwort/MFA des eigenen lokalen Kontos | Ja | Ja | Ja |

**Wichtige Grenze:** Die gesamte Mediathek wird global zwischen den Nutzern geteilt.
Für Mandanten-/Akten-separierte Berechtigungen ist eine ACL je Aufnahme erforderlich.
Diese Version bietet weder Unveränderlichkeitsnachweis des Audits noch automatisches
User-Provisioning aus authentik.

## Produktions-Check vor Freigabe

- [ ] PostgreSQL-Backup und Volumes-Backup vor Migration
- [ ] Starke `.env`-Geheimnisse; `ZOOMVCR_SECRET_KEY` nicht ändern, ohne MFA-Folgen zu planen
- [ ] Einmaliges Bootstrap-Login mit `admin`, anschließend das Bootstrap-Passwort aus `.env` entfernen
- [ ] Admin aktiviert TOTP, separates Wiederherstellungsverfahren sicherstellen
- [ ] Caddy/HTTPS-Domain exakt wie `ZOOMVCR_PUBLIC_ORIGIN`
- [ ] authentik-Anwendung, genaue Redirect URI, Scopes und `email_verified` kontrollieren
- [ ] Nur manuell angelegte SSO-Konten, keine Auto-Registrierung
- [ ] Browserintegration in allen drei Rollen testen
- [ ] Datenaufbewahrung und Löschkonzept für Aufnahmen/Audits festlegen
- [ ] Belastungstest und echte Zoom-Aufzeichnung gesondert durchführen
