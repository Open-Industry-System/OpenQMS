# Deployment-Leitfaden

Dieses Dokument behandelt den Produktivbetrieb auf Oracle ARM64 und die lokale Entwicklung. Für die Produktion sind ausschließlich die aktuellen Skripte im Repository maßgeblich; nur in der lokalen Entwicklung darf Docker Compose direkt verwendet werden.

---

## 1. Produktivbetrieb auf Oracle ARM64

### 1.1 Feste Zielumgebung und Topologie

| Punkt | Vorgabe für die Produktion |
|------|----------|
| Öffentliche Domain | `qms.smartindustry.world` |
| Rechenknoten | Einzelner Oracle Cloud Ampere ARM64-Host |
| Mandanten-/Testmodus | `TENANT_MODE=single`, `E2E_MODE=false`: ein Mandant, E2E-Endpunkte in der Produktion deaktiviert |
| Verwaltungszugang | Tailscale-SSH und Abnahme im privaten Netz |
| Öffentlicher Zugang | Namecheap BasicDNS `qms` A → `150.230.197.45` → Caddy `80/443` |
| Datendienste | PostgreSQL 15, Redis 7, Neo4j 5 |
| Anwendungsdienste | backend, graph-worker, web/Caddy |
| KI | Ollama wird zunächst nicht bereitgestellt; in dieser öffentlich beschreibbaren Demo-Instanz dürfen keine echten LLM-/Embedding-API-Schlüssel konfiguriert werden |

Caddy verwendet im festen Produktionsnetz die Adresse `172.30.0.10`; `--forwarded-allow-ips` des Backends vertraut nur dieser Adresse. Das ist die Trusted-Proxy-Grenze für Login-Rate-Limiting und die Ermittlung der Quell-IP. Ändern Sie `172.30.0.0/24`, die Caddy-Adresse oder die Vertrauensliste nicht beliebig; ist eine Änderung unvermeidbar, muss die Proxy-Prüfung erneut laufen.

`/` ist die einzige ausdrücklich öffentliche Ausnahme der Routenschutz-Konvention; `/login` ist der Einstieg zur Anmeldung. `/dashboard` und alle Qualitätsrouten bleiben durch `ProtectedRoute`, RBAC sowie Werks- und Produktlinienbereich geschützt. Eine öffentliche Startseite bedeutet keine öffentlichen Geschäftsdaten. Access-JWTs sind 120 Minuten gültig; ein Passwort-Reset widerruft die Refresh-Sitzungen, ein bereits ausgestelltes zustandsloses Access-JWT kann aber bis zu seinem ursprünglichen Ablauf gültig bleiben.

### 1.2 Umgebungsdatei und Produktions-Wrapper

Die Dateien `.env` / `.env.production` im Wurzelverzeichnis werden von Compose gelesen. Beim ersten Deployment erzeugt `init-production-env.sh` atomar eine `.env.production` mit Rechten `0600`. Kopieren Sie keine echten generierten Werte, DSNs oder Schlüsselinhalte in Dokumente, Tickets oder Chats.

Danach müssen **alle Compose-Befehle in der Produktion** so aufgerufen werden:

```text
./scripts/production-compose.sh <subcommand> ...
```

Der Wrapper legt Projektname `openqms`, Projektverzeichnis, `.env.production` und `docker-compose.prod.yml` fest und entfernt ambient gesetzte Umgebungsvariablen aus der Shell, damit gleichnamige Variablen der aktuellen Shell keine geprüften Produktionswerte überschreiben. Compose-Parameter dürfen nicht am Wrapper vorbei von Hand zusammengesetzt werden.

