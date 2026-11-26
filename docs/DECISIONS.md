# Entscheidungsprotokoll (Architecture Decision Records)

Dieses Dokument hält zentrale Designentscheidungen von OpenQMS fest – mit dem Kontext zum Zeitpunkt der Entscheidung und ihren Folgen.
Aufgenommen werden nur Entscheidungen, die Code oder Team **langfristig binden**; umkehrbare Implementierungsdetails und vorübergehende Workarounds gehören nicht hierher.

## Format

Jede Entscheidung folgt einem schlanken ADR-Format:

- **Nummer**: `ADR-NNNN`, monoton steigend, nach Festlegung nie wiederverwendet
- **Datum**: Tag der Festlegung (`YYYY-MM-DD`)
- **Status**: `Accepted` / `Superseded by ADR-XXXX` / `Deprecated`
- **Kontext**: damaliges Problem, Randbedingungen, Alternativen
- **Entscheidung**: was gewählt wurde und was **nicht**
- **Folgen**: positive und negative Auswirkungen auf Code, Betrieb und Team

Neue Entscheidungen werden am Ende angehängt. **Festgelegte Entscheidungen nicht an Ort und Stelle umschreiben** – wird eine Entscheidung revidiert, eine neue ADR anlegen und den Status der alten auf `Superseded by ADR-XXXX` setzen.

---

## ADR-0001 — Primärschlüssel einheitlich als in Python erzeugte UUID v4

- **Datum**: 2025-08-15
- **Status**: Accepted
- **Kontext**: Bei mehreren Werken und Mandanten müssen IDs datenbankübergreifend eindeutig und offline erzeugbar sein; fortlaufende IDs sollen kein Geschäftsvolumen verraten. Alternativen: PG `bigserial`, PG-seitiges `gen_random_uuid()`, Python-seitiges `uuid4()`.
- **Entscheidung**: Alle Primärschlüssel der Geschäftstabellen sind `UUID v4`, erzeugt in Python (`uuid.uuid4()`); das ORM definiert `default=uuid.uuid4`, der Spaltentyp ist `UUID(as_uuid=True)`.
- **Folgen**:
  - ✅ Keine ID-Konflikte über Werke/Mandanten hinweg; erleichtert spätere Konzernzusammenführung und Anbindung externer Systeme
  - ✅ Die Service-Schicht kennt die ID bereits vor dem `flush` und kann verknüpfte Objekte zusammenbauen
  - ⚠️ Indizes sind größer als bei `bigint`; nicht nach Primärschlüssel paginieren/sortieren, sondern einheitlich nach `created_at DESC`
  - ⚠️ Alembic-Migrationen müssen `UUID(as_uuid=True)` explizit angeben, sonst fällt PG auf `VARCHAR(36)` zurück

## ADR-0002 — FMEA als JSONB-Graphmodell, keine Aufteilung in relationale Tabellen

- **Datum**: 2025-09-10
- **Status**: Accepted
- **Kontext**: Die Knotenbeziehungen der PFMEA/DFMEA nach AIAG-VDA (7 Schritte) bilden einen dynamischen Graphen (System→Subsystem→…→FailureMode→Effect/Cause→Controls) mit vielen und häufig neuen Knotentypen. Alternativen: vollständig relational (≥ 12 Verknüpfungstabellen), dokumentenorientiert (MongoDB), JSONB-Graph.
- **Entscheidung**: Die JSONB-Spalte `fmea_documents.graph_data` speichert `{nodes: [...], edges: [...]}`, Knoten- und Kantentypen werden über Enum-Strings eingeschränkt; `fmeaTable.ts` im Frontend wandelt bidirektional in Tabellenzeilen mit 20+ Spalten um.
- **Folgen**:
  - ✅ Neue oder entfallende Knotentypen brauchen keine Schemamigration; DFMEA/PFMEA teilen sich denselben Code
  - ✅ Der ganze Graph wird in einem Zug gelesen/geschrieben, kein N+1
  - ⚠️ FMEA-übergreifende Abfragen („In welchen FMEAs kommt dieses Bauteil vor?“) brauchen `jsonb_array_elements()` und können keinen Index nutzen – daher die doppelten Repositories Neo4j + JSONB (siehe ADR-0010)
  - ⚠️ Gemeinsam genutzte Knoten (Maßnahmen, Aktionen) erfordern Referenzzählung beim Löschen: `fmeaTable.ts` prüft beim Zeilenlöschen, ob andere Zeilen sie noch referenzieren, sonst würde versehentlich gelöscht
  - ⚠️ Die RPN-Aggregation im Dashboard nutzt rohes SQL + `jsonb_array_elements()` (siehe ADR-0007)

