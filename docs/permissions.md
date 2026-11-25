# OpenQMS-Berechtigungsreferenz

> Private Aufgabenanhänge (R4b-2) prüfen stets aktuell CAPA-VIEW für Aufgabe/CAPA, die eigene Aufgabenidentität sowie Werks- und Produktlinienbereich; Downloads erzeugen keine Direktlinks. Betriebsgrenzen siehe [Anleitung zu Anhängen](development/agent-task-attachments.md).

> Zuletzt aktualisiert: 2026-10-29 (eigenständig eingefrorene CAPA-Ergebnisse und Grenzen externer Gates) | Grundlage: Berechtigungsmodell im Code (ModuleKey × PermissionLevel × Role)

---

## 1. Berechtigungsmodell

OpenQMS verwendet ein dreistufiges Modell aus **Rolle + Modul-Berechtigungsstufe + Werks-/Produktlinienbereich**:

```
Benutzer (User)
  └→ Rolle (RoleDefinition) — 7 vordefinierte Rollen
       └→ Rollenberechtigung (RolePermission) — module × permission_level
  └→ Werksbereich (UserFactory) — Liste zugänglicher Werke
  └→ Produktlinienbereich (UserProductLine) — Liste zugänglicher Produktlinien
```

### 1.1 Enum PermissionLevel

| Wert | Konstante | Bedeutung |
|:--:|------|------|
| 0 | NONE | Keine Berechtigung, Modulmenü ausgeblendet |
| 1 | VIEW | Nur lesen |
| 2 | CREATE | Neue Datensätze anlegen |
| 3 | EDIT | Bestehende Datensätze bearbeiten |
| 4 | APPROVE | Freigeben/abschließen/archivieren |
| 5 | ADMIN | Vollzugriff |

### 1.2 ModuleKey-Liste

Das Backend-Enum `Module` und der Frontend-Typ `ModuleKey` entsprechen sich eins zu eins:

| ModuleKey | Beschreibung |
|-----------|------|
| fmea | FMEA-Verwaltung |
| capa | 8D/CAPA |
| planning | Produktionslenkungsplan/APQP |
| ppap | PPAP |
| iqc | Wareneingangsprüfung |
| supplier | Lieferantenmanagement |
| supplier_risk | Lieferantenrisiko |
| supply_chain_risk_map | Risikokarte der Lieferkette |
| customer_quality | Reklamationen/RMA |
| customer_audit | Kundenaudits |
| scar | SCAR |
| spc | Statistische Prozesslenkung |
| msa | Messsystemanalyse |
| special_characteristic | Besondere Merkmale |
| quality_goal | Qualitätsziele |
| audit | Interne Audits |
| management_review | Managementbewertung |
| dashboard | Dashboard |
| user_mgmt | Benutzerverwaltung |
| permission_mgmt | Berechtigungsverwaltung |
| knowledge_graph | Wissensgraph |
| mes | MES-Integration |
| plm | PLM-Integration |
| erp | ERP-Integration |
| group | Konzernverwaltung |

### 1.3 Rollendefinitionen

| Rolle | role_key | Beschreibung | Systemrolle | Bearbeitbar |
|------|----------|------|:--------:|:------:|
| Systemadministrator | admin | Vollzugriff | ✓ | ✗ |
| Qualitätsmanager | manager | Freigaberechte | ✓ | ✓ |
| Nur-Lese-Benutzer | viewer | Nur ansehen | ✓ | ✗ |
| Kundenqualitätsingenieur | customer_qe | Reklamationen/Audits bearbeiten | ✓ | ✓ |
| Lieferantenqualitätsingenieur | supplier_qe | Lieferanten/IQC bearbeiten | ✓ | ✓ |
| Qualitätsingenieur Fertigung | field_qe | FMEA/SPC bearbeiten | ✓ | ✓ |
| Qualitätsingenieur Vorausplanung | planning_qe | FMEA/PPAP bearbeiten | ✓ | ✓ |

> Die Berechtigungen der Rollen mit `is_system=True` (admin, viewer) sollten nicht geändert werden.

---

## Agent-Aufgaben und Plugin-Verwaltung (R1)

Die neuen Schnittstellen werden über `AGENT_TASK_RUNTIME_ENABLED` gesteuert und sind standardmäßig deaktiviert; im deaktivierten Zustand antworten sie vor Mandantenauflösung und Authentifizierung mit 404. Alte Agent-Pfade behalten ihre bisherigen Berechtigungsregeln.

