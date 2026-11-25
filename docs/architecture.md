# Architekturüberblick

> Sicherheitsgrenzen vom 2026-11-16: Administratoren werden über ein privates Terminal initialisiert; öffentliche privilegierte Passwörter werden bei normaler Anmeldung und Refresh abgelehnt; ein Replay eines Refresh-Vorgängers widerruft die ganze Token-Familie, Abmelden widerruft serverseitig. Der Zustand des Plattform-Login-Rate-Limits liegt ausschließlich in `public.platform_login_attempts`; FMEA, Produktionslenkungsplan, besondere Merkmale, historische Versionen sowie ERP/PLM verwenden den aktuellen Modul-, Werks- und Produktlinienbereich. Zugangsdaten externer Konnektoren sind an ihr Ziel gebunden, ERP-REST nutzt vom Betrieb freigegebene Origins/CIDRs; Importe werden vor dem multipart-Parsing begrenzt, Exporte behandeln Formelpräfixe als Text. Einzelverhalten, Upgrade-Anforderungen und Prüfung siehe [Protokoll der Sicherheitskorrekturen](development/2026-11-16-security-scan-fixes.md).

> Kontrollierte Aufgabenanhänge (R4b-2) verwenden ein privates Volume auf einem einzelnen Knoten, zuerst begrenztes privates Staging, dann lokale Stream-Übergabe an ClamAV und Download ohne Direktlinks; Topologie und nicht freigegebene Produktionsgrenzen siehe [Betriebsanleitung](development/agent-task-attachments.md).

Dieses Dokument beschreibt Systemarchitektur, Berechtigungsmodell, Datenflüsse und Entwicklungskonventionen von OpenQMS.

---

## 1. Technologie-Stack

| Schicht | Technologie | Beschreibung |
|----|------|------|
| Backend | Python 3.11 / FastAPI 0.115 | async-Framework, automatisch generierte OpenAPI-Dokumentation |
| ORM | SQLAlchemy 2.0 (async) | UUID-v4-Primärschlüssel, asynchrone Session |
| Datenbank | PostgreSQL 15 | Speicherung des JSONB-Graphmodells, GIN-Indizes |
| Cache | Redis 7 | Konfiguriert, noch keine Cache-Logik |
| Wissensgraph | Neo4j 5 Community | Visualisierung von FMEA/CP-Verknüpfungen und intelligente Empfehlungen |
| KI | Ollama | Lokale LLM-Inferenz für die Empfehlungs-Engine |
| Frontend | React 18 / TypeScript 5.6 | Single-Page-Anwendung |
| Build | Vite 5.4 | Entwicklungsserver + Proxy |
| UI-Framework | Ant Design 5 | Lokalisierung Deutsch (Standard) und Englisch |
| Zustandsverwaltung | Zustand | Auth, Produktlinie, Werk |
| Migrationen | Alembic | Handgeschriebene Migrationsdateien |
| Container | Docker Compose | Orchestrierung der Dienste |

---

## 2. Verzeichnisstruktur

```
OpenQMS/
├── backend/
│   ├── app/
│   │   ├── api/            # Routen-Handler (dünn): Anfrage parsen, Service aufrufen, Antwort liefern
│   │   ├── services/       # Geschäftslogik: alle CRUD + manuelles AuditLog
│   │   ├── models/         # SQLAlchemy-2.0-ORM-Modelle (UUID-PK, DeclarativeBase)
│   │   ├── schemas/         # Pydantic-v2-Request-/Response-Schemas
│   │   ├── core/
│   │   │   ├── security.py  # bcrypt-Passwort-Hash + JWT/HS256 ausstellen/prüfen
│   │   │   ├── deps.py      # FastAPI-Dependency-Injection (get_current_user usw.)
│   │   │   ├── permissions.py # Enums Module/PermissionLevel + require_permission
│   │   │   └── factory_scope.py # Filter für Werks-/Produktlinienbereich
│   │   ├── i18n/            # Übersetzung von API-Meldungen je Accept-Language
│   │   ├── main.py          # FastAPI-App-Einstieg, Routenregistrierung, Middleware
│   │   └── seed.py          # Seed-Skript für Demodaten
│   ├── alembic/             # Datenbankmigrationen
│   └── tests/               # pytest-Backend-Tests (inkl. factory_id-Fixtures + modulübergreifende Regression)
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios-Instanz + API-Funktionen pro Modul
│   │   ├── components/      # Layoutkomponenten (AppLayout) + gemeinsame Komponenten (KPICard)
│   │   ├── hooks/
│   │   │   └── usePermission.ts # Berechtigungs-Hook (ModuleKey × PermissionLevel)
│   │   ├── i18n/ / locales/ # Übersetzungen de-DE / en-US, tr()-Helfer
│   │   ├── pages/           # Seitenkomponenten nach Modul
│   │   ├── store/
│   │   │   └── authStore.ts  # Zustand-Store für Auth (token, user, permissions)
│   │   ├── types/
│   │   │   └── index.ts     # Globale TypeScript-Interfaces
│   │   ├── utils/
│   │   │   ├── fmea.ts      # AIAG-VDA-AP-Tabelle
│   │   │   └── fmeaTable.ts  # Bidirektionale Umwandlung graph↔spreadsheet
│   │   └── App.tsx          # Routendefinition + ProtectedRoute
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/
    ├── deployment.md
    ├── architecture.md         # Dieses Dokument
    ├── permissions.md
    ├── user-guide.md
    ├── admin-guide.md
    ├── development.md
    └── modules/
        └── *.md                 # Modulhandbücher nach Fachbereich
```

---

## 3. Ablauf der Anfrageverarbeitung

```
Browser → Vite Dev Server (:5173)
          ↓ /api/* Proxy
        Nginx / Vite-Proxy
          ↓
FastAPI (:8000)
  ├── CORS-Middleware
  ├── JWT-Authentifizierung (get_current_user)
  ├── Berechtigungsprüfung (require_permission)
  ├── API-Routen (api/*.py)
  │     ↓
  ├── Service-Schicht (services/*.py)
  │     ├── Geschäftslogik
  │     ├── AuditLog schreiben
  │     └── ValueError → HTTPException
  └── SQLAlchemy AsyncSession
        ↓
      PostgreSQL
```

**Wichtige Konventionen**:
- Die API-Schicht parst nur Anfragen und formatiert Antworten, ohne Geschäftslogik.
- Die Service-Schicht trägt die gesamte Geschäftslogik und schreibt `AuditLog` manuell.
- Die Service-Schicht wirft `ValueError`, die API-Schicht wandelt in `HTTPException` um.
- Listen-Endpunkte liefern einheitlich `{ items, total, page, page_size }`.