## ADR-0003 — Werkstrennung über zeilenweisen `factory_id`-Filter statt Schema pro Mandant (innerhalb eines Deployments)

- **Datum**: 2025-10-02
- **Status**: Accepted (SaaS-Mandantenschicht siehe ADR-0012)
- **Kontext**: Bei Kunden mit mehreren Werken soll „die Ingenieurin in Werk A die Daten von Werk B nicht sehen“ – bei gleichem Code und gleicher Datenbank. Alternativen: Schema je Werk, Datenbank je Werk, zeilenweise `factory_id`.
- **Entscheidung**: Alle Geschäftstabellen haben `factory_id NOT NULL`; `core/factory_scope.py` stellt `check_factory_access(entity, scope)` bereit; `RequestScope` in `core/deps.py` injiziert pro Anfrage die „für den Benutzer sichtbaren Werke“. In der Tabelle `users` darf `factory_id` NULL sein; das kennzeichnet Konzernadministratoren.
- **Folgen**:
  - ✅ Einfaches Deployment und einfache Migration; werksübergreifende Berichte und Konzernaudits ohne föderierte Abfragen
  - ✅ Zeilenrechte und RBAC sind entkoppelt: Rollen regeln „was darf ich tun“, der Scope „welche Zeilen darf ich sehen“
  - ⚠️ **Jede Service-Methode eines neuen Moduls muss `check_factory_access` explizit aufrufen** – ein vergessener Aufruf ist eine Rechteausweitung, die CI nicht statisch erkennt
  - ⚠️ Werksübergreifende Statistikschnittstellen (Group-Admin-Dashboard) müssen ausdrücklich als Ausnahme gekennzeichnet werden, sonst filtert der Scope sie leer

## ADR-0004 — AuditLog manuell in der Service-Schicht statt automatischer SQLAlchemy-Event-Hooks

- **Datum**: 2025-10-18
- **Status**: Accepted
- **Kontext**: Compliance (IATF 16949 / ISO 9001) verlangt Rückverfolgbarkeit aller Qualitätsaufzeichnungen. Alternativen: automatisches Audit per SQLAlchemy `event.listens_for(Session, "after_flush")`, AOP-Dekorator, manuelles Schreiben in der Service-Schicht.
- **Entscheidung**: Jede CRUD-Operation legt in der Service-Methode **manuell** eine `AuditLog`-Zeile an, mit den Feldern `actor_id / module / action / entity_id / before / after / reason`.
- **Folgen**:
  - ✅ Fachlicher Kontext ist explizit („warum geändert“ – das sieht ein automatischer Hook nicht); fachliche Felder wie 8D-Phase oder FMEA-Revisionsnummer lassen sich mitschreiben
  - ✅ Tests können prüfen „ein update → ein Audit-Eintrag“; Event-Hooks sind schwer zu testen
  - ⚠️ **Ein vergessenes AuditLog in neuen Service-Methoden ist der häufigste Fehler** – Pflichtpunkt der Code-Review-Checkliste
  - ⚠️ `enqueue_embedding()` muss **vor** `await db.commit()` aufgerufen werden, sonst gehen Outbox-Zeilen verloren (gleiche Transaktion wie das Audit)

