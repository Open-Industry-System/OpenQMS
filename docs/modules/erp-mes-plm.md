# Integrationsmodule ERP / MES / PLM — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-06-13 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

OpenQMS bietet Integrationsmodule für die drei externen Systeme ERP, MES und PLM. Über eine **Konnektor-Architektur (Connector)** werden bestehende Unternehmenssysteme angebunden und Qualitätsdaten mit Lieferkette, Fertigungssteuerung und Produktlebenszyklus verbunden – für durchgängige Rückverfolgbarkeit.

Alle drei Module sind als **Integrations-Dashboard (Integration Dashboard)** aufgebaut: Konfigurierte Konnektoren holen Daten aus externen Systemen, die in OpenQMS angezeigt, verknüpft und für Qualitätsprozesse genutzt werden.

| Modul | Kernfunktionen | Typischer Einsatz |
|------|---------|---------|
| ERP | Synchronisation von Lieferanten-/Kundenstammdaten, Verfolgung von Einkaufs- und Verkaufsaufträgen, Bestandsabfrage, Qualitätskostenanalyse, Chargenrückverfolgung vorwärts und rückwärts | Rückverfolgen, bei welchem Lieferanten eine Rohmaterialcharge gekauft und an welchen Kunden sie geliefert wurde; Qualitätskosten ermitteln |
| MES | Überwachung des Fertigungsauftragsfortschritts, Anlagen-OEE, Verfolgung von Fehlteilen/Ausschuss, automatische Rückmeldung von SPC-Messdaten | Linienstatus in Echtzeit; MES sendet Messdaten an OpenQMS und löst SPC-Alarme aus |
| PLM | Synchronisation von Teilen/Stücklisten, ECN-Änderungsmanagement, FMEA-Verknüpfung und Stücklistenimport, Bestätigung besonderer Merkmale | Nach Teileänderungen automatisch betroffene FMEA-Knoten analysieren; Stücklistenstruktur in die FMEA importieren |

**Datenflüsse:**

- **Abholen (Pull):** Konnektoren synchronisieren zeitgesteuert Daten aus externen Systemen in die zugehörigen OpenQMS-Tabellen
- **Senden (Push):** Externe Systeme senden Daten aktiv über die Ingest-API an OpenQMS
- **Rückschreiben (Outbox Push):** Das MES-Modul kann SPC-Alarmereignisse an das MES senden (Konnektor mit `push_enabled`)

**Frontend-Routen:**

| Modul | Seite | Route | Routenschutz |
|------|------|------|---------|
| ERP | Dashboard | `/erp` | `requiredModule="erp"` |
| | Verbindungsverwaltung | `/erp/connections` | `requiredModule="erp"` |
| | Stammdaten | `/erp/master-data` | `requiredModule="erp"` |
| | Lieferkette | `/erp/supply-chain` | `requiredModule="erp"` |
| | Geschäft/Kosten | `/erp/commercial` | `requiredModule="erp"` |
| | Rückverfolgung | `/erp/traceability` | `requiredModule="erp"` |
| MES | Dashboard | `/mes/dashboard` | Nur Anmeldung (kein `requiredModule`) |
| | Verbindungsverwaltung | `/mes/connections` | Nur Anmeldung |
| | Fertigungsaufträge | `/mes/orders` | Nur Anmeldung |
| | Ausschussverfolgung | `/mes/scrap` | Nur Anmeldung |
| PLM | Dashboard | `/plm/dashboard` | `requiredModule="plm"` |
| | Verbindungsverwaltung | `/plm/connections` | `requiredModule="plm"` |
| | Teile/Stücklisten | `/plm/parts` | `requiredModule="plm"` |
| | Änderungsaufträge | `/plm/change-orders` | `requiredModule="plm"` |

> **Hinweis:** Die MES-Frontend-Routen haben keinen Schutz über `requiredModule` und prüfen nur die Anmeldung; die Backend-API prüft die Rechte jedoch weiterhin über `get_user_permission(user, Module.MES, db)`.

---

## 2. Rollen und Berechtigungen

Das System nutzt ein Berechtigungsmodell mit 6 Stufen: NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| `erp` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `mes` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |
| `plm` | 5 | 4 | 2 | 1 | 1 | 1 | 1 |

**Bedeutung der Rechte:**

- **admin (5 — ADMIN):** Vollzugriff, einschließlich Löschen von Verbindungen und Konfiguration von Verschlüsselungsschlüsseln
- **manager (4 — APPROVE):** Verbindungen anlegen/bearbeiten, Synchronisation auslösen, alle Daten ansehen
- **field_qe (2 — CREATE):** Bei ERP/MES nur Daten ansehen, bei PLM Verbindungen anlegen, FMEA verknüpfen und besondere Merkmale bestätigen
- **planning_qe / supplier_qe / customer_qe (1 — VIEW):** nur Dashboards und Berichte ansehen
- **viewer (1 — VIEW):** nur Dashboards und Berichte ansehen

### Operationen und Mindestberechtigung

#### ERP-Operationen

