# Entwicklerhandbuch

> Kontrollierte Aufgabenanhänge (R4b-2) sind standardmäßig deaktiviert; tatsächliches Scannen und lokale Abnahme beschreibt die [Anleitung zu privaten Aufgabenanhängen](development/agent-task-attachments.md). Diese Anleitung ist keine Freigabe für produktiven Objektspeicher oder Datenabfluss.

Dieses Dokument richtet sich an Entwickler von OpenQMS und beschreibt Projektkonventionen, Entwicklungsablauf und das Hinzufügen neuer Module.

---

## 1. Backend-Konventionen

### 1.1 Code-Struktur

```
backend/app/
├── api/           # Routen-Handler (dünne Schicht)
├── services/      # Geschäftslogik
├── models/        # SQLAlchemy-ORM-Modelle
├── schemas/       # Pydantic-v2-Request-/Response-Schemas
├── core/          # Sicherheit, Dependency Injection, Berechtigungen, Werksbereich
├── state_machines/ # Zustandsautomaten (FMEAState, EightDState usw.)
├── main.py        # FastAPI-Einstieg
└── seed.py        # Seed-Daten-Skript
```

### 1.2 Muster der Anfrageverarbeitung

```
API-Schicht (api/*.py)
  ├── Anfrageparameter parsen
  ├── Service-Schicht aufrufen
  ├── ValueError abfangen → HTTPException
  └── Antwort zurückgeben

Service-Schicht (services/*.py)
  ├── Geschäftslogik
  ├── Datenbankoperationen
  ├── AuditLog manuell schreiben
  └── ValueError werfen (wird in der API-Schicht umgewandelt)
```

**Wichtige Konventionen**:
- Die API-Schicht enthält keine Geschäftslogik.
- Die Service-Schicht schreibt `AuditLog` manuell, kein automatisches Audit.
- Listen-Endpunkte liefern einheitlich `{ items, total, page, page_size }`.
- Fehler werden per `raise ValueError("Fehlermeldung")` geworfen und in der API-Schicht einheitlich umgewandelt. Neue benutzersichtbare Backend-Meldungen gehören in den Katalog `backend/app/i18n/messages.json`.

### 1.3 Berechtigungsprüfung

```python
# API-Schicht: require_permission als Dependency verwenden
from app.core.permissions import require_permission, Module, PermissionLevel

@router.get("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.VIEW))])
async def list_fmea(...):
    ...
```

### 1.4 Datenbankmigrationen

Die Plattformkette verwendet `alembic.ini`; die Mandantenkette `alembic_tenant.ini` und darf nur über `MaintenanceContext.run_migration` mit exklusiver Wartungssperre auf der übergebenen Verbindung ausgeführt werden. ORM-`create_all`, manuelles stamp oder das Kopieren der neuesten public-Historie ersetzen die Mandantenkette nicht. Das bestehende `tv001_business_snapshot` bleibt unveränderlich; neue Geschäftstabellen brauchen sowohl ein public-Inkrement als auch ein eigenes Mandanten-Inkrement.

Der Neuaufbau von Testmandanten zeigt standardmäßig nur eine Vorschau: im Backend `python -m app.cli.rebuild_test_tenants --inventory /path/inventory.json --compose-project <project>` ausführen. Das Inventar muss `{"test_only":true,"targets":[{"tenant_id":"UUID","slug":"slug","schema_name":"tenant_slug","generation":1,"status":"active"}]}` lauten und darf keine Zugangsdaten enthalten. Nur wenn Testdaten ausdrücklich verworfen werden sollen, außerhalb des production-Modus und auf einer `_test`-Datenbank `ALLOW_TEST_TENANT_REBUILD=1` setzen und `--execute --confirm discard-test-data` anhängen; das Passwort wird interaktiv abgefragt. Das Programm prüft, dass vorhandene backend- und graph-worker-Container beendet sind, und verlangt, dass keine anderen Datenbankclients verbunden sind; es stoppt keine Dienste und beendet keine Verbindungen. Nach einem Fehlschlag oder Wartungsmarker das exakte Inventar aktualisieren und erneut versuchen; ein normales `resume_tenant` umgeht keine Belege für einen fehlgeschlagenen Neuaufbau. Automatische Abnahmen verwenden nur von Fixtures angelegte und wieder bereinigte eigene Datenbanken und bauen keine Benutzerumgebungen neu auf.

Migrationen werden **von Hand** geschrieben, nicht automatisch generiert:

```bash
# Neue Migrationsdatei anlegen
alembic revision -m "add_new_table"

# Migrationen anwenden
alembic upgrade head

# Eine Version zurück
alembic downgrade -1
```

### 1.5 Basis-Schnittstellen für Agent-Aufgaben

Der Benutzereinstieg von R1 ist `/api/agent/tasks` (anlegen, paginierte Liste, Detail, Nachricht anhängen), der Administratoreinstieg `/api/admin/agent-plugins` (registrieren, Liste/Detail, aktivieren/deaktivieren, rotieren, langfristige Grants). Die Schnittstellen werden über `AGENT_TASK_RUNTIME_ENABLED` gesteuert und liefern im standardmäßig deaktivierten Zustand 404. R2 umfasst Lauf-Übernahme durch Plugins, Fähigkeitserkennung, geordnete Nachrichtenübernahme/-bestätigung, D4-Metadatenabfrage/-Receipt, Schreiben von Ereignissen/Ergebnissen und das Lesen historischer Ergebnisse durch Benutzer; zwei Abfragerunden in einem separaten Prozess und die abschließende vollständige Prüfung sind bestanden. Die Berechtigungen im Detail stehen in der [Berechtigungsreferenz](permissions.md).

Registrierungs- und Rotationsantworten liefern das Installations-Secret genau einmal; Abfrage-DTOs geben weder Secret noch Hash zurück. Langfristige Grants sind standardmäßig deaktiviert, die Aktivierung prüft den serverseitigen Fähigkeitskatalog und wirkt nur im DIRECT-Kontext; der Installationsschalter ändert nicht die DENY-Erklärung der CAPA-Standard-Baseline. Administrator-Services verwenden die Transaktion des Aufrufers, die API committet explizit; Aufgabenerstellung und Nachrichtenanhang committen fachliche Metadaten und Sicherheitsaudit jeweils atomar in ihrem eigenen Service. Eine erfolgreiche Nachrichtenantwort bedeutet „eingereiht“; R1 liefert keinen Text an Plugins oder Modelle. Mandantenfähige Tests müssen eine tatsächlich gebundene TenantSession verwenden und dürfen Isolation nicht mit einer öffentlichen Session plus info simulieren.

Die Lauf-Übernahme akzeptiert nur Installations-ID, Installations-Secret und den aktuellen Übernahmeschlüssel, keine Benutzer-, Schema- oder Berichts-IDs. Die Antwort enthält Aufgaben-/Lauf-ID, ein kurzlebiges Token und Lease-Informationen; Folgeaufrufe verwenden das eigene Lauf-Token und prüfen jedes Mal aktuelle Berechtigungen und Lease. Die Beispielkette verwendet einmalige synthetische Daten und serverseitige Testdeklarationen; die vertrauenswürdige Deployment-Richtlinie ist standardmäßig leer, und weder Plugin-Manifest noch Request-Header können die Auslieferung selbst aktivieren.

Die R3-Schnittstellen für Benutzer-control und Plugin-finish sind abgenommen: Anfragen tragen weder Client-Autorisierung noch Zieländerungen; Status, Invalidierung der Zugangsdaten, Aktivitätszeiger und Audit werden unter der Sperrfolge INSTALL→TASK→RUN atomar committet. Beide realen Commit-Reihenfolgen von Abschluss/Anhang und der Rechteentzug am Ende sind regressionsgetestet. Checkpoints, streng begrenzte history und das Wiederaufnehmen ab dem neuesten sicheren Checkpoint sind abgenommen; die Übernahmeantwort enthält zusätzlich accepted_message_seq/has_resume_checkpoint. Aktivitätsfenster und Installationsverzeichnis sind abgenommen, die betroffene Gruppe mit 72 Tests bestand ebenso wie die zweistufige Nachprüfung; die einheitliche Seitenleiste ist abgenommen (78 fokussierte Tests sowie Typprüfung/Build bestanden). Bedienelemente lesen den zuletzt beobachteten Lauf/Epoch, Netzwerk-Wiederholungen behalten ursprüngliche Parameter und Schlüssel, und eine Ablehnung durch den Katalog zieht Inhalte sofort zurück. Das eigenständige Beispiel unterstützt Übernahme, historische Eingaben, Checkpoints und das Abschlussprotokoll; echte HTTP-/Prozesstests und acht Browser-Szenarien haben Spezifikations- und Qualitätsprüfung bestanden; lange Zeichenketten und der Erhalt des Zustellstatus beim Abbrechen sind per echter Regression und unabhängiger Prüfung bestätigt. Der abschließende eingefrorene Stand: Backend 2731 passed / 4 skipped / 3 xfailed / 2 xpassed, Frontend 78 Tests sowie Typprüfung/Build und Typprüfung der dedizierten E2E bestanden; die Einmal-Datenbank wurde bereinigt.