## ADR-0005 — JWT HS256 mit 120 Minuten Gültigkeit, kein OAuth2-Drittanbieter/Refresh-Token

- **Datum**: 2025-09-25
- **Status**: Superseded by ADR-0014
- **Kontext**: Überwiegend interne Deployments ohne Dritt-IdP; Benutzer akzeptieren eine erneute Anmeldung nach 2 Stunden. Alternativen: JWT RS256 (Schlüsselverteilung nötig), Session + Redis, OAuth2 + Refresh-Token.
- **Entscheidung**: HS256 mit einem Secret aus der Umgebungsvariablen `SECRET_KEY`; Token mit `sub=user_id` und 120 Minuten `exp`; `ProtectedRoute` im Frontend prüft den Ablauf lokal; bei Ablauf löscht der Axios-Interceptor das Token → `/login`. Kein Refresh-Token.
- **Folgen**:
  - ✅ Einfache Umsetzung, keine serverseitige Session-Speicherung
  - ⚠️ Keine aktive Abmeldung bzw. kein Widerruf – nach einer Passwortänderung bleibt ein altes Token bis zu 2 Stunden gültig
  - ⚠️ `SECRET_KEY` muss in Deployment und Tests übereinstimmen; Tests verwenden `SECRET_KEY=test-secret-key`
  - ⚠️ Kein Rate-Limiting beim Login (siehe Known Gaps in `PROGRESS.md`), muss nachgezogen werden

## ADR-0006 — Berechtigungsmatrix = 7 Rollen × 25 Module × 5 Stufen, kein ACL-/Policy-Engine

- **Datum**: 2025-10-12
- **Status**: Accepted
- **Kontext**: Im Qualitätsmanagement sind die Zuständigkeiten klar (admin / manager / quality_engineer / viewer + group_admin / supplier_manager / customer_manager); ein beliebiges Subjekt-Objekt-Aktion-Policy-System ist unnötig. Alternativen: Casbin, OPA, eingebaute RBAC-Matrix.
- **Entscheidung**: Die Tabellen `role_definitions` × `permissions` speichern die Matrix; `core/permissions.py` definiert die Enums `Module` / `PermissionLevel`; die API-Schicht nutzt `require_permission(Module.X, PermissionLevel.Y)`; der Frontend-Hook `usePermission` spiegelt die Logik für die Menüfilterung. Freigaberechte der Zustandsautomaten (FMEA-Freigabe, 8D-Abschluss D7/D8) sind in der Service-Schicht als Rollenprüfung fest codiert und nicht Teil der Matrix.
- **Folgen**:
  - ✅ Die Matrix ist sichtbar und gut auditierbar; neue Rollen werden nur im Seed ergänzt
  - ✅ Konsistenz zwischen Frontend und Backend über dieselben `Module`-Konstanten (im Frontend aus `types/index.ts` gespiegelt)
  - ⚠️ Fachliche Querschnittsregeln wie „nur im eigenen Werk freigeben“ stehen nicht in der Matrix, sondern verstreut in Services – gebündelt über `core/factory_scope.py` (siehe ADR-0003)
  - ⚠️ Die vollständige Matrix steht in `docs/permissions.md`; bei Änderungen **muss** dieses Dokument mit aktualisiert werden

## ADR-0007 — Dashboard-Aggregation mit rohem SQL + JSONB-Funktionen statt ORM

- **Datum**: 2025-11-04
- **Status**: Accepted
- **Kontext**: Das Dashboard muss alle FailureMode-Knoten aus dem JSONB `graph_data` der FMEAs flach auswerten und die RPN statistisch aggregieren; das kann das SQLAlchemy-ORM nicht ausdrücken. Alternativen: ORM-Relation-Hack, Aggregation in Python, rohes SQL mit `text()`.
- **Entscheidung**: `services/dashboard_service.py` nutzt `db.execute(text(...))` mit `jsonb_array_elements(graph_data->'nodes')` zum Abflachen und danach `GROUP BY`, `AVG`, `COUNT`. Alle Benutzereingaben im SQL laufen über Bind-Parameter (`:name`).
- **Folgen**:
  - ✅ Eine einzige Abfrage, statt 1000 FMEA-Dokumente nach Python zu laden
  - ⚠️ SQL ist an PG gebunden und nicht portabel – akzeptiert
  - ⚠️ Änderungen an JSONB-Pfaden (umbenannte Felder im Knotenschema) lassen das Dashboard stillschweigend 0 liefern; bei Schemaänderungen hier mitprüfen