| Operation | Mindest-PermissionLevel | Beschreibung |
|------|---------------------|------|
| Dashboard/Daten ansehen | VIEW (1) | Für alle Rollen sichtbar |
| Lieferanten/Kunden ansehen (geschwärzt) | VIEW (1) | Mit VIEW maskierte Daten |
| Lieferanten/Kunden ansehen (vollständig) | APPROVE (4) | Ab APPROVE vollständige Informationen |
| Lieferanten verknüpfen/entknüpfen | EDIT (3) | field_qe hat dieses Recht nicht, nur manager/admin |
| Kunden verknüpfen/entknüpfen | EDIT (3) | Wie oben |
| Verbindung anlegen | APPROVE (4) | Nur manager, admin |
| Verbindungskonfiguration ändern | APPROVE (4) | Nur manager, admin |
| Verbindung testen | APPROVE (4) | Nur manager, admin |
| Manuelle Synchronisation auslösen | APPROVE (4) | Nur manager, admin |
| Verbindung löschen | ADMIN (5) | Nur admin |
| Senden über die Ingest-API | API-Key-Authentifizierung | Keine Rollenrechte, Header X-API-Key |

#### MES-Operationen

| Operation | Mindest-PermissionLevel | Beschreibung |
|------|---------------------|------|
| Dashboard/Fertigungsaufträge/Anlagen/Ausschuss ansehen | VIEW (1) | Für alle Rollen sichtbar |
| Verbindung anlegen | APPROVE (4) | Nur manager, admin |
| Verbindung ändern/löschen | APPROVE (4) | Nur manager, admin |
| Verbindung testen | APPROVE (4) | Nur manager, admin |
| Manuelle Synchronisation auslösen | APPROVE (4) | Nur manager, admin |
| Senden über die Ingest-API | API-Key-Authentifizierung | Keine Rollenrechte, Header X-API-Key + X-Connection-Id |

#### PLM-Operationen

| Operation | Mindest-PermissionLevel | Beschreibung |
|------|---------------------|------|
| Dashboard/Teile/Stücklisten/Änderungsaufträge ansehen | VIEW (1) | Für alle Rollen sichtbar |
| Verbindung anlegen | CREATE (2) | Ab field_qe |
| Verbindungskonfiguration ändern | EDIT (3) | field_qe hat dieses Recht nicht, nur manager/admin |
| Verbindung testen | EDIT (3) | Nur manager/admin |
| Manuelle Synchronisation auslösen | EDIT (3) | Nur manager/admin |
| Teil mit FMEA verknüpfen | EDIT (3) | Nur manager/admin |
| Besondere Merkmale bestätigen | EDIT (3) + SC CREATE (2) | Erfordert PLM EDIT und SPECIAL_CHARACTERISTIC CREATE |
| Änderungsauswirkungsanalyse auslösen | EDIT (3) | Nur manager/admin |
| Stückliste in FMEA importieren | EDIT (3) | Nur manager/admin |
| Verbindung löschen | ADMIN (5) | Nur admin |

> **Besonderes PLM-Recht:** Die Schnittstelle `confirm_part_sc` prüft sowohl EDIT (3) im PLM-Modul als auch CREATE (2) im Modul SPECIAL_CHARACTERISTIC.

---

## 3. ERP-Integration

### 3.1 Dashboard

Das ERP-Dashboard (`/erp`) bietet folgende Übersicht:

| Bereich | Inhalt | Datenquelle |
|------|------|--------|
| Synchronisationszustand | Letzte Synchronisation, Status und Fehlschläge je Datentyp | `erp_sync_jobs` |
| Zusammenfassung Qualitätskosten | Qualitätskosten nach Kategorie | `erp_cost_records` |
| Offene Punkte | Auffälligkeiten mit Handlungsbedarf (z. B. Bestandswarnung, Versandrisiko) | Systemaggregation |
| Bestandswarnungen | Niedriger Bestand oder Ablaufwarnung | `erp_inventory_balances` |
| Versandrisiken | Verspätete oder auffällige Sendungen | `erp_shipments` |
| KPI-Kennzahlen | Zentrale Leistungskennzahlen | Systemberechnung |

### 3.2 Verbindungsverwaltung

**Route:** `/erp/connections`

#### 3.2.1 Konnektortypen

| Typ | Beschreibung |
|------|------|
| `mock` | Eingebauter Simulationskonnektor mit Beispieldaten der Produktlinie DC-DC-100 für Demo und Test |
| `rest` | Allgemeiner REST-API-Konnektor mit vollständiger Konfiguration für Paginierung, Authentifizierung, Retry und Feldzuordnung |

#### 3.2.2 Konfiguration des REST-Konnektors

Beim Anlegen eines REST-Konnektors sind folgende Parameter zu konfigurieren:

**Grundkonfiguration:**

| Parameter | Beschreibung | Beispiel |
|------|------|------|
| `name` | Verbindungsname | „SAP S/4HANA Produktion“ |
| `connector_type` | Fest `rest` | — |
| `product_line_code` | Produktliniencode | "DC-DC-100" |
| `config.base_url` | Basis-URL der ERP-API | `https://erp.example.com/api/v1` |
| `config.timeout` | Anfrage-Timeout (Sekunden) | 30 |
| `config.retry` | Retry-Konfiguration | `{"max_retries": 3, "backoff_factor": 1.0}` |

**Authentifizierung (`config.auth_type`):**

| Typ | Beschreibung | Zusätzliche Parameter |
|------|------|---------|
| `none` | Keine Authentifizierung | — |
| `basic` | HTTP Basic Auth | `auth_config.username`, `auth_config.password` |
| `bearer` | Bearer Token | `auth_config.token` |
| `api_key` | API-Key-Header | `auth_config.header_name`, `auth_config.api_key` |

> Authentifizierungsdaten werden mit Fernet symmetrisch verschlüsselt gespeichert (Umgebungsvariable `ERP_ENCRYPTION_KEY`) und in API-Antworten automatisch geschwärzt (Entfernen von `auth_config`, `*_encrypted`, `*_hash`).

