# OpenQMS

OpenQMS ist eine modulare Qualitätsmanagement-Plattform für die Fertigung. Sie deckt FMEA-Risikoanalyse, Produktionslenkungspläne, Wareneingangsprüfung, statistische Prozessregelung (SPC) und 8D-Korrekturmaßnahmen ab und unterstützt Qualitätsprozesse nach IATF 16949.

**[English documentation →](README_EN.md)** · **[Betrieb auf dem Raspberry Pi →](docs/raspberry-pi.md)** · **[Sicherheitsprüfung →](docs/sicherheitspruefung.md)**

> Diese Fassung des Projekts hat eine deutsche Oberfläche (Standard) mit Umschaltung auf Englisch. Ein Teil der weiterführenden Dokumentation unter `docs/` liegt weiterhin nur auf Chinesisch bzw. Englisch vor.

## Wie die Fachmodule mit KI-Agenten zusammenarbeiten

Beispiel 8D-Bericht: Im standardmäßig deaktivierten Agent-Pilotbetrieb können Mitarbeitende ein freigegebenes Modell-Deployment wählen und den Agenten auf Basis der verifizierten D4-Grundursache und der verknüpften FMEA-Belege D5-Abstellmaßnahmen vorschlagen lassen. Vorschläge werden zunächst als zu prüfende Einträge gespeichert; erst wenn berechtigte Mitarbeitende die Grundlage geprüft, die Formulierung bestätigt und den Vorschlag übernommen haben, erfasst CAPA ihn als formale Maßnahme. [8D-Agent-Pilot und Modellkonfiguration](docs/development/r5-model-egress.md)

- **Einheitliche fachliche Grundlage.** Die Architektur verlangt, dass Plugins den Kontext über die Schnittstellen der Fachmodule lesen und dabei Berichte, Quellnachweise und deren Versionen weiterverwenden. Oberfläche und Agent beziehen sich auf dieselben Qualitätsfakten; Mitarbeitende können jeden Vorschlag bis zu seiner Grundlage zurückverfolgen.
- **Fähigkeiten je Aufgabe kombinieren.** Jedes Modul deklariert, welchen Kontext es bereitstellt und welche fachlichen Befehle ausführbar sind. Der Agent kann über mehrere Runden Informationen ergänzen und den nächsten Schritt wählen; die Plattform prüft bei jedem Aufruf Identität, Plugin-Berechtigung und Aufgabenumfang, während das Fachmodul für Statuswechsel, Freigaben und Audit zuständig ist.

8D ist das erste angebundene Muster. Weitere Qualitätsmodule werden schrittweise nach ihren eigenen Daten- und Bedienregeln angebunden. [Aktuelle Architektur](docs/architecture.md) · [Roadmap](docs/ROADMAP.md)

---

## Funktionsübersicht

| Modul | Beschreibung |
|------|------|
| **FMEA** | PFMEA/DFMEA nach AIAG-VDA (7 Schritte), Graph-Editor, Erstellungsassistent, automatische RPZ/AP-Berechnung, Freigabe-Workflow |
| **8D / CAPA** | Schrittweise D1–D8, Teambildung, FMEA-Verknüpfung, geschlossener Freigabekreislauf |
| **Produktionslenkungsplan** | Erzeugung aus der PFMEA per Klick, bidirektionale Synchronisierung, Versionsverwaltung |
| **Besondere Merkmale** | CC/SC-Kennzeichnung, Abdeckungsmatrix, FMEA→PLP-Verknüpfung, Rückverfolgungsansicht |
| **SPC** | X̄-R / I-MR / p/np/c/u-Regelkarten, 8 Prüfregeln, Cp/Cpk-Berechnung |
| **MSA** | GR&R, Bias, Linearität, Stabilität, attributive Kappa-Analyse |
| **Wareneingangsprüfung (IQC)** | AQL-Stichprobenpläne, Prüflosverwaltung, AQL-Optimierung |
| **Lieferantenmanagement** | Lieferantenprofile, Leistungsbewertung, Konfiguration des Lieferantenrisikos |
| **SCAR** | Korrekturmaßnahmenanforderungen an Lieferanten, Lebenszyklus mit 5 Status |
| **Reklamationen / RMA** | Erfassung von Kundenreklamationen, RMA-Rücksendungen, Verknüpfung mit CAPA/FMEA |
| **APQP** | Gate-Management über fünf Phasen, Gantt-Diagramm, Checklisten für Ergebnisse |
| **PPAP** | 18 AIAG-Elemente, Lebenszyklus mit 5 Status, Pflichtelemente je Vorlagestufe 1–5 |
| **Managementbewertung** | Automatisches Datenpaket nach ISO 9001 §9.3, Nachverfolgung der Maßnahmen |
| **Internes Audit** | System-, Prozess- und Produktaudits, Checklisten, Verfolgung von Feststellungen |
| **Kundenaudit** | Auditplanung, Verfolgung von Feststellungen, Abschluss der Korrekturen |
| **Qualitätsziele** | Dreistufiger Zielbaum, Freigabe-Workflow, KPI im Dashboard |
| **ERP / MES / PLM** | Dashboards und Datensynchronisierung mit externen Systemen |
| **Wissensgraph** | Verknüpfung und Visualisierung von FMEA-/PLP-Wissen |
| **Konzernverwaltung** | Dashboard über mehrere Werke, Werksvergleich, Konzernlieferanten und -audits |
| **Produkttyp-Stammdaten** | Werksübergreifende Produktklassifizierung, Zuordnung von Produktlinien, Filter für semantische Suche |