| Schnittstelle | Aktuelle Anforderungen an Berechtigung und Bereich |
|---|---|
| `/api/agent/tasks` anlegen, Liste, Detail | Aktueller Benutzer und Rolle aktiv, CAPA VIEW, Zielbericht im aktuell zugänglichen Werks- und Produktlinienbereich; nur selbst gestartete und ausgeführte Aufgaben werden geliefert. Liste und Anzahl werden ebenso gefiltert. |
| `/api/agent/tasks/{task_id}/messages` | Wie oben, zusätzlich darf die Aufgabe nicht beendet sein; nach dem Warten auf die Aufgabensperre wird erneut geprüft. Nachrichten sind standardmäßig restricted; wiederholte Anfragen erzeugen weder neue Nachrichten noch Audits. |
| `/api/admin/agent-plugins` sowie aktivieren/deaktivieren, rotieren, Grants | Aktueller Rollenschlüssel admin und PERMISSION_MGMT auf ADMIN; Schreiboperationen prüfen nach dem Warten auf die Zeilensperre erneut. Registrierung und Rotation liefern das Secret genau einmal; Liste und Detail enthalten keinen Zugangsdaten-Hash. |
| `/api/admin/agent-plugins/{installation_id}/revoke-local-trial` | Aktuell admin + PERMISSION_MGMT ADMIN, erneute Prüfung nach dem Warten auf die Installationssperre; CAS mit strikt erwartetem Epoch: schließen, Hash tauschen, Epoch erhöhen, genau ein Audit. Keine gültige Versuchsrichtlinie nötig; Aufgaben werden nicht abgebrochen, kein neuer Schlüssel wird geliefert. |
| `/api/agent/runtime/claim`, `capabilities` (R2 abgenommen) | Das Installations-Secret dient nur zur Lauf-Übernahme; danach wird ein eigenes JWT verwendet. Jedes Mal werden aktueller Mandant/Generation, Lease, Installation, Aufgabe, ausführender Benutzer/Rolle, CAPA VIEW, Werk/Produktlinie sowie Plugin-/Aufgaben-Grants aller erforderlichen Fähigkeiten geprüft. |

Eine Aufgabe legt ausführenden Benutzer, Zielbericht und Installationsversion fest; das auf der Seite gewählte Werk verkleinert die autorisierte Werksmenge nicht. Ein Aufgaben-Grant enthält nur die Nur-Lese-Schnittmenge für den festen Bericht und kann bereits widerrufene Benutzer- oder Plugin-Rechte nicht behalten. Plugin-Installationen und langfristige Grants sind standardmäßig deaktiviert; aktivierbar sind nur Kontext-Grants, die laut Spezifikation als DIRECT deklariert sind. Der CAPA-Standard-Baseline-Katalog bleibt DENY, die Aktivierung einer Installation ändert den Katalog nicht; unter der Standardrichtlinie sind Aufgaben blocked_capability ohne Lauf. Die geordnete Nachrichtenauslieferung ist umgesetzt, restricted-Originaltext ist aber nur unter einer ausdrücklich vertrauenswürdigen serverseitigen Deployment-Richtlinie erlaubt; die vertrauenswürdige Standardrichtlinie ist leer. Die CAPA-Metadatenprojektion ist abgenommen: Vor der Abfrage und vor der Rückgabe werden vollständige Berechtigungen und Auslieferungsrichtlinie erneut geprüft, die Produktlinie des Snapshots muss zum Ziel der jeweils abschließenden Autorisierung passen; ein serverseitiger Receipt wird nur bei erfolgreicher Auslieferung gespeichert. Das Schreiben von Ereignissen/Ergebnissen akzeptiert nur serverseitige Receipts des aktuellen Task/Run/Lease/Generation; freie Ergebnisse sind fest restricted. Normale Benutzer brauchen zum Lesen von Ergebnissen weiterhin die eigene Aufgabe und Zugriff auf jedes Quellobjekt; unbekannte oder unsichtbare Quellen liefern weder Text noch Zusammenfassung noch Anzahl. Deaktivierte Plugins, beendete Läufe und datenerhaltende Mandantenwartung machen historische Ergebnisse nicht automatisch ungültig. Die Prozessabnahme mit 22 Tests sowie die abschließenden vollständigen Backend- und Frontend-Gates (Typprüfung/Build) sind bestanden.

Die R3-Laufsteuerung für Benutzer ist abgenommen: Pausieren/Abbrechen erfordert die eigene Aufgabe und aktuellen CAPA-, Werks- und Produktlinienzugriff und kann eine Aufgabe auch nach Deaktivierung des Plugins stoppen; das Fortsetzen desselben Laufs erfordert zusätzlich die Installation der festen Version, die ausführende Identität, die Schnittmenge aller erforderlichen Fähigkeiten und eine gültige vertrauenswürdige Auslieferung. Wirksame Steuerungen und finish erhöhen den Epoch und leeren die Lease, sodass alte Lauf-Zugangsdaten ungültig werden. Ein erfolgreicher Abschluss lehnt queued/claimed-Eingaben oder ein inkonsistentes akzeptiertes Präfix ab; ein ACK belegt nur den Empfang. Speichern von Checkpoints und erneutes Lesen historischer Eingaben erfordern aktuelle vollständige Laufrechte, Quellen und vertrauenswürdige restricted-Auslieferung. Historische Checkpoints sind für Benutzer auch nach Deaktivierung des Plugins oder Ende der Lease einsehbar, prüfen aber erneut die eigene Aufgabe und den Zugriff auf alle Quellen; ein Wiederöffnen braucht zusätzlich aktuelles Plugin, Fähigkeiten und Auslieferung und darf nur den neuesten, wasserstandskonsistenten Checkpoint eines pausierten Laufs verwenden. Aktivitätsfenster und Installationskatalog sind abgenommen; jede Seite prüft erneut die eigene Aufgabe und alle tatsächlichen Quellen, am Ende des Katalogs werden Ziel- und Installationsberechtigung erneut verifiziert, unabhängig vom auf der Seite gewählten Werk. Die einheitliche Seitenleiste ist abgenommen und verwendet nur das vorhandene Benutzer-JWT; eine Ablehnung durch Aufgabenkatalog oder Aktivität zieht Inhalte sofort zurück, Abmelden und Wechsel der Mandantenidentität leeren die Auswahl, wiederholte Steuerungsversuche behalten Schlüssel und Parameter. Frontend-Validierung mit 78 Tests sowie Typprüfung/Build bestanden; echte Prozess-Wiederaufnahme und acht Browser-Szenarien haben die zweistufige Prüfung bestanden; Abbrechen erhält queued/claimed und den ursprünglichen Stapelnachweis; alte Lauf-Zugangsdaten sind ungültig, aktuell berechtigte Benutzer können die Historie weiter lesen. Gesamtprüfung und abschließendes eingefrorenes Gate bestanden (Backend 2731 passed / 4 skipped / 3 xfailed / 2 xpassed, Frontend 78 Tests sowie Typprüfung/Build).

