# Modul Kundenqualität — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-06-13 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Das Modul Kundenqualität deckt den geschlossenen Gesamtablauf von der Annahme einer Kundenreklamation bis zur Lieferanten-Korrekturmaßnahme (SCAR) ab und umfasst vier Teilmodule:

| Teilmodul | Route | Funktionsumfang |
|--------|------|----------|
| Reklamationsmanagement | `/customer-quality`, `/customer-quality/complaints/:id` | Erfassung, Untersuchung, Antwort und Abschluss von Kundenreklamationen |
| RMA – Rücksendungen | `/customer-quality`, `/customer-quality/rma/:id` | Rücksendeeingang, Fehleranalyse, Verantwortungszuordnung, Abschluss |
| Kundenaudits | `/customer-audits`, `/customer-audits/:id` | Kundenauditplanung, Verfolgung von Feststellungen, Kundenbestätigung |
| SCAR – Lieferanten-Korrekturmaßnahmen | `/scars`, `/scars/:id` | SCAR aus Reklamation/RMA/IQC-Fehler auslösen, Korrekturen des Lieferanten verfolgen |

Die vier Teilmodule sind über Datenverknüpfungen durchgängig rückverfolgbar: Reklamationen lassen sich mit RMA, FMEA und CAPA verknüpfen; RMAs mit Reklamationen, FMEA und CAPA; SCAR kann per Klick aus Reklamation oder RMA ausgelöst werden; Feststellungen aus Kundenaudits lassen sich mit CAPA verknüpfen.

---

## 2. Rollen und Berechtigungen

Das Berechtigungsmodell ist dreistufig: **ModuleKey × PermissionLevel × Rolle**. Bedeutung von PermissionLevel: 0 = NONE (unsichtbar), 1 = VIEW (nur lesen), 2 = CREATE (anlegen), 3 = EDIT (bearbeiten), 4 = APPROVE (freigeben/abschließen), 5 = ADMIN (Vollzugriff).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| customer_quality | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| customer_audit | 5 | 4 | 1 | 1 | 0 | 3 | 1 |
| scar | 5 | 4 | 1 | 1 | 3 | 1 | 1 |

**Operationen und Mindestberechtigung:**

| Operation | Erforderliche PermissionLevel |
|------|----------------------|
| Liste/Details ansehen | VIEW (1) |
| Anlegen/Bearbeiten/Statusübergang | CREATE (2) |
| Reklamation abschließen / RMA abschließen | APPROVE (4) |
| SCAR verifizieren (verify) / abschließen (close) | APPROVE (4) |
| SCAR starten (start) / beantworten (respond) | CREATE (2) |

> Hinweis: Die Rolle `supplier_qe` hat für die Module `customer_quality` und `customer_audit` die Stufe NONE (0) und sieht deren Menüs und Daten nicht; `customer_qe` hat für `scar` nur VIEW und kann SCARs nicht direkt bearbeiten.

---

## 3. Reklamationsmanagement

### 3.1 Reklamationsliste

**Route:** `/customer-quality` (Reiter: Reklamationen)

Die Liste unterstützt folgende Filter:

- Produktlinie (`product_line`)
- Kunde (`customer_id`)
- Status (`status`)
- Schwere (`severity`)
- Überfällig (`overdue`)
- Verantwortliche Person (`assignee_id`)

Gelieferte Felder: `complaint_no`, Kundenname, Produktlinie, Schwere, Kategorie, Status, Überfälligkeitskennzeichen, Erstellzeit.

### 3.2 Reklamation anlegen

**API：** `POST /api/customer-complaints`

Pflichtfelder:

| Feld | Beschreibung | Wert |
|------|------|------|
| `complaint_no` | Reklamationsnummer (global eindeutig) | Eigene Nummer, z. B. `CP-2026-001` |
| `product_line_code` | Produktlinie | Vorhandener Produktliniencode |
| `customer_id` | Kunde | Verknüpft mit Tabelle `customers` |
| `category` | Fehlerkategorie | `safety` (Sicherheit), `function` (Funktion), `appearance` (Aussehen), `delivery` (Lieferung) |
| `severity` | Schwere | Vier gespeicherte Schwerestufen (Altwerte in der Datenbank), angezeigt als kritisch, schwer, mittel, gering |
| `defect_desc` | Fehlerbeschreibung | Freitext |
| `received_date` | Eingangsdatum | Datum |