---

## Technologie

| Schicht | Technologie |
|----|------|
| Backend | Python 3.11 / FastAPI 0.116 (async) / SQLAlchemy 2.0 (async) / PostgreSQL 15 / Redis 7 |
| Frontend | React 18 / TypeScript 5.6 / Vite 5.4 / Ant Design 5 / i18next (Deutsch, Englisch) |
| Infrastruktur | Docker Compose / Alembic (Migrationen) / Neo4j 5 (Wissensgraph) / externe KI-Anbieter (optional) |

---

## Betrieb im eigenen Netzwerk (Raspberry Pi)

Für den Betrieb auf einem Raspberry Pi (oder einem anderen arm64-/x86-Server) im lokalen Netzwerk gibt es ein eigenes, abgesichertes Setup: `docker-compose.pi.yml`. Nur der Web-Port ist von außen erreichbar, Datenbank und Redis bleiben im internen Docker-Netz, alle Passwörter kommen aus einer `.env`-Datei.

```bash
cp .env.pi.example .env
```

```bash
docker compose -f docker-compose.pi.yml up -d --build
```

Schritt-für-Schritt-Anleitung inklusive Administratorkonto, HTTPS, Backup und Firewall: **[docs/raspberry-pi.md](docs/raspberry-pi.md)**.

---

## Schnellstart für die lokale Entwicklung (nicht für den Produktivbetrieb)

Die einfachen `docker compose`-Befehle in diesem Abschnitt dienen nur der lokalen Entwicklung; auch mit geänderten Demopasswörtern wird daraus keine Produktivkonfiguration. Für den Betrieb im Netzwerk siehe den Abschnitt Raspberry Pi oben bzw. für die Oracle-Produktion `production-compose.sh` und den Ablauf weiter unten; vollständige Schritte im [Deployment-Leitfaden](docs/deployment.md).

### Voraussetzungen

