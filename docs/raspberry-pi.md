# OpenQMS auf einem Raspberry Pi im lokalen Netzwerk

Diese Anleitung beschreibt den Betrieb von OpenQMS mit Docker auf einem
Raspberry Pi, erreichbar für alle Rechner im lokalen Netzwerk.

## Voraussetzungen

| | Empfehlung |
|---|---|
| Hardware | Raspberry Pi 4 oder 5 mit **mindestens 4 GB RAM** (8 GB empfohlen) |
| Speicher | SSD per USB 3 statt SD-Karte (Datenbank-Schreiblast), mind. 32 GB frei |
| Betriebssystem | **64-Bit** Raspberry Pi OS (Bookworm) oder Ubuntu Server 24.04 arm64 |
| Netzwerk | Feste IP-Adresse oder DHCP-Reservierung im Router |

Alle verwendeten Images (PostgreSQL/pgvector, Redis, Python, Node, Caddy) gibt
es für arm64. Ein 32-Bit-System wird **nicht** unterstützt.

## 1. Docker installieren

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo usermod -aG docker $USER
```

Danach ab- und wieder anmelden. Prüfen:

```bash
docker compose version
```

## 2. OpenQMS holen und konfigurieren

```bash
git clone <URL-Ihres-Forks> openqms
```

```bash
cd openqms
```

```bash
cp .env.pi.example .env
```

In `.env` **alle** Platzhalter ersetzen. Zufallswerte erzeugen:

```bash
openssl rand -hex 32
```

- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`: je ein eigener Zufallswert
- `SECRET_KEY`: Zufallswert mit mindestens 32 Zeichen (signiert die Anmelde-Tokens)

Die Datei `.env` enthält Geheimnisse – nicht ins Git-Repository übernehmen
(sie ist in `.gitignore` bereits ausgeschlossen) und Rechte einschränken:

```bash
chmod 600 .env
```

## 3. Bauen und starten

Der erste Build dauert auf dem Pi je nach Modell 15–40 Minuten.

```bash
docker compose -f docker-compose.pi.yml up -d --build
```

Status prüfen (alle Dienste sollten `healthy` bzw. `running` sein):

```bash
docker compose -f docker-compose.pi.yml ps
```

Die Datenbank-Migrationen laufen beim Start des Backends automatisch.

## 4. Administrator anlegen

Das Administratorkonto wird bewusst nicht über die Weboberfläche oder
Umgebungsvariablen angelegt, sondern einmalig per Kommandozeile. Das Passwort
wird verdeckt abgefragt (14–72 Zeichen, Groß-/Kleinbuchstaben, Ziffer, Sonderzeichen):

```bash
docker compose -f docker-compose.pi.yml exec backend python -m app.cli.bootstrap_admin --username admin
```

Weitere Benutzer legen Sie danach in der Oberfläche unter
**Systemeinstellungen → Benutzerverwaltung** an.

## 5. Aufrufen

Im Browser eines beliebigen Rechners im Netzwerk:

```
http://<IP-des-Pi>
```

Die Oberfläche startet auf **Deutsch**; oben rechts kann auf **English**
umgeschaltet werden. Die Auswahl wird im Browser gespeichert.

## Optional: Demodaten

Für einen Testbetrieb können Demodaten geladen werden:

```bash
docker compose -f docker-compose.pi.yml exec backend python -m app.seed
```

**Achtung:** Die Demodaten legen Benutzer mit öffentlich bekannten Passwörtern
an (`engineer`, `manager`, `viewer`). Im produktiven Betrieb **keine** Demodaten
laden bzw. diese Konten anschließend deaktivieren oder ihre Passwörter ändern.

## Optional: HTTPS im lokalen Netz

Standardmäßig läuft OpenQMS per HTTP auf Port 80. Für verschlüsselte Verbindungen
(empfohlen, da Anmeldedaten übertragen werden) in `.env` setzen:

```
OPENQMS_HOSTNAME=openqms.local
CADDYFILE=./deploy/pi/Caddyfile.https
```

`OPENQMS_HOSTNAME` muss der Name bzw. die IP sein, unter der die Clients den Pi
aufrufen. Danach neu starten:

```bash
docker compose -f docker-compose.pi.yml up -d
```

Caddy erzeugt eine eigene lokale Zertifizierungsstelle. Damit Browser keine
Warnung zeigen, deren Stammzertifikat einmalig exportieren und auf den Clients
als vertrauenswürdig importieren:

```bash
docker compose -f docker-compose.pi.yml cp web:/data/caddy/pki/authorities/local/root.crt ./openqms-root.crt
```

## Optional: KI-Funktionen

Ohne Konfiguration arbeitet OpenQMS im reinen Regel-Engine-Modus. Für KI-Vorschläge
in `.env` einen Anbieter eintragen (`LLM_PROVIDER=claude`, `openai` oder `local`
für einen Ollama-Server im Netzwerk) oder später unter
**Systemeinstellungen → KI-Modellkonfiguration**. Ein lokales Sprachmodell direkt
auf dem Pi ist wegen des Speicherbedarfs nicht empfehlenswert.

## Betrieb

Logs ansehen:

```bash
docker compose -f docker-compose.pi.yml logs -f backend
```

Aktualisieren (neuen Stand holen, neu bauen, Migrationen laufen automatisch):

```bash
git pull && docker compose -f docker-compose.pi.yml up -d --build
```

Datenbank-Backup erstellen:

```bash
docker compose -f docker-compose.pi.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > openqms-$(date +%F).dump
```

Backup zurückspielen (überschreibt vorhandene Daten):

```bash
docker compose -f docker-compose.pi.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < openqms-JJJJ-MM-TT.dump
```

Backups regelmäßig (z. B. per `cron`) erstellen und **auf einem anderen Gerät**
ablegen.

## Sicherheitshinweise für den Netzwerkbetrieb

- Nur Port 80 (und ggf. 443) wird veröffentlicht. Datenbank und Redis sind nur im
  internen Docker-Netz erreichbar.
- Den Pi **nicht** per Portweiterleitung ins Internet stellen. Für Fernzugriff ein
  VPN (z. B. WireGuard) verwenden.
- Firewall auf dem Pi, die nur SSH und HTTP/HTTPS aus dem lokalen Netz erlaubt:

```bash
sudo apt install -y ufw && sudo ufw allow from 192.168.0.0/16 to any port 22,80,443 proto tcp && sudo ufw enable
```

  (Netzbereich an Ihr Netzwerk anpassen.)

- Hinweis: Docker veröffentlicht Ports an `ufw` vorbei. Wer den Zugriff auf
  bestimmte Netze begrenzen muss, setzt in `.env` z. B. `HTTP_PORT=192.168.1.10:80`
  (nur an diese Pi-Adresse binden) oder filtert im Router.
- Betriebssystem und Images regelmäßig aktualisieren (`sudo apt upgrade`,
  `docker compose ... up -d --build --pull always`).
- Die Entwicklungs-Compose-Datei `docker-compose.yml` ist **nicht** für den
  Netzwerkbetrieb gedacht (Standardpasswörter, offene Datenbank-Ports).

Weitere Ergebnisse der Sicherheitsprüfung: [sicherheitspruefung.md](sicherheitspruefung.md).