---

### R4a: Richtlinie nur für lokale Metadaten

`AGENT_LOCAL_TRIAL_MODE=local_metadata` wird nur unter dev auf einem vertrauenswürdigen lokalen Host mit Loopback und einem Worker betrieben; der Einstieg lehnt echte Nicht-Loopback-Peers und alle forwarded-Header ab. Die strikte Starterklärung bindet exakt Mandant/Generation, Installation/Epoch, ausführende Person, Bericht/Werk/Produktlinie, festen Worker-Hash und Ablauf; fehlende, ungültige oder abgelaufene Richtlinien lassen nichts durch. Nur wenn der Server aktuelle Fakten bestätigt, wird `local_metadata_v1` gewählt; nur `capa.d4.summary.masked.v1` ist DIRECT, Clients können kein Profil wählen, Befehle und Standard-Baseline bleiben DENY.

Aktiviert ein Administrator einen langfristigen Grant, sind ausdrücklich echtes Objekt/Werk/Produktlinie und ein begrenzter Ablauf nötig, der nicht nach der abdeckenden Erklärung liegt; der Administrator muss nicht als ausführende Person eingetragen sein. Ausführende Benutzer brauchen stets CAPA VIEW und den aktuellen Bereich, beide Grant-Ebenen müssen gültig bleiben; neue JWTs/Leases sind an das Ende der Erklärung gebunden, eine Verlängerung der Richtlinie verlängert keine alten Aufgaben-Grants. Erlaubte exakte Auslieferungen sind nur fachliche Metadaten internal/masked→plugin und kontrollierter Aufgabentext restricted/raw→plugin, ohne Modellfreigabe. Ein Widerruf erhöht den Epoch und tauscht Schlüssel ohne Rückgabe; weder alte Richtlinien noch erneutes Aktivieren stellen alte Zugangsdaten wieder her; aktuell berechtigte Benutzer können weiter historisch lesen, pausieren/abbrechen, bei Quellenentzug werden weder Inhalt noch Zusammenfassung noch Anzahl geliefert. Fakten und Nachweise siehe [Anleitung zum lokalen Versuch](development/agent-local-trial.md); das ist keine Freigabe für Text, Anhänge, fachliches Schreiben oder Produktions-Deployment.

### R4b-1: Interner Textkandidat für Mitarbeitende

Standard ist `CAPA_D4_TEXT_PREVIEW_ENABLED=false`; die betreffenden Pfade antworten im deaktivierten Zustand vor Authentifizierung/Mandant/Text/DB mit 404. Normales Benutzer-JWT mit aktuellem CAPA VIEW und Werks-/Produktlinienzugriff erlaubt Mitarbeitenden, schreibgeschützt einen eingeschränkten Kandidaten für drei D4-Textpositionen zu erzeugen; Lauf-JWT/Installationsschlüssel berechtigen dazu nicht, und Bereichsfelder aus Frontend und Client ersetzen keine Backend-Identität. Für nicht leere FMEA-Quellen werden zusätzlich aktuelles FMEA VIEW sowie Verknüpfung, Koordinaten und Knoten geprüft; ungültige oder unsichtbare Quellen führen zur Ablehnung des ganzen Kandidaten ohne Text, Quell-ID, Zusammenfassung oder Anzahl. Text ohne Referenz bleibt restricted mit unbestätigter Quelle und erhält keine neue Quellen- oder Herabstufungsfreigabe.

Kandidaten sind fest restricted/redaction_candidate/not_approved/external_delivery_allowed=false; ein Treffer begrenzter Regeln bedeutet keine vollständige Schwärzung. Nach separatem readonly-Snapshot, vollständigem HMAC der Quellversion und abschließender Prüfung von aktueller Berechtigung und Quelle wird nur ein sicheres Vorschau-Audit geschrieben; es werden keine fachlichen Felder geschrieben, kein Text gecacht, indexiert oder an Plugins/Modelle geliefert. Die Oberfläche für normale Mitarbeitende prüft alle 2 Sekunden und verfällt nach höchstens 30 Sekunden; Rechteverlust, Unsicherheit, Identitäts- oder Zielwechsel und Schließen ziehen Kandidat und sensible Begriffe zurück; Begriffe werden nicht gespeichert. Konkrete Regeln, Eingabebudgets und die Fehlersemantik der Inhaltssicherheit siehe [Vorschau-Anleitung](development/capa-d4-text-preview.md). Originaltext-Ausnahmen, herabgestufte Veröffentlichung und weitere R4b-/Produktions-Gates sind nicht geöffnet.

## 2. Standard-Berechtigungsmatrix

> Datenquelle: Migration `028_permission_matrix` + Migrationen `029`–`035` + `seed.py`