**Endpunkte (`config.endpoints`):**

Für 9 Datentypen sind Abrufendpunkte zu konfigurieren:

| Endpunktschlüssel | Daten | Beschreibung |
|--------|---------|------|
| `suppliers` | Lieferanten | Lieferantenstammdaten |
| `customers` | Kunden | Kundenstammdaten |
| `materials` | Material | Materialstammdaten |
| `locations` | Lagerorte | Lager-/Lagerortinformationen |
| `purchase_orders` | Einkaufsaufträge | PO-Positionen |
| `sales_orders` | Verkaufsaufträge | SO-Positionen |
| `inventory_balances` | Bestandssalden | Bestandsschnappschuss in Echtzeit |
| `shipments` | Sendungen | Versanddatensätze |
| `cost_records` | Kostendatensätze | Qualitätskostendaten |

Je Endpunkt werden `url_path`, `method` (Standard GET), Paginierungsart (`offset` / `cursor` / `none`), Feldzuordnung usw. konfiguriert.

**Feldzuordnung (`config.field_mapping`):**

Ordnet Feldnamen des externen Systems internen OpenQMS-Feldnamen zu, Beispiel:

```json
{
  "suppliers": {"ext_feld_lieferantencode": "supplier_code", "ext_feld_name": "name"},
  "materials": {"MaterialNo": "material_code"}
}
```

#### 3.2.3 Lebenszyklus einer Verbindung

| Operation | Berechtigung | Beschreibung |
|------|------|------|
| Verbindung anlegen | APPROVE (4) | Name, Typ und Konfiguration eingeben |
| Verbindung testen | APPROVE (4) | Eine Testanfrage an das externe System senden und Erreichbarkeit sowie Authentifizierung prüfen |
| Konfiguration ändern | APPROVE (4) | Verbindungsparameter aktualisieren |
| Manuelle Synchronisation auslösen | APPROVE (4) | Alle Datentypen sofort abholen |
| Verbindung löschen | ADMIN (5) | Weiches Löschen (Kennzeichen `is_active = false`) |

**Synchronisationsmechanismus:**

Die ERP-Synchronisation nutzt eine **DAG-Steuerung in 4 Phasen**:

- **Phase 1:** suppliers, customers, materials, locations (Stammdaten)
- **Phase 2:** purchase_orders, sales_orders (Belege, abhängig von Phase 1)
- **Phase 3:** inventory_balances, shipments (Echtzeitdaten)
- **Phase 4:** cost_records (aggregierte Daten)

Je Datentyp gibt es einen `ERPSyncJob`; `SELECT ... FOR UPDATE SKIP LOCKED` verhindert Konflikte. Nach 3 aufeinanderfolgenden Fehlschlägen wird die Verbindung automatisch deaktiviert.

### 3.3 Stammdaten

**Route:** `/erp/master-data`

Zeigt die vier aus dem ERP synchronisierten Stammdatenarten:

| Daten | Wichtige Felder | Beschreibung |
|------|---------|------|
| **Lieferanten (Suppliers)** | supplier_code, name, status, payment_terms, currency, tax_id, bank_info, link_status | Mit VIEW geschwärzte Daten (Bankdaten maskiert), mit APPROVE vollständige Daten |
| **Kunden (Customers)** | customer_code, name, status, region, customer_level, tax_id, link_status | Wie Lieferanten, nach Berechtigung geschwärzt |
| **Material (Materials)** | material_code, name, specification, unit, material_type, is_purchased, is_manufactured, default_supplier_code, status | Materialart unterscheidet Kauf- und Eigenfertigungsteile |
| **Lagerorte (Locations)** | location_code, warehouse_code, zone_code, location_type, is_enabled | Dreistufige Struktur Lager–Bereich–Lagerplatz |

**Verknüpfung von Lieferanten/Kunden:**

Jeder Lieferanten-/Kundendatensatz hat ein Feld `link_status` mit den Werten:

| Status | Beschreibung |
|------|------|
| `pending` | Synchronisiert, aber nicht mit einem internen OpenQMS-Lieferanten/-Kunden verknüpft |
| `linked` | Mit einem OpenQMS-Lieferanten/-Kunden verknüpft |
| `unlinked` | Verknüpfung aufgehoben |

Verknüpfungen erfolgen über `/api/erp/suppliers/{id}/link` und `/api/erp/customers/{id}/link` (erfordert EDIT) und stellen eine bidirektionale Referenz zwischen externem ERP-Lieferanten und der OpenQMS-Tabelle `suppliers` her.

### 3.4 Lieferkette

**Route:** `/erp/supply-chain`

Zeigt Lieferkettendaten in den vier Dimensionen Einkauf, Verkauf, Bestand und Versand:

| Daten | Wichtige Felder | Beschreibung |
|------|---------|------|
| **Einkaufsaufträge (Purchase Orders)** | po_number, line_number, supplier_code, material_code, quantity, unit_price, delivery_date, received_quantity, status, lot_no | Mit Chargennummer, rückverfolgbar bis zum Lieferanten |
| **Verkaufsaufträge (Sales Orders)** | so_number, line_number, customer_code, material_code, quantity, unit_price, delivery_date, status | Nach Kunde einsehbar |
| **Bestandssalden (Inventory Balances)** | material_code, location_code, lot_no, supplier_lot_no, quantity, unit, inventory_status, manufacture_date, expiry_date | Mit Charge und Lieferantencharge, Unterstützung von Haltbarkeitsdaten |
| **Sendungen (Shipments)** | shipment_number, so_number, customer_code, material_code, lot_no, quantity, shipment_date, link_status | Verknüpfbar mit OpenQMS-Versandprüfdatensätzen |