### 1.6 Eigenständiges D4-Metadaten-Plugin (Beispiel)

Dieser Abschnitt bewahrt die Beschreibung des festen Worker-Protokolls und der Fixture-Abnahme aus R2/R3. Ein R4a-Versuch unter Normalkonfiguration verwendet eine sichere Zugangsdatei und das feste CLI, siehe [Anleitung zum lokalen Versuch](development/agent-local-trial.md); die Umgebung darf nicht über Änderungen an DIRECT oder dem vertrauenswürdigen Auslieferungskatalog geöffnet werden.

Das [eigenständige Plugin](../backend/examples/readonly_8d_plugin.py) verwendet die Python-Standardbibliothek, übernimmt per HTTP einen Lauf, bestätigt Nachrichten in Reihenfolge, liest Berichtsmetadaten und fragt anschließend mit der in Runde eins gelieferten Berichts-ID die Verifizierungsdatensätze ab. Zwei serverseitige Receipts verknüpfen jeweils Ereignis und restricted-Ergebnis. Das Beispiel liest die normierte Phase `D4_ROOT_CAUSE` und ist mit `D4_ANALYSIS` aus alten Abnahmedaten kompatibel. Bei der Wiederaufnahme wird zuerst das serverseitig bestätigte Eingabepräfix seitenweise (höchstens 20 Einträge pro Seite) neu gelesen und erst dann werden neue Nachrichten übernommen, ohne doppeltes ACK; Nachrichtentexte werden nicht als Code oder Fachbefehl ausgeführt; Metadatenstatistiken bestimmen keine Grundursache und ersetzen keine Beweisprüfung.

Die Laufkonfiguration kommt aus der Umgebung; das Beispiel akzeptiert weder Auswahl eines Startberichts noch Benutzer-Token:

| Umgebungsvariable | Zweck |
|---|---|
| `OPENQMS_API_BASE_URL` | Nur Loopback-HTTP/HTTPS-Origin, ohne Pfad, Query, Fragment oder Benutzerinformation. |
| `OPENQMS_INSTALLATION_ID` | UUID der registrierten Installation. |
| `OPENQMS_INSTALLATION_SECRET` | Einmalig ausgegebenes Installations-Secret. |
| `OPENQMS_CLAIM_KEY` | Stabiler Schlüssel der aktuellen Lease-Übernahme, Standard `readonly-8d-v1`. |
| `OPENQMS_TENANT_SLUG` | Optionales Entwicklungs-Mandantenrouting; keine Berechtigung und keine vertrauenswürdige Deployment-Erklärung. |
| `OPENQMS_READONLY_CHECKPOINT` | `off` (Standard) oder `save`; speichert aktuelle Serverquelle und bestätigte Position. |
| `OPENQMS_READONLY_FINISH` | `off` (Standard) oder `completed`; leert zuerst die Eingaben, fordert dann den Abschluss an und lehnt bei konkurrierendem Anhang sicher ab. |

Nach der Konfiguration aus dem Repository-Wurzelverzeichnis `python backend/examples/readonly_8d_plugin.py` ausführen. Das Beispiel ignoriert Proxy-Umgebungsvariablen, lehnt alle HTTP-Weiterleitungen ab und gibt nur die UUIDs erfolgreicher Datensätze und den Abschlussstatus aus; bei Fehlern erscheint eine feste Meldung ohne Schlüssel, Token, Nachrichten oder Fehlerantworttext. Schlüssel für Ereignisse, Ergebnisse und Checkpoints erhalten ab späteren Epochs die Runde, die Schlüssel der ersten Runde bleiben kompatibel; ein erneuter Start im selben aktiven Epoch bedeutet nicht, dass ein beliebiger interner Pipeline-Zustand wiederhergestellt wird. Historische Eingaben umfassen höchstens 1000 Seiten, neue Eingaben im Abschlussmodus höchstens 1000 Stapel; standardmäßig wird nur ein Stapel übernommen. Der offizielle Katalog bleibt DENY, der Standardschalter ist aus; der [Originalprozesstest](../backend/tests/e2e/test_readonly_agent_process.py) und der [Wiederaufnahme-/Browsertest](../backend/tests/e2e/test_agent_readonly_resume_process.py) konfigurieren serverseitige synthetische Erklärungen nur innerhalb eines vollständigen Einmal-Mandanten.