Optionale Felder:

| Feld | Beschreibung |
|------|------|
| `product_id` | Produktnummer |
| `batch_no` | Chargennummer |
| `serial_number` | Seriennummer |
| `impact_qty` | Betroffene Menge, Standard 0 |
| `occurred_date` | Auftretensdatum |
| `due_date` | Fälligkeitsdatum |
| `fmea_ref_id` | Verknüpftes FMEA-Dokument |
| `capa_ref_id` | Verknüpfter 8D/CAPA-Bericht |
| `assignee_id` | Verantwortliche Person |
| `preliminary_response` | Erste Antwort |
| `root_cause` | Grundursache |
| `corrective_action` | Korrekturmaßnahme |
| `attachments` | Anhangsliste (JSONB) |
| `supplier_responsibility` | Lieferantenverantwortung festgestellt, Standard false |
| `supplier_id` | Verantwortlicher Lieferant |
| `scar_ref_id` | Verknüpfte SCAR |

> `status` ist standardmäßig `open`. Beim Anlegen können `closed` oder `cancelled` nicht gesetzt werden.

### 3.3 Statusübergänge der Reklamation

Reklamationen folgen diesem Zustandsautomaten:

```
open ──start_investigation──▶ investigating
investigating ──mark_responded──▶ responded
responded ──close──▶ closed
open / investigating ──cancel──▶ cancelled
responded ──start_investigation──▶ investigating
```

| Aktueller Status | Operation | Zielstatus | Mindestberechtigung | API |
|----------|------|----------|----------|-----|
| open | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |
| investigating | mark_responded | responded | CREATE | `POST /api/customer-complaints/{id}/mark-responded` |
| responded | close | closed | APPROVE | `POST /api/customer-complaints/{id}/close` |
| open / investigating | cancel | cancelled | CREATE | `POST /api/customer-complaints/{id}/cancel` |
| responded | start_investigation | investigating | CREATE | `POST /api/customer-complaints/{id}/start-investigation` |

Beim Abschluss einer Reklamation erfasst das System automatisch den Zeitstempel `closed_at`.

### 3.4 Verknüpfungen

| Operation | API | Beschreibung |
|------|-----|------|
| CAPA verknüpfen | `POST /api/customer-complaints/{id}/link-capa?capa_ref_id=…` | Bestehenden 8D/CAPA-Bericht mit der Reklamation verknüpfen |
| CAPA aus Reklamation anlegen | `POST /api/customer-complaints/{id}/create-capa?document_no=…` | Legt automatisch einen 8D-Bericht an und verknüpft ihn; die Reklamation wechselt auf `investigating` |
| FMEA verknüpfen | `POST /api/customer-complaints/{id}/link-fmea?fmea_ref_id=…` | FMEA-Dokument mit der Reklamation verknüpfen |
| SCAR aus Reklamation anlegen | `POST /api/customer-complaints/{id}/create-scar` | Voraussetzung: `supplier_responsibility=true` und noch keine SCAR verknüpft |

### 3.5 Einschränkungen beim Bearbeiten

- Ist eine Reklamation bereits mit RMA-Datensätzen verknüpft, können Kunde (`customer_id`) und Produktlinie (`product_line_code`) nicht geändert werden.
- Beim Bearbeiten von `status` sind nur gültige Übergänge erlaubt; `closed` und `cancelled` müssen über den transition-Endpunkt gesetzt werden.
- Schwere (`severity`) und Kategorie (`category`) müssen den vordefinierten Enums entsprechen.

### 3.6 Überfälligkeit

Die Überfälligkeit einer Reklamation ergibt sich aus `due_date` und `status`:

- `due_date < heute` und Status weder `closed` noch `cancelled` → überfällig
- `due_date` leer oder Endstatus → nicht überfällig

---

## 4. RMA – Rücksendungen

### 4.1 RMA-Liste

**Route:** `/customer-quality` (Reiter: RMA)

Filter: Produktlinie, Kunde, verknüpfte Reklamation, Status, Verantwortlicher, verantwortliche Person.