**Versandverknüpfung:** Bei der Synchronisation ordnet das System über `customer_id + lot_no + shipment_date` automatisch ein OpenQMS-`ShipmentRecord` zu und schreibt `openqms_shipment_id` in den ERP-Versanddatensatz.

### 3.5 Geschäft und Kosten

**Route:** `/erp/commercial`

Zeigt Qualitätskostendaten:

| Daten | Wichtige Felder | Beschreibung |
|------|---------|------|
| **Kostendatensätze (Cost Records)** | record_type, cost_category, cost_type, amount, currency, period_month, source_document_no, material_code, supplier_code, cost_center, cost_date, description | Mehrdimensionale Kostenzuordnung |

Dimensionen der Kostenklassifizierung:

- **record_type:** Datensatzart (z. B. Verhütungs-, Prüf-, interne Fehler-, externe Fehlerkosten)
- **cost_category:** Kostenkategorie
- **cost_type:** konkrete Kostenposition
- **cost_center:** Kostenstelle

### 3.6 Rückverfolgung

**Route:** `/erp/traceability`

Bietet chargenbasierte **bidirektionale Rückverfolgung (Traceability)**:

- **Vorwärts:** von der Rohmaterialcharge → Einkaufsauftrag → Lieferant → Versand des Fertigprodukts → Kunde
- **Rückwärts:** von der Kundenreklamation → Versanddatensatz → Fertigungscharge → Rohmaterialcharge → Lieferant

**Ergebnis der Rückverfolgung:**

```json
{
  "nodes": [/* Liste der Knoten */],
  "edges": [/* Beziehungen zwischen Knoten */],
  "gaps": [/* Hinweise auf Datenlücken */]
}
```

Das Feld `gaps` markiert Unterbrechungen der Kette und weist auf Abschnitte mit unvollständigen Daten hin.

---

## 4. MES-Integration

### 4.1 Dashboard

Das MES-Dashboard (`/mes/dashboard`) bietet folgende Übersicht:

| Bereich | Inhalt | Datenquelle |
|------|------|--------|
| Anlagenübersicht | OEE je Anlage (Verfügbarkeit × Leistung × Qualitätsrate), Anzahl laufender/stehender Anlagen | `mes_equipment_status` |
| Produktionsstatistik | Geplante vs. tatsächliche Gesamtmenge | `mes_production_orders` |
| Fehlerverteilung | Ausschussmenge nach Fehlerkategorie | `mes_scrap_records` |
| Ausschusstrend | Ausschusstrend der letzten 7 Tage | `mes_scrap_records` |

### 4.2 Verbindungsverwaltung

**Route:** `/mes/connections`

#### 4.2.1 Konnektortypen

| Typ | Beschreibung |
|------|------|
| `mock` | Eingebauter Simulationskonnektor mit Beispieldaten der Produktlinie DC-DC-100 |
| `rest` | Allgemeiner REST-API-Konnektor mit vollständiger Unterstützung für Paginierung, Authentifizierung, Retry, Feldzuordnung und Datenprüfung |

#### 4.2.2 Konfiguration des REST-Konnektors

Ähnlich wie beim ERP-Konnektor, aber nur mit Endpunkten für 4 Datentypen:

| Endpunktschlüssel | Daten | Beschreibung |
|--------|---------|------|
| `production_orders` | Fertigungsaufträge | Auftragsnummer, Produkttyp, Arbeitsplan, geplante/tatsächliche Menge |
| `equipment_status` | Anlagenstatus | Anlagencode, Name, OEE, Stillstandsgrund |
| `scrap_records` | Ausschussdatensätze | Auftragsnummer, Fehlerart, Fehlermenge |
| `measurements` | Messdaten | Daten von SPC-Prüfmerkmalen, an das SPC-Modul von OpenQMS gesendet |

Die **Authentifizierung** entspricht ERP (none / basic / bearer / api_key); der Verschlüsselungsschlüssel ist die Umgebungsvariable `MES_ENCRYPTION_KEY`.

**Sendekonfiguration:**

Ist beim MES-Konnektor `push_enabled = true` gesetzt, muss der Endpunkt `push_event` konfiguriert werden; OpenQMS sendet SPC-Alarmereignisse dann über das Outbox-Muster an das MES.

#### 4.2.3 Lebenszyklus einer Verbindung

Wie beim ERP nutzt auch MES das Nebenläufigkeitsmuster mit claim_token und `SELECT ... FOR UPDATE SKIP LOCKED`; nach 3 aufeinanderfolgenden Fehlschlägen wird die Verbindung automatisch deaktiviert.

**Synchronisationsmechanismus:** Die MES-Synchronisation läuft je Datentyp unabhängig, 4 Synchronisationsaufgaben parallel:

| Datentyp | Synchronisationsstrategie |
|---------|---------|
| `production_orders` | UPSERT, Deduplizierung nach `connection_id + order_no` |
| `equipment_status` | INSERT ON CONFLICT DO NOTHING |
| `scrap_records` | UPSERT, `order_id` wird nachgetragen |
| `measurements` | Dedupliziert gespeichert, IC verknüpft + SampleBatch angelegt + SPC-Alarme neu bewertet |

**Synchronisationsparameter:**