## ADR-0008 — Im Frontend verwaltet Zustand nur Auth + Produktlinie + Werk, Geschäftsdaten über `useState`

- **Datum**: 2025-09-30
- **Status**: Accepted
- **Kontext**: React 18 + Vite + Ant Design waren gesetzt; die Zustandsverwaltung musste entschieden werden. Alternativen: Redux Toolkit, Zustand global, reines `useState` + Props.
- **Entscheidung**: Zustand trägt nur seitenübergreifende globale Zustände: `useAuthStore`, `useProductLineStore`, `useFactoryStore`. Listen-, Filter- und Formularzustände jeder Seite liegen in lokalem `useState`; paginierte Daten folgen dem generischen `PaginatedResponse<T>`.
- **Folgen**:
  - ✅ Geringe Lernkurve, Seitendateien sind in sich geschlossen
  - ✅ Keine undurchsichtigen Selector-Re-Renders
  - ⚠️ Seitenübergreifender Cache („Liste aktualisieren, Detail öffnen, zurück“) geht verloren – akzeptiert
  - ⚠️ Kein React Query / SWR: alle Axios-Aufrufe behandeln Loading/Error von Hand, viel wiederholter Boilerplate

## ADR-0009 — FMEA-Editor ohne Tabellenbibliothek, eigene Tabelle aus Ant `Input`+`Select`

- **Datum**: 2025-10-22
- **Status**: Accepted
- **Kontext**: 20+ Spalten, stark unterschiedliche Zelltypen (Dropdown, Kaskade, Langtext, Zahl) und zeilenübergreifende Abhängigkeiten (S/O/D → AP per Tabelle). Alternativen: AG Grid, Handsontable, ant-table-edit, native Tabelle.
- **Entscheidung**: Tabelle von Hand aus Ant Design `Input`, `Select` und `InputNumber`; `utils/fmea.ts` enthält die AIAG-VDA-Action-Priority-Tabelle; `utils/fmeaTable.ts` übernimmt die bidirektionale Umwandlung JSONB-Graph ↔ Zeilenmodell.
- **Folgen**:
  - ✅ Keine Lizenzkosten und kein Bundle-Zuwachs; passt von Haus aus zum Ant-Design-Stil
  - ✅ Vollständig steuerbar (Zeilen-Fan-out nach Ursache × Folge, mehrere Folgen, Referenzzählung gemeinsamer Knoten – alles selbst definiert)
  - ⚠️ Performancegrenze: ab > 500 Zeilen pro Dokument wird es träge, bisher nicht erreicht
  - ⚠️ Tabellenübliche Funktionen wie Kopieren/Einfügen, Mehrfachauswahl und Rückgängig müssen selbst gebaut werden

## ADR-0010 — Wissensgraph mit doppeltem Repository Neo4j + JSONB statt Migration nach Neo4j