Im Mac-Betriebsrepository wird zuerst ein unveränderliches Release ausgecheckt; getrackte Dateien und Index müssen exakt `HEAD` entsprechen. Nicht getrackte, fachfremde Plan- oder Referenzdateien zählen nicht zur Deployment-Identität. Das erste Deployment verwendet keine Synchronisation mit Löschen auf der Gegenseite. Die Deployment-Bytes werden nur per `git archive "$RELEASE_SHA"` in eine private Stage mit Rechten `0700` extrahiert und nicht mehr aus dem veränderlichen Arbeitsverzeichnis gelesen; auch der Pfadstrom stammt aus dem Commit-Objekt über `git ls-tree`. Das Manifest erfasst für jeden getrackten Pfad SHA-256 und den Git-Modus `100644`/`100755` und lehnt Symlinks sowie unsichere Pfade ab. Oracle prüft das Manifest selbst, den Verifier, Hash und Modus aller getrackten Dateien sowie die vollständige Menge deploybarer Pfade; ausgenommen ist nur der persistente Laufzeitzustand `.env.production`, `backups/`, `.release-sha` und `.release-manifest`. Zusätzliche oder übrig gebliebene Quell-, Konfigurations- oder Skriptdateien führen zum Abbruch (fail closed). Erst nach erfolgreicher Inhaltsprüfung wird die nicht sensible `RELEASE_SHA` in den Marker geschrieben und zurückgelesen; die Stage wird bei normalem Abschluss, EXIT oder Signal aufgeräumt:

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

Lokaler Migrationscode, Tests/Preflight und die Container auf dem Zielhost müssen aus demselben unveränderlichen Release stammen. Die folgenden Befehle laufen in der **Shell des Oracle-Hosts unter `/opt/openqms`**:

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

Die internen Dienst-DSNs in `.env.production` verwenden Compose-Hostnamen, für PostgreSQL etwa `db:5432`. Migration, Identitätsprüfung und Preflight auf dem Betriebsrechner greifen über einen SSH-Tunnel auf dieselbe Instanz zu und verwenden `127.0.0.1:<tunnel-port>`; der Text unterscheidet sich, die Datenbankidentität zur Laufzeit muss aber identisch sein.

### 1.3 Öffentliche Demo-Konten und eigenständiges Vite

Der Produktions-Build des Web-Frontends veröffentlicht standardmäßig nur den Viewer:

```env
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
```

Die im Browser sichtbaren Viewer-Werte sind schreibgeschützte Demo-Zugangsdaten und kein Geheimnis. `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` ist eine **optionale, standardmäßig leere** Eingabe für den öffentlichen Build; diese Instanz erlaubt nur die zwei zusätzlichen Konten `engineer` und `manager`. Beim Bearbeiten der vorhandenen `.env.production` (Modus `0600`) auf dem Server: Ist der Schlüssel schon vorhanden, den vorhandenen leeren Wert ersetzen; nur anhängen, wenn der Schlüssel in der alten Datei fehlt – und zwar als vollständige einzeilige JSON-Zeile wie unten, niemals als doppelten Schlüssel. `admin` und `groupadmin` bleiben privat und dürfen nicht in diese Variable. Datenbank-, JWT- oder andere generierte Schlüssel nicht neu schreiben und den Dateiinhalt nicht im Terminal oder in Tickets ausgeben:

```env
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=[{"username":"engineer","password":"Engineer@2026"},{"username":"manager","password":"Manager@2026"}]
```

Der neue Wrapper erlaubt, dass der Schlüssel fehlt oder leer ist. Sie können daher zuerst den neuen Quellstand aus dem unveränderlichen Archiv synchronisieren und das Manifest prüfen, dann `.env.production` bearbeiten und vor dem Bau des Web-Images mit `./scripts/production-compose.sh config --quiet` validieren. Fehlt das JSON, bleibt es bei Viewer-only; ein nicht leeres JSON muss genau Engineer und Manager enthalten, sonst schlägt das Frontend geschlossen fehl und zeigt keine Demo-Zugangsdaten an. Bei vollständiger Konfiguration zeigen sowohl `/login` als auch `/login?demo=viewer` Viewer, Engineer und Manager; ein Klick füllt die Felder nur aus und meldet nicht automatisch an. Engineer hat für `user_mgmt` die Stufe 0, Manager nur VIEW=1 – beide können keine Passwörter anderer Konten ändern, aber gemeinsame Qualitätsdaten bearbeiten. Es gibt kein automatisches Zurücksetzen, **es dürfen keine echten Daten und keine echten API-Schlüssel eingegeben werden**. Andere echte Produktivumgebungen müssen die Demo-Passwörter weiterhin rotieren und diesen optionalen Wert leer lassen.