### 4.2 RMA anlegen

**API：** `POST /api/rma-records`

Pflichtfelder:

| Feld | Beschreibung | Wert |
|------|------|------|
| `rma_no` | RMA-Nummer (global eindeutig) | Eigene Nummer |
| `product_line_code` | Produktlinie | Vorhandener Produktliniencode |
| `customer_id` | Kunde | Verknüpft mit Tabelle `customers` |
| `return_qty` | Rücksendemenge | Positive ganze Zahl |
| `defect_type` | Fehlerart | Freitext |

Optionale Felder:

| Feld | Beschreibung |
|------|------|
| `complaint_id` | Verknüpfte Reklamation (falls vorhanden) |
| `product_id` | Produktnummer |
| `batch_no` | Chargennummer |
| `serial_number` | Seriennummer |
| `responsibility` | Verantwortung: `supplier`, `internal`, `transport`, `customer_misuse`, `unknown` |
| `analysis_result` | Analyseergebnis |
| `corrective_action` | Korrekturmaßnahme |
| `fmea_ref_id` | FMEA verknüpfen |
| `capa_ref_id` | Verknüpfter 8D/CAPA-Bericht |
| `scar_ref_id` | Verknüpfte SCAR |
| `attachments` | Anhangsliste (JSONB) |
| `assignee_id` | Verantwortliche Person |
| `tracking_number` | Sendungsnummer |
| `received_date` | Wareneingangsdatum |

> Ist `complaint_id` gesetzt, prüft das System, dass `customer_id` und `product_line_code` der RMA mit der verknüpften Reklamation übereinstimmen, sonst wird ein Fehler geliefert. Beim Anlegen einer RMA mit verknüpfter Reklamation setzt das System `has_rma` der Reklamation automatisch auf `true`.

### 4.3 Statusübergänge der RMA

```
open ──start_analysis──▶ analysis
analysis ──mark_action_pending──▶ action_pending
action_pending ──close──▶ closed
open / analysis ──cancel──▶ cancelled
```

| Aktueller Status | Operation | Zielstatus | Mindestberechtigung | API |
|----------|------|----------|----------|-----|
| open | start_analysis | analysis | CREATE | `POST /api/rma-records/{id}/start-analysis` |
| analysis | mark_action_pending | action_pending | CREATE | `POST /api/rma-records/{id}/mark-action-pending` |
| action_pending | close | closed | APPROVE | `POST /api/rma-records/{id}/close` |
| open / analysis | cancel | cancelled | CREATE | `POST /api/rma-records/{id}/cancel` |

Beim Abschluss einer RMA erfasst das System automatisch den Zeitstempel `closed_at`.

### 4.4 Verantwortungszuordnung

Das Feld `responsibility` der RMA hält fest, wem die Rücksendung zuzurechnen ist:

| Wert | Bedeutung | Folgen |
|----|----------|----------|
| `supplier` | Lieferant | SCAR direkt aus dieser RMA anlegbar |
| `internal` | Intern | Interne Korrektur |
| `transport` | Transport | Transportschadenreklamation |
| `customer_misuse` | Fehlgebrauch durch Kunden | Ablehnung/Erläuterung |
| `unknown` | Offen | Weitere Untersuchung |

### 4.5 Verknüpfungen

| Operation | API | Beschreibung |
|------|-----|------|
| Reklamation verknüpfen | `POST /api/rma-records/{id}/link-complaint?complaint_id=…` | Prüft Übereinstimmung von Kunde und Produktlinie |
| CAPA verknüpfen | `POST /api/rma-records/{id}/link-capa?capa_ref_id=…` | Verknüpfter 8D/CAPA-Bericht |
| FMEA verknüpfen | `POST /api/rma-records/{id}/link-fmea?fmea_ref_id=…` | FMEA verknüpfen |
| SCAR aus RMA anlegen | `POST /api/rma-records/{id}/create-scar` | Voraussetzung: `responsibility=supplier` und noch keine SCAR verknüpft |

### 4.6 Zusammenspiel von Reklamation und RMA