| Parameter | Wert | Beschreibung |
|------|---|------|
| Synchronisationsintervall | 5 Minuten | `SYNC_INTERVAL_MINUTES` |
| Überlappungsfenster | 300 Sekunden | `OVERLAP_WINDOW_SECONDS` |
| Timeout | 10 Minuten | `TIMEOUT_MINUTES` |
| Maximale Fehlschläge | 3 | `MAX_FAILURES` |
| Stapelgröße | 100 | `BATCH_SIZE` |

#### 4.2.4 Datenlebenszyklus

Das MES-Modul enthält eine eingebaute Bereinigung nach Datenlebenszyklus:

| Datentyp | Aufbewahrung | Behandlung |
|---------|--------|---------|
| Anlagenstatus | 90 Tage | Direkt löschen |
| Ausschussdatensätze | 365 Tage | Erst in `mes_scrap_monthly_summary` aggregieren, dann Details löschen |
| Abgeschlossene Fertigungsaufträge | 730 Tage | Archivierung in `mes_production_orders_archive` |

Die Bereinigung verhindert parallele Ausführung mit `pg_try_advisory_xact_lock(42)`.

### 4.3 Fertigungsaufträge

**Route:** `/mes/orders`

Zeigt aus dem MES synchronisierte Fertigungsaufträge:

| Feld | Beschreibung |
|------|------|
| `order_no` | Auftragsnummer (eindeutige Kennung, innerhalb der Verbindung dedupliziert) |
| `product_model` | Produkttyp |
| `process_route` | Arbeitsplan |
| `planned_qty` | Geplante Menge |
| `actual_qty` | Tatsächliche Menge |
| `status` | Auftragsstatus: `planned` / `in_progress` / `completed` / `closed` |
| `started_at` | Startzeit |
| `completed_at` | Fertigstellungszeit |

Filter nach Status, Zeitraum usw. sowie Paginierung werden unterstützt.

### 4.4 Ausschussverfolgung

**Route:** `/mes/scrap`

Zeigt aus dem MES synchronisierte Ausschuss-/Fehlteildatensätze:

| Feld | Beschreibung |
|------|------|
| `order_no` | Verknüpfte Auftragsnummer |
| `order_id` | Verknüpfte Auftrags-ID (Fremdschlüssel) |
| `equipment_code` | Anlagencode |
| `defect_type` | Fehlerart |
| `defect_category` | Fehlerkategorie |
| `defect_qty` | Fehlermenge |
| `total_qty` | Geprüfte Gesamtmenge |
| `defect_description` | Fehlerbeschreibung |

Ausschussdatensätze sind über `order_id` mit Fertigungsaufträgen verknüpft und lassen sich nach Auftrag, Anlage, Fehlerart usw. analysieren.

### 4.5 SPC-Kopplung

Die zentrale modulübergreifende Kopplung des MES ist **Messdaten → SPC**:

1. Das MES sendet Messdaten über die Ingest-API oder per Abholung
2. Daten werden in `mes_measurement_ingestions` geschrieben und nach `(connection_id, external_id)` dedupliziert
3. Das System sucht das zugehörige InspectionCharacteristic (Prüfmerkmal) und legt ein SampleBatch an
4. Die SPC-Alarmregeln werden neu bewertet
5. Entsteht ein Alarm und ist beim Konnektor `push_enabled` gesetzt, wird das Alarmereignis in `MESPushOutbox` geschrieben
6. Der Push-Worker sendet den Alarm zurück an das MES

**Format der Sendeereignisse:** SPC-Alarmereignisse enthalten Prüfmerkmal-ID, Alarmregel, Auslösezeit, Stichprobendaten usw.; das MES kann daraufhin Linienstopp oder zusätzliche Prüfung auslösen.

---

## 5. PLM-Integration

### 5.1 Dashboard

Das PLM-Dashboard (`/plm/dashboard`) bietet folgende Übersicht:

| Bereich | Inhalt | Datenquelle |
|------|------|--------|
| Teilestatistik | Anzahl Teile | `plm_parts` |
| Stücklistenstatistik | Anzahl Stücklistenpositionen | `plm_boms` |
| Offene ECN | Anzahl freizugebender Änderungsaufträge | `plm_change_orders` |
| Zu bestätigende besondere Merkmale | Anzahl zu bestätigender Sicherheits-/kritischer Merkmale | `plm_part_sc_links` (status=pending) |
| Letzte Änderungen | Liste der letzten Änderungsaufträge | `plm_change_orders` |

### 5.2 Verbindungsverwaltung

**Route:** `/plm/connections`

#### 5.2.1 Konnektortypen

| Typ | Beschreibung | Umsetzungsstand |
|------|------|---------|
| `mock` | Eingebauter Simulationskonnektor mit Beispieldaten der Produktlinie DC-DC-100 | Umgesetzt |
| `rest` | Allgemeiner REST-API-Konnektor | Gerüst umgesetzt, Abrufmethoden noch TODO |
| `siemens_tc` | Konnektor Siemens Teamcenter | Gerüst umgesetzt (abgebildet auf RESTPLMConnector) |
| `dassault_enovia` | Konnektor Dassault ENOVIA | Gerüst umgesetzt (abgebildet auf RESTPLMConnector) |
| `ptc_windchill` | Konnektor PTC Windchill | Gerüst umgesetzt (abgebildet auf RESTPLMConnector) |

> **Wichtig:** Derzeit können über die API nur Verbindungen vom Typ `mock` angelegt werden. Das Backend prüft `IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`; andere Typen liefern einen Fehler 400. Die Konnektorgerüste für `rest`, `siemens_tc`, `dassault_enovia` und `ptc_windchill` existieren, ihre Abrufmethoden werfen aber `NotImplementedError`.