`.env` / `.env.production` im Wurzelverzeichnis werden nur von Compose verwendet; ein eigenständiges Vite liest `frontend/.env*`. Für lokalen Betrieb oder den Build der öffentlichen Startseite können Sie `frontend/.env.local` schreiben:

```bash
cat > frontend/.env.local <<'EOF'
VITE_PUBLIC_DEMO_ENABLED=true
VITE_PUBLIC_DEMO_USERNAME=viewer
VITE_PUBLIC_DEMO_PASSWORD=Viewer@2026
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS=
EOF
npm --prefix frontend run dev
```

Alternativ vor dem Build exportieren. Beim Deaktivieren des Demo-Logins müssen `false` und alle leeren Zugangswerte gemeinsam gesetzt werden, damit keine alten Shell-Werte ins Bundle gelangen:

```bash
VITE_PUBLIC_DEMO_ENABLED=false \
VITE_PUBLIC_DEMO_USERNAME= \
VITE_PUBLIC_DEMO_PASSWORD= \
VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS= \
  npm --prefix frontend run build
```

### 1.4 Reihenfolge der Erstveröffentlichung

#### A. Vorbereitung und Infrastruktur

1. Im Mac-Betriebsrepository gemäß 1.2 dieselbe `RELEASE_SHA` festlegen und synchronisieren, danach das Release auf Oracle unter `/opt/openqms` initialisieren.
2. `.env.production` erzeugen und `./scripts/production-compose.sh config --quiet` prüfen.
3. Nur `db redis neo4j` starten und auf `healthy` warten; backend/web noch nicht starten.
4. Auf dem Mac-Betriebsrechner in einem eigenen Terminal den Tunnel zum Oracle-Ziel aufbauen; der lokale Port ist fest `15432`, um die lokale PostgreSQL auf `5432` nicht zu überdecken.

```bash
ssh -N \
  -i "$HOME/.ssh/<private-key-file>" \
  -L 15432:127.0.0.1:5432 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  ubuntu@100.84.141.70
```

#### B. Zieldatenbank, Testdatenbank und Laufzeit-Identitätsprüfung

Die folgenden Befehle laufen im **Mac-Betriebsterminal, in dem die Synchronisation aus 1.2 ausgeführt wurde und `RELEASE_SHA`/`RELEASE_STAGE` noch gesetzt sind**. Zuerst `cd "$RELEASE_STAGE"`, damit der lokale Code für Migration, Check, Preflight und Zielidentität aus dem unveränderlichen Archiv stammt. Die Stage benötigt Python 3.11, Node 20 und npm, erzeugt aus der `backend/requirements.txt` des Archivs ein frisches venv und führt aus `frontend/package-lock.json` ein sauberes `npm ci` aus; `.venv`, `node_modules`, nicht getrackte oder später geänderte Quellen des ursprünglichen Checkouts werden nicht wiederverwendet.

`DATABASE_URL` zeigt über den lokalen Tunnel `15432` auf die Oracle-Datenbank `qms`. Zuerst ein feindliches ambient gesetztes `TEST_DATABASE_URL` entfernen und ablehnen, dann für die registrierte Datenbank `qms_test` im exklusiven PostgreSQL-Container dieser Aufgabe auf dem Mac die tatsächliche URL bilden und exportieren. Diese URL und die Parameter `TEST_DB`/`PG*` müssen beim ersten stillen `make check-test-db` und im verschachtelten `make check` vollständig identisch sein. Beide Datenbanken müssen vor der Distinct-Prüfung existieren und erreichbar sein; ein Rückfall auf das Anlegen oder Migrieren eines Standard-`qms_test` ist ausgeschlossen. Lokaler Benutzername und lokales Passwort sind Platzhalter ohne Produktionsbezug; xtrace ist aus, make läuft still, und weder lokale noch produktive Passwörter dürfen ausgegeben werden.