- Nach der Verknüpfung wird `has_rma` der Reklamation automatisch `true`.
- Wird die Verknüpfung aufgehoben (auf eine andere Reklamation geändert), fällt `has_rma` der alten Reklamation automatisch auf `false` zurück, sofern keine weitere RMA verknüpft ist.
- Solange RMAs verknüpft sind, können Kunde und Produktlinie der Reklamation nicht geändert werden.

---

## 5. Kundenaudits

### 5.1 Auditliste

**Route:** `/customer-audits`

Filter: Kundentyp, Auditart, Kundenname, Status, Produktlinie.

### 5.2 Audit anlegen

**API：** `POST /api/audit-plans`

Pflichtfelder:

| Feld | Beschreibung | Wert |
|------|------|------|
| `audit_scope` | Auditumfang | Freitext |
| `audit_criteria` | Auditkriterien | Freitext |
| `planned_date` | Geplantes Datum | Datum |
| `customer_name` | Kundenname | Freitext |
| `customer_type` | Kundentyp | `OEM`, `Tier 1`, `Tier 2` sowie ein gespeicherter Altwert für „Sonstige“ |

Optionale Felder:

| Feld | Beschreibung |
|------|------|
| `audit_mode` | Auditart: `on_site` (vor Ort), `remote` (aus der Ferne) |
| `lead_auditor` | Leitender Auditor |
| `team_members` | Mitglieder des Auditteams (JSONB) |
| `checklist` | Auditcheckliste (JSONB) |
| `product_line_code` | Produktlinie |

> Das System erzeugt automatisch eine Auditnummer (`plan_no`) im Format `CA-{Jahr}-{Nummer}`, z. B. `CA-2026-001`, und legt das Kundenauditprogramm (`AuditProgram`) des Jahres automatisch an bzw. verknüpft es.

### 5.3 Auditstatus

Kundenaudits nutzen das Modell `AuditPlan` mit festem `audit_category` = `"customer"` und dem Zustandsautomaten des Auditmoduls:

| Status | Beschreibung |
|------|------|
| `planned` | Geplant |
| `in_progress` | In Bearbeitung |
| `completed` | Abgeschlossen |

**Bedingung für den Abschluss:** Alle Feststellungen müssen geschlossen sein (`status=closed`) und vom Kunden bestätigt (`customer_confirmed=true`).

### 5.4 Feststellungen

Feststellungen aus Kundenaudits verwenden das Modell `AuditFinding` mit zusätzlichen Feldern zur Kundenbestätigung:

| Feld | Typ | Beschreibung |
|------|------|------|
| `customer_confirmed` | boolean | Vom Kunden bestätigt, Standard false |
| `customer_confirmation_date` | date | Datum der Kundenbestätigung |
| `customer_confirmation_attachments` | JSONB | Anhänge der Kundenbestätigung |

Statusübergänge der Feststellung:

```
open ──start_progress──▶ in_progress ──close──▶ closed
```

**Bedingungen für das Schließen:**
- `root_cause` und `corrective_action` müssen ausgefüllt sein
- Ist ein CAPA verknüpft, muss es den Status `D8_CLOSURE` haben
- Beim Schließen von Kundenaudit-Feststellungen muss `customer_confirmed` `true` sein

### 5.5 Kundenbestätigung

**API：** `POST /api/audit-findings/{finding_id}/customer-confirm`

Kunden können Feststellungen unabhängig bestätigen (ohne den Workflow-Status zu ändern), mit:
- `confirmation_date`: Bestätigungsdatum
- `attachments`: Bestätigungsanhänge

Danach wird `customer_confirmed` `true`, Datum und Anhänge werden gespeichert.

### 5.6 Auditstatistik

**API：** `GET /api/audit-plans/customer-stats`

Gelieferte Kennzahlen:

| Feld | Beschreibung |
|------|------|
| `total_customer_audits` | Anzahl Audits |
| `planned` | Geplant |
| `in_progress` | In Bearbeitung |
| `completed` | Abgeschlossen |
| `open_findings` | Offene Feststellungen |
| `major_nc_count` | Schwerwiegende Abweichungen |
| `customer_confirmed_count` | Vom Kunden bestätigt |
| `pending_confirmation_count` | Warten auf Kundenbestätigung |

---