#### 5.2.2 Beispieldaten des Mock-Konnektors

Der Mock-Konnektor erzeugt folgende Beispieldaten für DC-DC-100:

**Teile (5):**

| Teilenummer | Name | Besondere Kennzeichnung |
|--------|------|---------|
| DC-DC-100-ASM | Baugruppe DC-DC-100 | safety + key_characteristic |
| PCBA-MAIN-01 | Steuerplatinen-Baugruppe | key_characteristic |
| HOUSING-TOP-01 | Obergehäuse | — |
| HEATSINK-01 | Kühlkörper | — |
| CAP-CER-100UF | Keramikkondensator 100 μF | — |

**Stückliste (5 Positionen, 3 Ebenen):**

```
DC-DC-100-ASM (L0)
├── PCBA-MAIN-01 (L1, qty=1)
├── HOUSING-TOP-01 (L1, qty=1)
└── HEATSINK-01 (L1, qty=1)
    └── CAP-CER-100UF (L2, qty=2)
```

**Änderungsaufträge (2):**

| Änderungsnummer | Titel | Status | Priorität |
|--------|------|------|--------|
| ECN-2026-001 | Werkstoff-Upgrade des Kühlkörpers | approved | high |
| ECN-2026-002 | Spezifikationsanpassung des Keramikkondensators | draft | normal |

#### 5.2.3 Synchronisationsmechanismus

Die PLM-Synchronisation läuft in 3 Phasen:

| Phase | Datentyp | Beschreibung |
|------|---------|------|
| Phase 1 | `part` | Teilestammdaten (automatische SC-Verknüpfung für Sicherheits-/kritische Merkmale) |
| Phase 2 | `bom` | Stücklistenstruktur (Deduplizierung über eindeutigen Constraint auf 6 Spalten) |
| Phase 3 | `change_order` | Änderungsaufträge (bei Status `approved` wird automatisch eine Änderungsauswirkungsanalyse angelegt) |

Auch hier gilt das claim_token-Muster; nach 3 aufeinanderfolgenden Fehlschlägen wird die Verbindung automatisch deaktiviert.

### 5.3 Teile und Stücklisten

**Route:** `/plm/parts`

#### 5.3.1 Teileliste

Zeigt aus dem PLM synchronisierte Teiledaten:

| Feld | Beschreibung |
|------|------|
| `part_number` | Teilenummer (eindeutig je Verbindung + Version) |
| `name` | Teilename |
| `revision` | Version (Standard „A“) |
| `material` | Werkstoff |
| `specification` | Spezifikation |
| `status` | Status |
| `is_safety_related` | Sicherheitsrelevant ja/nein |
| `is_key_characteristic` | Kritisches Merkmal ja/nein |
| `sc_links` | Liste verknüpfter besonderer Merkmale |

**Kopplung besonderer Merkmale:**

Bei `is_safety_related = true` legt die Synchronisation automatisch ein `PLMPartSCLink` an (`characteristic_type = "safety"`, `status = "pending"`); bei `is_key_characteristic = true` einen SC-Link mit `characteristic_type = "key_characteristic"`.

#### 5.3.2 Stücklistenbaum

Über `/api/plm/connections/{id}/boms/tree/{part_number}` lässt sich der vollständig aufgelöste Stücklistenbaum eines Teils abrufen:

```json
{
  "part_number": "DC-DC-100-ASM",
  "revision": "A",
  "children": [
    {
      "part_number": "PCBA-MAIN-01",
      "revision": "A",
      "quantity": 1,
      "children": []
    }
  ]
}
```

#### 5.3.3 Teil mit FMEA verknüpfen

Über `/api/plm/parts/{part_id}/link-fmea` wird ein Teil mit einem bestimmten Knoten eines FMEA-Dokuments verknüpft:

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "link_type": "manual"
}
```

Werte von `link_type`: `auto_import` (automatisch beim Stücklistenimport) oder `manual` (manuell).

#### 5.3.4 Besondere Merkmale bestätigen

Über `/api/plm/parts/{part_id}/confirm-sc` wird die Kennzeichnung besonderer Merkmale eines Teils bestätigt; Voraussetzungen:
- EDIT (3) im PLM-Modul
- CREATE (2) im Modul SPECIAL_CHARACTERISTIC

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "node_id": "uuid-of-fmea-node",
  "characteristic_type": "safety"
}
```

#### 5.3.5 Stückliste in FMEA importieren

Über `/api/plm/connections/{id}/boms/{part_number}/import-to-fmea` wird die Stücklistenstruktur in ein bestimmtes FMEA-Dokument importiert:

```json
{
  "fmea_id": "uuid-of-fmea-document",
  "overwrite": false
}
```

Das System wandelt den Stücklistenbaum in FMEA-Graphknoten und -kanten um und legt `PLMPartFMEALink` an (`link_type = "auto_import"`).

### 5.4 Änderungsaufträge

**Route:** `/plm/change-orders`

Zeigt aus dem PLM synchronisierte technische Änderungsaufträge (ECN):

| Feld | Beschreibung |
|------|------|
| `change_number` | Änderungsnummer (eindeutig je Verbindung) |
| `title` | Änderungstitel |
| `description` | Änderungsbeschreibung |
| `change_type` | Änderungsart |
| `status` | Status (draft / approved / implemented / closed) |
| `priority` | Priorität |
| `affected_part_numbers` | Liste betroffener Teile (JSONB) |
| `proposed_changes` | Vorgeschlagene Änderungen (JSONB) |
| `requested_by` | Antragsteller |
| `approved_by` | Freigebende Person |
| `planned_implementation_date` | Geplantes Umsetzungsdatum |
| `actual_implementation_date` | Tatsächliches Umsetzungsdatum |