Die Browserabnahme startet über eine Backend-pytest-Fixture eigene Backend-, Vite- und Plugin-Unterprozesse auf zugewiesenen lokalen Ports mit der [dedizierten Playwright-Konfiguration](../frontend/playwright.agent.config.ts) und ruft weder gemeinsame E2E-Initialisierung noch Reset oder Container-Lebenszyklus auf. Frontend-Abhängigkeiten, Playwright und Chromium müssen vorab installiert sein; `OPENQMS_AGENT_BROWSER_EXECUTABLE` gibt den Pfad zum installierten Browser an, fehlt er, schlägt der Test ausdrücklich fehl, ohne automatische Installation oder Skip. Den Einmal-Datenbank-Runner aus diesem Abschnitt mit `tests/e2e/test_agent_readonly_resume_process.py tests/e2e/test_readonly_agent_process.py -q -rs` verwenden; zusätzlich im Frontend `node_modules/.bin/tsc -p tsconfig.e2e.json` ausführen. Die Abnahme konfiguriert keine Modellzugangsdaten: Der 422-Hinweis „LLM-Zugangsdaten nicht konfiguriert“ der bestehenden D4-Empfehlungsschnittstelle bleibt bestehen, die Schnittstelle der Verifizierungsdatensätze muss 200 liefern; der Hinweis gilt nicht als Fehlschlag des Nur-Lese-Agenten.

### 1.7 Lokaler Metadaten-Versuch unter Normalkonfiguration

R4a umfasst eine strikte Startrichtlinie, ein exaktes serverseitiges Profil, regulären Administrator-Grant/Benutzerkatalog/feste Zielerstellung, gebundenes JWT mit Frist, frühe Prüfung des Loopback-Einstiegs, dauerhaften Epoch-Widerruf und einen festen stdlib-Starter. Versuche nur unter dev, auf einem vertrauenswürdigen lokalen Host, mit Loopback, einem Worker und ohne Proxy-Vertrauen; Standardschalter und Baseline-DENY bleiben unverändert, es gibt keine Migrations-, Text-/Anhangs-, Modell- oder fachlichen Schreibfähigkeiten. `python -m app.cli.agent_local_trial` bietet `check-policy`, `run` und `revoke`, greift nicht direkt auf die Datenbank zu und hält keine Wartungsrechte; Installationsschlüssel und Administrator-JWT werden aus separaten sicheren Dateien gelesen, nicht aus argv oder Logs. Korrekte Registrierung, exakte Deklaration, eigener Neustart, begrenzter Grant, Ablauf/Rotation sowie die Semantik von vorübergehendem disable und dauerhaftem revoke beschreibt die [Betriebsanleitung](development/agent-local-trial.md).

Prozess- und Browser-Fixtures der Normalkonfiguration laufen durch echtes lifespan/get_db, Administrator-/Benutzer-APIs und das feste CLI, ohne Fähigkeitskatalog, authorize oder delivery zu ersetzen; sie verwenden eine eigene, zufällig benannte, vollständig migrierte Testdatenbank, zugewiesene Ports und das installierte Chromium. Ausführen: `tests/e2e/test_agent_local_trial_process.py tests/e2e/test_agent_local_trial_browser.py`; die acht alten Szenarien wählen ausdrücklich `readonly-sidebar.spec.ts`, die neuen `local-trial.spec.ts`; die dedizierte Konfiguration unterstützt beide und erzeugt keine Skip-Ergebnisse. Ein lokales Bestehen schließt die Gates für R4b bzw. Produktion nicht.

### 1.8 Interner eingeschränkter D4-Textkandidat für Mitarbeitende

`CAPA_D4_TEXT_PREVIEW_ENABLED` ist standardmäßig false und steuert nur die drei Endpunkte availability/preview/version für normale Mitarbeitende; ist er aus, wird vor Mandant/Body/Datenbank mit 404 geantwortet, ohne R4a-Laufzeitschalter, Katalog oder festen Worker zu verändern. `capa_current_access` teilt die Regeln für aktuellen Namespace, Identität und Objekt; alte Laufzeit-Hooks bleiben bestehen. Der reine Redactor liest weder Datenbank noch Netz, das Budget für den Textschnappschuss wird vor dem Laden geprüft, aktuelle Berechtigung und Version der ausdrücklichen FMEA-Quelle werden unabhängig nachgeprüft, und ein Erfolg schreibt nur ein Audit ohne Wörter oder Text. Kurzlebige Kandidaten sind fest restricted und erhalten weder Herabstufung noch Originaltext-Ausnahme noch Plugin-/Modell-/Veröffentlichungsfreigabe.