---

## 4. Berechtigungsmodell

### 4.1 Aufbau

OpenQMS verwendet ein dreistufiges Modell aus **Rolle + Modul-Berechtigungsstufe + Werks-/Produktlinienbereich**:

```
Benutzer → Rolle (role_key)
         → Rollenberechtigungen (role_permissions: module × permission_level)
         → Werksbereich (user_factories)
         → Produktlinienbereich (user_product_lines)
```

### 4.2 PermissionLevel

| Stufe | Konstante | Beschreibung |
|:----:|------|------|
| 0 | NONE | Keine Berechtigung, kein Zugriff |
| 1 | VIEW | Nur lesen |
| 2 | CREATE | Anlegen |
| 3 | EDIT | Bearbeiten |
| 4 | APPROVE | Freigeben |
| 5 | ADMIN | Vollzugriff |

### 4.3 Berechtigungs-Hook im Frontend

```typescript
// frontend/src/hooks/usePermission.ts
const { canView, canCreate, canEdit, canApprove, canAdmin, isAdmin, roleKey } = usePermission();

// Prüfung pro Modul
canView("fmea")      // PermissionLevel >= 1
canCreate("fmea")    // PermissionLevel >= 2
canEdit("fmea")      // PermissionLevel >= 3
canApprove("fmea")   // PermissionLevel >= 4
canAdmin("fmea")     // PermissionLevel >= 5
```

### 4.4 Berechtigungsprüfung im Backend

