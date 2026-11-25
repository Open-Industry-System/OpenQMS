# E2E Test Suite

Browser full-stack E2E via Playwright against a dedicated docker-compose stack. Manual only — not in CI.

## Run

```bash
make e2e           # up + migrate + seed + playwright test
make e2e-up        # start e2e stack (db/redis/backend/frontend)
make e2e-seed      # re-run deterministic seed (idempotent)
make e2e-down      # down -v (clears e2e DB volume)
make e2e-reset     # down -v + up + migrate + seed
```

Single module: `make e2e TEST_ARGS="--grep m1-core/fmea"`.

## Credentials

The seeded Compose suite has no committed credential template. Supply an authorized local profile only when an explicitly live test requires it; missing provider configuration means that AI-only specs skip with a warning while the non-AI suite remains runnable. Do not put a provider key in shell history, receipts, uploaded artifacts, or a copied source tree.

## Conventions

- Seed known docs use `-E2E-` infix (`PFMEA-E2E-001`); write-flow created docs use `E2E-` prefix at start (`E2E-M1-CAPA-001`). Cleanup never deletes seed.
- Account names/factories come from `/api/e2e/seed-state` — never hardcode in specs.
- Selectors use `data-e2e="..."` attributes; prefer `getByRole`. AI assertions check structure/behavior, never exact text.
- `workers:1`, `fullyParallel:false` (serial — cleanup prefixes must not race).
- E2E endpoints are gated: `E2E_MODE=1` AND `TENANT_MODE != "production"` or they don't load.

## Add a spec

1. Add input fixtures under `frontend/e2e/fixtures/input/` if needed.
2. Write `frontend/e2e/specs/<module>/<name>.spec.ts`; `loginAs(page, role)`; use `data-e2e` testids; `afterAll` → `cleanupByPrefix("E2E-<module>")`.
3. Add `data-e2e` attributes to the production component if missing (testability only).
4. Run `make e2e TEST_ARGS="--grep <name>"` to verify in isolation.

## Geschichtete CI-Abnahme (Task 7)

Diese geschichtete CI ist unabhängig von der manuellen Compose-E2E oben. Sie verwendet ein
einziges PostgreSQL-Testziel mit geprüfter Zugehörigkeit, setzt in den normalen Schichten kein
`E2E_MODE` und leert Provider- und Embedding-Zugangsdaten ausdrücklich. Reset/Seed aus
`make e2e-*` nicht mitbenutzen und deren historische Quittungen nicht als CI-Nachweis verwenden.

### Kontrollierte lokale Einstiegspunkte

In einem frischen Source-Export zuerst `OPENQMS_TEST_RESOURCE_FILE` und genau ein
`TEST_DATABASE_URL` setzen, dann die Make-Ziele schichtweise ausführen:

```bash
make check             # check-backend + check-frontend; ohne browser/live/scanner
make check-backend     # Ziel prüfen, Datenbank anlegen/migrieren, dann deterministisches pytest
make check-browser     # deterministische Chromium-Schutzschicht auf demselben geprüften Ziel
make check-live        # nur ausdrücklich freigegebene Live-Provider-Schicht
make agent-attachment-e2e  # eigenständiger echter ClamAV-Prozess + Host-Browser-Gate
```

`make check-test-db` ist Vorstufe von check/check-backend/check-browser/check-live: Es prüft zuerst die
Zugehörigkeit des Containers, legt dann ausschließlich `*_test`-Datenbanken an und migriert sie.
`make check-browser` verwendet nur das im Projekt installierte Chromium und lädt keinen Browser
herunter. Frontend-Abhängigkeiten müssen im Export per `npm ci` aus der Lockfile installiert werden;
`node_modules` kopieren oder `npm install` stattdessen verwenden ist nicht zulässig. `agent-attachment-e2e`
ist ein eigenständiges Scanner-Gate und nicht Teil von `make check`.