Nach erfolgreicher Manifestprüfung auf Oracle und erfolgreichem Wrapper-Build werden die nicht sensiblen sha256-IDs der neu gebauten Images `openqms-backend:prod` / `openqms-web:prod` direkt per `docker image inspect` gelesen; `images -q` von Compose ist ungeeignet, weil es nur Images bereits erstellter Container auflistet. graph-worker nutzt das Backend-Tag mit. Die IDs werden readonly/exportiert und an die aktuelle `RELEASE_SHA` gebunden; der spätere Image-Guard auf dem Zielhost vergleicht die aktuelle Tag-ID, sodass jeder Neubau oder Austausch vor der Migration fail closed abbricht.

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
```

Das Remote-Identitätsskript führt per SSH auf dem Oracle-Host `./scripts/production-compose.sh exec -T db ...` aus und vergleicht PostgreSQL-System-Identifier, Datenbanknamen und OID. Dieses `TARGET_IDENTITY_CMD` läuft vor jeder Migration und kann nicht übersprungen werden.


Release test database ownership: provision a dedicated pgvector/pgvector:pg15 Docker container with a random `openqms.owner` label and a loopback-only published port. Before executing this block, prepare a mode 0600 JSON registration with `container`, full `container_id`, `owner_nonce` matching that label, `image`, `host`, `port`, `test_database` set to `qms_test` matching RELEASE_GATE_DB, and `application_database` set to `postgres`. Set OPENQMS_TEST_RESOURCE_FILE to that file and LOCAL_TEST_PG* to that exact container. Do not register a business database or another task's container. `make check-test-db` verifies the registration before creating/migrating the test database; it must succeed before `make deploy-release` touches the target. Current full acceptance fixtures require `qms_test`; use that name only inside the dedicated container. Never use a shared qms_test instance. SDK build tooling is pinned in the stage venv and CHECK_CMD explicitly selects that interpreter.

#### C. Serielles Release und Initialisierung

Die feste Reihenfolge von `deploy-release.sh` lautet: Distinct-DB-Prüfung → Zielidentität → Migration → Mandantenmigration (falls konfiguriert) → Check → Initialisierung → Preflight → Rollout. Schlägt ein Schritt fehl, wird abgebrochen.

Das erste Deployment befüllt die Datenbank über `INITIALIZE_CMD`; das Release-Skript stellt sicher, dass der Initializer vor dem Preflight läuft. `--no-print-credentials` verhindert, dass privilegierte Demo-Passwörter im Log erscheinen. Bei späteren Releases mit bereits initialisierten Daten kann `INITIALIZE_CMD` entfallen. `deploy-release.sh` wertet die Befehlszeichenketten auf dem Mac-Betriebsrechner aus; Initializer und Rollout müssen daher ausdrücklich per SSH auf Oracle wechseln, nach `/opt/openqms` gehen und den Wrapper auf dem Zielhost aufrufen – nicht das lokale Compose auf dem Mac.

Weiter in `RELEASE_STAGE` arbeiten. `TARGET_IDENTITY_CMD` prüft auf Oracle zuerst erneut Manifest/Baum/Modi, Marker sowie Backend-/Web-Image-ID und erst dann die Datenbankidentität, sodass Abweichungen bei Image oder Quellcode vor der Migration blockiert werden. Initializer und Rollout wiederholen ebenfalls alle Remote-Prüfungen und rufen erst danach den Wrapper auf:

```bash
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

Migration, Check, Preflight und Rollout dürfen nicht in parallel laufende Befehle aufgeteilt werden. `deploy-release.sh` leitet `REPO_ROOT` aus der Stage ab, daher lesen Standard-Migration und -Preflight den Archivcode; das explizite `CHECK_CMD` übergibt dasselbe `TEST_DATABASE_URL`, `TEST_DB` und `PG*` an das verschachtelte make. `DATABASE_URL` dient nur der Zielmigration bzw. dem Preflight; in der Check-Phase werden `DATABASE_URL` und `TEST_DATABASE_URL` an die einzige isolierte Testdatenbank gebunden; der Rollout erhält keine dieser Host-DSNs.