- [Docker](https://www.docker.com/get-started) mit Docker Compose
- Mindestens 4 GB freier Arbeitsspeicher (PostgreSQL + Redis + Neo4j + Anwendungsdienste)

### 1. Dienste starten

```bash
git clone https://github.com/your-org/OpenQMS.git
cd OpenQMS
docker compose up -d
```

Warten, bis alle Container bereit sind (ca. 30 Sekunden):

```bash
docker compose ps   # db/redis/neo4j müssen healthy, backend/frontend running sein
```

### 2. Datenbank initialisieren

```bash
docker compose exec backend alembic upgrade head
```

### 3. Demodaten laden

```bash
docker compose exec backend python -m app.seed
```

Die Ausgabe `Seed data created successfully!` bestätigt den Erfolg.

### 4. System aufrufen

Im Browser **http://localhost:5173** öffnen und mit einem der folgenden Konten anmelden:

| Benutzername | Passwort | Rolle | Beschreibung |
|--------|------|------|------|
| `admin` | private Initialisierung | Systemadministrator | Alle Rechte, Verwaltung von Benutzern und Berechtigungen |
| `engineer` | `Engineer@2026` | Fertigungsqualitätsingenieur | Bearbeitung von FMEA/SPC/MSA und CAPA |
| `manager` | `Manager@2026` | Qualitätsmanager | Freigaberechte, kann CAPA schließen |
| `viewer` | `Viewer@2026` | Nur-Lese-Benutzer | Alle Module nur lesend |
| `groupadmin` | private Initialisierung | Systemadministrator (Konzern) | Verwaltungsrechte über mehrere Werke |

Administratoren werden beim Start nicht automatisch angelegt, und `admin`/`groupadmin` aus den Demodaten haben kein öffentliches Passwort. Führen Sie `docker compose exec backend python -m app.cli.bootstrap_admin --username admin --replace-existing` aus und geben Sie das installationsspezifische Passwort in einem privaten Terminal interaktiv ein; für neue Konten ohne Demodaten `--replace-existing` weglassen. Hinweise zum Upgrade im [Protokoll der Sicherheitskorrekturen](docs/development/2026-11-16-security-scan-fixes.md).

> ⚠️ Die obigen Demokonten mit Passwörtern sind nur für die lokale Entwicklung oder für öffentliche Demos gedacht, die der Betreiber ausdrücklich freigegeben hat. `qms.smartindustry.world` ist eine gemeinsam beschreibbare Demoumgebung: Administratoren können Konten, Passwörter und Daten ändern – geben Sie dort keine echten Daten oder echten API-Schlüssel ein. Jede andere produktive Installation muss die privilegierten Passwörter ändern.

### 5. API-Dokumentation

- Swagger UI: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**

---

## Produktivbetrieb auf Oracle ARM64

Produktionsziel ist `qms.smartindustry.world`: eine einzelne Oracle-Cloud-ARM64-Maschine mit `TENANT_MODE=single` und `E2E_MODE=false`. Tailscale dient der Administration und der Abnahme im privaten Netz, der `qms`-A-Record bei Namecheap BasicDNS zeigt direkt auf `150.230.197.45`, Caddy terminiert HTTPS. Die Produktions-Compose-Datei enthält PostgreSQL, Redis, Neo4j, Backend, Graph-Worker und Caddy-Web; **Ollama wird nicht deployt**, und in dieser öffentlich beschreibbaren Demoinstanz dürfen keine echten LLM-/Embedding-API-Schlüssel konfiguriert werden.

`/` ist die einzige ausdrücklich öffentliche Ausnahme vom Routenschutz, `/login` ist der Einstieg zur Anmeldung; Dashboard und alle Fachrouten bleiben durch `ProtectedRoute` und Modulberechtigungen geschützt. Access-JWTs gelten 120 Minuten; ein Passwort-Reset widerruft Refresh-Sitzungen, bereits ausgestellte zustandslose Access-JWTs bleiben aber bis zu ihrem ursprünglichen Ablauf gültig. Caddy ist fest auf `172.30.0.10` gesetzt und das Backend vertraut nur dieser Proxy-Adresse; Produktions-Subnetz oder Trusted-Proxy-Grenze nicht ändern, ohne die Proxy-Prüfung erneut auszuführen.

### Produktionsumgebung und Compose-Wrapper

Compose verwendet die `.env` / `.env.production` im Projektverzeichnis. Nachdem `.env.production` einmalig auf dem Server erzeugt wurde, müssen alle Produktionsbefehle über den Wrapper laufen; er legt Projektname `openqms`, Projektverzeichnis, Compose-Datei und Umgebungsdatei fest und entfernt Umgebungsvariablen aus der Shell, die die Produktionskonfiguration verfälschen könnten.

Im Betriebs-Repository auf dem Mac muss zuerst ein unveränderliches Release festgelegt werden, dessen versionierte Inhalte mit HEAD übereinstimmen; nicht versionierte Plan- oder Referenzdateien gehören nicht zur Deployment-Identität. Die zu deployenden Bytes werden ausschließlich per `git archive "$RELEASE_SHA"` in eine private Stage mit Rechten `0700` extrahiert, nie aus dem veränderlichen Arbeitsverzeichnis; auch die Pfadliste stammt aus dem Commit-Objekt per `git ls-tree`. Das Manifest erfasst für jeden versionierten Pfad SHA-256 und Git-Modus `100644`/`100755` und weist Symlinks und unsichere Pfade zurück. Oracle prüft das Manifest selbst, den Verifier, Hash/Modus aller versionierten Dateien und die vollständige Menge deploybarer Pfade; ausgenommen ist nur dauerhafter Laufzeitzustand (`.env.production`, `backups/`, `.release-sha`, `.release-manifest`). Erst nach erfolgreicher Prüfung wird ein nicht vertraulicher Commit-SHA-Marker geschrieben. Das erste Deployment löscht nichts auf dem Server; zusätzliche oder übrig gebliebene Quell-, Konfigurations- oder Skriptdateien führen zum Abbruch. Die Stage wird bei normalem Ende, EXIT oder Signal entfernt.

```bash
set +x
set -euo pipefail
cd '<local-openqms-checkout>'
export LOCAL_RELEASE_REPO=$(pwd -P)
git checkout --detach '<immutable-release-sha>'
git diff --quiet
git diff --cached --quiet
export RELEASE_SHA=$(git rev-parse HEAD)
export ORACLE_SSH_TARGET=ubuntu@100.84.141.70
export ORACLE_SSH_KEY="$HOME/.ssh/<private-key-file>"
RELEASE_STAGE=""
cleanup_release_stage() {
  if [[ -n "$RELEASE_STAGE" ]]; then
    rm -rf -- "$RELEASE_STAGE"
    RELEASE_STAGE=""
  fi
}
handle_release_signal() {
  trap - HUP INT TERM QUIT
  cleanup_release_stage
  exit 1
}
trap cleanup_release_stage EXIT
trap handle_release_signal HUP INT TERM QUIT
RELEASE_STAGE=$(mktemp -d)
chmod 700 "$RELEASE_STAGE"
RELEASE_MANIFEST="$RELEASE_STAGE/.release-manifest"
umask 022
git archive --format=tar "$RELEASE_SHA" | tar -xf - -C "$RELEASE_STAGE"
git ls-tree -r -z --name-only "$RELEASE_SHA" | \
  python3 "$RELEASE_STAGE/scripts/check-release-tree.py" create --root "$RELEASE_STAGE" \
  > "$RELEASE_MANIFEST"
git ls-tree -r -z --name-only "$RELEASE_SHA" | \
  rsync --from0 --files-from=- -a \
    -e "ssh -i $ORACLE_SSH_KEY" \
    "$RELEASE_STAGE/" "$ORACLE_SSH_TARGET:/opt/openqms/"
scp -i "$ORACLE_SSH_KEY" \
  "$RELEASE_MANIFEST" \
  "$ORACLE_SSH_TARGET:/opt/openqms/.release-manifest"
export RELEASE_MANIFEST_SHA=$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$RELEASE_MANIFEST")
export RELEASE_GUARD_SHA=$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$RELEASE_STAGE/scripts/check-release-tree.py")
export REMOTE_RELEASE_VERIFY='test "$(sha256sum .release-manifest | cut -d " " -f1)" = "'"$RELEASE_MANIFEST_SHA"'" && test "$(sha256sum scripts/check-release-tree.py | cut -d " " -f1)" = "'"$RELEASE_GUARD_SHA"'" && python3 scripts/check-release-tree.py verify --root . --manifest .release-manifest >/dev/null'
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
  "cd /opt/openqms && $REMOTE_RELEASE_VERIFY"
printf '%s\n' "$RELEASE_SHA" | \
  ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
    'cat > /opt/openqms/.release-sha'
REMOTE_RELEASE_SHA=$(ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" 'cat /opt/openqms/.release-sha')
test "$REMOTE_RELEASE_SHA" = "$RELEASE_SHA"
command -v python3.11 >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
test "$(python3.11 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11"
test "$(node -p 'process.versions.node.split(".")[0]')" = "20"
python3.11 -m venv "$RELEASE_STAGE/backend/.venv"
"$RELEASE_STAGE/backend/.venv/bin/python" -m pip install \
  --disable-pip-version-check --no-input \
  -r "$RELEASE_STAGE/backend/requirements.txt" \
  --index-url https://pypi.org/simple
"$RELEASE_STAGE/backend/.venv/bin/python" -m pip install --index-url https://pypi.org/simple pytest setuptools==79.0.1
(cd "$RELEASE_STAGE/frontend" && npm ci)
```

Die folgenden Initialisierungsbefehle werden in der **Shell des Oracle-Hosts in `/opt/openqms`** ausgeführt:

```bash
cd /opt/openqms
SITE_ADDRESS=qms.smartindustry.world \
  TAILSCALE_IP='<tailscale-ip>' \
  OUTPUT_PATH=.env.production \
  ./scripts/init-production-env.sh
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d db redis neo4j
./scripts/production-compose.sh ps
```

Die im Browser sichtbaren Viewer-Zugangsdaten sind bewusst bereitgestellte Nur-Lese-Demozugänge; der Standard-Build veröffentlicht nur den Viewer. Diese Instanz veröffentlicht zusätzlich `engineer` und `manager` als **gemeinsam beschreibbare** Demokonten: Nur wenn das optionale `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` mit dem vollständigen JSON beider Konten gesetzt ist, zeigen das normale `/login` und `?demo=viewer` drei Konten; die Schaltflächen füllen nur das Formular aus und melden nicht automatisch an. `admin` und das ebenfalls administrative `groupadmin` bleiben privat und gelangen nie in das Browser-Bundle. Engineer hat keine Benutzerverwaltungsrechte, Manager nur Leserechte; keiner von beiden kann Passwörter anderer Konten ändern. Andere Besucher können dennoch gemeinsame Qualitätsdaten verändern; diese Konfiguration ist eine öffentliche Build-Eingabe, kein Geheimnis – keine echten Daten oder API-Schlüssel eingeben. Beim Abschalten der Demo müssen alle Zugangsdaten-Variablen gleichzeitig geleert werden.

```env
# Nur diese Instanz: vorhandenen leeren Wert ersetzen; nur anhängen, wenn der Schlüssel in der .env.production (Modus 0600) fehlt
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=[{"username":"engineer","password":"Engineer@2026"},{"username":"manager","password":"Manager@2026"}]
```

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF

# Öffentlichen Demo-Zugang deaktivieren
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS= \
  npm --prefix frontend run build
```

### Identitätsprüfung und serielles Release

Die DSN innerhalb der Container verwendet `db:5432`. Ein eigenes Terminal auf dem Mac tunnelt das Oracle-Ziel auf den lokalen Port `15432`; die lokale PostgreSQL-Instanz auf `5432` stellt die einzige Release-Gate-Datenbank für diesen Lauf bereit. Die Betriebs-Shell entfernt zunächst ein eventuell vorhandenes `TEST_DATABASE_URL` aus der Umgebung, erstellt und exportiert vor dem ersten `make --silent check-test-db` eine eindeutige URL und übergibt über ein explizites `CHECK_CMD` dieselbe URL, denselben Datenbanknamen und dieselben PG-Parameter an das verschachtelte `make check` von deploy-release – ohne jemals auf `qms_test` zurückzufallen. Alle migrate/check/preflight-Skripte laufen aus `RELEASE_STAGE`; die Stage erstellt mit Python 3.11 aus dem `backend/requirements.txt` des Archivs eine frische `.venv` und führt mit Node 20 ein sauberes `npm ci` auf dem `frontend/package-lock.json` des Archivs aus. Nicht versionierte Abhängigkeiten oder Quellen des ursprünglichen Checkouts werden nicht wiederverwendet. Nach dem Build ermittelt der Oracle-Wrapper per `docker image inspect` die sha256-Image-IDs der neu gebauten `openqms-backend:prod` / `openqms-web:prod` (der Graph-Worker nutzt das Backend-Tag), fixiert sie und verknüpft sie mit `RELEASE_SHA`; `images -q` von Compose ist ungeeignet, da es nur bereits erstellte Container widerspiegelt. Die Zielidentität prüft vor der Migration zuerst erneut Remote-Baum, Marker und Tag-Images; Initializer und Rollout wiederholen dieselbe Prüfung.

Eigenes Tunnel-Terminal auf dem Mac:

```bash
ssh -N \
  -i "$HOME/.ssh/<private-key-file>" \
  -L 15432:127.0.0.1:5432 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  ubuntu@100.84.141.70
```

Betriebs-Terminal auf dem Mac, das synchronisiert und `RELEASE_SHA` beibehält (Platzhalter zuvor durch die Zugangsdaten der lokalen Testdatenbank ersetzen; Produktionspasswörter oder DSN nie ausgeben):

Eigentum an der Release-Testdatenbank: Stellen Sie einen eigenen Docker-Container `pgvector/pgvector:pg15` mit zufälligem `openqms.owner`-Label und nur auf Loopback veröffentlichtem Port bereit. Erstellen Sie vor Ausführung dieses Blocks eine JSON-Registrierung mit Modus 0600 mit `container`, vollständiger `container_id`, zum Label passendem `owner_nonce`, `image`, `host`, `port`, `test_database` = `qms_test` (passend zu RELEASE_GATE_DB) und `application_database` = `postgres`. Setzen Sie OPENQMS_TEST_RESOURCE_FILE auf diese Datei und LOCAL_TEST_PG* auf genau diesen Container. Registrieren Sie keine Geschäftsdatenbank und keinen Container einer anderen Aufgabe. `make check-test-db` prüft die Registrierung, bevor die Testdatenbank angelegt bzw. migriert wird; das muss erfolgreich sein, bevor `make deploy-release` das Ziel berührt. Die aktuellen Abnahme-Fixtures erfordern `qms_test`; verwenden Sie diesen Namen nur innerhalb des dedizierten Containers und nie eine gemeinsam genutzte qms_test-Instanz. Die SDK-Build-Werkzeuge sind in der venv der Stage fixiert, und CHECK_CMD wählt diesen Interpreter ausdrücklich.

```bash
cd "$RELEASE_STAGE"
test "$(git -C "$LOCAL_RELEASE_REPO" rev-parse HEAD)" = "$RELEASE_SHA"
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY"
REMOTE_RELEASE_SHA=$(ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" 'cat /opt/openqms/.release-sha')
test "$REMOTE_RELEASE_SHA" = "$RELEASE_SHA"

read -r BACKEND_IMAGE_ID WEB_IMAGE_ID <<< "$(
  ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" \
    bash -s -- "$RELEASE_SHA" "$RELEASE_MANIFEST_SHA" "$RELEASE_GUARD_SHA" <<'REMOTE_BUILD'
set -euo pipefail
release_sha=$1
manifest_sha=$2
guard_sha=$3
cd /opt/openqms
test "$(sha256sum .release-manifest | cut -d " " -f1)" = "$manifest_sha"
test "$(sha256sum scripts/check-release-tree.py | cut -d " " -f1)" = "$guard_sha"
python3 scripts/check-release-tree.py verify --root . --manifest .release-manifest >/dev/null
test "$(cat .release-sha)" = "$release_sha"
./scripts/production-compose.sh build >/dev/null
revision_label='{{ index .Config.Labels "org.opencontainers.image.revision" }}'
backend_id=$(docker image inspect openqms-backend:prod --format '{{.Id}}')
web_id=$(docker image inspect openqms-web:prod --format '{{.Id}}')
backend_revision=$(docker image inspect openqms-backend:prod --format "$revision_label")
web_revision=$(docker image inspect openqms-web:prod --format "$revision_label")
[[ "$backend_id" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$web_id" =~ ^sha256:[0-9a-f]{64}$ ]]
test "$backend_revision" = "$release_sha"
test "$web_revision" = "$release_sha"
printf '%s %s\n' "$backend_id" "$web_id"
REMOTE_BUILD
)"
[[ "$BACKEND_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$WEB_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]
readonly BACKEND_IMAGE_ID WEB_IMAGE_ID
export BACKEND_IMAGE_ID WEB_IMAGE_ID
export REMOTE_IMAGE_VERIFY='revision_label='\''{{ index .Config.Labels "org.opencontainers.image.revision" }}'\'' && test "$(docker image inspect openqms-backend:prod --format "{{.Id}}")" = "'"$BACKEND_IMAGE_ID"'" && test "$(docker image inspect openqms-web:prod --format "{{.Id}}")" = "'"$WEB_IMAGE_ID"'" && test "$(docker image inspect openqms-backend:prod --format "$revision_label")" = "'"$RELEASE_SHA"'" && test "$(docker image inspect openqms-web:prod --format "$revision_label")" = "'"$RELEASE_SHA"'"'

unset TEST_DATABASE_URL
test -z "${TEST_DATABASE_URL+x}"
export OPENQMS_TEST_RESOURCE_FILE='<owner-only-registration-file>'
export PG15_CONTAINER="$("$RELEASE_STAGE/backend/.venv/bin/python" -c 'import json,os; print(json.load(open(os.environ["OPENQMS_TEST_RESOURCE_FILE"]))["container_id"])')"
export LOCAL_TEST_PGUSER='<local-test-user>'
export LOCAL_TEST_PGPASSWORD='<local-test-password>'
export LOCAL_TEST_PGHOST=127.0.0.1
export LOCAL_TEST_PGPORT='<registered-loopback-port>'
export LOCAL_TEST_PASSWORD_ENCODED=$(LOCAL_TEST_PGPASSWORD="$LOCAL_TEST_PGPASSWORD" python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["LOCAL_TEST_PGPASSWORD"], safe=""))')
export RELEASE_GATE_DB="qms_test"
export TEST_DATABASE_URL="postgresql+asyncpg://${LOCAL_TEST_PGUSER}:${LOCAL_TEST_PASSWORD_ENCODED}@${LOCAL_TEST_PGHOST}:${LOCAL_TEST_PGPORT}/${RELEASE_GATE_DB}"
PGUSER="$LOCAL_TEST_PGUSER" \
PGPASSWORD="$LOCAL_TEST_PGPASSWORD" \
PGHOST="$LOCAL_TEST_PGHOST" \
PGPORT="$LOCAL_TEST_PGPORT" \
TEST_DB="$RELEASE_GATE_DB" \
TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  make --silent check-test-db TEST_DB="$RELEASE_GATE_DB"

export DATABASE_URL='postgresql+asyncpg://qms:<url-encoded-production-password>@127.0.0.1:15432/qms'
export ORACLE_APP_DIR=/opt/openqms
export CHECK_CMD='PGUSER="$LOCAL_TEST_PGUSER" PGPASSWORD="$LOCAL_TEST_PGPASSWORD" PGHOST="$LOCAL_TEST_PGHOST" PGPORT="$LOCAL_TEST_PGPORT" TEST_DB="$RELEASE_GATE_DB" TEST_DATABASE_URL="$TEST_DATABASE_URL" make --silent -C "$REPO_ROOT" check SDK_PYTHON_BIN="$PYTHON_BIN"'
export TARGET_IDENTITY_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY" && "$PYTHON_BIN" "$REPO_ROOT/scripts/check-oracle-target-database.py"'
export INITIALIZE_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY && ./scripts/production-compose.sh run --rm --no-deps backend python -m app.seed --no-print-credentials"'
export ROLLOUT_CMD='ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY && ./scripts/production-compose.sh up -d --wait backend graph-worker web"'
test "$(git -C "$LOCAL_RELEASE_REPO" rev-parse HEAD)" = "$RELEASE_SHA"
ssh -i "$ORACLE_SSH_KEY" "$ORACLE_SSH_TARGET" "cd /opt/openqms && $REMOTE_RELEASE_VERIFY && test \"\$(cat .release-sha)\" = \"$RELEASE_SHA\" && $REMOTE_IMAGE_VERIFY"
TENANT_MODE=single make deploy-release
cleanup_release_stage
trap - EXIT HUP INT TERM QUIT
```

Die Proxy-Prüfung vor der Veröffentlichung muss auf dem Oracle-Host laufen und die Tailnet-HTTP-Site von Caddy treffen; wird nach Ausstellung des öffentlichen Zertifikats erneut gegen `qms.smartindustry.world` geprüft, muss `SITE_SCHEME=https` ausdrücklich gesetzt werden.

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=100.84.141.70 \
SITE_SCHEME=http \
LOGIN_PASSWORD=Viewer@2026 \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

Diese Instanz nutzt bereits den `qms`-A-Record bei Namecheap BasicDNS und Caddy-HTTPS, öffentlich sind 80/443; die Login-Seite zeigt nur Viewer, Engineer und Manager. `admin` und `groupadmin` bleiben privat, damit Besucher keine Passwörter oder Berechtigungen ändern können; andere Produktivumgebungen sollten dennoch alle Demopasswörter ändern. Öffentliches SSH auf Port 22 bleibt nach Entscheidung des Betreibers vorerst offen; soll es später geschlossen werden, muss zuvor Tailscale-SSH erneut geprüft und eine gesonderte Freigabe eingeholt werden.

### Backup, Wiederherstellung und Rollback

Installation, manuelle Ausführung und Prüfung der Backups erfolgen in der **Shell des Oracle-Hosts in `/opt/openqms`**:

```bash
sudo install -m 0644 deploy/openqms-backup.service /etc/systemd/system/openqms-backup.service
sudo install -m 0644 deploy/openqms-backup.timer /etc/systemd/system/openqms-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now openqms-backup.timer
sudo -u ubuntu OPENQMS_DIR=/opt/openqms \
  BACKUP_DIR=/opt/openqms/backups/postgres \
  RETENTION_DAYS=7 \
  /opt/openqms/scripts/backup-postgres.sh
sudo systemctl list-timers openqms-backup.timer
latest=$(find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' | sort | tail -1)
test -n "$latest"
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

Das Backup-Skript erzeugt täglich einen per `pg_restore --list` geprüften Dump im Custom-Format, veröffentlicht ihn erst nach erfolgreicher Prüfung und bewahrt sieben Tage auf. Eine Wiederherstellung muss nach Stopp der Schreibzugriffe zuerst in eine **neue, leere Datenbank** geprobt werden; das Skript sichert keine Neo4j-/Caddy-Volumes und bietet keine Ein-Klick-Wiederherstellung, die die Produktionsdatenbank überschreibt.

Für ein Code-Rollback wird zunächst im **Mac-Repository** auf eine geprüfte Version gewechselt und der Quellcode mit demselben kontrollierten rsync-Ablauf (Task 14) synchronisiert; anschließend werden die Anwendungsdienste auf dem **Oracle-Host** neu gebaut. Über ein Schema-Rollback ist anhand der Migrationskompatibilität und eines geprüften Backups gesondert zu entscheiden. Die folgenden Schritte behalten die benannten Volumes und enden mit laufenden Diensten und einer `ps`-Prüfung:

```bash
# Mac-Repository: Version wechseln und Quellcode kontrolliert synchronisieren
git checkout '<previous-release-tag>'

# Oracle-Host /opt/openqms: nach der Synchronisierung neu bauen und laufen lassen
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
```

Das vollständige zweisprachige Betriebshandbuch: [Deployment-Leitfaden (Chinesisch)](docs/deployment.md) und [English Deployment Guide](docs/en/deployment.md).

---

## Stand der Module

| Status | Bedeutung |
|------|------|
| ✅ Ausgereift | Frontend und Backend vollständig, mit Demodaten |
| 🔧 In Entwicklung | Backend-API vorhanden, Frontend teilweise umgesetzt |
| 📋 Geplant | Nur Designdokumente, noch nicht entwickelt |

| Modul | Status | Beschreibung |
|------|:----:|------|
| FMEA | ✅ | PFMEA/DFMEA-Editor, Erstellungsassistent mit 7 Schritten, Freigabe-Workflow |
| 8D / CAPA | ✅ | Schrittweise D1–D8, FMEA-Verknüpfung |
| Produktionslenkungsplan | ✅ | Erzeugung aus der PFMEA, Versionsverwaltung |
| Besondere Merkmale | ✅ | CC/SC-Kennzeichnung, Abdeckungsmatrix, Rückverfolgung |
| SPC | ✅ | Regelkarten + Prüfregeln + Prozessfähigkeit |
| MSA | ✅ | GR&R / Bias / Linearität / Stabilität / Kappa |
| Wareneingangsprüfung | ✅ | AQL-Stichproben, Prüflose, AQL-Optimierung |
| Lieferanten | ✅ | Profile + Leistung + Risikokonfiguration |
| SCAR | ✅ | Lebenszyklus mit 5 Status |
| Reklamationen / RMA | ✅ | Reklamationen + Rücksendungen + CAPA-Verknüpfung |
| APQP | ✅ | Gates über fünf Phasen + Gantt-Diagramm |
| PPAP | ✅ | 18 Elemente, Stufen 1–5 |
| Managementbewertung | ✅ | Datenpaket + Maßnahmenverfolgung |
| Internes Audit | ✅ | Drei Auditarten + Feststellungen |
| Kundenaudit | ✅ | Auditplanung + Korrekturabschluss |
| Qualitätsziele | ✅ | Dreistufiger Zielbaum + KPI |
| Lieferantenrisiko | ✅ | Konfiguration der Risikoregeln + Risiko-Dashboard |
| Lieferketten-Risikokarte | ✅ | Mehrdimensionale Risiko-Heatmap |
| Konzernverwaltung | ✅ | Dashboard über mehrere Werke + Vergleich + Konzernlieferanten |
| Produkttyp-Stammdaten | ✅ | Werksübergreifende Klassifizierung der Produktlinien + Filter für semantische Suche |
| ERP-Integration | ✅ | Dashboard + Verbindungskonfiguration + Datensynchronisierung |
| MES-Integration | ✅ | Dashboard + Verbindungskonfiguration + Produktions-/Ausschussdaten |
| PLM-Integration | ✅ | Teile/Stücklisten/Änderungsaufträge + Mock-Konnektor |
| Wissensgraph | ✅ | Neo4j-Visualisierung + FMEA-/PLP-Verknüpfung |
| Änderungsauswirkung | ✅ | Auswirkungsanalyse + Risikobewertung |

---

## Dokumentation

| Dokument | Beschreibung |
|------|------|
| [Betrieb auf dem Raspberry Pi](docs/raspberry-pi.md) | Deployment im lokalen Netzwerk (Deutsch) |
| [Sicherheitsprüfung](docs/sicherheitspruefung.md) | Ergebnisse und offene Empfehlungen (Deutsch) |
| [Deployment-Leitfaden](docs/deployment.md) | Docker / Einrichtung der lokalen Entwicklungsumgebung |
| [Architekturüberblick](docs/architecture.md) | Frontend-/Backend-Architektur, Berechtigungsmodell, Datenfluss |
| [Benutzerhandbuch](docs/user-guide.md) | Anmeldung, Navigation, allgemeine Bedienung |
| [Administratorhandbuch](docs/admin-guide.md) | Benutzerverwaltung, Berechtigungen, Werkszuordnung |
| [Berechtigungsreferenz](docs/permissions.md) | Vollständige Berechtigungsmatrix |
| [Entwicklerhandbuch](docs/development.md) | Entwicklungskonventionen, neue Module hinzufügen |
| [Roadmap](docs/ROADMAP.md) | Entwicklungsplan und Fortschritt |
| [Entscheidungsprotokoll](docs/DECISIONS.md) | Wichtige Architekturentscheidungen (ADR) mit Hintergrund und Auswirkungen |

### Modulhandbücher

| Handbuch | Module |
|------|----------|
| [Planung und FMEA](docs/modules/planning.md) | FMEA, Produktionslenkungsplan, APQP, PPAP, besondere Merkmale |
| [CAPA / 8D](docs/modules/capa.md) | 8D-Schritte, Freigabe-Workflow |
| [Wareneingang und Lieferanten](docs/modules/iqc-supplier.md) | Wareneingangsprüfung, Lieferantenmanagement, Lieferantenrisiko, Lieferketten-Risikokarte |
| [SPC und MSA](docs/modules/spc-msa.md) | Statistische Prozessregelung, Messsystemanalyse |
| [Kundenqualität](docs/modules/customer-quality.md) | Reklamationen, RMA, Kundenaudits, SCAR |
| [Managementbewertung und Qualitätsziele](docs/modules/management-review.md) | Managementbewertung, Qualitätsziele, Dashboard |
| [ERP / MES / PLM](docs/modules/erp-mes-plm.md) | Integration externer Systeme |
| [Wissensgraph und Änderungsauswirkung](docs/modules/knowledge-graph.md) | Visualisierung des Wissensgraphen, Analyse von Änderungsauswirkungen |
| [Konzernverwaltung](docs/modules/group.md) | Mehrere Werke, Konzernlieferanten, Konzernaudits |

---

## Lizenz

MIT-Lizenz – siehe [LICENSE](LICENSE).
Konfiguration und Abnahme des automatischen Deployments: [Oracle-CI/CD-Leitfaden](docs/oracle-automation.md); maßgeblich für den Aktivierungsstand von Produktion und Vorschau sind die tatsächlichen Einträge in PROGRESS.md.