## 6. SCAR – Lieferanten-Korrekturmaßnahmen

### 6.1 SCAR-Liste

**Route:** `/scars`

Filter: Status (Mehrfachauswahl, kommagetrennt), Lieferant, Quellart (`source_type`).

### 6.2 SCAR anlegen

**API：** `POST /api/scars`

Pflichtfelder:

| Feld | Beschreibung | Wert |
|------|------|------|
| `supplier_id` | Lieferant | Verknüpft mit Tabelle `suppliers` |
| `source_type` | Quellart | `iqc`、`complaint`、`rma`、`manual` |
| `description` | Problembeschreibung | Freitext |

Optionale Felder:

| Feld | Beschreibung |
|------|------|
| `source_id` | Quell-ID (IQC-Prüfung / Reklamation / RMA) |
| `product_line_code` | Produktlinie |
| `requested_action` | Vom Lieferanten geforderte Maßnahmen |
| `due_date` | Fälligkeitsdatum |

> Das System erzeugt automatisch eine SCAR-Nummer im Format `SCAR-{YYMMDD}-{Nummer}`, z. B. `SCAR-260613-001`. Der Status ist standardmäßig `open`.

### 6.3 Statusübergänge der SCAR

SCAR hat einen Lebenszyklus mit 5 Status:

```
open ──start──▶ in_progress ──respond──▶ responded
responded ──verify──▶ verified ──close──▶ closed
responded ──reject──▶ open
verified ──reopen──▶ in_progress
```

| Aktion | Aktueller Status | Zielstatus | Mindestberechtigung | Pflichtfelder |
|------|----------|----------|----------|----------|
| start | open | in_progress | CREATE (2) | — |
| respond | in_progress | responded | CREATE (2) | `supplier_response` |
| verify | responded | verified | APPROVE (4) | — |
| reject | responded | open | APPROVE (4) | — |
| close | verified | closed | APPROVE (4) | `resolution_summary` |
| reopen | verified | in_progress | APPROVE (4) | — |

**API：** `POST /api/scars/{id}/transition`

Request-Body:
```json
{
  "action": "start",
  "supplier_response": "...",
  "resolution_summary": "..."
}
```

### 6.4 SCAR aus Reklamation/RMA anlegen

Neben dem direkten Anlegen kann eine SCAR per Klick aus Reklamation oder RMA ausgelöst werden:

| Quelle | API | Voraussetzung |
|------|-----|-----------|
| Reklamation | `POST /api/customer-complaints/{id}/create-scar` | `supplier_responsibility=true` und `scar_ref_id` leer |
| RMA | `POST /api/rma-records/{id}/create-scar` | `responsibility=supplier` und `scar_ref_id` leer |

Beim Auslösen aus einer Reklamation trägt das System die ID der neuen SCAR automatisch in `scar_ref_id` der Reklamation ein; für RMAs gilt dasselbe.

Request-Body (SCARRelatedCreate):

```json
{
  "supplier_id": "uuid",           // Pflicht (bei RMA ohne Standardwert, muss angegeben werden)
  "description": "...",            // Optional, Standard ist defect_desc der Reklamation bzw. der Wert der RMA defect_type + analysis_result
  "requested_action": "...",       // Optional
  "due_date": "2026-07-31"         // Optional
}
```

### 6.5 CAPA verknüpfen

**API：** `POST /api/scars/{id}/link-capa`

Request-Body: `{ "capa_ref_id": "uuid" }`

Verknüpft einen 8D/CAPA-Bericht mit der SCAR, um die Wirksamkeit der Lieferantenkorrektur zu verfolgen.

### 6.6 SCAR-Abschluss und Kopplung mit Risikowarnungen

Wechselt eine SCAR auf `closed`, markiert das System alle verknüpften offenen Lieferanten-Risikowarnungen (`SupplierRiskAlert`) automatisch als geschlossen.

---

## 7. Dashboard Kundenqualität

**API：** `GET /api/customer-quality/dashboard`

Das Dashboard liefert Daten zu folgenden Dimensionen:

| Kennzahl | Beschreibung |
|------|------|
| Reklamationen gesamt / offen / überfällig | Statistik je Zeitfenster |
| RMAs gesamt / Rücksendemenge / eigenständige Rücksendemenge | Eigenständige Rücksendemenge = Rücksendungen aus RMAs ohne verknüpfte Reklamation |
| Betroffene Menge (impact_qty) | Summe der betroffenen Mengen aller Reklamationen |
| PPM | (betroffene Menge + eigenständige Rücksendemenge) / Versandmenge × 1.000.000 |
| Risikoampel | red/yellow/green, basierend auf Überfälligen, kritischen Reklamationen und PPM im Vergleich zum Zielwert |
| SPC Cpk/Ppk | Prozessfähigkeitsindex je Produktlinie |
| Gewährleistungskosten | Gewährleistungssumme im Zeitfenster |
| Kundenzufriedenheit | Mittlere Zufriedenheitsbewertung |
| Zusammenfassung Kundenaudits | Abgeschlossene Audits, Feststellungen, Datum des letzten Audits |

**Kundenzusammenfassung (Customer Summary):**

Je Kunde: Reklamationen, offene Reklamationen, überfällige, kritische Reklamationen, RMAs, PPM, Risikoampel.

**Trenddaten:** Monatliche Summen von Reklamationen, RMAs und Rücksendemenge.

---

## 8. Häufige Fragen

### F1: Warum kann ich keine SCAR anlegen?

**A:** Folgendes prüfen:
1. Sie haben CREATE im Modul `scar` (supplier_qe oder höher).
2. Beim Auslösen aus einer Reklamation muss deren `supplier_responsibility` `true` und `scar_ref_id` leer sein.
3. Beim Auslösen aus einer RMA muss deren `responsibility` `supplier` sein.
4. Die Lieferanten-ID muss im System existieren.

### F2: Warum ist die Schaltfläche zum Abschließen der Reklamation ausgegraut?

**A:** Das Abschließen erfordert APPROVE (PermissionLevel >= 4). Nur die Rollen admin und manager können Reklamationen abschließen.

### F3: Beim Verknüpfen von RMA und Reklamation erscheint „nicht derselbe Kunde oder dieselbe Produktlinie“?

**A:** `customer_id` und `product_line_code` der RMA müssen exakt mit der verknüpften Reklamation übereinstimmen. Bitte Kunde und Produktlinie in RMA und Reklamation prüfen.

### F4: Eine Feststellung aus dem Kundenaudit lässt sich nicht schließen?

**A:** Für das Schließen müssen alle Bedingungen erfüllt sein:
1. `root_cause` (Grundursache) und `corrective_action` (Korrekturmaßnahme) sind ausgefüllt.
2. Ist ein CAPA verknüpft, muss es den Status `D8_CLOSURE` haben.
3. `customer_confirmed` muss `true` sein. Die Kundenbestätigung kann separat über `POST /api/audit-findings/{finding_id}/customer-confirm` erfolgen.

### F5: Was tun bei Konflikten der SCAR-Nummer?

**A:** SCAR-Nummern werden automatisch aus Datum und laufender Nummer erzeugt. Bei sehr schnell parallel angelegten SCARs kann es zu Konflikten kommen; das System versucht es automatisch bis zu 3-mal erneut. Bei anhaltendem Fehlschlag später erneut versuchen.

### F6: Wie lege ich direkt aus einer Reklamation ein CAPA an?

**A:** Mit `POST /api/customer-complaints/{id}/create-capa?document_no=XXX`. Das System legt automatisch einen 8D-Bericht an (Status `D1_TEAM`), verknüpft `capa_ref_id` der Reklamation und schaltet die Reklamation auf `investigating`.

### F7: Sieht die Rolle customer_qe die SCAR-Liste?

**A:** Ja. customer_qe hat VIEW im Modul `scar` und kann SCAR-Liste und -Details ansehen, aber keine SCARs anlegen, weiterschalten oder abschließen. Dafür supplier_qe oder eine höhere Rolle verwenden.

### F8: Wie wird die Überfälligkeit berechnet?

**A:** Überfällig = `due_date` liegt vor heute und der Status ist weder `closed` noch `cancelled`. Ist `due_date` leer, gilt die Reklamation nicht als überfällig.

### F9: Wie wird die PPM berechnet?