#### 5.4.1 Änderungsauswirkungsanalyse

Wechselt ein Änderungsauftrag auf `approved`, legt das System automatisch einen `PLMChangeImpactTask` an. Manuell lässt sich die Analyse über `/api/plm/change-orders/{change_id}/impact-analysis` auslösen.

Ablauf der Auswirkungsanalyse:

1. `affected_part_numbers` des Änderungsauftrags lesen
2. Betroffene FMEA-Dokumente und Knoten über `PLMPartFMEALink` ermitteln
3. `ChangeImpactService.analyze()` für jeden betroffenen Knoten aufrufen
4. Analyseergebnis zurückgeben

---

## 6. Hinweise zur Verbindungskonfiguration

### 6.1 Verbindung anlegen

1. Die Seite „Verbindungsverwaltung“ des jeweiligen Moduls öffnen
2. Auf „Neue Verbindung“ klicken
3. Grunddaten eingeben:
   - **Name:** Anzeigename der Verbindung
   - **Konnektortyp:** `mock` (Test) oder `rest` (Produktion) wählen
   - **Produktlinie:** passenden Produktliniencode wählen
4. Bei Typ `rest` zusätzlich konfigurieren:
   - **API-Basisadresse:** URL des externen Systems
   - **Authentifizierung:** none / basic / bearer / api_key
   - **Endpunkte je Datentyp:** API-Pfad für jeden Datentyp
   - **Feldzuordnung:** Zuordnung externer Felder zu OpenQMS-Feldern
5. Auf „Anlegen“ klicken

### 6.2 Verbindung testen

Nach dem Anlegen in der Verbindungsliste auf „Testen“ klicken. Das System versucht:

- **ERP:** einen Lieferantendatensatz abzuholen, Rückgabe `{success, message}`
- **MES:** einen Fertigungsauftrag abzuholen, Rückgabe `{ok, error}`
- **PLM:** Teiledaten abzuholen, Rückgabe `{status, parts_count}` oder `{status, error, error_class}`

Ein erfolgreicher Test zeigt nur, dass die Verbindung nutzbar ist, nicht dass alle Endpunkte korrekt sind.

### 6.3 Datensynchronisation

#### Manuelle Synchronisation

In der Verbindungsliste auf „Synchronisieren“ klicken; das System startet sofort eine vollständige Synchronisation:

- **ERP:** alle 9 Datentypen in der DAG-Reihenfolge der 4 Phasen
- **MES:** 4 Datentypen parallel
- **PLM:** in 3 Phasen Teile → Stücklisten → Änderungsaufträge

#### Automatische Synchronisation

Im Hintergrund läuft die Synchronisation im konfigurierten Intervall; `SELECT ... FOR UPDATE SKIP LOCKED` verhindert doppelte Ausführung.

#### Sendemodus (Ingest)

Externe Systeme können Daten auch aktiv an OpenQMS senden:

**Request-Header:**

| Modul | Pflicht-Header |
|------|--------|
| ERP | `X-API-Key: <api_key>` |
| MES | `X-API-Key: <api_key>` + `X-Connection-Id: <connection_id>` |

**Request-Body ERP-Ingest:**

```json
{
  "data_type": "suppliers",
  "connection_id": "uuid",
  "items": [{...}, {...}]
}
```

Erlaubte Werte für `data_type`: `suppliers`, `customers`, `materials`, `locations`, `purchase_orders`, `sales_orders`, `inventory_balances`, `shipments`, `cost_records`

**Request-Body MES-Ingest:** Verwendet eine Discriminated Union; das Feld `data_type` muss angegeben werden:

- `production_orders`
- `equipment_status`
- `scrap_records`
- `measurements`

### 6.4 Verschlüsselung der Verbindungen

Alle Authentifizierungsdaten (Passwort, Token, API-Key) werden mit Fernet symmetrisch verschlüsselt gespeichert:

| Modul | Umgebungsvariable | Zweck |
|------|---------|------|
| ERP | `ERP_ENCRYPTION_KEY` | Verschlüsselt ausgehende Zugangsdaten, hasht eingehende API-Keys |
| MES | `MES_ENCRYPTION_KEY` | Wie oben |

**Sicherheitsmaßnahmen:**

- Ausgehende Zugangsdaten (Passwort, Token) werden Fernet-verschlüsselt gespeichert
- Eingehende API-Keys werden als SHA-256-Hash gespeichert und zeitkonstant verglichen (`hmac.compare_digest`)
- API-Antworten werden automatisch geschwärzt: `auth_config`, `*_encrypted`, `*_hash` werden entfernt

---

## 7. Häufige Fragen

### F1: Beim Anlegen eines REST-Konnektors erscheint „nicht unterstützter Konnektortyp“

**Ursache:** Das PLM-Modul erlaubt derzeit nur Verbindungen vom Typ `mock` (`IMPLEMENTED_CONNECTOR_TYPES = {"mock"}`); die Abrufmethoden von `rest`, `siemens_tc` usw. sind noch nicht umgesetzt.

**Lösung:** Für Demo und Test den `mock`-Konnektor verwenden; für die Produktion auf künftige Unterstützung des REST-Konnektors warten.