Mitarbeitende erzeugen den Kandidaten ausdrücklich auf der D4-Seite; ein schreibgeschützter Dialog zeigt reinen Text an und prüft im Abstand von 2 Sekunden (höchstens 30 Sekunden) auf Widerruf. Die erfolgreiche Schnittstelle liest nur drei freigegebene Felder; Verifizierungsergebnis/-methode/-personen/-anhänge gehören nicht zum Textschnappschuss. Eine routeneigene Validierungsabbildung verhindert, dass die standardmäßige 422-Antwort Eingaben zurückspiegelt; Axios fügt beim festen preview-Pfad keinen factory-Parameter ein und sendet private Begriffe nach einem 401-Refresh nicht erneut. Bedienungsgrenzen siehe [Anleitung](development/capa-d4-text-preview.md). Die neue Browser-Fixture wählt `d4-text-preview.spec.ts` und verwendet ebenfalls eine eigene vollständig migrierte Datenbank, zugewiesene Ports und das installierte Chromium; die beiden bestehenden Agent-Skripte werden weiterhin ausdrücklich ausgewählt.

---

## 2. Frontend-Konventionen

### 2.1 Code-Struktur

```
frontend/src/
├── api/           # Axios-Instanz + API-Funktionen pro Modul
├── components/    # Layoutkomponenten (AppLayout) + gemeinsame Komponenten
├── hooks/
│   └── usePermission.ts  # Berechtigungs-Hook
├── pages/         # Seitenkomponenten nach Modul
├── store/
│   └── authStore.ts      # Zustand-Store für Auth
├── types/
│   └── index.ts           # Globale TypeScript-Interfaces
├── utils/
│   ├── fmea.ts             # AIAG-VDA-AP-Tabelle
│   └── fmeaTable.ts        # Umwandlung graph↔spreadsheet
└── App.tsx        # Routendefinition + ProtectedRoute
```

### 2.2 Routen registrieren

Neue Module brauchen eine Route in `App.tsx` mit Modulschutz über `ProtectedRoute`:

```tsx
<Route path="/my-module" element={<ProtectedRoute requiredModule="my_module"><MyModulePage /></ProtectedRoute>} />
```

### 2.3 Berechtigungs-Hook

In Seitenkomponenten steuert `usePermission` die Sichtbarkeit von Schaltflächen und Formularen. Sichtbare Texte ohne Übersetzungsschlüssel laufen über `tr(de, en)` / `useTr()`:

```tsx
const { canView, canCreate, canEdit, canApprove } = usePermission();

// Schaltfläche „Neu“ ausblenden
{canCreate("fmea") && <Button onClick={handleCreate}>{tr("Neue FMEA", "New FMEA")}</Button>}

// Eingabefeld deaktivieren
<Input disabled={!canEdit("fmea")} />
```

### 2.4 API-Client

Jedes Modul erhält eine eigene Datei unter `api/`:

```typescript
// api/myModule.ts
import client from './client';

export const listMyModule = (params: any) => client.get('/api/my-module', { params });
export const getMyModule = (id: string) => client.get(`/api/my-module/${id}`);
export const createMyModule = (data: any) => client.post('/api/my-module', data);
```

### 2.5 Build und Prüfung

```bash
cd frontend
npm run build    # TypeScript-Typprüfung + Vite-Build
npm run lint     # ESLint
npm run dev      # Entwicklungsserver (:5173, Proxy /api → :8000)
```

---

## 3. Neues Modul hinzufügen

### 3.1 Backend-Schritte

1. **Modell anlegen**: `my_module.py` unter `models/`, erbt von `Base`.
2. **Modell registrieren**: in `models/__init__.py` importieren und in `__all__` aufnehmen.
3. **Schema anlegen**: `my_module.py` unter `schemas/` mit Request-/Response-Schemas.
4. **Service anlegen**: `my_module_service.py` unter `services/` mit CRUD + AuditLog.
5. **API anlegen**: `my_module.py` unter `api/` mit den Routen.
6. **Router registrieren**: per include_router in `main.py`.
7. **Berechtigungsmodul ergänzen**: im Enum `Module` in `core/permissions.py` `MY_MODULE = "my_module"` hinzufügen.
8. **Migration anlegen**: `alembic revision -m "add_my_module_tables"` und das SQL für die Tabellen schreiben.
9. **Berechtigungsdaten ergänzen**: in der Migration jeder Rolle eine Stufe für `my_module` zuweisen.
10. **Frontend synchronisieren**: im Typ `ModuleKey` in `usePermission.ts` `"my_module"` ergänzen.