```python
# backend/app/core/permissions.py
@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.5 Vollständige Berechtigungsmatrix

Siehe [Berechtigungsreferenz](permissions.md).

### 4.6 Berechtigungskern der Agent-Module und Aufgabenbasis

`backend/app/services/agent/permissions/` enthält einen reinen Richtlinienkern: Fähigkeitserklärungen der Module, Schnittmenge aus ausführender Identität und Plugin-/Aufgaben-Grants, Freigabestufen für Operationen und Freigabeberechtigung von Mitarbeitenden, Bewertung ausgehender Auslieferung sowie Herkunftsbeschränkungen abgeleiteter Inhalte. Im Standardkatalog `baseline` für 8D D4 sind Kontexte und Kandidatenbefehle `DENY`; `authorize()` liest den nicht an Ort und Stelle änderbaren Serverkatalog neu ein und lehnt unbekannte Fähigkeiten sowie vom Katalog abweichende Definitionen ab.

Die Fähigkeitserklärungen liegen im CAPA-Modul in `capa_agent_capabilities.py`; kontrollierte Profile leiten nur die Freigabeuntergrenze für summary ab und kopieren oder erweitern keine Schreibrechte. Ein unbegrenzter Werksbereich erfordert aktuelles GROUP ADMIN; eine unbegrenzte Produktlinie braucht eine ausdrückliche Zeilenausnahme, Modulrechte ersetzen keinen Bereich. Freigaben durch Mitarbeitende schließen Selbstfreigabe durch Ausführende und Antragstellende aus. Abgeleitete Inhalte behalten Version, Fähigkeit und tatsächliche Projektion aller Quellen; wird eine Quelle aktuell entzogen, wird das ganze Paket abgelehnt, eine herabgestufte Auslieferung ist nicht erlaubt.

Der Berechtigungskern wird für die Nur-Lese-Autorisierung des neuen Aufgabenservices verwendet; bestehendes Agent-Gateway, Modellaufrufe und Freigabe-API laufen weiterhin über ihre ursprünglichen Pfade. Im Mandanten gibt es Tabellen für Plugin-Installationen und langfristige Grants mit deaktivierten Standardwerten; persistente Aufgaben, Läufe, Nur-Lese-Aufgaben-Grants und eingeschränkte Nachrichten haben eigene Modelle und ausdrückliche public-/tenant-Migrationen. Der Service für Installationsregistrierung/-rotation speichert nur den Schlüssel-Hash und liefert das Secret einmalig; Identität und Berechtigung des Administrators werden bei jedem Schreiben neu gelesen, den Commit übernimmt der Aufrufer.

Ein eigenes Lauf-JWT hat eigene issuer/audience/type, Mandanten-Generation sowie Installations-/Lease-Epoch und gilt höchstens bis zum Ende der aktuellen Lease; Datensätze ohne oder mit abgelaufener Lease taugen nicht als Laufidentität. Mandantenfähige Prüfungen verlangen eine echte, je Transaktion gebundene Session; jede Operation prüft erneut Registrierung, Lauf, Aufgabe, Installation, ausführenden Benutzer mit aktueller Rolle, Werk/Produktlinie und beide Grant-Ebenen. Normale Benutzer-Zugangsdaten und Lauf-Zugangsdaten berechtigen sich nicht gegenseitig.

Der zielgebundene Aufgabenservice ist an aktuelle Rolle, Werk und Produktlinie angebunden; Anlegen, Liste, Detail und Wiederholung autorisieren jeweils neu; Nur-Lese-Grants fixieren den Bericht, das Standard-DENY erzeugt eine blockierte Aufgabe ohne Lauf. Nachrichtenanhänge des Initiators vergeben Sequenznummern unter der Aufgabensperre, sind idempotent und autorisieren nach der Sperre erneut; der Text ist restricted. Benutzer-APIs für Aufgaben/Nachrichten sowie Administrator-APIs für Plugins/langfristige Grants sind angebunden; `AGENT_TASK_RUNTIME_ENABLED` ist standardmäßig aus und liefert dann vor der Mandantenauflösung 404. Administratorkonfiguration ändert die normierte Fähigkeitsuntergrenze nicht. Bestehende Rollenrechte und alte Agent-Werkzeuge laufen weiter über ihre ursprünglichen Pfade.

Lauf-Übernahme und Fähigkeitserkennung aus R2 sind umgesetzt und haben die zweistufige Prüfung bestanden. Das Installations-Secret dient nur dazu, im gerouteten Mandanten einen Lauf der festen Installation zu übernehmen; Übernahme und spätere Änderungen teilen die Sperrfolge Installation→Aufgabe→Lauf, nach dem Warten auf Sperren werden Beziehungen und Berechtigungen erneut geprüft. Der Idempotenzschlüssel der Übernahme bindet die aktuelle Lease, eine erneute Übernahme nach Ablauf erhöht den Epoch; die Fähigkeitserkennung liefert nur normierte Servereinträge. Nachrichtenübernahme und fortlaufende Bestätigung haben die zweistufige Prüfung ebenfalls bestanden: Aktueller Lauf und Lease binden stabile Stapel, Datenbankzeilen belegen tatsächliche Übernahme und Annahme, Teilbestätigungen und Wiederholungen akzeptieren nichts doppelt; nach dem Lesen wird erneut vollständig autorisiert, Sicherheitsaudit und Status werden atomar committet. Die vertrauenswürdige Deployment-Auslieferungsrichtlinie ist standardmäßig leer; Originalnachrichten werden nur unter ausdrücklich erlaubter kontrollierter Plugin-Richtlinie ausgeliefert. Die Nur-Lese-Projektion ist abgenommen: Eine separate Verbindung setzt zuerst REPEATABLE READ READ ONLY und bindet dann den Mandanten; explizite Metadatenfelder und Verifizierungsdatensätze teilen einen vollständigen Digest. Während des Lesens sind Rechteentzüge erlaubt; vor der Auslieferung werden Berechtigungen vollständig aufgefrischt, die Produktlinie des jeweils autorisierten Ziels geprüft und dann Receipt und Sicherheitsaudit atomar gespeichert. Ereignisse und Ergebnisse sind abgenommen: begrenzte DTOs, Prüfung mehrerer Receipts des aktuellen Laufs, serielle Idempotenz und atomarer Commit des Sicherheitsaudits. Freie Ergebnisse sind fest restricted, Herkunftslabels erben internal. Historisches Lesen durch normale Benutzer prüft Aufgabe und alle Quellen unabhängig auf aktuelle Fachberechtigung und hängt nicht davon ab, dass das Plugin noch aktiv oder der Lauf noch aktiv ist. Ein eigenständiger stdlib-Prozess hat über echtes HTTP zwei abhängige Abfragerunden, Nachrichtenbestätigung und Ereignis/Ergebnis mit doppeltem Receipt abgenommen (22 Tests); die abschließenden vollständigen Backend- und Frontend-Gates (Typprüfung/Build) sind bestanden.

Steuerungs-Idempotenz, Nur-Lese-Checkpoint/Receipt-Verknüpfung, Aktivitätssequenzen und das Referenzmodell für Laufwiederaufnahme aus R3 sowie zwei v4-Inkrementmigrationen sind abgenommen; historische Aufgaben werden deterministisch nachgefüllt, Laufanlage wird nicht fälschlich als Übernahme markiert. Der Aktivitätsservice ist abgenommen: Anfangseingabe/Laufanlage und gültige Übernahme, Nachrichtenanhang, ACK, Ereignisse und Ergebnisse werden mit ihrem Aktivitätszeiger atomar committet, idempotente Wiederholungen ohne Duplikate; die tatsächliche Stapelübernahme speichert den Status claimed. Pausieren/Fortsetzen/Abbrechen durch Benutzer und completed/failed durch Plugins sind abgenommen; Steuerungen aktualisieren Status, Epoch, Lease, Aktivitätszeiger und Audit atomar; ein erfolgreicher Abschluss prüft unter der TASK-Sperre, dass keine unbestätigten Eingaben vorliegen und das akzeptierte Präfix konsistent ist; vor dem Schreiben von Steuerung/Abschluss werden aktuelle Berechtigungen erneut geprüft. Speichern von Nur-Lese-Checkpoints, seitenweises Neulesen bestätigter Eingaben, historisches Durchsuchen mit aktueller Quellautorisierung des Benutzers und Wiederöffnen ab dem neuesten sicheren Checkpoint sind abgenommen; das Wiederöffnen stoppt atomar den alten Lauf und legt einen neuen mit geerbtem Annahme-Wasserstand an, liest nach erneuter Übernahme die aktuellen Metadaten, und alte Receipts werden nicht für Ausgaben des neuen Laufs verwendet. Aktivitätsfenster über aktuelle Quellen und Installationskatalog sind abgenommen: Das Fenster bindet die aktuelle Runde W, prüft pro Objekt und am Ende alle tatsächlichen Quellen erneut, und eine ungültige Quelle lehnt die ganze Seite ab; der Installationskatalog prüft tatsächliches Ziel, Installation der festen Version und Autorisierung erneut. Die einheitliche Seitenleiste ist abgenommen: AppLayout hält die Aufgabenauswahl mit festem Ziel, CAPA legt nur über eine ausdrückliche Aktion an; das zweiseitige Polling der Benutzer-API ersetzt pro Runde vollständig, Schließen, Ausblenden, Identitätswechsel oder Ablehnung ziehen Inhalte zurück, Wiederholungen behalten Idempotenzschlüssel und Parameter. Die Übernahmeantwort von R3 liefert Annahme-Wasserstand und Kennung des Wiederaufnahme-Checkpoints; das eigenständige stdlib-Beispiel liest zuerst das bestätigte Präfix neu, dann die aktuellen Metadaten, und erzeugt Ausgaben mit Idempotenzschlüsseln des neuen Epochs. Echte Prozesse und acht Browser-Szenarien haben die zweistufige Prüfung bestanden; Abbrechen erhält die Unterscheidung queued/claimed unbestätigter Nachrichten und den ursprünglichen Stapelnachweis. Die Code-Prüfung des gesamten Abschnitts ist bestanden; R3 eingefroren mit Backend 2731 passed / 4 skipped / 3 xfailed / 2 xpassed, Frontend 78 Tests sowie Typprüfung/Build bestanden. Standardabschaltung und Grenzen der vertrauenswürdigen Auslieferung bleiben unverändert.

Der lokale kontrollierte Metadaten-Versuch aus R4a ist umgesetzt: lifespan lädt einmalig eine strikte Sicherheitsdatei als eingefrorene Richtlinie, `get_db` reicht nur eine echte app-state-Referenz weiter, fehlende Referenzen ergeben standardmäßig eine leere Richtlinie. Das Profil des normierten Katalogs ist unveränderlich; nur wenn aktueller dev-Mandant/Generation, Installation/Epoch, ausführende Person und Berichtskoordinaten exakt übereinstimmen, wird `local_metadata_v1` gewählt; nur summary ist DIRECT, Standard-Baseline und Befehle bleiben DENY. Begrenzte Grants regulärer Administratoren, Installationskatalog der Benutzer, Ableitung von Einzelberichtsaufgaben und die Autorisierung jedes Laufs teilen diese Auswahl; die Richtlinie ersetzt weder aktuelle Identität noch Fachbereich, Manifest oder die beiden Grant-Ebenen.

Das Versuchs-JWT bindet den SHA-256 der Erklärung; Lease und Token laufen höchstens bis zum Ende der Richtliniengültigkeit; nach der Sperre und vor der abschließenden Auslieferung wird erneut autorisiert. Ein dauerhafter Widerruf schließt unter der Installationssperre atomar, tauscht gegen einen zufälligen, nicht zurückgegebenen Schlüssel-Hash, erhöht den Epoch und auditiert; alte Schlüssel/JWTs/Erklärungen lassen sich durch erneutes Aktivieren nicht wiederherstellen, die Historie wird weiterhin nach aktueller Fach-/Quellautorisierung gelesen. Ein ausdrücklicher local_metadata-Einstieg prüft nach dem frühen 404 im deaktivierten Zustand und vor Mandant/Body/Datenbank auf einen echten Loopback-Peer und lehnt forwarded-Header ab. Das feste CLI führt nur auditierte stdlib-Worker-Bytes aus, mit privater Zugangsdatei, minimaler Umgebung, Ausgabe-/Zeitlimits und Einsammeln eigener Unterprozesse; es bietet keine Modellaufrufe, keinen Text/Anhang, keine fachlichen Schreibvorgänge und keine OS-/Produktionsisolation. Unter Normalkonfiguration ist die fokussierte Abnahme von Prozess und Chromium bestanden; Betriebsablauf siehe [Anleitung zum lokalen Versuch](development/agent-local-trial.md). Standardmäßig deaktiviert; die Gates für R4b und Produktion sind unabhängig.

R4b-1 ergänzt die Grundlage für interne geschwärzte D4-Textkandidaten für Mitarbeitende: `capa_current_access` bündelt die bestehenden Regeln für aktuellen Namespace, Rolle und Objektbereich, alte Laufzeiteinstiege bleiben bestehen; reine Regeln und ausdrückliche Literalbegriffe verarbeiten nur drei D4-Textpositionen, die Ausgabe ist fest restricted, ohne freigegebene Herabstufung und ohne externe Auslieferung. Der Vorschauservice prüft zuerst das Budget und liest dann die ausdrücklichen Felder in einem separaten RR/READ-ONLY-Snapshot des erfassten Mandanten; ausdrückliche FMEA-Referenzen prüfen aktuelle Quellberechtigung, Koordinaten und Knoten erneut, geliefert werden nur Metadaten berechtigter Quellen, ohne Graph, Titel oder Anhänge zu laden. Quellversionen verwenden ein domänengetrenntes HMAC; nach abschließender erneuter Prüfung von Berechtigung und Quellversion wird nur das Sicherheitsaudit committet, weder Originaltext noch Status noch Outbox werden geschrieben. Die drei Schnittstellen für normale Benutzer sind durch einen eigenen, standardmäßig deaktivierten Schalter sowie Eingabe-/Fehlergrenzen der Inhaltssicherheit geschützt; Lauf-Zugangsdaten gelten hier nicht. Die Nur-Lese-Komponente cacht weder Text noch Begriffe, prüft sichtbar alle 2 Sekunden, lebt lokal höchstens 30 Sekunden und zieht bei Rechteverlust, Unsicherheit, Schließen oder Ausblenden private Inhalte und Begriffe zurück; alte Antworten werden nach Identität, Ziel und Anfragerunde getrennt. Echte Mitarbeiter-API und Chromium sind durchgängig verbunden; Bedienung und Regelgrenzen siehe [Vorschau-Anleitung für Mitarbeitende](development/capa-d4-text-preview.md). Der R4a-Plugin-Katalog wird nicht erweitert, es gibt keine Text- oder Modellweitergabe; Anhänge, SDK, Deployment und das Gate für formale Herabstufung bleiben unabhängig.

Die kompatiblen internen `agent_read_tasks`/`agent.read_task_service` sind weiterhin auf einen Mandanten beschränkt: Für ein einzelnes, dem aktuellen Benutzer sichtbares CAPA wird eine 24-Stunden-Aufgabe angelegt; bei jeder Prüfung werden aktuelle Berechtigung und fester Objektbereich erneut geprüft, Widerruf und Audit werden unterstützt; es gibt keine neuen HTTP-, Plugin- oder Modelleinstiege. Der objektbezogene Grant ändert die Baseline-DENY nicht. Das gemeinsame `capa_agent_projection.build_masked_d4_projection(capa_id, *, binding=None, engine=None)` akzeptiert nur serverseitige Bindung/Engine: im Einzelmandanten ausdrücklich public, im Mehrmandantenbetrieb eine business-Bindung mit Prüfung von aktueller Registrierung/Generation; zuerst wird ein separates REPEATABLE READ READ ONLY gesetzt, dann werden feste Metadaten und D4-Verifizierungsunterdatensätze desselben Werks gelesen und ein vollständiger stabiler Digest berechnet, ohne Text, Anhänge oder den gesamten ORM-Zustand zu laden. Laufpfade prüfen vor der abschließenden Auslieferung weiterhin aktuelle Berechtigungen und alle Quellen.

Die lokale kontrollierte Auslieferung der D4-Grundursache aus R4b basiert in einem standardmäßig deaktivierten, separaten dev-Profil mit echtem Loopback auf ausdrücklicher Vollständigkeitserklärung der Mitarbeitenden, kontrollierter Revision und FMEA-Quellverifizierung; Plugin und Aufgabe speichern jeweils ihren exakten Quellbereich und fixieren denselben Eltern-Grant. Ein fester Nur-Lese-Empfänger liest über das Nachrichten-Gate einen begrenzten geschwärzten Einzelfeldkandidaten aus RR/READ ONLY, prüft abschließend erneut und committet einen eigenen restricted-Receipt; es gibt keine Modell- oder Produktionsweitergabe. Ein vom Benutzer ausdrücklich ausgelöster eingeschränkter Neustart speichert nur Steuerkoordinaten, führt über den festen Einstieg erneut aus, liest aktuelle Fakten neu und erzeugt einen neuen Receipt; er stellt weder Agent-Gedächtnis wieder her noch verwendet er alte Receipts oder erweitert die ursprüngliche Autorisierung. Checkpoint/Neustart und Stopp-Steuerung haben Berechtigungsgrenzen vor dem Commit, Quellen werden zuerst auf Sichtbarkeit geprüft; parallele Berechtigungspflege kann die Stopp-Steuerung alter Metadaten kurzzeitig mit 503 beantworten. Die Wiederaufnahme sperrt historische Nachweise, Revisionen und Verifizierungsmetadaten zeilenweise und wächst linear mit der Historie; für große Historien gibt es noch keine Performancenachweise.

Ein eigenständiges Python-SDK für Metadaten implementiert eingefrorene DTOs, einen strikten Codec, synchronen stdlib-Transport und einen Client mit zehn Operationen, für Python ≥3.11 ohne Laufzeitabhängigkeiten; es importiert kein Backend und greift nicht auf die Datenbank zu. Der Server autorisiert weiterhin bei jedem Aufruf; das SDK cacht keine Berechtigungen, parst keine Lauf-Tokens, wiederholt oder verlängert nicht automatisch und führt keine Nachrichten aus; eine monotone Deadline deckt die ganze Operation ab; wurde finish möglicherweise gesendet, aber nicht vollständig bestätigt, wird nur unknown gemeldet und ein erneutes Senden lokal verhindert. Unit-Tests, eigene Loopback-Tests, isolierte Installation des echten Wheels und die echte HTTP-Fixture unter normal-policy sind stufenweise abgenommen; die Make-/CI-Anbindung ist doppelt geprüft, das vollständige lokale Kombinations-Gate des eingefrorenen Commits ist bestanden; Remote-CI wurde nicht ausgeführt. Das SDK ändert weder festen Worker/Hash/Profil/Katalog noch Produktionszulassung und öffnet weder Weitergabe von Text/Anhängen noch Modellaufrufe noch fachliches Schreiben in R5; siehe [SDK-README](../sdk/python/README.md).

### 4.7 Mandantentransaktionen und unabhängige Migration

Mandantenfähige Geschäftssitzungen holen zu Beginn jeder Transaktion erneut eine gemeinsame Transaktionssperre, prüfen in `public.tenants` Status active, Schema und Generation und setzen dann `SET LOCAL search_path` nur auf Mandantenschema und `pg_catalog`. Anfragen und Hintergrundaufgaben über mehrere Commits hinweg behalten die erfasste Generation; nach Wartung oder Neuaufbau lehnen alte Bindungen die Fortsetzung ab. Der Einzelmandantenmodus verwendet ausdrücklich public; im Mehrmandantenmodus gibt es keinen Rückfall auf public.

Mandantenwartung hält über eine feste physische Verbindung eine exklusive Sitzungssperre; auf derselben Verbindung werden ein attempt angelegt, die Generation erhöht, die eigene Alembic-Kette ausgeführt und atomar gesät. Wartungstransaktionen prüfen PID, attempt, Generation und Sperrbesitz und fordern keine gemeinsame Geschäftssperre mehr an. public-Plattformmigrationen und Mandantenmigrationen werden getrennt geführt; die Mandanten-Baseline `tv001_business_snapshot` ist eingefrorene DDL; vor der Aktivierung werden Schema-Parität auf Objektebene, Seed und Isolation geprüft.

Eine normale Wiederaufnahme behandelt nur bekannte vollständige Phasen desselben Mandanten, lehnt unbekannte oder teilweise Schemas ab und löscht keine Daten. Der aktuelle Head der unabhängigen Migration ist `tv010_refresh_sessions`: Nachdem `tv009_r4b_main_merge` `tv007_characteristic_refs` und `tv008_d4_recovery` zusammengeführt hat, wird eine nach Browser getrennte Tabelle für Refresh-Sessions ergänzt. Der Merkmals-Branch ergänzt nach `agent_read_tasks` aus tv006 nur JSONB-Quellreferenzen in CP-Zeilen und UUID-Quellfelder für besondere Merkmale; public `20261108_merge_characteristics` führt ohne DDL `20261101_char_refs` und `20261103_merge_agent_foundations` zusammen und bewahrt beide veröffentlichten Historien. tv001–tv005 und der eingefrorene Snapshot werden nicht umgeschrieben; tv006 behält die in main veröffentlichten Bytes und unterscheidet sich von R4b nur in der Beschreibungszeile (keine DDL-Differenz); Hash und semantische Gleichwertigkeit beider Quellen werden separat getestet. Das public `20261114_r4b_main_merge` ohne DDL führt die beiden Heads aus main-Merkmalen und R4b-Wiederaufnahme zusammen; das ebenfalls DDL-freie `20261114_production_merge` verbindet zusätzlich den bereits deployten Branch `20260913_user_refresh_sessions` und bewahrt alle veröffentlichten Knoten. Vollständige alte Mandanten (inkl. beider alter Heads und tv009) werden auf derselben Wartungsverbindung unter exklusiver Sperre und Generation vorwärts aktualisiert; die Parität alter Versionen zieht von der public-Referenz nur die geprüften kumulativen Inkremente nach dieser Version ab (einschließlich der beiden Merkmals-Quellspalten und der Refresh-Session-Tabelle) und verdeckt keine zusätzlichen oder teilweisen Objekte auf Mandantenseite. Ein Mandanten-Downgrade verlangt zusätzlich, dass jeder Elternpfad dasselbe Ziel erreicht, und prüft danach auf genau eine Version; Merge-Heads lassen sich nur auf den gemeinsamen Vorfahren tv006 oder früher herabstufen, das Aufspalten eines Merges in mehrere Heads wird abgelehnt. Der aktuelle Head muss allen Geschäftsobjekten des neuesten public entsprechen; fehlende oder beschädigte Quellspalten werden ebenfalls abgelehnt. Exporttests bleiben an den public-Head im eingefrorenen Manifest gebunden und schreiben neue Felder nicht in den historischen Snapshot zurück. Für den Offline-Neuaufbau von Tests gibt es einen eigenen ausdrücklichen Einstieg: exaktes Inventar ohne Zugangsdaten, Testdatenbank, Umgebungsschalter, beobachtetes Anhalten von backend/graph-worker und keine anderen Datenbankclients; unter der exklusiven Sperre wird erneut geprüft, und schemaübergreifende Abhängigkeiten werden abgelehnt. Bei Fehlschlag bleiben Nachweise erhalten; eine normale Wiederaufnahme kann einen unvollständigen Neuaufbau nicht umgehen.

### 4.8 Alte Einzelbericht-Nur-Lese-Basis im Hauptzweig und Integrationsgrenzen

`backend/app/services/capa_agent_capabilities.py` hält die normierte Nur-Lese-Erklärung von CAPA; beide Standardfähigkeiten sind `DENY`, summary braucht ein ausdrückliches Ziel. Der Plattformkatalog überschreibt nur für serverseitige eingeschränkte lokale Profile die Freigabeuntergrenze von summary und akzeptiert keine vom Aufrufer erklärte Herabstufung. Ein unbegrenzter Werksbereich erfordert `GROUP ADMIN`, eine unbegrenzte Produktlinie eine vor Ort aufgelöste ausdrückliche Zeilenausnahme; die Ausnahme ersetzt weder Werk noch Fachmodul noch die beiden Grant-Ebenen. Freigaben werden nach den Modulrechten des Fähigkeitseigentümers und eigener Freigabeberechtigung beurteilt; Selbstfreigabe durch Ausführende und Antragstellende ist ausgeschlossen, `DENY` ist nicht freigebbar.

Der Hauptzweig behält `AgentReadTask` / `agent_read_tasks` und `read_task_service` als eigenständige alte Einzelbericht-Basis; sie ersetzen `AgentTask` / `AgentRun` nicht und sind keine migrierte Fassung davon. Der alte Service unterstützt nur `TENANT_MODE=single`, legt 24-Stunden-Autorisierungen an, prüft den Bereich bei jedem Aufruf neu, unterstützt Widerruf und Audit, ergänzt keine HTTP-/Plugin-/Modelleinstiege und öffnet keine Baseline-Fähigkeiten. Die gemeinsame Projektionsfunktion nutzt die separate RR/READ-ONLY-Verbindung der Laufzeit; mandantenfähiges Lesen braucht eine vom Server erfasste gültige Geschäftsbindung, ohne Bindung gibt es keinen Rückfall auf public.

Herkunftslabels bewahren Eigentümer, Objekt, Fähigkeit, tatsächliche Projektion und Version; historische Ausgaben erzeugen erst nach bestandener Prüfung der aktuellen fachlichen ACL die Vier-Schlüssel-Menge der Quellautorisierung und prüfen vor und nach der Serialisierung erneut. Gespeicherte alte Receipts oder korrekte Digests ersetzen keine aktuelle Quellautorisierung. Die beiden ursprünglichen public-Agent-Migrationsketten werden ausdrücklich über `20261102_agent_mainline_merge` zusammengeführt; das eigenständige tenant-`tv006_agent_read_tasks` ergänzt die alte Tabelle, ohne die eingefrorene Baseline zu ändern.

---

## 5. Datenmodell im Überblick

### 5.1 Kerntabellen

| Tabelle | Beschreibung | Primärschlüssel |
|----|------|------|
| `users` | Benutzer | UUID |
| `role_definitions` | Rollendefinitionen (7 vordefinierte Rollen) | UUID |
| `role_permissions` | Rolle × Modul × Berechtigungsstufe | UUID |
| `user_factories` | Werksbereich der Benutzer | UUID |
| `user_product_lines` | Produktlinienbereich der Benutzer | UUID |
| `factories` | Werke | UUID |
| `product_lines` | Produktlinien | UUID |
| `product_types` | Stammdaten Produkttypen (werksübergreifend, von product_lines referenziert) | String (code) |
| `fmea_documents` | FMEA-Dokumente (JSONB graph_data) | UUID |
| `capa_eightd` | 8D/CAPA-Berichte | UUID |
| `audit_logs` | Audit-Log | UUID |

### 5.2 FMEA-Graphmodell

Die FMEA speichert die Graphstruktur in der JSONB-Spalte `graph_data`:

```
{
  "nodes": [
    {"id": "ps_1", "type": "ProcessStep", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    {"id": "fm_1", "type": "FailureMode", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    ...
  ],
  "edges": [
    {"source": "ps_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
    ...
  ]
}
```

`fmeaTable.ts` im Frontend wandelt bidirektional zwischen Graphstruktur und Tabellenzeilen um.

### 5.3 Zustandsautomat CAPA 8D

Die Statusübergänge von `capa_eightd` definiert `backend/app/state_machines/eightd_state.py`, streng in Reihenfolge:

```
D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE → D5_CORRECTION
  → D6_VERIFICATION → D7_PREVENTION → D7_COMPLETED → D8_GATE_PENDING
  → D8_APPROVAL_PENDING → D8_CLOSURE → ARCHIVED
                     ↑                                   │
                     └───── Zurückweisung (reject) ──────┘
```

**Rechte je Übergang**:
- `D8_APPROVAL_PENDING → D8_CLOSURE`, `D8_APPROVAL_PENDING → D7_PREVENTION` (Zurückweisung) und `D8_CLOSURE → ARCHIVED` erfordern `APPROVE`;
- alle übrigen Übergänge (`D1_TEAM → … → D8_APPROVAL_PENDING`) erfordern `EDIT`.

**Wichtige Gates**:
- `D4_ROOT_CAUSE → D5_CORRECTION`: mindestens ein Verifizierungsdatensatz der Grundursache mit `is_verified=true`;
- `D7_PREVENTION → D7_COMPLETED`: alle D7-node-actions sind bearbeitet (confirmed / skipped / auto_filled);
- `D7_COMPLETED → D8_GATE_PENDING → D8_APPROVAL_PENDING`: über das Gate für Dokumentaktualisierungen verbunden;
- `D8_APPROVAL_PENDING → D8_CLOSURE`: erfordert Freigaberecht und schreibt ein Audit; bei Zurückweisung wird `reject_reason` erfasst.

---

## 6. Datenflüsse zwischen Modulen

```
FMEA ──→ Besondere Merkmale (SC/CC) ──→ Produktionslenkungsplan (CP)
  │                                  │
  │                                  ↓
  └──→ 8D/CAPA ←── SCAR ←── Wareneingangsprüfung (IQC)
        │    ↑         ↑
        │    │         │
        └→ SPC-Regelkarten   Lieferantenmanagement
             │              │
             └──→ MSA ←────┘

Reklamation/RMA → SCAR → Lieferant
  │                   │
  └→ FMEA ←───────────┘

Managementbewertung ← Qualitätsziele ← KPI-Daten
  ↑
  ├── CAPA-Statusübersicht
  ├── SPC-Prozessfähigkeit
  └── Kennzahlen Reklamationen/Lieferanten

ERP/MES/PLM ──→ Synchronisation der Dashboard-Daten
Wissensgraph ← Verknüpfungsdaten FMEA/CP
Konzernverwaltung ← Aggregation mehrerer Werke
```

---

## 7. API-Dokumentation

FastAPI erzeugt automatisch eine interaktive API-Dokumentation:

| Dokumentationsart | URL | Beschreibung |
|----------|-----|------|
| Swagger UI | `http://localhost:8000/docs` | Interaktive Testoberfläche |
| ReDoc | `http://localhost:8000/redoc` | Besser lesbare API-Referenz |

Alle API-Pfade beginnen mit `/api/`; die Authentifizierung erfolgt per Bearer-Token (JWT).

---

## 8. 8D-PPT-Ausgabe und Verwaltung der Prüf-Skills

### 8.1 Erzeugung des 8D-Berichts als PPT

Nach dem D8-Abschluss können Benutzer mit einem Klick eine 8D-Präsentation (python-pptx) erzeugen: Deckblatt + je eine Seite für D1–D8 + verknüpfter Anhang (Nachweise der Grundursachenverifizierung).

**Datenfluss**:

```
Benutzer klickt „PPT erzeugen“ → POST /api/capa/{id}/ppt-export
  ├── capa_ppt_service.generate_content()  → PptContent aus den D-Feldern von capa_eightd zusammenstellen
  ├── capa_ppt_review_service.review_and_correct() → Regelprüfung + Prüfschleife mit 3 LLM-Runden
  │     ├── Regelprüfung: _validate_ppt_content() liefert issues, löst regenerate-from-DB aus
  │     ├── Runde 1: LLM prüft die Inhaltsqualität → issues + suggestions
  │     ├── Runde 2: regenerate_from_db() → PptContent neu aus der Datenbank (keine LLM-Umformulierung)
  │     └── Runde 3: abschließende LLM-Prüfung → review_status (skipped/passed/needs_review)
  ├── capa_ppt_service.render_pptx()     → .pptx-Bytestrom erzeugen
  └── In Tabelle capa_ppt_export + AuditLog schreiben
```

**Wichtige Tabellen**:

| Tabelle | Beschreibung |
|----|------|
| `capa_ppt_export` | PPT-Exportdatensätze (export_id, capa_id, factory_id, tenant_schema, generated_at, generated_by, version `YYYYMMDDTHHMMSSZ`, file_url stets `None`, review_status, review_rounds, review_report JSONB, created_at) |
| `agent_review_skill` | Konfiguration der Prüf-Skills (skill_id, tenant_schema zur Mandantentrennung, `name` fest `capa_ppt_review`, content Text, version, is_active, updated_by, updated_at, created_at; Eindeutigkeit über einen Ausdrucksindex auf `COALESCE(tenant_schema, '')`) |

**Berechtigungen**:
- Schaltfläche zum Erzeugen: `canCreate('capa')` (L2, ab quality_engineer)
- Sichtbar nur in den Status D8_CLOSURE / ARCHIVED
- Verwaltungsseite: `require_admin` (nur Rolle admin)

### 8.2 Verwaltung der Prüf-Skills

Ein Prüf-Skill ist die Prompt-Vorlage der LLM-Prüfung und wird von Administratoren über die Endpunkte `/api/admin/review-skills` verwaltet:

- **Standard-Skill**: Der Migrations-Seed schreibt ihn in die Tabelle `agent_review_skill` (name=`capa_ppt_review`), mit Prüfkriterien für die Seiten D1–D8
- **Mandantentrennung**: Über `tenant_schema` sind mandantenspezifische Skill-Inhalte möglich; `name` ist fest `capa_ppt_review`; ohne Mandantenkonfiguration wird auf den öffentlichen Standard zurückgegriffen
- **Operationen**: Administratoren können Skills lesen/aktualisieren (`GET /api/admin/review-skills`, `GET /api/admin/review-skills/{name}`, `PUT /api/admin/review-skills/{name}`; kein DELETE-Endpunkt)
- **Deduplizierung**: nach `name` + `tenant_schema`; mandantenspezifische Inhalte haben Vorrang vor dem öffentlichen Standard

### 8.3 Prüfschleife mit 3 LLM-Runden

`capa_ppt_review_service` setzt die Schleife „prüfen → korrigieren → erneut prüfen“ in 3 Runden um (v3: die Korrektur umfasst nun eine LLM-Umformulierung):

1. **Prüfen**: LLM prüft die Qualität von PptContent und liefert issues + suggestions
2. **Korrigieren** (zwei Arten):
   - Regel-issues (Struktur-/Datenlücken) → `_correct_by_issues()` fragt die Daten neu ab (`generate_content`); verbleibende Probleme führen direkt zu `needs_review`
   - Inhaltsvorschläge des LLM → `_correct_by_suggestions()` lässt das LLM die value-Werte der section je Seite umformulieren (**nur Darstellungsschicht, keine erfundenen Daten, keine Änderung an gespeicherten Fakten zu linked/verification**; bei abweichender Struktur Rückfall auf den Originalinhalt)
3. **Abschließende Prüfung**: LLM bestätigt den korrigierten Inhalt und liefert `review_status` (`skipped`/`passed`/`needs_review`)

- **v4 Schutz der Faktentreue**: Die Strukturprüfung stellt nur sicher, dass Seiten/sections/labels unverändert sind, nicht dass das LLM keine Faktenwerte verfälscht hat. Daher gilt: **besteht schon die erste Runde (ohne Korrektur, Inhalt datenbanktreu) → `passed`; jeder per LLM korrigierte und übernommene Inhalt → zwingend `needs_review`**, mit Vermerk im Bericht „manuell prüfen, dass keine Daten erfunden wurden“ (Inhalte müssen aus gespeicherten Daten stammen; Daten dürfen nicht erfunden werden). Ein Rückfall auf den Originalinhalt (Struktur passt nicht/Regel verletzt/LLM-Fehler) zählt nicht als „korrigiert“; eine in Runde 1 bestandene Prüfung kann weiterhin `passed` sein.
- Verbleiben nach der eingebauten Regelprüfung issues (Struktur-/Datenlücken, durch Korrektur nicht behebbar) → `review_status="needs_review"`, der Bericht zeigt die issues, ohne LLM-Runden zu verbrauchen; ist kein LLM konfiguriert und gibt es keine Regel-issues → `review_status="skipped"`
- Fehler des Korrektur-LLM führen nicht zu 500: Die Prüfung hat bereits einen Bericht erzeugt, nur die automatische Korrektur schlug fehl → Rückfall auf den Originalinhalt, abschließend needs_review + Bericht (benutzersichtbare Informationen bleiben erhalten)
- Laufzeitfehler des Prüf-LLM (Timeout/Authentifizierung/Antwortformat, nicht „nicht konfiguriert“) gelten als FAILED und werden nicht zu `needs_review` herabgestuft: Der Fehler wird weitergereicht, die API-Schicht liefert 500 und speichert keinen Exportdatensatz
- Prüfergebnisse werden in `capa_ppt_export.review_status` + `review_rounds` + `review_report` geschrieben

---

## 9. Bekannte Einschränkungen

| Einschränkung | Beschreibung |
|------|------|
| Testabdeckung wird laufend ausgebaut | Das Backend nutzt pytest (inkl. factory_id-Fixtures, modulübergreifender Regression und API-Schutztests), das Frontend vitest für zentrale Werkzeuge und Seiten; einige ältere Module brauchen noch Fixtures |
| Widerrufsfenster für zustandslose Access-JWTs | Refresh-Tokens werden pro Browser gehasht gespeichert und rotiert; ein Passwort-Reset widerruft die Refresh-Sessions, bereits ausgestellte Access-JWTs bleiben bis zu ihrem ursprünglichen Ablauf gültig. Das Frontend koordiniert Refreshs nach Identitätsgeneration; abgelehnte private CAPA-Lesezugriffe wiederholen keine alten Operationen. |
| Redis ungenutzt | Konfiguriert, aber ohne Cache-Logik |

---

## 10. Geschichtete Abnahme und Release-Grenzen

Die Testinfrastruktur läuft über getrennte Schichten: SDK, Backend, deterministischer Browser, Frontend sowie ausdrückliche Scanner-/Live-Schichten; `make check`
kombiniert SDK-, Backend- und Frontend-Prüfungen und ruft weder implizit echte Modelle noch Scanner auf. Das SDK ist in Unit-Tests (Python-socket-audit), eigene Loopback-Tests und isolierte Installation des echten Wheels gegliedert, mit eigenem Interpreter und ohne Laufzeitabhängigkeiten, ohne Datenbank oder Backend-requirements; ein Python-audit ist keine OS-Sandbox. Die Backend-Schicht baut zuerst offline das aktuelle SDK-Wheel und übergibt es über eine eigene Ressourcenvariable ausdrücklich an die HTTP-Fixture unter normal-policy, ohne alte Build-Quittungen wiederzuverwenden. Jede Schicht erzeugt anhand tatsächlicher Auswahl, JUnit-/Hook-Zähler,
Exit-Code und gefilterter Logs eine Quittung; null ausgewählte Tests, skip/xfail/xpass oder fehlende Quittungen gelten bei expliziten Gates nicht als Erfolg.
Das Backend behält tatsächliche Skips nicht konfigurierter Abhängigkeiten und zählt sie nicht als passed.

Öffentliche Migrationen, pytest und kontrollierte Fixtures verwenden dasselbe geprüfte PostgreSQL-Ziel. Geprüft werden vollständige Container-ID, Owner-Label,
Image, gebundene Adresse/Port und Datenbankidentität; localhost wird als IPv4 normiert, IPv6 verwendet ausdrücklich ::1, zusätzliche libpq-Routingparameter werden abgelehnt,
und Prüfung sowie tatsächliche Verbindung beider Treiber nutzen dieselbe numerische Adresse. Bekannte Python-Testeinstiege sperren implizites dotenv vor dem Import der Anwendung; der pure-Modus
fragt beim Sammeln keine Datenbank ab und lehnt vom Projekt unterstützte Netzwerk-/Datenbankeinstiege ab, ohne sich als OS-Sandbox für beliebige Prozesse auszugeben.

Normale und Browser-Unterprozesse erhalten weder Modellzugangsdaten noch ein nachgetragenes E2E_MODE; die Browserumgebung nutzt eine feste Allowlist und behält streng den geprüften
ausdrücklichen Chromium-Pfad. Der Scanner verwendet ein festes Image und ein zufälliges eigenes Compose-Projekt, exportiert zuerst die tatsächlichen Nachweise, baut dann ab und prüft Rückstände.
Manuelle Remote-Workflows verlangen weiterhin main, einen eingefrorenen Commit und ausdrückliche Administratorkonfiguration; ein bestandenes lokales Gate bedeutet weder eine Remote-Ausführung noch eine aktivierte Produktion
und berechtigt weder zu main-Updates noch zu Deployments.
Noch nicht umgesetzte Teile von SDK, Weitergabe von Text/Anhängen und fachlichem Schreiben folgen weiterhin eigenen Entwürfen und Phasen-Gates.


### Oracle-Release-Controller und PR-Vorschau

Automatische Deployments liest ein vertrauenswürdiger Workflow im Standardbranch anhand der tatsächlichen Prüfergebnisse von Test OpenQMS; er verifiziert geprüften Commit, aktuellen main- bzw. PR-Merge-Ref, Autorenrechte und Quittungszähler. Die normale Testphase hat keine Deployment-Zugangsdaten; in der Deployment-Phase werden auf dem Runner weder Installationsskripte noch Makefile, Migrationen oder Anwendungsimporte des PRs ausgeführt. Produktion und Vorschau verwenden getrennte GitHub-Environments und rollengebundene SSH-Schlüssel; der Empfänger auf dem Server erlaubt nur feste Operationen und hält Release- und Operationssperren.

Automatisierungs-Controller und interaktiver Produktions-Wrapper werden getrennt gehalten, führen gleichwertige Umgebungs- und Identitätsprüfungen aus und steuern über `make deploy-release` seriell Zielidentität, Migration, Bestätigung des exakten CI-Ergebnisses, Initialisierung, Preflight und Release. Anwendungsoperationen laufen in ressourcenbegrenzten Containern. Vorschauen nutzen eigene Datenbanken, Schlüssel, Volumes und private Netze; nur web tritt dem Edge-Netz bei, öffentlich bleibt nur der Nur-Lese-Viewer. Der Admin-Zugang des Produktions-Caddy ist ein Unix-Socket im Container, Vorschau-Routen werden nach Prüfung neu geladen. Vor Produktionsmigrationen wird gesichert; ein fehlgeschlagenes Anwendungs-Release wird über das gesperrte Image wiederhergestellt, die Datenbank wird nicht automatisch zurückgesetzt.

Umsetzung und Konfiguration siehe [Automatisches Deployment](oracle-automation.md) und [Server-Controller](oracle-production-setup.md). Vorhandene Implementierung bedeutet nicht, dass der Server installiert oder die Schalter aktiviert sind; Nachweise und verbleibende Bedingungen stehen in PROGRESS.md.