Die lokale Ressourcenregistrierung ist ein JSON ohne Secrets, das für group/world nicht beschreibbar ist
(0644 erlaubt, 0600 empfohlen), mit mindestens `container`, vollständiger `container_id`, `owner_nonce`,
`image`, `host`, `port`, `test_database`, `application_database` und optional `volume`. Der Container
muss das Label `openqms.owner=<owner_nonce>` tragen, der Port muss exakt zur Loopback-URL passen; die
Registrierungsdatei enthält weder URL noch Passwort noch Provider-Konfiguration. Wird lokal zusätzlich
`PG15_CONTAINER` für die Snapshot-Werkzeuge gesetzt, muss es dem registrierten Containernamen oder der
vollständigen ID entsprechen und darf keine CI-Run-/Job-Metadaten enthalten. Die Migrations-Fixture
registriert `OPENQMS_MIGRATION_TEST_DATABASE_URL` erst, nachdem sie ihre eigene temporäre Datenbank
tatsächlich angelegt hat; die Snapshot-Werkzeuge erlauben nur diese registrierte `*_test`-URL oder die
Basis-Testdatenbank, wobei Instanzendpunkt, Benutzer und Zugangsdaten übereinstimmen müssen.
CI-Services verwenden stattdessen `PG15_CONTAINER` und die drei Labels
`openqms.ci.run` / `openqms.ci.attempt` / `openqms.ci.job`; GitHub-Metadaten dürfen nicht gefälscht
werden, um den lokalen Pfad zu nehmen.

### Umgebung, Quittungen und Status

Normale api/browser/scanner-Unterprozesse erhalten nur freigegebene System-/Laufzeitvariablen;
Zugangsdaten `LLM_*`, `OPENAI_*`, `ANTHROPIC_*` und `EMBEDDING_*` werden geleert; die SDK-Variablen
`OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` werden aus der Unterprozessumgebung entfernt statt auf leere
Zeichenketten gesetzt, damit das SDK keinen leeren Wert als echten Endpunkt nutzt. Anwendungsfelder wie
`LLM_BASE_URL` werden weiterhin ausdrücklich geleert; `LLM_TIMEOUT` wird nicht als leere Zeichenkette
injiziert. Live akzeptiert nur ein explizites `--test-profile` oder die Environment-Konfiguration des
Live-Jobs, und das Profil gelangt nur in den Live-Unterprozess; `.env` wird nicht implizit gelesen, und
Proxy- oder ambient gesetzte Provider-Werte werden nicht geerbt. Ist das optionale `LLM_TIMEOUT` nicht
gesetzt oder leer, gilt 30 Sekunden; explizit gesetzt muss es eine ganze Zahl von 1–120 sein. Ein
explizites `OPENQMS_AGENT_BROWSER_EXECUTABLE` löst der Controller zu einem absoluten, geprüften
ausführbaren Pfad auf; nur dieser erlaubte Schlüssel geht an die pytest-Unterprozesse von
browser/live/scanner, und bei fehlendem Cache wird nicht auf einen anderen Browser ausgewichen.

Der Runner speichert rohe JUnit- und Hook-Dateien in einem privaten temporären Verzeichnis und
veröffentlicht nur gefilterte Logs und JSON-Quittungen. Eine Quittung erfasst
selected/passed/failed/errors/skipped/xfail/xpass/deselected/warnings, Befehl, Exit-Code und Dauer. Die
expliziten Gates browser/live/scanner akzeptieren weder skip noch xfail noch xpass; die normale
Backend-Schicht erfasst bestehende umgebungsbedingte Skips wahrheitsgemäß und bezeichnet übersprungene
Fälle nicht als bestanden. Alle Schichten verlangen eine von null verschiedene Anzahl tatsächlich
ausgewählter Tests, eine vollständige Quittung und Exit-Code null.
GitHub setzt für jede Ausführungsschicht ein eigenes Verzeichnis `OPENQMS_TEST_ARTIFACTS` und lädt mit
`always()` die tatsächlichen `*-receipt.json` und gefilterten `*.log` hoch, auch bei Fehlschlag;
Typprüfung und Build des Frontends behalten jeweils tatsächlichen Befehl, Log und Exit-Code (keine
pytest-Zähler). Der Runner zeigt Verzeichnis, Zähler und Exit-Code in der Konsole und bei Fehlschlag die
gefilterte Diagnose. Weder rohe XML-/Hook-Dateien noch Profile/env, Ressourcenregistrierung oder das
ganze temporäre Wurzelverzeichnis hochladen. Lokal kann ein neues dediziertes absolutes Verzeichnis
gesetzt werden; ohne Angabe vergibt der Runner eines, gibt es aus und verwendet keine alten Quittungen.