### 3.2 Frontend-Schritte

1. **Typen ergänzen**: Interfaces in `types/index.ts` definieren.
2. **API ergänzen**: API-Datei des Moduls unter `api/` anlegen.
3. **Seite anlegen**: `myModule/MyModulePage.tsx` unter `pages/`.
4. **Route registrieren**: Route + `ProtectedRoute` in `App.tsx`.
5. **Menü ergänzen**: Eintrag in der Seitenleiste unter `components/layout/`.

---

## 4. Tests

### 4.1 Tägliche Prüfung

Das Backend nutzt pytest, das Frontend TypeScript/Vite und Vitest. Die übliche Konsistenzprüfung läuft aus dem Repository-Wurzelverzeichnis:

```bash
make check-sdk SDK_PYTHON_BIN=/absolute/path/to/developer-venv/bin/python # eigenständige SDK-Prüfung (drei Schichten)
make check-backend SDK_PYTHON_BIN=/absolute/path/to/developer-venv/bin/python # geprüfte PostgreSQL + aktuelles SDK-Wheel
make check-frontend-tsc  # Typprüfung
make check-frontend-build # Produktions-Build
make check SDK_PYTHON_BIN=/absolute/path/to/developer-venv/bin/python # SDK + Backend + tsc + Build
```

Die Backend-Prüfung normaler PRs gegen main wählt anhand der geänderten Pfade die betroffenen Testgruppen aus (Modul-Routing). Lokales `make check-backend` ohne weitere Angaben und Pushes auf main führen die vollständige Suite aus.

`SDK_PYTHON_BIN` des SDK ist standardmäßig `python3` und unabhängig von `PYTHON_BIN` des Backends; der Aufrufer muss Python ≥3.11, pytest, pip und tatsächlich setuptools==79.0.1 bereitstellen, die Prüfeinstiege installieren nichts und lockern keine Build-Versionen. `check-sdk-unit`, `check-sdk-loopback` und `check-sdk-wheel` laufen einzeln und ohne Abhängigkeit von Datenbank oder Backend-requirements; `check-sdk` fasst die drei Schichten zusammen. Die Backend-Prüfung baut zuerst offline ein Wheel aus dem aktuellen Quellstand, prüft den tatsächlichen Pfad und SHA256 aus dem Build-JSON und übergibt es über ein eigenes `OPENQMS_SDK_WHEEL` an die echte HTTP-Fixture; fehlt das Wheel, wird nicht übersprungen. Nachweise zu Build/Installation und Tests landen in einem privaten Unterverzeichnis dieses Laufs; das Elternverzeichnis lässt sich über `SDK_ARTIFACT_ROOT` festlegen. Details unter [SDK-Nutzung und Sicherheitsgrenzen](../sdk/python/README.md).

`make check` startet weder implizit Chromium noch echte Provider oder ClamAV. Die Backend-Schicht erlaubt nur `not ci_browser and not ci_r5_native
and not live_provider and not real_scanner`; die beiden bestehenden Ausschlüsse für graph worker/projection werden weiterhin
explizit per Make-Parameter übergeben. Reine CI-Infrastrukturtests laufen mit `python scripts/check-ci-pure.py tests/ci/
tests/e2e/test_capa_outcome_runner.py -q -rA`. Der pure-Modus verlangt, dass
die Collection keine Datenbank anspricht; eine fälschlich verwendete DB-Fixture schlägt ausdrücklich fehl statt zum Skip zu werden; implizites dotenv ist vor dem Import gesperrt,
und für Python-Netzwerkzugriffe sowie bekannte Datenbankeinstiege des Projekts gilt ein Ablehnungsschutz, den bekannte pytest-Unterprozesse über denselben Bootstrap übernehmen.
Das ist keine allgemeine OS-Netzwerk-Sandbox für beliebige Shell-, Node-, nativen oder nicht vertrauenswürdigen Code; unbekannte externe Programme dürfen damit nicht ausgeführt werden.

