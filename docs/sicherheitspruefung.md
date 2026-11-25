# Sicherheitsprüfung (November 2026)

Überprüft wurden Abhängigkeiten, Konfiguration, Authentifizierung, Docker-Setup
und typische Schwachstellenmuster im Code. Ziel war der Betrieb auf einem
Raspberry Pi im lokalen Netzwerk ([Anleitung](raspberry-pi.md)).

## Behoben

| Bereich | Befund | Maßnahme |
|---|---|---|
| Backend-Abhängigkeit | `python-jose 3.3.0`: bekannte Lücken (u. a. Token-Fälschung bei bestimmten Schlüsseltypen, ungepatcht bis 3.5.0) und unsichere Abhängigkeit `ecdsa` (Timing-Angriff) | Ersetzt durch **PyJWT 2.15.1** (gleiches HS256-Format, `aud`/`iss`/`exp`-Prüfung unverändert) |
| Backend-Abhängigkeit | `starlette 0.38.6` (über FastAPI 0.115.0): Speicher-/DoS-Lücken beim Verarbeiten von Formular-Uploads | FastAPI **0.116.2**, Starlette **≥ 0.47.2** (installiert 0.48.0) |
| Backend-Abhängigkeit | `python-multipart 0.0.12`: mehrere DoS-Lücken | **0.0.34**; Import auf `python_multipart` umgestellt |
| Frontend-Abhängigkeit | `axios` (über `follow-redirects`/`form-data`): Weitergabe von Zugangsdaten bei Weiterleitungen, CRLF-Injection | `axios` **1.21.1** |
| Frontend-Abhängigkeit | `i18next < 26.3.4`: DoS | **26.7.x** |
| Frontend-Abhängigkeit | `react-router 6.30.3` / `@remix-run/router 1.23.2`: Open Redirect | `react-router-dom` **6.30.6** / `@remix-run/router` **1.23.4** |
| Datenschutz / Offline | Schriftarten wurden von Google Fonts und einem CDN nachgeladen (IP-Übertragung an Dritte, DSGVO-relevant; im LAN ohne Internet nicht verfügbar) | Externe Importe entfernt, System-Schriften |
| Lieferkette | Backend-Image installierte Python-Pakete standardmäßig über einen chinesischen PyPI-Spiegel | Standard auf `https://pypi.org/simple` |
| Deployment | Entwicklungs-Compose veröffentlicht Datenbank, Redis, Neo4j und Backend mit Standardpasswörtern auf allen Netzwerkschnittstellen | Neues `docker-compose.pi.yml`: nur Web-Port nach außen, DB/Redis nur intern, Pflicht-Passwörter aus `.env`, Redis mit Passwort |
| Deployment | Backend-Container lief als `root` | Im Pi-Setup als unprivilegierter Benutzer (UID 10001) |
| Deployment | API-Dokumentation (`/docs`, `/openapi.json`) öffentlich erreichbar | Im Pi-Setup gesperrt |
| Deployment | Keine Content-Security-Policy; Anmelde-Token liegt im `localStorage` (bei XSS auslesbar) | Strikte CSP (nur eigene Quellen) und weitere Sicherheits-Header im Pi-Setup; HTTPS-Variante mit HSTS |

## Positiv aufgefallen (bereits vorhanden)

- `SECRET_KEY` mit Platzhalterwert wird beim Start abgelehnt.
- Passwortrichtlinie (Länge, Zeichenklassen), Administrator nur per privatem CLI-Befehl.
- Begrenzung von Anmeldeversuchen.
- Werks-/Mandantentrennung auf Zeilenebene (`check_factory_access`), umfangreiche Tests dazu.
- Excel-Import mit Schutz gegen Zip-Bomben, XML-Entitäten und übergroße Dateien.
- Dynamisches SQL verwendet nur feste Fragmente und gebundene Parameter; kein `eval`, kein `dangerouslySetInnerHTML`.
- Refresh-Tokens mit Sitzungsbindung und Widerruf.

## Offen / Empfehlungen

| Priorität | Punkt | Empfehlung |
|---|---|---|
| Hoch | Demodaten (`python -m app.seed`) legen Konten mit öffentlich bekannten Passwörtern an | Im Produktivbetrieb nicht ausführen bzw. Konten deaktivieren |
| Mittel | Anmelde-Token im `localStorage` statt `HttpOnly`-Cookie | Mittelfristig auf Cookie-basierte Sitzung umstellen; bis dahin CSP beibehalten |
| Mittel | Starlette 0.48 enthält noch Lücken, die erst in Starlette 1.x behoben sind (Host-/Pfad-Rekonstruktion von `request.url`, Grenzen bei URL-encoded Formularen) | Upgrade auf aktuelle FastAPI/Starlette 1.x in einem eigenen Schritt (größere Versionssprünge, vollständiger Testlauf nötig). Im Pi-Setup mindern Caddy als Reverse-Proxy und das Upload-Limit das Risiko |
| Niedrig | `react-router` v6: zwei mittlere Hinweise (Open Redirect über Backslash bei nicht vertrauenswürdigen Zielen, SSR-Hydration – SSR wird nicht genutzt) | Upgrade auf React Router v7 |
| Niedrig | HTTP ohne TLS im Standard-Pi-Setup | `CADDYFILE=./deploy/pi/Caddyfile.https` verwenden |
| Hinweis | Entwicklungs-Compose (`docker-compose.yml`) | Nur lokal zur Entwicklung verwenden |

## Prüfwerkzeuge

- `pip-audit -r backend/requirements.txt`
- `npm audit --omit=dev` (im Verzeichnis `frontend`)