### F2: Die Synchronisation schlägt dauerhaft fehl, die Verbindung wurde automatisch deaktiviert

**Ursache:** Nach 3 aufeinanderfolgenden Fehlschlägen setzt das System die Verbindung auf `is_active = false` und schreibt ein Audit-Log.

**Lösung:**
1. Erreichbarkeit des externen Systems prüfen (Funktion „Verbindung testen“)
2. Authentifizierungskonfiguration prüfen (API-Key, Benutzername/Passwort usw.)
3. Endpunkt-URLs prüfen (insbesondere ob die Feldzuordnung zum Antwortformat des externen Systems passt)
4. Nach der Korrektur die Verbindung reaktivieren und manuell synchronisieren

### F3: MES-Seiten sind sichtbar, aber die API liefert 403

**Ursache:** Die MES-Frontend-Routen haben keinen Schutz über `requiredModule` und prüfen nur die Anmeldung. Die Backend-API prüft aber weiterhin über `get_user_permission(user, Module.MES, db)`. Ohne VIEW im MES-Modul liefert die API 403.

**Lösung:** Der Benutzerrolle in der Berechtigungskonfiguration mindestens VIEW (1) im MES-Modul geben.

### F4: ERP-Lieferanten-/Kundeninformationen werden maskiert angezeigt

**Ursache:** Mit VIEW werden sensible Felder wie Bankdaten von Lieferanten oder Steuerdaten von Kunden automatisch geschwärzt. Für vollständige Informationen ist mindestens APPROVE (4) nötig.

**Lösung:** Mit Rolle manager oder admin anmelden oder die ERP-Berechtigung der aktuellen Rolle erhöhen.

### F5: Die PLM-Änderungsauswirkungsanalyse liefert kein Ergebnis

**Mögliche Ursachen:**

1. `affected_part_numbers` des Änderungsauftrags ist leer
2. Die betroffenen Teile sind noch mit keinem FMEA-Dokument verknüpft (kein `PLMPartFMEALink`)
3. Der Änderungsauftrag ist nicht `approved` (automatische Auslösung nur beim Wechsel auf approved)

**Lösung:** Betroffene Teile zuerst über „Teil mit FMEA verknüpfen“ mit den passenden FMEA-Knoten verknüpfen und dann die Analyse auslösen.

### F6: Das Senden von Alarmereignissen an das MES schlägt fehl

**Ursache:** Das Senden nutzt das Outbox-Muster mit exponentiellem Backoff (Intervall = 2^retry_count Minuten, höchstens 32 Minuten).

**Prüfschritte:**
1. Prüfen, ob beim MES-Konnektor `push_enabled` gesetzt ist
2. Prüfen, ob der Endpunkt `push_event` korrekt konfiguriert ist
3. In der Tabelle `mes_push_outbox` `retry_count` und Fehlermeldung fehlgeschlagener Einträge ansehen
4. Sicherstellen, dass die Empfangsschnittstelle des externen MES verfügbar ist

### F7: Die ERP-Rückverfolgung zeigt „gaps“ (Datenlücken)

**Ursache:** Die Rückverfolgungskette enthält Abschnitte mit unvollständigen Daten, zum Beispiel:

- Einkaufsaufträgen fehlt die Chargennummer
- Versanddatensätze sind nicht mit OpenQMS-Versandprüfdatensätzen verknüpft (`openqms_shipment_id` leer)
- Bestandssalden fehlt die Lieferantencharge

**Lösung:** Schlüsselfelder im externen System ergänzen (Chargennummer, Lieferantencharge usw.) oder Daten über die Ingest-API ergänzen und neu synchronisieren.

### F8: Wie sehe ich den Status der Synchronisationsaufgaben?

**Lösung:** Die Tabellen `*_sync_jobs` der Module erfassen je Datentyp Synchronisationsstatus, Checkpoint und Anzahl aufeinanderfolgender Fehlschläge. Der Synchronisationszustand ist im ERP-/MES-/PLM-Dashboard sichtbar oder direkt per Datenbankabfrage:

```sql
-- Status der ERP-Synchronisationsaufgaben ansehen
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM erp_sync_jobs WHERE connection_id = '...';

-- Status der MES-Synchronisationsaufgaben ansehen
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM mes_sync_jobs WHERE connection_id = '...';

-- Status der PLM-Synchronisationsaufgaben ansehen
SELECT job_id, data_type, status, checkpoint, consecutive_failures
FROM plm_sync_jobs WHERE connection_id = '...';
```

### F9: Beim Bestätigen besonderer Merkmale in PLM erscheint „Berechtigung nicht ausreichend“

**Ursache:** Die Schnittstelle `confirm_part_sc` verlangt zwei Rechte zugleich:

1. EDIT (3) im PLM-Modul
2. CREATE (2) im Modul SPECIAL_CHARACTERISTIC

**Lösung:** Sicherstellen, dass die Rolle in beiden Modulen die nötige Stufe erreicht. Beispielsweise hat die Rolle `field_qe` im PLM-Modul Stufe 2 (CREATE) und erfüllt EDIT (3) nicht, kann also keine besonderen Merkmale bestätigen.

### F10: Lassen sich die Daten des Mock-Konnektors ändern?

Der Mock-Konnektor erzeugt bei jeder Synchronisation dieselben festen Beispieldaten (Produktlinie DC-DC-100) und ist nicht anpassbar. Für echte Daten einen REST-Konnektor an das tatsächliche ERP/MES/PLM anbinden. Mock-Daten dienen nur Demo und Test.