Frontend-Abhängigkeiten werden mit `npm ci` installiert; nach Änderungen an der Lockfile muss in der CI-Umgebung mit Node 20/npm 10 erneut geprüft werden; ein Build mit vorhandenem `node_modules` ersetzt keine saubere Installation. Die Release-Diagnose `doc-gate-preflight` und die Migration `deploy-migrate` behalten das `SECRET_KEY` des Aufrufers und überschreiben `.env` nicht mit einem leeren Wert, wenn keines übergeben wird; nur wenn der Aufrufer keinen nicht leeren Schlüssel liefert, wird aus Kompatibilität ein explizites `PYTEST_SECRET_KEY` akzeptiert. Diese Einstiege erhalten keinen neuen Produktions-Standardschlüssel.

### 4.2 Ressourcen und Grenzen der geschichteten Abnahme

`make check-browser` verwendet `ci_browser and not live_provider and not real_scanner`
und benötigt das im Projekt installierte Chromium; `make check-live` wählt nur `live_provider` und muss ausdrücklich freigegeben sein;
normale Aufgaben dürfen `E2E_MODE=false` nicht als Abschalter verwenden. Die geschichteten Einstiege (einschließlich des separaten Scanners) und das Format der lokalen Registrierung stehen im
[E2E-Leitfaden](e2e.md#geschichtete-ci-abnahme-task-7). Der Aufrufer setzt vor Make ein für group/world nicht beschreibbares, secret-freies
`OPENQMS_TEST_RESOURCE_FILE` und genau ein Loopback-`TEST_DATABASE_URL`; wird lokal zusätzlich
`PG15_CONTAINER` gesetzt, muss es dem registrierten Containernamen oder der vollständigen ID entsprechen und darf keine CI-Metadaten verwenden. Die SDK-Variablen
`OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` müssen entfernt statt geleert werden, die Provider-Konfiguration der Anwendung bleibt
ausdrücklich deaktiviert. Ressourcen dürfen nicht aus alten Registrierungen,
`run-owned.py`, festen `/Users/`-Pfaden oder Umgebungsdateien abgeleitet werden.

Die lokale Ressourcenprüfung lehnt vor Docker-inspect oder DB-I/O zusätzliche `PGHOSTADDR`, `PGSERVICE`,
`PGSERVICEFILE`, `PGSYSCONFDIR` und `PGOPTIONS` ab; die tatsächliche libpq-Verbindung ist zudem auf eine numerische Loopback-Adresse festgelegt.
`localhost` verwendet IPv4-Loopback; reine IPv6-Instanzen sollten ausdrücklich `::1` verwenden. Die Migrationsvorstufe normaler Tests und die Test-Recipes
teilen ein testspezifisches `SECRET_KEY`-Fallback und behalten explizite Werte des Aufrufers; `doc-gate-preflight` und
`deploy-migrate` verlangen dagegen ein ausdrücklich übergebenes echtes `SECRET_KEY` und erben weder das Test-Fallback noch das alte `PYTEST_SECRET_KEY`.
Diese Beschreibung berechtigt nicht zur Ausführung von Deployment-Befehlen.

Ein lokaler Source-Export kopiert nur aktuell getrackte vorhandene Quellen und ausdrücklich gelistete CI-Implementierungsdateien,
nicht `.git`, `.env*`, `.superpowers`, `.codegraph`, Caches, `node_modules` oder alte owned-Registrierungen;
nach dem Einfrieren per SHA-256-Manifest wird im Export `npm ci` ausgeführt. Normale und Provider-Zugangsdaten bleiben leer;
`PYTHON_BIN` darf auf einen vom Operator bereitgestellten Interpreter zeigen, wird aber nicht in den Quellcode geschrieben. Wird ein Installationsskript oder ein fehlender Browser blockiert,
als BLOCKED erfassen und die lauffähigen Backend-/statischen Prüfungen fortsetzen; das darf nicht durch Abhängigkeits-Upgrades oder Browser-Downloads umgangen werden.

Der Runner veröffentlicht nur geschwärzte Receipts/Logs; rohe JUnit-/Hook-Dateien und Konfigurationen bleiben privat. Jeder Job bewahrt über ein eigenes
`OPENQMS_TEST_ARTIFACTS` und `always()` die tatsächlichen Quittungen erfolgreicher und fehlgeschlagener Läufe auf, keine Status-Wrapper; der Scanner
exportiert Prozessnachweise vor dem Teardown und protokolliert die Bereinigung getrennt; die Summary prüft eingefrorene SHA und tatsächliche Zähler. Das optionale
`LLM_TIMEOUT` ist ohne Angabe oder leer 30 Sekunden, explizit gesetzt streng 1–120. Ein Receipt muss
Befehl, Exit-Code, selected/passed/failed/errors/skipped/xfail/xpass/deselected/warnings und
Bereinigungsumfang enthalten. Veröffentlicht wird erst nach der Bestätigung, dass ein fiktiver Sentinel weder in der Node-Allowlist noch in hochzuladenden Artefakten steht. Vom Controller behaltene
Container/Volumes nicht stoppen, löschen oder prunen; nur die in diesem Lauf erzeugten Runner-Artefakte bereinigen.

### 4.3 Automatische und manuelle Schichten auf GitHub

Das normale Backend läuft in zwei unabhängigen PostgreSQL-Jobs, gruppiert nach vollständigen Testmodulen; der zusammenfassende Check bleibt `backend-tests`. Lokal ohne `BACKEND_SHARD` läuft weiterhin die vollständige Menge. Ein Klassifikator aus der vertrauenswürdigen Base erlaubt es, dass reine Dokumentationsänderungen und streng begrenzte Darstellungsänderungen der öffentlichen Startseite das vollständige Backend überspringen; Typprüfung, Build und Browserprüfungen des Frontends laufen weiter.

Chromium-Jobs (automatisch browser-protection, manuell live-capa/scanner) sind fest auf `ubuntu-24.04` gesetzt, damit `ubuntu-latest` nicht auf ein System wechselt, das die aktuelle Playwright-Version nicht unterstützt. Netzwerkfreie Tests der SDK-Standardendpunkte verwenden den öffentlichen Standard-HTTP-Client des jeweiligen SDK mit passendem Transport; alte `httpx`-Objekte dürfen nicht in ein bereits auf `httpx2` umgestelltes SDK injiziert werden. Offizielle URLs werden weiterhin streng geprüft, ambient gesetzte Overrides entfernt und echte Anfragen verboten.

Abnahme-Unterprozesse geben je Testfall in Echtzeit start/finish-Diagnosen aus, nur mit Quelltestkennung und Laufnummer, ohne Parameter-ID oder Text. Der Elternprozess prüft exakte JSON-Struktur und lückenlos gepaarte Sequenz, baut die Ausgabe neu auf und schwärzt sie, bevor sie in die Konsole gespiegelt wird; Präfixkollisionen, Wiedergabe erfasster Ausgaben und verschachtelter Fortschritt werden abgelehnt. Das ist weder Authentifizierung noch Erfolgsquittung. Ist ein einzelner Testfall nach 120 Sekunden nicht fertig, speichert pytest die Thread-Stacks; er wird deswegen **nicht** übersprungen, vorzeitig bestanden oder länger ausgeführt. Bei einem Abbruch durch Timeout müssen letztes start/finish, Stack und tatsächliche Zähler geprüft werden; eine fehlende Abschlussquittung gilt nie als bestanden.

Automatische Jobs laufen secret-frei bei main-Pushes und PRs gegen main (Pushes auf Feature-Branches lösen nicht erneut aus; Feature-Branches ohne offenen PR führen Test OpenQMS nicht aus), mit `contents: read` und Checkout
`persist-credentials: false`. Live/Scanner per `workflow_dispatch` gibt es nur auf `main`, mit festen
Optionen und main-only-Preflight: Zuerst werden event/ref/gate geprüft und die main-SHA eingefroren, erst dann
verwenden nachfolgende Jobs diese SHA. Die workflow_dispatch-Datei muss zuerst regulär im Standardbranch main liegen; nur der Live-Job nutzt das Environment `ci-acceptance` und die Modellkonfiguration, der Scanner liest
keine Modellschlüssel und hängt nicht von diesem Environment ab. Freigabeberechtigte des Environments, erlaubtes main und Testkonfiguration richtet der Administrator in GitHub ein;
der Code liest keine lokalen Zugangsdaten und legt weder Secrets noch Environments oder Branch-Schutz an. GITHUB_AUTO/GITHUB_MANUAL ohne tatsächlichen push
bzw. dispatch sind kein PASS und bleiben BLOCKED bzw.
NOT_REQUESTED.

---

## 5. Commit-Konventionen

```
<type>(<scope>): <subject>

<body>
```

Typen: `feat` / `fix` / `docs` / `refactor` / `test` / `chore`

Beispiele:
```
feat(fmea): add DFMEA generation rules engine
fix(capa): fix D7/D8 transition permission check
docs(permissions): update permission matrix for new modules
```