Der Scanner exportiert vor dem Teardown seines eigenen Compose-Projekts die tatsächlichen Quittungen und
Logs aus dem gestoppten Prozesscontainer nach `<artifacts>/process/`, der Host-Browser schreibt nach
`<artifacts>/browser/`; der Export kopiert nur kontrollierte reguläre Dateien und legt sie als Host-Benutzer
lesbar neu an, ohne die 0600-Eigentümerschaft von root im Container zu übernehmen. Die Prozessquittung
übernimmt nur sichere Beobachtungen aus den Tests: VERSIONCOMMANDS von Daemon/Definitionen, EICAR FOUND,
Parsing-Phasen, Ablehnungen wegen Schadcode/Verschlüsselung/Entpackgrenzen und saubere Downloads; rohes
XML wird nicht kopiert. `cleanup.json` erfasst die Exit-Codes von Export, down und Ressourcenprüfung sowie
die tatsächlich verbliebenen Container/Volumes/Netze, auch bei Fehlschlag. Die Bereinigung beschränkt sich
auf das zufällige Projekt dieses Laufs; der vom Controller registrierte PG-Container, dessen Volume und
Ressourcen anderer Projekte bleiben erhalten.

### Grenzen auf GitHub

Der automatische Workflow läuft bei Pushes auf alle Branches und bei PRs gegen `main`; Fork-PRs erhalten
keine Secrets. Echte Live- und Scanner-Läufe gibt es nur per `workflow_dispatch` und nur auf main: Der
Preflight friert zuerst die main-SHA ein, nachfolgende Jobs checken genau diese SHA aus. Die Summary prüft
SHA, vollständige Zähler, Befehl, Exit-Code und nicht leeres Log der tatsächlichen Quittung; der Scanner
braucht zusätzlich zwei Stufen, tatsächliche Beobachtungen und eine erfolgreiche Bereinigung; ein separat
geschriebener PASSED-Wrapper ersetzt kein echtes Ergebnis. Eine workflow_dispatch-Datei muss zuerst
regulär im Standardbranch main liegen, bevor manuelle Remote-Ereignisse möglich sind. Nur der Live-Job
verwendet das feste Environment `ci-acceptance` mit dessen Freigabe und Testmodellkonfiguration; der
Scanner-Job liest keine Modellzugangsdaten und hängt nicht von diesem Environment ab. Administratoren
konfigurieren nur Freigabeberechtigte für main/Environment und die erlaubte Testkonfiguration; Secrets,
Environments oder Branch-Schutz werden weder in der Dokumentation noch im Workflow stellvertretend
eingerichtet. Fehlt die Berechtigung für push/dispatch oder wurde ein automatisches bzw. manuelles
Remote-Gate nicht ausgelöst, wird `BLOCKED` bzw. `NOT_REQUESTED` erfasst; lokale oder statische
Quittungen ersetzen das nie.

## Owned CAPA outcome-review acceptance (Task 7)

This gate is separate from the seeded Compose suite above. Do **not** use its
reset/seed commands or six synthetic passed-gate reports as positive evidence.
Use an explicitly registered owned target and a dependency-complete Python
interpreter. Database preparation is a separate verified Make step; do not reset
shared data, enable plugins, install a local browser, or copy production config.

From the repository root with `OPENQMS_TEST_RESOURCE_FILE` and the matching
`TEST_DATABASE_URL` set:

```bash
python backend/tests/e2e/capa_outcome_runner.py api
python backend/tests/e2e/capa_outcome_runner.py acceptance --test-profile "$TEST_PROVIDER_PROFILE"
```

`api` runs the outcome API/concurrency and runner tests plus the unmarked,
provider-free HTTP source-denial protection. `acceptance` orchestrates separate
api/browser/live pytest processes: only live gets the validated provider config.
The browser-only diagnostic covers CAPA protection; `make check-browser` selects
all deterministic browser protections. Missing configuration/provider/browser or
an unexecuted required gate is failure, never a skip/pass.

There is no implicit private `run-owned.py`, historical resource registry or
`.env.e2e` discovery. Live config comes only from explicit `--test-profile PATH`
or the explicit live job Environment mapping. The allowed provider fields are
`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`; profile
loading performs no shell evaluation or dotenv interpolation. Ordinary children
cannot inherit provider credentials, vendor SDK endpoint overrides or proxies.
Node/Vite/Chromium receive only the separate runtime allowlist and disposable
fixture logins, never provider/database credentials. Invalid live configuration
fails in preflight rather than silently exercising a fallback.