| Modul | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| fmea | ADMIN | APPROVE | EDIT | EDIT | VIEW | VIEW | VIEW |
| capa | ADMIN | APPROVE | EDIT | VIEW | EDIT | EDIT | VIEW |
| planning | ADMIN | APPROVE | VIEW | EDIT | VIEW | VIEW | VIEW |
| ppap | ADMIN | APPROVE | NONE | EDIT | EDIT | NONE | VIEW |
| iqc | ADMIN | APPROVE | VIEW | VIEW | EDIT | NONE | VIEW |
| supplier | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| supplier_risk | ADMIN | APPROVE | EDIT | VIEW | EDIT | VIEW | VIEW |
| supply_chain_risk_map | ADMIN | ADMIN | EDIT | EDIT | EDIT | EDIT | VIEW |
| customer_quality | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| customer_audit | ADMIN | APPROVE | VIEW | VIEW | NONE | EDIT | VIEW |
| scar | ADMIN | APPROVE | VIEW | VIEW | EDIT | VIEW | VIEW |
| spc | ADMIN | APPROVE | EDIT | VIEW | VIEW | VIEW | VIEW |
| msa | ADMIN | APPROVE | EDIT | NONE | NONE | NONE | VIEW |
| special_characteristic | ADMIN | APPROVE | NONE | EDIT | NONE | NONE | VIEW |
| quality_goal | ADMIN | APPROVE | NONE | NONE | NONE | NONE | VIEW |
| audit | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |
| management_review | ADMIN | APPROVE | VIEW | VIEW | NONE | NONE | VIEW |
| dashboard | ADMIN | APPROVE | VIEW | VIEW | VIEW | VIEW | VIEW |
| user_mgmt | ADMIN | VIEW | NONE | NONE | NONE | NONE | NONE |
| permission_mgmt | ADMIN | NONE | NONE | NONE | NONE | NONE | NONE |
| knowledge_graph | VIEW | VIEW | — | — | — | — | — |
| mes | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| plm | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| erp | ADMIN | APPROVE | CREATE | VIEW | VIEW | VIEW | VIEW |
| group | ADMIN | EDIT | — | — | — | — | — |

> `—` bedeutet, dass die Rolle in den Seed-Daten keine Berechtigungszeile für dieses Modul hat; die tatsächliche PermissionLevel ist NONE (0).

---

## 3. Berechtigungsschutz im Frontend

### 3.1 Routenschutz

```typescript
// frontend/src/hooks/usePermission.ts
const { canView, canCreate, canEdit, canApprove, canAdmin, isAdmin, roleKey } = usePermission();
```

- `canView(module)` → `permissionLevel >= 1`
- `canCreate(module)` → `permissionLevel >= 2`
- `canEdit(module)` → `permissionLevel >= 3`
- `canApprove(module)` → `permissionLevel >= 4`
- `canAdmin(module)` → `permissionLevel >= 5`
- `isAdmin` → `role_key === "admin"`

### 3.2 Routen ohne Modulschutz

~~Früher verwendeten einige Routen `ProtectedRoute` (nur Anmeldung erforderlich) ohne `requiredModule`. Inzwischen vollständig behoben.~~

Alle fachlichen Routen haben `requiredModule`, das eins zu eins dem Backend-Enum `Module` entspricht.

---

## 4. Berechtigungsprüfung im Backend

### 4.1 Prüfung als Dependency

```python
from app.core.permissions import require_permission, Module, PermissionLevel

@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.2 Prüfung im Code

Einige Operationen prüfen Berechtigungen direkt in der Service-Schicht:

```python
# FMEA-Freigabe: nur admin/manager dürfen in den Status approved weiterschalten
if target_status == "approved" and user.role_definition.role_key not in ("admin", "manager"):
    raise ValueError("...")  # Meldung wird über backend/app/i18n je Accept-Language übersetzt
