# 12 – Anmeldung über OIDC

ZoomVCR kann die Anmeldung an einen OpenID-Connect-Anbieter Ihrer Organisation abgeben, z. B. authentik, Keycloak oder Microsoft Entra ID. Die Schritte unten zeigen authentik; bei anderen Anbietern heißen die Menüpunkte anders, die Werte sind dieselben. Die Schaltfläche heißt dann **Mit SSO anmelden**.

## In authentik

1. **Provider** vom Typ OAuth2/OpenID Connect anlegen, Authorization Code Flow, mit Signing Key.
2. Redirect URI exakt: `https://vcr.example.com/api/auth/oidc/callback` (die eigene `ZOOMVCR_PUBLIC_ORIGIN`).
3. Scopes `openid`, `profile`, `email`. Die E-Mail muss im ID-Token als `email_verified=true` ankommen.
4. **Application** `zoomvcr` mit diesem Provider anlegen und den berechtigten Gruppen zuweisen.
5. Zwei-Faktor und Passwortregeln für diese Benutzer beim Anbieter festlegen.

## In ZoomVCR

```env
ZOOMVCR_OIDC_DISCOVERY_URL=https://auth.example.com/application/o/zoomvcr/.well-known/openid-configuration
ZOOMVCR_OIDC_CLIENT_ID=<client-id>
ZOOMVCR_OIDC_CLIENT_SECRET=<client-secret>
```

Danach `docker compose up -d --force-recreate api`.

Vor dem ersten Login legt ein Admin für jede Person ein Konto vom Typ **Zentrale Anmeldung (SSO)** an, mit derselben bestätigten E-Mail wie beim Anbieter und der gewünschten Rolle ([Kapitel 6](06-benutzer-und-rechte.md)).

## Wie es geprüft wird

- Authorization Code mit PKCE, `state` und `nonce` (Authlib). Der ID-Token wird gegen die Schlüssel des Anbieters geprüft.
- Nur vorab angelegte Konten; keine automatische Registrierung, keine Rollen aus dem Token.
- Beim ersten Login verknüpft ZoomVCR das Konto mit dem `sub` des Anbieters. Danach zählt diese Verknüpfung, nicht mehr die E-Mail.
- Eine Sperre in ZoomVCR wirkt sofort, auch auf laufende Sitzungen.

Ein lokales Admin-Konto mit Authenticator als Notzugang behalten, falls der Anbieter ausfällt.
