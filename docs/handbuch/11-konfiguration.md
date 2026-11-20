# 11 – Konfiguration

Alle Einstellungen stehen in `.env` im Projektordner; `.env.example` ist die Vorlage. Änderungen greifen erst nach `docker compose up -d --force-recreate` (ein `restart` liest `.env` nicht neu).

## Grundlagen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `ZOOMVCR_PUBLIC_ORIGIN` | – | Öffentliche Adresse, z. B. `https://vcr.example.com`. Muss exakt stimmen (Cookies, OIDC-Rückleitung, Links in Mails). Ohne HTTPS nur `http://localhost` bzw. `http://127.0.0.1`, mit oder ohne Port. |
| `ZOOMVCR_SITE` | `:80` | Site-Adresse für den mitgelieferten Caddy. |
| `ZOOMVCR_HTTP_PORT`, `ZOOMVCR_HTTPS_PORT` | `80`, `443` | Ports des mitgelieferten Caddy auf dem Host, z. B. `8080` für einen Probelauf. |
| `ZOOMVCR_TIMEZONE` | `Europe/Berlin` | Zeitzone für Termine und Mails. |
| `ZOOMVCR_STORAGE_ROOT` | `/data/recordings` | Ablage im Container (Volume `recordings`). |
| `POSTGRES_PASSWORD` | – | Datenbankkennwort, Pflicht. |
| `ZOOMVCR_DATABASE_URL`, `ZOOMVCR_REDIS_URL` | aus Compose | Werden in `compose.yml` gesetzt. |

## Geheimnisse

| Variable | Bedeutung |
| --- | --- |
| `ZOOMVCR_SECRET_KEY` | Schlüssel für Sitzungen und für die Verschlüsselung von API-Key und TOTP-Schlüsseln. **Nicht ändern**, sonst sind gespeicherter KI-Key und alle Authenticator-Einrichtungen ungültig. Mit sichern. |
| `ZOOMVCR_API_TOKEN` | Admin-Token für die Kommandozeile `./zoomvcr`. Nie im Browser verwenden. |
| `ZOOMVCR_ADMIN_PASSWORD` | Nur für den allerersten Start (legt das Admin-Konto an), danach entfernen. |
| `ZOOMVCR_BOOTSTRAP_ADMIN_USERNAME` | Name dieses ersten Kontos, Standard `admin`. |
| `ZOOMVCR_VNC_PASSWORD` | Kennwort für VNC auf den Zoom-Desktop. |

## Zoom-Desktop

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `ZOOMVCR_ENABLE_DESKTOP` | `false` | `true` schaltet echte Zoom-Aufnahmen frei. |
| `ZOOMVCR_DESKTOP_AGENT_URL` | `http://desktop:8765` | Interner Agent. |
| `ZOOMVCR_DESKTOP_WIDTH`, `_HEIGHT`, `_FPS` | `1920`, `1080`, `15` | Auflösung und Bildrate von Bildschirm und Aufnahme. 1280×720 spart CPU und Speicher und genügt für Folien. |
| `ZOOMVCR_JOIN_TIMEOUT_SECONDS` | `180` | So lange wartet der Beitritt auf ein erkennbares Meeting. |
| `ZOOMVCR_JOIN_GRACE_SECONDS` | `12` | Wartezeit nach dem Start von Zoom. |
| `ZOOMVCR_ASSUME_JOINED_AFTER_SECONDS` | `0` | `0` = nie auf Verdacht aufnehmen. Ein Wert > 0 nimmt nach dieser Zeit auch ohne Erkennung auf (unsicher, nur bewusst). |
| `ZOOMVCR_REQUIRE_NAME_CONFIRMATION` | `true` | `true` = Aufnahme erst, wenn der Name erkannt oder bestätigt ist. `false` = trotzdem aufnehmen, Status „unbestätigt“. |
| `ZOOMVCR_JOIN_LEAD_MINUTES` | `5` | Beitritt vor dem Beginn. |
| `ZOOMVCR_END_BUFFER_MINUTES` | `15` | Aufnahme über das geplante Ende hinaus. |
| `ZOOMVCR_RECORD_SEGMENT_SECONDS` | `60` | Länge der Aufnahmestücke; bei einem Absturz geht höchstens ein Stück verloren. |

## Schnitt

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `ZOOMVCR_CUT_ENABLED` | `true` | Automatischen Schnitt an- oder abschalten. |
| `ZOOMVCR_CUT_SILENCE_DB` | `-50` | Ab dieser Lautstärke gilt es als still. |
| `ZOOMVCR_CUT_EDGE_SECONDS` | `20` | Mindestlänge für stillen Anfang und stilles Ende. |
| `ZOOMVCR_CUT_PAUSE_SECONDS` | `120` | Mindestlänge für Pausen in der Mitte. |
| `ZOOMVCR_CUT_PAD_SECONDS` | `3` | Bleibt an jeder Schnittkante stehen. |

## Transkription und KI

Normalerweise in der Oberfläche eingestellt ([Kapitel 7](07-ki-und-benachrichtigung.md)). Die Variablen gelten nur, solange dort nichts eingetragen ist.

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `ZOOMVCR_ASR_PROVIDER` | `openai` | `openai`, `local` oder `off`. |
| `ZOOMVCR_ASR_MODEL` | `small` | Modell für lokales Whisper. |
| `ZOOMVCR_LOCAL_ASR` | `false` | `true` baut das Backend-Image mit lokalem Whisper ([Kapitel 9](09-installation.md#lokales-whisper)). |
| `ZOOMVCR_AI_URL`, `ZOOMVCR_AI_MODEL`, `ZOOMVCR_AI_API_KEY` | leer | KI-Dienst als Rückfall. |
| `ZOOMVCR_OCR_LANG` | `deu+eng` | Sprachen der Texterkennung (Folien, Zoom-Oberfläche). |

## Mail

| Variable | Bedeutung |
| --- | --- |
| `ZOOMVCR_ALERT_EMAIL` | Empfänger der Warnungen. Leer = keine Mails. |
| `ZOOMVCR_SMTP_URL` (oder `SMTP_URL`) | z. B. `smtps://benutzer:kennwort@mail.example.com:465`. |
| `ZOOMVCR_MAIL_FROM` (oder `MAIL_FROM`) | Absender, z. B. `rekorder@example.com`. |
| `ZOOMVCR_AUDIO_ALERT_SECONDS` | Ab so vielen Sekunden ohne Zoom-Ton geht eine Mail, Standard `120`. |

## Anmeldung über OIDC

`ZOOMVCR_OIDC_DISCOVERY_URL`, `ZOOMVCR_OIDC_CLIENT_ID`, `ZOOMVCR_OIDC_CLIENT_SECRET`. Ohne alle drei bleibt der Kanzlei-Login aus ([Kapitel 12](12-anmeldung-oidc.md)).