`owned_outcome_server` provisions two nonce-owned business tenants with real
migrations and TenantSession, normal auth/permissions/get_db/commit, allocated
loopback sockets, and narrow production review-error handlers. Identical report
UUIDs in separate schemas contain distinguishable material. Legacy terminal
protection records are explicitly synthetic, contain no fabricated approval or
gate, and cannot count as a successful lifecycle. An unbound legacy source
correctly returns conflict rather than reconstructing an approval version.

The live report starts at D1 through the real business POST. D3 import/provider,
root-cause verification, implemented D5/D6 material, current D7 dispositions and
real D8 document services precede pending. Empty-source and new-controlled-document
paths are distinct. The latter publishes actual FMEA/CP versions and requires the
provider's actual affected documents and real audit to pass; no invented decision
or skipped source is substituted. Knowledge/lateral services run unmodified on
browser approval. A legitimate empty lateral result is not evidence of a lateral
LLM call. Pending/stale-round assertions remain unverified when the provider blocks.

Chromium logs in normally and captures the actual outgoing displayed revision/
round on approval. Same-document identity switching calls the production login
action with real credentials while a nonce-controlled window holds actual server
response bytes; no forged store authority, synthetic DTO or browser sleep.
Post-close direct HTTP rejection compares material/audit/embedding/outbox snapshots.
Supplement is visibly unreviewed; archive-only supplement keeps existing 400,
while reviewed-core or mixed PUT remains 409. Transaction proofs use actual
PostgreSQL blocking witnesses, including rejection source-row waits.

Timestamped redacted logs/exit JSON and secret-free teardown journals use
`OPENQMS_TEST_ARTIFACTS`, a unique `RUNNER_TEMP` child, or a private temporary
directory, never a fixed historical `.superpowers` path. Fixtures clean only
their recorded tenants, sockets and child processes. Registered PostgreSQL
resources are not stopped by these fixtures; the scanner gate separately cleans
only its own random Compose project. Normal backend hashing explicitly
uses `public.digest`, matching the existing tenant trigger without adding public
to strict search_path. CP creation returns the existing eager-loaded service view
so async serialization does not lazy-load `items` after commit.

### Characteristic integration dedicated endpoint

The opt-in characteristic bootstrap/config keep the original explicitly owned
`127.0.0.1:55432/qms_test` contract. The PR29 integration additionally authorizes
only `127.0.0.1:55433/qms_test`, with identical explicit `DATABASE_URL` and
`TEST_DATABASE_URL` and a genuine `OPENQMS_TEST_RESOURCE_FILE` verified against
Docker's immutable container ID, image, ownership label and port binding via
`tests.ci.owned_resources.verify_owned_instance`. A URL or handwritten registration
alone is insufficient. The Playwright config and read-only outbox check invoke
the same Python guard. This is not permission to launch arbitrary endpoints,
reset retained evidence, or skip normal approvals/version guards. Use a fresh
tag/manifest and identity-verified task-owned worker/backend/UI; shared global
setup/seed/reset remain disabled. Retain both integration and prior containers
and volumes unless their owner explicitly authorizes cleanup.


PR29 separates retained browser evidence on registered55433 from a separately
approved, genuinely registered full-suite-only55434 (`qms_test` in each instance,
independent volumes). Never run the actor bootstrap/browser against55434 or run
whole destructive fixture suites over retained55433 approvals. The browser's
Agent runtime remains OFF: only an actual same-origin exact GET
`/api/agent/tasks/availability`404, attributed to its response URL and accompanied
by an absent Agent-task entry, is an expected capability probe. Raw console,
page-error and HTTP failure records remain intact; CP collaboration404 and all
other unexpected404/500 still fail. Existing intentional PFMEA409 handling is
unchanged. The diagnostic helper lives only in `frontend/e2e/helpers/` and is
shared with focused unit tests, not shipped as application behavior.


### Pflichtabnahme R5 D5