- **Datum**: 2025-12-08
- **Status**: Accepted
- **Kontext**: FMEA-übergreifende Suche (ähnliche Fehlerarten, BFS für Änderungsauswirkungen) ist auf PG-JSONB nicht indexierbar; eine vollständige Migration nach Neo4j würde Transaktionen und Alembic-Migrationen aufgeben. Alternativen: reines PG + materialisierte Views, reines Neo4j, Synchronisation zweier Quellen.
- **Entscheidung**: PG-JSONB ist die **führende Quelle** (source of truth); beim Speichern einer FMEA wird asynchron nach Neo4j synchronisiert (Modul `graph/`); Abfragen werden je Fall geroutet – CRUD über das JSONB-Repository, Ähnlichkeit/BFS über das Neo4j-Repository. Gehen Neo4j-Daten verloren, lassen sie sich aus PG neu aufbauen.
- **Folgen**:
  - ✅ Transaktionen und Audit bleiben in PG; ein Neo4j-Ausfall beeinträchtigt die Kernprozesse nicht
  - ✅ Empfehlungen und Auswirkungsanalysen profitieren von der Graph-Traversierung
  - ⚠️ Konsistenz beim doppelten Schreiben: beruht auf Outbox + Retry, kein strenges Prüfskript
  - ⚠️ Ein Dienst mehr im Deployment (in docker-compose enthalten)

## ADR-0011 — Agent-Framework ohne pydantic-ai, eigener schlanker Harness direkt auf openai/anthropic-SDK

- **Datum**: 2026-06-15
- **Status**: Accepted
- **Kontext**: Die P0-AI-Agent-Basis braucht Tool-Aufrufe + HITL-Freigabe + dreistufiges Gedächtnis + Guardrails. pydantic-ai war erste Wahl, benötigt aber pydantic ≥ 2.10, während das Projekt pydantic 2.9.2 fixiert (FastAPI 0.115 + viele bestehende Schemas, kein Upgrade möglich). Alternativen: pydantic im ganzen Stack aktualisieren, LangChain, eigener Harness.
- **Entscheidung**: Eigener Harness in `app/agent/` – dreistufiges Gateway (5-Tupel-Whitelist) + HITL-Freigabe + 3-stufiges Memory + Guardrails; Tool-Aufrufe direkt über die offiziellen openai/anthropic-SDKs.
- **Folgen**:
  - ✅ Die Fixierung auf pydantic 2.9.2 bleibt intakt
  - ✅ 6 Tabellen `agent_*` + 82 Unit-Tests, kontrollierbares Verhalten
  - ⚠️ Die Tool-Call-Schleife wird selbst gepflegt; parallele Tools und das `tool_result`-Shaping für anthropic sind P2-Folgearbeiten
  - ⚠️ Detaillierte Ursachenanalyse in der Memory-Notiz `ai-driven-qms-p0-agent-base.md`

## ADR-0012 — SaaS-Mandantenfähigkeit über Schema pro Mandant + JWT-Domänentrennung, kein zusätzliches `tenant_id` pro Zeile

- **Datum**: 2026-01-20
- **Status**: Accepted
- **Kontext**: SaaS-Kunden verlangen „physisch getrennte Daten“, der Code soll aber mehrere Kunden bedienen. Alternativen: `tenant_id` in allen Tabellen (zusätzlich zu `factory_id`), Schema pro Mandant, Datenbank pro Mandant.
- **Entscheidung**: Jeder Mandant erhält ein eigenes PG-Schema (`tenant_xxx`); die JWT-Domäne (`acme.openqms.com`) wird auf das passende Schema geroutet; innerhalb des Schemas gilt weiter die zeilenweise `factory_id`-Trennung aus ADR-0003. Neue Mandanten entstehen per Klon eines Vorlagen-Schemas.
- **Folgen**:
  - ✅ Physische Trennung ist compliance-freundlich; Export/Migration eines Mandanten braucht nur `pg_dump --schema`
  - ✅ Bestehender Geschäftscode braucht kein `tenant_id`
  - ⚠️ Alembic-Migrationen müssen für jedes Schema laufen – im Deployment-Skript gekapselt
  - ⚠️ Mandantenübergreifende Konzernberichte sind nicht möglich (so gewollt)

## ADR-0013 — Alembic-Migrationen von Hand, kein autogenerate