```

---

## 5. Werks- und Produktlinienbereich

### 5.1 Datentrennung

| Benutzertyp | Werksbereich | Produktlinienbereich |
|----------|----------|------------|
| Normaler Benutzer | Nur eigene Werke | Nur zugewiesene Produktlinien |
| Konzernadministrator | Alle Werke | Alle Produktlinien |

### 5.2 Bereichsfilter

`factory_scope.py` im Backend filtert automatisch:

- Listenabfragen erhalten automatisch eine `factory_id`-Bedingung.
- Beim Anlegen wird automatisch die `factory_id` des aktuellen Benutzers gesetzt.
- Konzernadministratoren (ADMIN im Modul `group`) können werksübergreifend arbeiten.

---

## 6. Bekannte Probleme

| # | Schwere | Problem | Ort | Status |
|---|:------:|------|------|:----:|
| 1 | Hoch | ~~Frontend-Routen ohne Modulschutz (knowledge_graph, change_impact, MES)~~ | `App.tsx` | ✅ Behoben |
| 2 | Mittel | ~~Frontend ruft Refresh-Token nicht automatisch auf; Vollständigkeit des Mechanismus prüfen~~ | `authStore.ts`, `client.ts` | ✅ Behoben |
| 3 | Mittel | ~~Kein Rate-Limiting der Login-Schnittstelle~~ | `api/auth.py` | ✅ Behoben |
| 4 | Niedrig | ~~Kein Audit-Log für Authentifizierung~~ | `api/auth.py` | ✅ Behoben |

### Änderungsprotokoll

| Datum | Änderung |
|------|----------|
| 2026-06-13 | Frontend-Routenschutz: `/change-impact` erhält `requiredModule="fmea"`, die 4 MES-Routen `requiredModule="mes"`, `/dashboard` `requiredModule="dashboard"` |
| 2026-06-13 | Backend `search.py`: Endpunkte `semantic_search` und `ask` prüfen `Module.KNOWLEDGE_GRAPH VIEW` |
| 2026-06-13 | Backend `graph.py`: 4 Nur-Lese-Endpunkte prüfen `Module.KNOWLEDGE_GRAPH VIEW` |
| 2026-06-13 | Backend `auth.py`: `register` und `list_users` von `require_admin` auf `require_permission(Module.USER_MGMT, PermissionLevel.ADMIN)` umgestellt |
| 2026-06-13 | Frontend-Seitenleiste: Menüeinträge mit eigenem `module`-Attribut, rekursive Filterung von Untermenüs |
| 2026-06-13 | Veraltete Funktion `require_engineer_or_admin` entfernt |
| 2026-06-13 | Automatisches Refresh-Token im Frontend: refresh_token speichern, bei 401 automatisch erneuern, parallele Anfragen warten in einer Queue |
| 2026-06-13 | Login-Rate-Limiting: höchstens 10 Anmeldeversuche pro IP in 5 Minuten, darüber 429 |
| 2026-06-13 | Authentifizierungs-Audit: Login erfolgreich/fehlgeschlagen, Konto deaktiviert, Registrierung, Refresh erfolgreich/fehlgeschlagen werden strukturiert protokolliert |

> **D3-Eindämmung (2026-07-12)**: D3-Endpunkte verwenden das bestehende Berechtigungsmodell des Moduls `capa`; es wurden keine neuen Berechtigungspunkte oder Rollen eingeführt.


## Versionsbindung der CAPA-D8-Ergebnisprüfung (2026-10-25, Task 4)

`POST /api/capa/{report_id}/advance` behält die bestehenden Statusübergänge. Nur
`D8_APPROVAL_PENDING → D8_CLOSURE` (Freigabe) und
`D8_APPROVAL_PENDING → D7_PREVENTION` (Zurückweisung) müssen übermitteln:

- `expected_outcome_revision`: die von `GET /api/capa/{report_id}/outcome-review` gelieferte 64-stellige hexadezimale Revision in Kleinbuchstaben.
- `expected_review_round_id`: die UUID der Prüfrunde aus derselben Abfrage.

Fehlt einem aktuell berechtigten Aufrufer eines der Felder, folgt `409 CAPA_OUTCOME_REVIEW_REQUIRED`;
haben sich Material, ausdrückliche Quellversion oder Runde geändert, folgt `409 CAPA_OUTCOME_REVIEW_CHANGED`.
Ungültige Feldformate liefert weiterhin das DTO mit 422. Unberechtigte Aufrufer werden zuerst abgelehnt; die Version ist kein Berechtigungsnachweis.
Frühere Weiterschaltungen mit EDIT sowie `D8_CLOSURE → ARCHIVED` brauchen diese Felder nicht; wer selbst eingereicht hat und aktuell APPROVE besitzt,
kann weiterhin freigeben – es gibt keinen neuen Schalter, der Selbstfreigabe verbietet oder erlaubt. Eine Zurückweisung braucht weiterhin eine nicht leere Begründung, führt zurück nach D7 und kompensiert keine Maßnahmen vor Ort.

HTTP und direkte Service-Aufrufe lösen CAPA-Berechtigung sowie Werks-/Produktlinienbereich des aktuellen Benutzers neu auf und prüfen unabhängig
FMEA VIEW / PLANNING VIEW für alle erforderlichen Quellen. RR-/Nur-Lese-Snapshot und Lese-Fence des GET ersetzen keine Schreibberechtigung; die Schreibtransaktion berechnet mit dem echten Collector
das vollständige HMAC neu. Sperrreihenfolge: CAPA-Elternzeile → aktuelle analysis → ProductLine → sortierte Gesamtmenge der CP-/FMEA-Elternzeilen;
ausdrücklich referenzierte FMEAs, die nicht im Snapshot des Dokument-Gates stehen, gehören ebenfalls in diese sortierte Sperrmenge. Die Sperren gelten bis zum Ende der abschließenden Transaktion;
nach jedem Warten auf eine Sperre werden Material und aktuelle Berechtigungen erneut geprüft. Die Freigabe verwendet das vollständige C8/C9/waiver-Gate und verlangt, dass die aktuelle Grundursache zu einem passed-
Verifizierungsdatensatz passt und die formalen D5-Maßnahmen sowie die D6-Verifizierungsergebnisse nicht leer sind; ein nicht leerer Text bedeutet nicht, dass die Wirksamkeit freigegeben ist.

Nach den langen awaits von Wissensablage und Querausrollung wird jeweils erneut geprüft; nach dem Schreiben von MES-Outbox, Status und Audit und vor dem abschließenden Commit werden
Akteur/Bereich/Quellberechtigung, Mandantenzulassung, Runde und Revision noch einmal geprüft. Bei Fehlschlag werden die Abschluss-Seiteneffekte in der Datenbank zurückgerollt; es wird nicht behauptet, ein Datenbank-
Rollback könne Informationen zurückholen, die zuvor rechtmäßig an externe Stellen gesendet wurden. Helper committen nicht vorzeitig.

`changed_fields.outcome_review` der bestehenden Einträge `D8_APPROVED` / `D8_REJECTED` enthält nur fünf Schlüssel:
`contract`, `round_id`, `revision`, `doc_decision_id`, `source_versions`.
Alle fünf Werte stammen aus der Serverprüfung; vom Client vorbereitete Receipts werden nicht akzeptiert, Text oder freie Verifizierungstexte nicht kopiert.
Reader aus Task 3 und der Collector der Quellreferenzen verarbeiten direkt diesen von der tatsächlichen Entscheidung erzeugten Umschlag.
Abschlussergänzung und Archivierung ersetzen den Receipt nicht. Kompatible alte offene Prüfrunden binden weiterhin nur tenant + report, nicht updated_at;
GET schreibt keine Runde, es gibt keine Migration. Bestehende E2E-API-Aufrufe für Wissensablage/Querausrollung lesen zuerst die Version und übermitteln dann; der Seed für offene Freigaben ergänzt nur
Grundursache, Gate und unveränderliche Quellversionen als Vorbedingungen und erzeugt keine D8-Freigabequittung im Voraus. Prüfpanel und Interaktion im Frontend gehören zu Task 5, echter Provider
und vollständiger Browserdurchlauf zu Task 7 und gelten hier nicht als abgenommen.


## Zentrales Frontend für die CAPA-D8-Ergebnisprüfung (2026-10-26, Task 5)

Die produktive Detailseite liest das zentrale Ergebnispanel nur in `D8_APPROVAL_PENDING`, `D8_CLOSURE` und `ARCHIVED`.
Vollständig angezeigt werden D4-Grundursache, tatsächliche D5-Maßnahmen, D6-Verifizierungsergebnisse, Verifizierungsschluss/-nachweismetadaten, D7-Aktionen mit tatsächlichem Status,
FMEA-/Produktionslenkungsplan-Objekte mit Version/Hash sowie Entscheidungsdatensätze; ein nicht leeres D6 wird nicht automatisch als wirksam markiert und D7 pending nicht als verified.
Historisch nicht versionierte oder nicht prüfbare Bindungen sind eigens gekennzeichnet. Quellen und Text sind maskierter Text und Metadaten; es werden keine beliebigen URLs geöffnet, kein
HTML/Markdown ausgeführt, keine Anhänge extrahiert und keine neuen Downloads angeboten. Normale formale Berichte haben keine 30-Sekunden-Vorschaufrist, und es werden keine fachlichen Daten im Browser gecacht.

Nur ein aktuell erfolgreich und vollständig gelesenes Panel kann dem einzigen bestehenden Freigabe-/Zurückweisungspfad `revision` + `review_round_id` liefern;
eine Zurückweisung enthält die ursprüngliche nicht leere Begründung. Vor dem Start der Anfrage wird das alte Token verbraucht und doppeltes Klicken gesperrt; nach 409 muss ausdrücklich neu geladen und erneut geprüft werden,
es wird nicht stillschweigend eine neue Version gelesen und automatisch freigegeben. Bei unklarem Netzwerkergebnis wird der tatsächliche Berichtsstatus abgefragt und die Entscheidung nicht automatisch erneut gesendet. 401/403 auf den exakten Lese-/advance-
URLs laufen nicht durch Axios-refresh/replay; die übrige Authentifizierungskoordination, private Routen und die unabhängige Backend-Autorisierung bleiben unverändert.
Wechsel von Identität, Zugangsdaten (einschließlich Refresh), Mandant, Bericht/Routenauswahl, Werk oder Produktlinie machen die lokale Ansicht ungültig; alle zugehörigen Seiten-/Panel-
Anfragen registrieren einen AbortController und prüfen nach jedem await den Ansichts-Epoch; alte Erfolge und alte Ablehnungen beeinflussen die neue Ansicht nicht.
Fehlgeschlagene, unvollständige oder unlesbare Quellen leeren Prüf-Token und Zurückweisungsbegründung; eine Freigabe auf Basis des vorherigen Materials ist ausgeschlossen.

Im Endzustand bieten EDIT/APPROVE/ADMIN weder Kernbearbeitung noch KI-Ersetzen/-Anhängen/-Rückgängig noch Pflege von Verknüpfungen oder Grundursachenverifizierung;
`D8_CLOSURE` erlaubt bei Berechtigung nur das Nachtragen in `d8_closure`, deutlich als „Ergänzung nach Abschluss, nicht Teil dieser Prüfung“ gekennzeichnet,
ohne das Kernprüfkennzeichen zu ändern. Ergänzungen in `ARCHIVED` sind ebenfalls schreibgeschützt. Frühere Schritte D4/D5/D6 werden weiter nach den bestehenden Regeln bearbeitet/übernommen/verifiziert;
es gibt keine neue schrittweise manuelle Freigabe oder Kandidatenfreigabe. Diese Schutzprüfungen im Frontend ersetzen weder den Endzustandsschutz noch die Prüfung aktueller Quellberechtigungen im Backend.
Echte Browser-/Provider-Abnahme des Gesamtablaufs gehört zu Task 7; dieser Abschnitt behauptet nicht, dass sie abgeschlossen ist.


### Task 5, Korrekturrunde 1: Zuordnung kompletter Operationen und Seiteneffekte der Authentifizierung

D4/D5-Übernahme, Grundursachenverifizierung, D7-Aktionen, Dokument-Gate und die tatsächliche Kette mehrerer awaits in D3 teilen sich eine lokale Anfragezuordnung.
Vorbedingungen vor dem Speichern müssen nach Abbruch der Ansicht reject liefern; nachfolgende POSTs, Callbacks, Hinweise und Neuladen prüfen erneut die ursprüngliche Ansicht
und behandeln eine normale Rückkehr einer alten Vorbedingung nicht als Erlaubnis, unter neuen Zugangsdaten weiterzuschreiben. Jede Lese-/Schreibanfrage übergibt das signal des ursprünglichen Lebenszyklus;
ein Generationswechsel in D3 bricht alle laufenden Anfragen dieser Unteransicht ab und setzt Busy-/Bearbeitungszustände zurück, bereits geladene Generationslisten werden nicht unnötig neu abgerufen.

Die ownership des lokalen signal wird geprüft, bevor Axios Zugangsdaten injiziert oder Authentifizierungs-Seiteneffekte auslöst. Zugehörige `/auth/me`- und Refresh-Aufrufe
übergeben dasselbe signal; alte Anfragen können weder `setUser` ausführen noch ein altes Token installieren oder die neue Sitzung abmelden. Der Refresh-Helper prüft nur bei ausdrücklich
owned CAPA-Aufrufen zusätzlich Zuordnung und ursprüngliches Refresh-Credential. Ungültige CAPA-Ansichten werden nicht automatisch unter anderen Zugangsdaten wiederholt und bleiben nicht
in der Refresh-Queue hängen; ein aktuell rechtmäßiger Refresh gibt die ursprünglich unabhängigen wartenden Lesezugriffe weiterhin frei. Bestehende Refresh-Strategien anderer Routen, der
Ausschluss privater Routen, die ursprüngliche Backend-Autorisierung und die fachlichen Freigaberegeln bleiben unverändert; der globale Auth-/Refresh-Zustandsautomat wird nicht neu gebaut.

Erneutes Laden des Prüfmaterials bei gleicher Identität leert nur Material, revision/round und Zurückweisungsbegründung dieses Panels und bricht weder unabhängige Wissenslesezugriffe der Seite
noch erneute Ablagen ab; solche Operationen laufen weiter oder enden normal, ohne ein dauerhaftes, nicht wiederholbares loading zu hinterlassen. Ein vollständiger Wechsel von Identität/Bereich
zerstört weiterhin die alte Ansicht und bricht alle eigenen Anfragen ab. Formales Material, eingefrorener Kern im Endzustand, Kennzeichen für ungeprüfte Ergänzungen, D4-
Vorschau-/Anhangsgrenzen und der einzige D8-Entscheidungseinstieg behalten ihren ursprünglichen Vertrag; echte Browser-/Provider-Abnahme erfolgt weiterhin in Task 7.


### Task 5, Korrekturrunde 2: Ende der Abonnenten nach abgebrochenem owned Refresh

Bricht das Schließen einer CAPA-Ansicht oder ein Auswahlwechsel deren Refresh ab und liefert der ursprüngliche Helper null bzw. ist ungültig, müssen die ursprünglich unabhängigen wartenden Anfragen
jeweils mit ihrem ursprünglichen 401 normal reject liefern und das Abonnement leeren; sie dürfen weder endlos warten noch bei einem späteren erfolgreichen Refresh automatisch wiederholt werden.
Aufrufer können ausdrücklich eine neue Anfrage starten; alte CAPA-Anfragen werden nie wiederholt. Verspätete Erfolge/Fehlschläge nach einem Sitzungswechsel dürfen weiterhin weder
neue Zugangsdaten ändern noch den neuen Benutzer abmelden. Ergänzt wird nur der Abonnenten-Abschlusszweig des owned Initiators; die bestehende Strategie, nach der unabhängige Anfragen selbst einen
Refresh auslösen, der Schutz privater Routen, Backend-Berechtigungen und fachliche Freigaberegeln bleiben unverändert.

### Task 6: Ableitung und Änderungsverantwortung für ungeprüfte Abschlussergänzungen

`d8_closure` gehört weder zum formalen Kern noch zum D8-Receipt; Nachträge ändern weder revision noch review round, Freigabedatensätze oder historische Quellversionen.
`fields.closure_review_scope` der Wissensablage ist fest `unreviewed_supplement`; die tags der D8-Lessons erhalten fest zusätzlich
`review_scope:unreviewed_supplement` (bei wiederholter Extraktion ohne Duplikat), D7-Lessons erhalten dadurch keine approved-Identität.
Bestehende Zusammenfassungshinweise kennzeichnen closure ausdrücklich als ungeprüfte Ergänzung, die nicht als geprüfte Grundursache oder verifizierte Wirkung gelten darf; Wissens-Embeddings und
abgeleitete Empfehlungstexte behalten denselben Warnhinweis. Ursprüngliches closure, Zusammenfassung, Klassifizierung und Autorisierung bleiben unverändert, es gibt keine zusätzlichen Provider-Aufrufe.

Die Wissens-API für historische Einträge ergänzt das Kennzeichen nur in der zurückgegebenen Kopie der fields; Listen liefern zusätzlich das nullbare `closure_review_scope`;
Empfehlungen aus Lessons Learned projizieren bei `source_d_step=d8` das Feld `review_scope`, Wissensempfehlungen projizieren bei CAPA-closure `closure_review_scope`, mit vorangestelltem
Hinweis „ungeprüfte Ergänzung“; aus dem bereits abgeschlossenen Quell-CAPA wird nicht auf approved geschlossen.
Lesen verändert weder ORM noch historische fields/tags, Embeddings oder Datenbank; keine Migration, kein Nachfüllen.

Die Verantwortung für Ergänzungen wird nur aus dem jüngsten UPDATE-Audit mit `d8_closure` desselben Berichts und Werks übernommen (Akteur und Zeit);
neue UPDATE-Audits erfassen die Werks-ID. Ohne passendes Audit oder ohne Akteur ist der jeweilige Wert null; es wird nicht aus updated_at oder
created_by der Haupttabelle geschlossen. Die Metadatenabfrage lädt keine privaten before/after-Daten des Audits; das Panel aus Task 5 verwendet den tatsächlichen Wert oder `—` als Rückfall.
Ursprünglicher savepoint, Bereinigung alter Embeddings/Outbox, Reihenfolge beim Rollback nach Fehlschlag sowie Endzustands- und Berechtigungsregeln bleiben unverändert.


### Task 8: Betriebsübergabe und aktuelle Abnahmegrenzen (2026-10-27)

Die [Anleitung zur CAPA-Ergebnisprüfung](development/capa-outcome-review.md) beschreibt Umsetzung/Verifizierung durch Ingenieure, vollständige Prüfung durch Prüfende, ausdrückliches Neuladen und den Umgang mit historisch ungebundenen Daten. Derzeit gibt es nur die bestehende Rollenzuweisung in der Benutzerverwaltung und die vorhandene Rollen-Berechtigungs-API, keinen in diesem Abschnitt neu eingeführten Rollendesigner; CAPA EDIT/APPROVE, FMEA VIEW, PLANNING VIEW und der aktuelle Bereich werden jeweils separat geprüft. Die aktuelle Regel zur D8-Selbstfreigabe bleibt unverändert, auch ADMIN kann einen geprüften Kern nicht an Ort und Stelle umschreiben. Eine Freigabe bedeutet die Annahme des Ergebnisses, keine externe Weitergabe, keine Entschlüsselung von Anhängen und keine Agent-Berechtigung.

Alle Einstiege zum Kernmaterial im Endzustand liefern einheitlich `409 CAPA_REVIEWED_CONTENT_LOCKED`, ohne Berechtigung bzw. bei Unsichtbarkeit wird zuerst abgelehnt. Ergänzungen in D8_CLOSURE werden einzeln als ungeprüft markiert; reine d8_closure-Ergänzungen in ARCHIVED behalten das ursprüngliche 400-Einfrieren, gemischte Kern-PUTs liefern atomar 409. Formale Datensätze haben weder eine 7-Tage-Bereinigung von Kandidaten noch eine 30-Sekunden-Vorschaufrist; kontrollierte Revision/Wiederöffnung ist nicht umgesetzt.

**Historischer Stand 2026-10-27**: Tasks 1–6 wurden unabhängig geprüft; das ist keine Abnahme des gesamten Abschnitts. Das vollständige echte Gate aus Task 7 ergab damals 2 failed / 1 passed / exit 1, weil im Arbeitsbaum die freigegebene `.env.e2e` fehlte; echter Provider im positiven Browserlauf, Wissen und Querausrollung waren nicht verifiziert. Die normale eingefrorene Regression aus Task 8, das dedizierte ClamAV-Gate und die echte Abnahme wurden getrennt erfasst; Mocks, Skips oder historische Baselines reichen nicht für eine Freigabe.

**Eingefrorenes Ergebnis 2026-10-29 (historisch)**: 1391 Hashes von Quellen/Konfigurationen/Tests unverändert; vollständiges make check mit 2 failed / 3415 passed / 12 skipped / 3 xfailed / 2 xpassed / 5 warnings (make exit 2), nur zwei erzwungene Live-Tests schlugen mangels ausdrücklichem Opt-in fehl. Dieser Lauf bleibt als historischer Fehlschlagnachweis erhalten und ist nicht das aktuelle Ergebnis.

**Aktuelle Übergabe 2026-11-01 (UTC-Quittung 2026-10-31)**: Mit freigegebenem TEST-Profil, statischer Allowlist und auf die exakten Live-Knoten begrenztem setup/call/teardown wurde in Task 7 ein echter Hauptdurchlauf Provider/HTTP/D8/Chromium/Wissen/Querausrollung sowie zwei Schutzketten abgeschlossen (3 passed, 5 warnings, exit 0); auch das separate echte ClamAV-Gate bestand (process 7, browser controller 1, exit 0). Der frische vollständige Lauf aus Task 8 ergab 3450 passed / 12 skipped / 3 xfailed / 2 xpassed / 5 warnings, make exit 0; 1390 Dateifingerabdrücke unverändert. Die beiden bestehenden graph-Ausschlüsse und alle Nicht-pass-Ergebnisse bleiben erhalten; das Scanner-Gate wird nicht durch normale Skips ersetzt. Task 8 und der gesamte Abschnitt haben die abschließende Prüfung bestanden; die registrierten Kerncontainer, eigenen Volumes und beiden Testdatenbanken wurden nach exakter Identitäts- und Null-Verbindungsprüfung entsorgt. Keine Berechtigungen, Selbstfreigabe-Regeln, Standard-Abschaltungen oder Produktionsöffnungen wurden geändert.