Responses-Erweiterung vom 2026-11-15: Der feste Katalog enthält zusätzlich 8 Knoten für Migration und
Kompatibilität des Paarprotokolls sowie 10 Knoten für die native Responses-Kette; aktuell sind es
portable migration 37, native API 68 und native browser 2, insgesamt 107 Pflichtknoten. Die normale CI
verwendet weiterhin ein deterministisches Modell; echte dedizierte OpenAI-Zugangsdaten werden nur in
ein freigegebenes, separates CLOUD-Versuchs-Backend injiziert und gelangen nie in CI, Vite oder
Plugin-Umgebungen.

R5-Prozess-, Modell- und Migrationsknoten stehen in `backend/tests/ci/r5_required.py`; portable api muss
die Migrationen ausführen, r5-api die nativen Prozess-/Modellknoten. `test_r5_d5_ui.py` und
`test_r5_d5_browser.py` führen in der Schicht r5-browser jeweils ihre echte Chromium-Spec aus. Der
Runner gleicht die feste Knotenmenge anhand von JUnit classname/name ab, einschließlich Duplikaten,
Fehlschlägen und Skips; erfolgreiches Sammeln oder andere bestandene Tests der normalen Schichten ersetzen
das nicht. Der Vertrag gilt, wenn das gesamte tests-Verzeichnis oder die betreffenden Dateien ausgewählt
werden; Einzelknoten werden direkt mit pytest_bootstrap debuggt, und Teilquittungen aus dem Debugging
gelten nicht als bestandene Schicht. Bei Änderungen an parametrisierten Knoten den festen Katalog und die
tatsächliche Sammlungs-/Schichtprüfung in `test_layer_selection.py` mit aktualisieren.

Normale API-/Browser-Unterprozesse verwenden die bestehende Umgebungs-Allowlist, leeren die
Provider-/Embedding-Konfiguration und verwerfen R5-Plattformzugangsdaten und private Pilotpfade; die
R5-Fixture erzeugt nur ein synthetisches Loopback-Modell und eine dedizierte kurzlebige Sandbox-Freigabe
und liest keine echte Deployment-Konfiguration. Die kontrollierte Sandbox benötigt zur tatsächlichen
Ausführung sandbox-exec unter Darwin; nicht unterstützte Hosts lehnen weiterhin ab, und ein Skip ersetzt
kein bestandenes R5. Die aktuelle Ubuntu-CI ist kein Nachweis für eine Darwin-Pilotausführung; das
vollständige R5-Gate muss auf einem freigegebenen Host mit registrierter dedizierter PostgreSQL,
installiertem Chromium und Darwin-Executor laufen.

Wiederholungen der neuen Schichten verwenden dieselbe geprüfte Ressource und eine serielle
Datenbankabnahme. Rohe HTTP-/Browser-Logs, temporäre Zertifikate, Datenbankverbindungen und
Richtliniendateien bleiben in privaten Verzeichnissen; Übergabeprotokolle enthalten nur Befehle, Knoten,
Zähler, Versionen und Verweise auf Sicherheitskontrollen. Echte LOCAL-/CLOUD-Modellversuche warten auf
registrierte Endpunkte und dedizierte Zugangsdaten und werden nicht wegen eines bestandenen
deterministischen Loopbacks abgehakt.


`ci_r5_native` trennt native Tests ausdrücklich ab. Portable api/browser schließen diesen Marker aus; die
eigenen Schichten `r5-api`/`r5-browser` verlangen anhand des festen Katalogs die tatsächliche Ausführung
jedes Knotens. Unter Darwin ergänzt `make check` automatisch `check-r5-api` und `make check-browser`
automatisch `check-r5-browser`; alternativ führt `make check-r5-native` beide Schichten seriell aus. Auf
nicht unterstützten Hosts schlägt der explizite native Einstieg direkt fehl, ohne Datenbankzugriff oder
Umgebungs-Skip; dieses Verhalten ist offline getestet.

Der R5-macOS-Pilot verwendet den separaten manuellen Workflow `.github/workflows/r5-native.yml`
(`R5 macOS pilot acceptance`) und akzeptiert nur `workflow_dispatch` auf main; `Test OpenQMS` startet
diesen Job bei normalen PRs und main-Pushes nicht mehr. Normale Linux-Prüfungen für Backend, Browser,
Migration, Berechtigungen und SDK laufen weiter; die bestehenden 8 Pflichtchecks für PRs bleiben
unverändert. Diese Anpassung betrifft die reguläre CI für das Linux-Deployment-Ziel und ändert nichts
daran, dass der kontrollierte R5-Executor auf Darwin/dev beschränkt und standardmäßig deaktiviert ist.