- **Datum**: 2025-08-20
- **Status**: Accepted
- **Kontext**: autogenerate erkennt JSONB, Enums, umbenannte Constraints und zusammengesetzte Indizes unzuverlässig; Produktionsmigrationen brauchen oft eigenes SQL (Datennachpflege, UPDATE in Tranchen). Alternativen: reines autogenerate, autogenerate + manuelle Prüfung, rein manuell.
- **Entscheidung**: Alle Migrationen werden **von Hand** mit `op.create_table / op.add_column / op.execute(...)` geschrieben; Benennung `NNNN_<verb>_<objekt>.py`; komplexe Datenmigrationen nutzen in `upgrade()` `op.execute(text(...))`.
- **Folgen**:
  - ✅ Daten- und Schemamigration liegen in derselben Datei, Rollback ist eindeutig
  - ✅ Verhalten von JSONB-Feldern und Check-Constraints ist steuerbar
  - ⚠️ Gelegentliche Nummernkonflikte (bei parallelen Branches) – in den Known Gaps von `PROGRESS.md` vermerkt, muss vereinheitlicht werden
  - ⚠️ Etwas höhere Einstiegshürde für neue Entwickler; an vorhandenen Migrationen orientieren

## ADR-0014 — Pro Browsersitzung gehashte, rotierende und widerrufbare Refresh-Tokens

- **Datum**: 2026-09-14
- **Status**: Accepted
- **Kontext**: Das einzelne 120-Minuten-Access-JWT aus ADR-0005 lässt sich bei Ablauf nicht unbemerkt verlängern, trennt mehrere Browser-Anmeldungen nicht und erkennt kein Replay von Refresh-Credentials. Ohne Dritt-OAuth2/IdP soll das HS256-Access-JWT erhalten bleiben und um einen minimalen, auditierbaren serverseitigen Sitzungs-Sicherheitszustand ergänzt werden.
- **Entscheidung**:
  - Jede Browser-Anmeldung erzeugt eine eigene Refresh-Session; die stabile `sid` im JWT identifiziert die Sitzung, jede Ausstellung erzeugt eine neue zufällige `jti`. Die Datenbank speichert nur den `SHA-256`-Hash des vollständigen Refresh-Tokens, nie den Klartext.
  - Beim Refresh werden Prüfung und Rotation unter einer **exakten Zeilensperre** (row lock) auf `(sid, user_id)` ausgeführt; der alte Hash ist nach einer erfolgreichen Rotation sofort ungültig, jedes Replay eines alten Tokens wird abgelehnt. Die Refresh-Frist ist rollierend (rolling) ab der letzten erfolgreichen Nutzung, also eine inactivity-basierte Inaktivitätsfrist und keine feste Gesamtdauer der Anmeldung.
  - Ein legacy Refresh-Token ohne `sid` darf genau einmal aufgewertet werden: unter der Zeilensperre des Benutzers wird der alte Wert geprüft, die alte Spalte geleert und ein neues Session-Token ausgestellt; danach ist weder erneutes Aufwerten noch Replay möglich.
  - Das Frontend bündelt gleichzeitige `401`-Antworten zu einem Refresh und wiederholt die ursprüngliche Anfrage nur, wenn altes und neues Access-JWT zur selben Identität (identity) gehören; über Tabs hinweg wird die neueste Generation synchronisiert, von der alten Identität abgeleiteter Zustand geleert und anschließend über `/auth/me` Benutzer, Berechtigungen und Werks-/Produktlinienbereich sicher wiederhergestellt.
  - Ein Passwort-Reset widerruft alle Refresh-Sessions des Benutzers; bereits ausgestellte zustandslose Access-JWTs (access) können bis zu ihrem ursprünglichen 120-Minuten-Ablauf gültig bleiben. Ein sofortiger Widerruf von Access-JWTs über Token-Version oder Denylist ist vertagt und nicht Teil dieser Entscheidung.
  - Zeilen in `user_refresh_sessions` sind Authentifizierungs-Sicherheitszustand und keine Qualitäts-/Geschäfts-CRUD-Datensätze; die Rotation schreibt daher kein fachliches `AuditLog`. Erfolgreiche und fehlgeschlagene Anmeldungen werden weiterhin in `LoginAuditLog` erfasst; der Passwort-Reset durch einen Administrator wird als Benutzeränderung weiterhin fachlich auditiert.