#### D. Abnahme im privaten Netz, gemeinsame Demo-Konten, Proxy-Prüfung und Freigabe ins Internet

1. Zuerst über die Tailscale-Adresse `/`, `/login`, Administrator-Login, fachliche Berechtigungen und Health abnehmen.
2. Die öffentliche Login-Seite zeigt nur `viewer`, `engineer` und `manager`. `admin` und das ebenfalls administrative `groupadmin` bleiben privat, damit Besucher nicht in die Benutzerverwaltung gelangen und Passwörter anderer Konten ändern; ihre Zugangsdaten dürfen nicht in `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` stehen. Engineer hat keine Benutzerverwaltungsrechte, Manager nur Leserechte, beide können aber gemeinsame Qualitätsdaten ändern; es gibt kein automatisches Zurücksetzen, daher keine echten Daten und keine echten API-Schlüssel eingeben.
3. Auf dem **Oracle-Host** die Proxy-/Rate-Limit-Prüfung mit dem aktuellen öffentlichen Viewer-Passwort ausführen und dabei ausdrücklich die Tailnet-Site `http://100.84.141.70` ansprechen. Das Skript verwendet intern den festen Produktions-Wrapper und prüft getrennte Client-Kontingente sowie gefälschte `X-Forwarded-For`-Header. Vor der Zertifikatsausstellung nicht die Standard-HTTP-Prüfung gegen die öffentliche Domain verwenden, sonst lässt die 308-HTTPS-Weiterleitung von Caddy die 401-Prüfung scheitern.
4. Der `qms`-A-Eintrag bei Namecheap BasicDNS zeigt auf `150.230.197.45`; Caddy beantragt und terminiert HTTPS selbst, ohne Cloudflare-Proxy.
5. Öffentlich `https://qms.smartindustry.world/`, `/login`, API-Health und Berechtigungen abnehmen; bei erneuter Proxy-Prüfung gegen die öffentliche Domain muss `SITE_SCHEME=https` gesetzt sein.
6. Öffentliches SSH (Port 22) bleibt auf Wunsch des Eigentümers vorerst offen; vor einer späteren Schließung zuerst HTTPS und Tailscale-SSH im privaten Netz verifizieren und dann die OCI-Eingangsregeln mit gesonderter Freigabe ändern. sshd auf dem Host wird nicht abgeschaltet.

Die folgenden Befehle laufen in der Shell des Oracle-Hosts unter `/opt/openqms`:

```bash
COMPOSE_FILE=/opt/openqms/docker-compose.prod.yml \
SITE_HOST=100.84.141.70 \
SITE_SCHEME=http \
LOGIN_PASSWORD=Viewer@2026 \
  ./scripts/check-proxy-rate-limit.sh
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend web
./scripts/production-compose.sh restart backend
```

### 1.5 Laufender Betrieb

Die folgenden Befehle laufen in der Shell des Oracle-Hosts unter `/opt/openqms`:

```bash
./scripts/production-compose.sh ps
./scripts/production-compose.sh logs --tail=200 backend graph-worker web
./scripts/production-compose.sh logs -f backend
./scripts/production-compose.sh restart backend
./scripts/production-compose.sh exec -T backend python -m app.seed --help
```

Alle `exec`-Beispiele laufen ebenfalls über den Wrapper. `.env.production` sollte nicht per `source` in eine interaktive Shell geladen werden.

### 1.6 PostgreSQL-Sicherung

`backup-postgres.sh` verwendet standardmäßig:

- `OPENQMS_DIR=/opt/openqms`
- `BACKUP_DIR=/opt/openqms/backups/postgres`
- `RETENTION_DAYS=7`

Das Skript führt über `$OPENQMS_DIR/scripts/production-compose.sh exec -T db` ein `pg_dump -Fc` aus und schreibt zunächst eine private Teildatei im selben Verzeichnis; leere Dateien werden abgelehnt, und erst nach `pg_restore --list` im Container wird atomar veröffentlicht. Erst nach erfolgreicher Veröffentlichung werden reguläre `*.dump`-Dateien jenseits der Aufbewahrungsfrist gelöscht; Symlinks, Teildateien und fremde Dateien bleiben unberührt.