Liegt der Workflow in main, wird er für eine Abnahme des macOS-Piloten manuell gestartet:

```bash
gh workflow run r5-native.yml --ref main --repo Open-Industry-System/OpenQMS
```

Der Ubuntu-Preflight prüft Ereignis, main-Ref und SHA-Format und friert den main-Commit dieses Dispatch
ein; erst danach kann `[self-hosted, macOS, openqms-r5-sandbox]` zugewiesen und genau die eingefrorene
SHA ausgecheckt werden. Ein Dispatch auf einem Feature-Branch schlägt fehl und bringt dessen Code nicht
auf den nativen Runner. Der manuelle Workflow behält den Jobnamen `r5-native`, 45 Minuten Timeout, den
vollständigen festen Katalog aus nativer API + Chromium, eine jobgebundene exklusive PG15 sowie die
Ablehnung bei Fehlschlag, Fehlen oder Skip; ohne passenden Runner wird gewartet, ohne Bundle schlägt der
Lauf fehl. Die manuelle Pilotabnahme ist ein eigenständiges Ergebnis: Eine erfolgreiche normale
Linux-CI bedeutet weder eine bestandene native macOS-Abnahme noch eine umgesetzte Linux-Sandbox.

Runner-/Hook-Konfiguration und native Remote-Ausführung sind weiterhin **PENDING / NOT RUN**: Ein
Maintainer muss diesen dedizierten Runner einrichten und Projektabhängigkeiten, setuptools 79.0.1, Node,
Chromium, sandbox-exec, Docker und eine gecachte PG15 vorinstallieren. Der Hook jedes Jobs muss eine neue
exklusive PG15-Instanz anlegen und unter `$RUNNER_TEMP/openqms-r5-native-job.json` ein nur für den
Eigentümer lesbares (0600) JSON schreiben: `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_JOB`,
`created_unix`, `owner_nonce`, `OPENQMS_TEST_RESOURCE_FILE`, `TEST_DATABASE_URL`. Die
Registrierungsdatei wird weiterhin nach dem bestehenden owned_resources-Vertrag auf vollständige
Container-ID, Owner-Label, Image, Loopback-Port und dedizierte Testdatenbank geprüft. Das Bundle muss zum
tatsächlichen Job passen, innerhalb von 15 Minuten erstellt worden sein und denselben Owner wie die
Registrierung haben; gemeinsame oder historische Ressourcen werden nicht als Ausweichlösung akzeptiert.
Der Einstieg liest weder dotenv noch echte Provider, sucht keine Ressourcen und legt keine an oder löscht
sie; jeder Hook behält oder entsorgt registrierte Ressourcen exakt nach seinem eigenen Lebenszyklus. Ein
nicht konfigurierter Runner gilt nicht als bestanden. Hochgeladen werden nur die vorhandenen gefilterten
Logs und Kontrollquittungen, nicht Bundle, Registrierung, Zugangsdaten oder rohe Screenshots.


Die exklusive Datenbank dieser Runde darf für den registrierten Owner einen zufälligen `*_test`-Namen
tragen; die Helper für Embedding- und unabhängige Transaktionstests behalten die ursprüngliche explizite
`qms_test`-Konfiguration und prüfen andere Namen zusätzlich über Containerzugehörigkeit und tatsächliche
Datenbankidentität. Die Beschränkung des characteristic-Browser-Bootstraps auf den dedizierten Endpunkt
ändert sich dadurch nicht. Wenn `mig_db_url` nach dem Anlegen seines eigenen
`qms_migtest_<32hex>_test` vorübergehend DATABASE_URL setzt, stellt der Helper die Konfiguration der
Elterndatenbank nur dann aus der geprüften Kopie wieder her, wenn Verbindungsidentität, fehlende Query,
Treiber und exakte registrierte URL mit der registrierten Elterndatenbank übereinstimmen; die tatsächliche
Umgebung wird nicht umgeschrieben, beliebige Geschwisterdatenbanken sind nicht erlaubt, und keine
Verbindung, kein Name und kein libpq-Schutz wird entfernt.