- **Folgen**:
  - ✅ Bei fortlaufender Nutzung wird automatisch verlängert, und verschiedene Browsersitzungen überschreiben sich nicht
  - ✅ Ein Datenbankleck legt keine direkt nutzbaren Refresh-Credentials offen; exakte Zeilensperre und Hash-Rotation schützen vor Mehrfachnutzung/Replay
  - ✅ Konkurrenz zwischen Tabs führt nicht dazu, dass Anfragen des alten Benutzers unter der neuen Identität wiederholt werden
  - ⚠️ Ein Passwort-Reset widerruft Access-JWTs nicht sofort; es bleibt ein Fenster von bis zu 120 Minuten, das Betrieb und Admin-Oberfläche klar benennen müssen
  - ⚠️ Die Refresh-Rotation ist hochfrequenter Authentifizierungszustand und wird bewusst nicht ins fachliche Compliance-`AuditLog` kopiert; Sicherheitsmonitoring nutzt Authentifizierungslogs und Anomalie-Kennzahlen

## ADR-0015 — Oracle-Instanz als öffentlich beschreibbare Demo, privilegierte Konten ausdrücklich öffentlich

- **Datum**: 2026-09-18
- **Status**: Superseded by ADR-0016
- **Kontext**: Der ursprüngliche Go-live-Plan veröffentlichte nur den Viewer und verlangte die Rotation der Passwörter von `admin`, `engineer`, `manager` und `groupadmin`. Der Eigentümer der Instanz entschied sich um, damit Besucher echte Berechtigungen ausprobieren können: Die vier gemeinsamen Demo-Konten bleiben mit vollen Schreib-/Verwaltungsrechten erhalten und ihre Zugangsdaten stehen auf der Login-Seite.
- **Entscheidung**:
  - Die Domain erhält bei Namecheap BasicDNS einen `qms`-A-Eintrag direkt auf die öffentliche Oracle-IP; Caddy terminiert HTTPS; kein Umzug auf einen Cloudflare-Proxy. Öffentliches SSH auf Port 22 bleibt vorerst nach Wahl des Eigentümers offen, Tailscale dient weiter der Verwaltung.
  - Der Standard-Build erlaubt weiterhin nur die schreibgeschützte Viewer-Demo; die vier zusätzlichen Konten müssen über das optionale vollständige JSON in `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` ausdrücklich aktiviert werden, werden beim Build ins Browser-Bundle eingebettet, und erst dann zeigt das normale `/login` fünf Konten samt Warnung zur gemeinsamen Schreibnutzung. Ein Klick füllt nur das Formular aus und meldet nicht automatisch an; das Backend-RBAC wird nicht abgeschwächt.
  - Diese Zugangsdaten sind absichtlich öffentliche Demo-Werte und dürfen keine Mitarbeiterpasswörter wiederverwenden. In dieser Instanz dürfen keine echten Daten und keine echten LLM-/Embedding-/API-Schlüssel erfasst werden; andere echte Produktivumgebungen müssen weiterhin alle privilegierten Passwörter rotieren und die zusätzliche Demo-Build-Eingabe deaktivieren.
- **Folgen**:
  - ✅ Besucher können Viewer-, Ingenieur-, Manager- und Administratorfunktionen ausprobieren; der Viewer bleibt schreibgeschützt.
  - ⚠️ `admin` und `groupadmin` haben echte Administratorrechte; jeder Besucher kann Passwörter, Berechtigungen und gemeinsame Daten ändern. Die Demodaten haben keine Integritätsgarantie und kein automatisches Zurücksetzen. Auf der statischen Seite angezeigte Passwörter können durch Besucher ungültig werden: Die Wiederherstellung des ursprünglichen öffentlichen Werts erfordert keinen Neubau; bei einem anderen öffentlichen Wert müssen Build-Eingabe und Release aktualisiert werden.
  - ⚠️ PostgreSQL-Sicherungen liegen derzeit nur auf demselben Host; eine öffentlich beschreibbare Umgebung eignet sich nicht für Kunden-, Mitarbeiter- oder Compliance-Daten. Beim Deaktivieren des Demo-Builds müssen alle `VITE_PUBLIC_DEMO_*`-Zugangseingaben geleert werden; nur die UI zu verstecken genügt nicht.