In der **Shell des Oracle-Hosts unter `/opt/openqms`** einen täglichen Timer um `03:17` mit Nachholen und zufälliger Verzögerung installieren:

```bash
sudo install -m 0644 deploy/openqms-backup.service /etc/systemd/system/openqms-backup.service
sudo install -m 0644 deploy/openqms-backup.timer /etc/systemd/system/openqms-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now openqms-backup.timer
sudo systemctl list-timers openqms-backup.timer
```

Manuell ausführen und die neueste Datei prüfen:

```bash
sudo -u ubuntu OPENQMS_DIR=/opt/openqms \
  BACKUP_DIR=/opt/openqms/backups/postgres \
  RETENTION_DAYS=7 \
  /opt/openqms/scripts/backup-postgres.sh
sudo systemctl status openqms-backup.service
sudo -u ubuntu find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' -ls
latest=$(find /opt/openqms/backups/postgres -maxdepth 1 -type f -name '*.dump' | sort | tail -1)
test -n "$latest"
./scripts/production-compose.sh exec -T db pg_restore --list < "$latest" >/dev/null
```

Die Sicherung umfasst nur PostgreSQL – nicht Neo4j, die Caddy-Volumes, `.env.production` oder externe KI-Konfiguration. Kopieren Sie die Dumps auf einen kontrollierten externen Speicher und prüfen Sie die Aufbewahrung; DSNs oder Passwörter dürfen nicht im Log erscheinen.

### 1.7 Wiederherstellungsübung und Rollback

Vor einer Wiederherstellung Schreibzugriffe stoppen und den aktuellen Zustand sichern. `pg_restore` muss zuerst in eine **neue, leere Datenbank** wiederherstellen; erst nach Abnahme von Schema, Daten und Anwendung wird der Umstieg geplant. Die laufende Produktionsdatenbank darf nicht direkt überschrieben werden. Ein Dump im Custom-Format ist kein Snapshot des ganzen Hosts; Neo4j lässt sich aus der PostgreSQL-Quelle neu aufbauen, dafür sollte aber eigene Zeit eingeplant werden.

Für einen Code-Rollback zuerst im **Mac-Repository** auf ein verifiziertes Release wechseln und den Quellcode mit demselben kontrollierten rsync-Ablauf wie beim Erst-Deployment nach `/opt/openqms` synchronisieren; danach auf dem **Oracle-Host** die Anwendungsdienste neu bauen:

```bash
# Mac-Repository: Version wechseln und kontrollierte Quellsynchronisation abschließen
git checkout '<previous-release-tag>'

# Oracle-Host /opt/openqms: nach der Synchronisation neu bauen und weiterlaufen lassen
./scripts/production-compose.sh config --quiet
./scripts/production-compose.sh up -d --build backend graph-worker web
./scripts/production-compose.sh ps
```

Benannte Volumes müssen erhalten bleiben. Datenbankmigrationen sind nicht zwingend umkehrbar; ist alter Code mit dem neuen Schema inkompatibel, wird vorwärts korrigiert oder anhand einer verifizierten Sicherung und des Migrations-Runbooks wiederhergestellt. Das Löschen von Volumes ist kein Ersatz für eine Wiederherstellungsstrategie.

---

### 1.8 PR-Vorschau und automatisches Produktions-Deployment

Konfiguration siehe [Automatisches Deployment](oracle-automation.md), [Installation des eingeschränkten Controllers](oracle-production-setup.md) und [Vorschau-Isolation](oracle-preview-setup.md). Interaktive Releases verwenden weiterhin den Produktions-Wrapper; die Automatisierung führt über einen von root installierten, eingeschränkten Controller dieselben Prüfungen für Umgebung, Quellcode, Images und Datenbank aus und ruft das serielle `make deploy-release` auf. Die vollständigen Checks laufen in CI ohne Deployment-Zugangsdaten; in der Release-Phase wird die Erfolgsquittung für den exakten Commit erneut geprüft. Übersprungene Backend-Tests werden wahrheitsgemäß als skipped erfasst, das Browser-Gate verlangt null übersprungene Tests.