**A:** PPM = (betroffene Menge der Reklamationen + eigenständige RMA-Rücksendemenge) / Versandmenge × 1.000.000. Für die Versandmenge gilt diese Reihenfolge:
1. Ausdrücklich übergebener Parameter `shipment_qty`
2. Versandsumme im Zeitfenster aus Tabelle `shipment_records`
3. `annual_shipment_qty` des Kunden, anteilig auf die Tage des Zeitfensters umgerechnet

Ist nichts davon verfügbar, liefert PPM `null`.

### F10: Wie wird die Risikoampel bestimmt?

| Bedingung | Ampel |
|------|------|
| Offene kritische Reklamation oder überfällige Reklamation vorhanden | 🔴 red |
| PPM > 2 × Zielwert | 🔴 red |
| PPM > Zielwert (und nicht red) | 🟡 yellow |
| Offene Reklamationen vorhanden (und nicht red/yellow) | 🟡 yellow |
| Keine der obigen Bedingungen | 🟢 green |

---

## Anhang: Übersicht der API-Endpunkte

### Kundenverwaltung

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/customers` | VIEW |
| POST | `/api/customers` | CREATE |
| GET | `/api/customers/{id}` | VIEW |
| PUT | `/api/customers/{id}` | CREATE |
| GET | `/api/customers/{id}/summary` | VIEW |

### Reklamationsmanagement

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/customer-complaints` | VIEW |
| POST | `/api/customer-complaints` | CREATE |
| GET | `/api/customer-complaints/{id}` | VIEW |
| PUT | `/api/customer-complaints/{id}` | CREATE |
| POST | `/api/customer-complaints/{id}/start-investigation` | CREATE |
| POST | `/api/customer-complaints/{id}/mark-responded` | CREATE |
| POST | `/api/customer-complaints/{id}/close` | APPROVE |
| POST | `/api/customer-complaints/{id}/cancel` | CREATE |
| POST | `/api/customer-complaints/{id}/link-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/create-capa` | CREATE |
| POST | `/api/customer-complaints/{id}/link-fmea` | CREATE |
| POST | `/api/customer-complaints/{id}/create-scar` | CREATE |

### RMA-Verwaltung

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/rma-records` | VIEW |
| POST | `/api/rma-records` | CREATE |
| GET | `/api/rma-records/{id}` | VIEW |
| PUT | `/api/rma-records/{id}` | CREATE |
| POST | `/api/rma-records/{id}/start-analysis` | CREATE |
| POST | `/api/rma-records/{id}/mark-action-pending` | CREATE |
| POST | `/api/rma-records/{id}/close` | APPROVE |
| POST | `/api/rma-records/{id}/cancel` | CREATE |
| POST | `/api/rma-records/{id}/link-complaint` | CREATE |
| POST | `/api/rma-records/{id}/link-capa` | CREATE |
| POST | `/api/rma-records/{id}/link-fmea` | CREATE |
| POST | `/api/rma-records/{id}/create-scar` | CREATE |

### SCAR-Verwaltung

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/scars` | VIEW |
| POST | `/api/scars` | CREATE |
| GET | `/api/scars/{id}` | VIEW |
| PUT | `/api/scars/{id}` | CREATE |
| POST | `/api/scars/{id}/transition` | Siehe Tabelle der Aktionsrechte |
| POST | `/api/scars/{id}/link-capa` | CREATE |

### Kundenaudits

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/audit-plans` | VIEW |
| POST | `/api/audit-plans` | CREATE |
| GET | `/api/audit-plans/{id}` | VIEW |
| PUT | `/api/audit-plans/{id}` | CREATE |
| POST | `/api/audit-plans/{id}/complete` | CREATE |
| GET | `/api/audit-plans/customer-stats` | VIEW |
| POST | `/api/audit-findings/{finding_id}/customer-confirm` | CREATE |

### Dashboard und Statistik

| Methode | Endpunkt | Mindestberechtigung |
|------|------|----------|
| GET | `/api/customer-quality/dashboard` | VIEW |
| GET | `/api/customer-quality/customers/{id}/trend` | VIEW |
| GET | `/api/customer-complaints/by-supplier/{supplier_id}` | VIEW |