## ADR-0016 — Öffentliche Demo nur mit drei Konten ohne Rechte zur Benutzeränderung

- **Datum**: 2026-09-19
- **Status**: Accepted (Supersedes ADR-0015)
- **Kontext**: ADR-0015 sah vor, `admin` und `groupadmin` zu veröffentlichen; beide haben die Rolle `admin` und können über `user_mgmt` Passwörter und Rechte anderer Konten ändern. Der Eigentümer der Instanz verlangte daraufhin ausdrücklich, Administratorkonten nicht zu veröffentlichen, damit Besucher keine anderen Konten verändern.
- **Entscheidung**: Die öffentliche Login-Seite zeigt nur `Viewer` (Konto `viewer`), `engineer` und `manager`; `admin` und `groupadmin` bleiben privat und dürfen auch nicht in `VITE_PUBLIC_DEMO_ADDITIONAL_ACCOUNTS` stehen. `engineer` hat für `user_mgmt` die Stufe 0, `manager` nur VIEW=1; beide können keine Benutzer oder Passwörter ändern. Das optionale JSON muss genau `engineer` und `manager` enthalten, sonst schlägt das Frontend geschlossen fehl (fail closed).
- **Folgen**:
  - ✅ Besucher können weiterhin Lesezugriff, Qualitätsingenieur- und Manager-Freigabeabläufe ausprobieren, gelangen aber nicht an die Schnittstellen zur Benutzeränderung.
  - ✅ Dass das aktuelle Standardpasswort von `admin` 401 liefert, blockiert die Veröffentlichung der Drei-Konten-Seite nicht mehr und muss für die öffentliche Anzeige nicht wiederhergestellt werden.
  - ⚠️ `engineer` und `manager` können weiterhin viele gemeinsame Qualitätsdaten ändern; die Demodaten werden nicht automatisch zurückgesetzt, daher weiterhin keine echten Daten und keine echten API-Schlüssel erfassen.
  - ⚠️ Dies ist eine Vorgabe zur Kontoanzeige und ersetzt nicht das Backend-RBAC; jedes Release muss die `user_mgmt`-Rechte der öffentlichen Konten und die 403-Grenze für `/api/auth/users/{id}` per Regression prüfen.

---

## Wann eine neue ADR schreiben

Eine ADR wird geschrieben, wenn einer dieser Punkte zutrifft:

1. Es wurde eine Technik oder ein Muster gewählt, das die Richtung des Codes **langfristig bindet** (Bibliothek, Protokoll, Datenmodell)
2. Ein plausibel wirkender Ansatz wurde **abgelehnt** (vorbeugende Dokumentation „warum nicht X“)
3. Externe Randbedingungen (Compliance, Performance, fixierte Abhängigkeiten) zwingen den Code weg vom üblichen Vorgehen

**Nicht** geschrieben wird für:

- Implementierungsdetails einzelner Dateien, Bugfixes, Umbenennungen
- Vorübergehende Workarounds (dafür `# TODO` oder `PROGRESS.md`)
- Modulinterne Entscheidungen ohne Wirkung auf andere Module

---

> Historischer Hinweis: Diese Datei entstand am 2026-06-30; die ersten 13 ADRs sind eine **nachträgliche Aufarbeitung** bereits bestehender Entscheidungen, das Datum entspricht dem jeweils relevantesten Code-Merge. Spätere Entscheidungen werden zum Zeitpunkt ihrer Festlegung erfasst.