Produktions- und Vorschau-Schalter sind anfangs deaktiviert. Vor der Aktivierung müssen die Controller-Installation auf dem Server, zwei rollengebundene eingeschränkte SSH-Schlüssel, die GitHub Environments und eine echte Lebenszyklus-Abnahme abgeschlossen sein. Die Produktionsdomain bleibt `qms.smartindustry.world`, Vorschauen verwenden `pr-<Nummer>.preview.openqms.smartindustry.world`.

## 2. Lokale Entwicklungsumgebung

Die folgenden Befehle dienen nur der Entwicklung und gelten nicht für die Produktion.

### 2.1 Voraussetzungen

| Abhängigkeit | Version |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ |
| Redis | 7+ |

### 2.2 Docker-Entwicklungsstack

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
docker compose ps
```

Den Entwicklungsstack stoppt `docker compose down`. Sollen Entwicklungsdaten zurückgesetzt werden, zuerst die benannten Volumes bestätigen und sie explizit und nachvollziehbar löschen; Produktions-Rollback-Verfahren nicht für Entwicklungs-Resets verwenden und umgekehrt.

### 2.3 Lokales Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Lokale DSNs verwenden `localhost`, Container-DSNs den Dienstnamen `db`. Tests benötigen ein eigenes `TEST_DATABASE_URL`; empfohlen wird die vollständige Prüfung über `make check`.

### 2.4 Lokales Frontend

```bash
cd frontend
npm install
npm run dev
npm run build
```

Vite läuft standardmäßig unter `http://localhost:5173` und leitet `/api` an `localhost:8000` weiter. Die Dateigrenzen für öffentliche Demo-Build-Werte stehen in 1.3.

---

## 3. Konventionen für Datenbankmigrationen

Alembic-Migrationen werden von Hand geschrieben. In der Entwicklung:

```bash
cd backend
alembic current
alembic history
alembic upgrade head
```

In der Produktion dürfen Migrationen nicht unter Umgehung der Identitätsprüfung aus 1.4 und des seriellen Gates `make deploy-release` einzeln ausgeführt werden.

---

## 4. Häufige Probleme

### 4.1 Datenbankverbindung schlägt fehl

- Im Container muss der Hostname `db` lauten; beim Host-Tunnel `127.0.0.1` und den richtigen Port prüfen.
- Produktionsstatus mit `./scripts/production-compose.sh ps db`, Logs mit `./scripts/production-compose.sh logs db`.
- Keine vollständigen DSNs in Fehlerberichte kopieren.

### 4.2 Probleme mit HTTPS oder Proxy-Quelladresse

- Prüfen, dass der `qms`-A-Eintrag bei Namecheap BasicDNS auf die öffentliche Oracle-IP auflöst und das Caddy-Zertifikat gültig ist.
- Prüfen, dass Caddy weiterhin `172.30.0.10` hat und das Backend nur dieser Adresse vertraut.
- Nach Netzwerkänderungen `check-proxy-rate-limit.sh` erneut ausführen.

### 4.3 KI-Empfehlungen nicht verfügbar

Der Produktionsstack lässt Ollama bewusst weg. Zuerst sicherstellen, dass die Qualitätskernprozesse funktionieren; danach trägt ein Administrator auf der KI-Konfigurationsseite einen externen Anbieter ein. API-Schlüssel gehören nicht in dieses Dokument.

### 4.4 Timer wird nicht ausgeführt

`systemctl list-timers openqms-backup.timer` und `systemctl status openqms-backup.service` prüfen. Schlägt auch das manuelle Skript fehl, zuerst prüfen, ob `/opt/openqms/.env.production` lesbar ist und die Prüfung des Produktions-Wrappers besteht; nicht auf direktes Compose ausweichen, um die Prüfung zu umgehen.
