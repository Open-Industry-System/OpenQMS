# Benutzerhandbuch IQC und Lieferantenmanagement

## 1. Funktionsüberblick

Dieses Handbuch behandelt vier eng verbundene Module von OpenQMS:

| Modul | Kernfunktionen | Präfix der Frontend-Routen |
|------|---------|-------------|
| IQC – Wareneingangsprüfung | Prüflose anlegen, AQL-Stichprobenpläne automatisch berechnen, Entscheid und Wiederholungsprüfung, dynamische AQL-Optimierung | `/iqc` |
| Lieferantenmanagement | Lieferantenstammdaten, Bewertung und Einstufung (A/B/C/D), Dashboard der Qualitätsleistung | `/suppliers` |
| Lieferantenrisiko | Konfiguration der Risikoregeln, Risikobewertung und Warnungen, Bearbeitung von Warnungen | `/supplier-risk` |
| Risikokarte der Lieferkette | Mehrdimensionale Heatmap, Vergleich von Lieferanten-Snapshots, Zeittrend | `/supply-chain-risk-map` |

Datenfluss zwischen den vier Modulen:

```
IQC Prüfung ──→ Leistungsdaten der Lieferanten (PPM, Losannahmequote)
                              │
                              ▼
Lieferantenbewertung (Einstufung A/B/C/D) ──→ Risikobewertung ──→ Risikokarte der Lieferkette
                                                        │
SCAR / CAPA ◄────────────── Bearbeitung von Warnungen ◄───────────────┘
```

---

## 2. Rollen und Berechtigungen

OpenQMS verwendet ein Berechtigungsmodell mit fünf Stufen: NONE(0), VIEW(1), CREATE(2), EDIT(3), APPROVE(4), ADMIN(5).

| Modul (ModuleKey) | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `iqc` | 5 | 4 | 1 | 1 | 3 | 0 | 1 |
| `supplier` | 5 | 4 | 1 | 1 | 3 | 1 | 1 |
| `supplier_risk` | 5 | 4 | 3 | 1 | 3 | 1 | 1 |
| `supply_chain_risk_map` | 5 | 5 | 3 | 3 | 3 | 3 | 1 |

**Berechtigungsstufen:**

| Stufe | Wert | Fähigkeiten |
|------|:-:|------|
| NONE | 0 | Kein Zugriff auf das Modul |
| VIEW | 1 | Nur lesen: Listen, Details, Dashboards ansehen |
| CREATE | 2 | VIEW + Datensätze anlegen |
| EDIT | 3 | CREATE + bestehende Datensätze ändern/bearbeiten |
| APPROVE | 4 | EDIT + Freigeben, Entscheiden, Abschließen und weitere erweiterte Operationen |
| ADMIN | 5 | Alle Operationen, einschließlich Konfiguration und Stapelbewertung |

**Typische Operationen und erforderliche Berechtigung:**

| Operation | Erforderliche Stufe |
|------|:---:|
| Liste der Prüfdatensätze ansehen | VIEW (1) |
| Prüflos anlegen | CREATE (2) |
| Ergebnisse der Prüfmerkmale bearbeiten | EDIT (3) |
| Prüfentscheid (Annahme/Rückweisung) | APPROVE (4) |
| AQL-Parameter konfigurieren | ADMIN (5) |
| Lieferantenliste ansehen | VIEW (1) |
| Lieferant anlegen | CREATE (2) |
| Lieferanteninformationen bearbeiten | EDIT (3) |
| Lieferanten bewerten | APPROVE (4) |
| Risikobewertung aller Lieferanten auslösen | APPROVE (4) |
| Risikoregeln ändern | ADMIN (5) |

---

## 3. IQC – Wareneingangsprüfung

### 3.1 Modulübersicht

Das Modul IQC (Incoming Quality Control, Wareneingangsprüfung) verwaltet die gesamte Qualitätsprüfung zugelieferter Materialien und unterstützt zwei Prüfmodi:

- **Schnellprüfung (quick)**: Prüfinformationen je Los erfassen, für die normale Wareneingangsprüfung
- **Detailprüfung (detailed)**: mehrere Prüfmerkmale aus einer Prüfvorlage, für kritische Materialien oder wenn Messdaten je Merkmal erfasst werden müssen

**Frontend-Routen:**

| Route | Funktion |
|------|------|
| `/iqc/inspections` | Liste der Prüflose |
| `/iqc/inspections/:id` | Prüflosdetails (mit Prüfmerkmalen und Messwerten) |
| `/iqc/materials` | Materialstammdaten |
| `/iqc/aql-optimization` | Hauptseite der dynamischen AQL-Optimierung |
| `/iqc/aql-optimization/profiles` | Liste der AQL-Profile |
| `/iqc/aql-optimization/profiles/:supplierId/:materialId` | Details eines Profils |
| `/iqc/aql-optimization/config` | Globale AQL-Konfiguration |

### 3.2 Materialstammdaten

**Route:** `/iqc/materials`

Materialstammdaten sind die Grundlage der IQC-Prüfung. Jeder Materialdatensatz enthält:

| Feld | Beschreibung |
|------|------|
| `part_no` | Materialnummer (eindeutig) |
| `part_name` | Materialname |
| `part_spec` | Spezifikation |
| `material_type` | Materialart, Standard `raw` (Rohmaterial) |
| `default_aql` | Standard-AQL (z. B. 1.0, 2.5) |
| `default_inspection_level` | Standard-Prüfniveau (z. B. `II`) |
| `unit` | Maßeinheit |
| `product_line_code` | Produktliniencode, Standard `DC-DC-100` |
| `status` | Status: `active` / `inactive` |

Materialstammdaten liefern Standard-AQL und -Prüfniveau für neue Prüflose, damit sie nicht jedes Mal manuell eingegeben werden müssen.

### 3.3 Prüflosverwaltung

**Route:** `/iqc/inspections`

#### 3.3.1 Prüflos anlegen

Beim Anlegen sind folgende Angaben nötig:

| Feld | Beschreibung | Pflicht |
|------|------|:---:|
| `supplier_id` | Lieferant | Ja |
| `inspection_mode` | Prüfmodus: `quick` (schnell) oder `detailed` (detailliert) | Ja |
| `material_id` | Material (verknüpfte Materialstammdaten) | Nein |
| `template_id` | Prüfvorlage (im Detailmodus Pflicht) | Nein |
| `part_no` | Teilenummer | Nein |
| `part_name` | Teilebezeichnung | Nein |
| `lot_no` | Chargennummer | Nein |
| `lot_qty` | Losgröße | Nein |
| `aql_level` | AQL-Wert | Nein (automatisch ermittelt) |
| `inspection_level` | Prüfniveau, Standard `II` | Nein |
| `inspection_date` | Prüfdatum | Nein |

**Automatische AQL-Ermittlung:**

1. Ohne `aql_level` sucht das System zuerst `current_aql` im AQL-Profil von Lieferant + Material
2. Fehlt das Profil oder ist es `frozen`, wird auf `default_aql` der Materialstammdaten zurückgegriffen
3. Sind Losgröße `lot_qty` und `aql_level` belegt, berechnet `calculate_aql_plan()` automatisch den Stichprobenplan

#### 3.3.2 Automatische Berechnung des AQL-Stichprobenplans

Das System berechnet AQL-Stichprobenpläne nach **ISO 2859-1 / GB/T 2828.1**. Nach Eingabe von Losgröße `lot_qty`, AQL `aql_level` und Prüfniveau `inspection_level` liefert es:

| Ausgabe | Beschreibung |
|------|------|
| `code_letter` | Kennbuchstabe des Stichprobenumfangs |
| `sample_qty` | Zu prüfende Menge |
| `accept_number` | Annahmezahl (Ac) |
| `reject_number` | Rückweisezahl (Re) |

**Anpassung des Kennbuchstabens je Prüfniveau:**

| Prüfniveau | Verschiebung des Kennbuchstabens |
|----------|---------|
| S-1 | -4 |
| S-2 | -3 |
| S-3 | -2 |
| S-4 | -1 |
| I | -1 |
| II | 0 (Basis) |
| III | +1 |

**Entscheidungsregeln:**
- Fehleranzahl ≤ Ac → Annahme (`accepted`)
- Fehleranzahl ≥ Re → Rückweisung (`rejected`)

#### 3.3.3 Prüfmerkmale und Messwerte

Im **Detailmodus (detailed)** mit Prüfvorlage erzeugt das System die Prüfmerkmale (IqcInspectionItem) automatisch aus der Vorlage:

| Feld | Beschreibung |
|------|------|
| `category` | Prüfkategorie (z. B. Aussehen, Maß, Funktion) |
| `item_name` | Name des Prüfmerkmals |
| `inspect_type` | Prüfart: `attribute` (attributiv) oder `variable` (variabel) |
| `spec_upper` / `spec_lower` | Obere / untere Spezifikationsgrenze |
| `target_value` | Zielwert |
| `sample_size` | Stichprobenmenge des Merkmals |
| `aql_level` | AQL-Wert des Merkmals |

Je Prüfmerkmal lassen sich mehrere Messwerte (IqcItemMeasurement) erfassen, mit `measured_value` (Messwert) oder `attribute_result` (attributives Ergebnis).

#### 3.3.4 Prüfentscheid

Zustandsautomat des Prüfloses:

```
pending → in_progress → judged
                          ├── accepted(Annahme)
                          ├── rejected(Rückweisung)
                          └── conditionally_accepted(bedingte Annahme)
```

Der Entscheid (`judge_inspection`) erfordert APPROVE. Dabei kann markiert werden:
- `has_safety_defect`: sicherheitsrelevanter Fehler vorhanden
- `defect_description`: Fehlerbeschreibung
- `linked_capa_id`: verknüpfter CAPA-Datensatz
- `linked_scar_id`: verknüpfter SCAR-Datensatz

#### 3.3.5 Wiederholungsprüfung

Für entschiedene Prüflose kann eine Wiederholungsprüfung (`request_reinspect`) angefordert werden. Das System:
- legt ein neues Prüflos mit `re_inspection = True` an
- setzt `parent_inspection_id` auf das ursprüngliche Prüflos
- löst bei ursprünglichem AQL-Status `normal` automatisch eine Bewertung für verschärfte Prüfung aus

### 3.4 Prüfvorlagen

Prüfvorlagen (IqcInspectionTemplate) sind mit einem Material verknüpft und dienen dem automatischen Erzeugen im Detailmodus:

- Eine Vorlage enthält mehrere Prüfmerkmale (IqcTemplateItem)
- Jedes Merkmal definiert Kategorie, Name, Prüfmethode, Spezifikationsgrenzen, Zielwert, Stichprobenumfang und AQL
- Vorlagen haben eine Versionsnummer `version` und lassen sich über `is_active` aktivieren/deaktivieren

### 3.5 Dynamische AQL-Optimierung

**Route:** `/iqc/aql-optimization`

Die dynamische AQL-Optimierung passt die AQL-Prüfung anhand der Prüfhistorie von Lieferant + Material automatisch an, senkt die Prüfkosten bei guten Lieferanten und verschärft die Kontrolle bei problematischen.

#### 3.5.1 AQL Profile

**Route:** `/iqc/aql-optimization/profiles`

Jede Kombination „Lieferant + Material“ hat ein AQL-Profil (IqcAqlProfile):

| Feld | Beschreibung |
|------|------|
| `base_aql` | Basis-AQL |
| `current_aql` | Aktuell gültiger AQL |
| `min_aql` / `max_aql` | Grenzen der AQL-Anpassung |
| `inspection_level` | Aktuelles Prüfniveau |
| `state` | Status: `normal` / `tightened` / `reduced` / `frozen` |
| `frozen_until` | Ende der Sperre (gilt im Status `frozen`) |
| `frozen_reason` | Grund der Sperre |
| `baseline_inspection_id` | Basis-Prüflos (für spätere Vergleiche) |

**Regeln für Statuswechsel:**

| Bedingung | Neuer Status | AQL-Änderung |
|------|--------|---------|
| N Lose in Folge angenommen | `reduced` | AQL kann gelockert werden (z. B. 1.0 → 1.5) |
| Rückweisung innerhalb von M aufeinanderfolgenden Losen | `tightened` | AQL wird verschärft (z. B. 1.0 → 0.65) |
| Sicherheitsfehler aufgetreten | `frozen` | Aktueller AQL wird bis zum Ende der Sperrfrist fixiert |

#### 3.5.2 AQL-Konfiguration

**Route:** `/iqc/aql-optimization/config`

Die AQL-Konfiguration (IqcAqlConfig) enthält Systemparameter, die je Produktlinie überschrieben werden können:

- Einträge werden über `config_key` identifiziert, z. B. `switch_normal_to_reduced_batches` (Anzahl angenommener Lose in Folge für reduzierte Prüfung)
- Jeder Eintrag kann einen globalen Standardwert und einen produktlinienspezifischen Wert haben
- `is_editable` legt fest, ob Benutzer den Wert ändern dürfen
- Nur mit ADMIN änderbar

Rangfolge: **Wert der Produktlinie > globaler Standard > fest codierter Standard**

#### 3.5.3 Qualitäts-Snapshots

Bei jeder AQL-Bewertung speichert das System einen Qualitäts-Snapshot (IqcAqlQualitySnapshot) für spätere Trendanalysen:

| Feld | Beschreibung |
|------|------|
| `total_inspections` | Anzahl Prüflose im Zeitfenster |
| `accepted_count` | Angenommene Lose |
| `rejected_count` | Zurückgewiesene Lose |
| `ppm` | PPM (Teile pro Million) |
| `calculated_state` | Berechneter empfohlener Status |

---

## 4. Lieferantenmanagement

### 4.1 Modulübersicht

**Frontend-Routen:**

| Route | Funktion |
|------|------|
| `/suppliers` | Lieferantenliste |
| `/suppliers/:id` | Lieferantendetails |
| `/suppliers/quality` | Qualitäts-Dashboard der Lieferanten |
| `/suppliers/quality/:supplierId` | Qualitätsdetails eines Lieferanten |

### 4.2 Lieferantenstammdaten

#### 4.2.1 Lieferant anlegen

Beim Anlegen sind anzugeben:

| Feld | Beschreibung | Pflicht |
|------|------|:---:|
| `name` | Vollständiger Lieferantenname | Ja |
| `short_name` | Kurzname | Ja |
| `contact_name` | Ansprechpartner | Nein |
| `contact_phone` | Telefon | Nein |
| `contact_email` | E-Mail | Nein |
| `address` | Adresse | Nein |
| `product_scope` | Lieferumfang | Nein |

Nach dem Anlegen erhält der Lieferant automatisch eine `supplier_no` (Format `SUP-{YYYY}-{Nummer}`), der Anfangsstatus ist `pending_review`.

#### 4.2.2 Statusübergänge des Lieferanten

```
pending_review → audit_required → approved
                    ↓                  ↓
                 rejected          suspended
```

| Status | Beschreibung |
|------|------|
| `pending_review` | Wartet auf Prüfung, Anfangsstatus nach dem Anlegen |
| `audit_required` | Vor-Ort-Audit erforderlich |
| `approved` | Freigegeben, normale Geschäftsbeziehung |
| `rejected` | Prüfung nicht bestanden |
| `suspended` | Zusammenarbeit ausgesetzt |

#### 4.2.3 Lieferantenzertifizierungen

Jeder Lieferant kann mehrere Zertifizierungen (SupplierCertification) haben:

| Feld | Beschreibung |
|------|------|
| `cert_type` | Zertifizierungsart (z. B. ISO 9001, IATF 16949) |
| `cert_no` | Zertifikatsnummer |
| `issued_by` | Zertifizierungsstelle |
| `issue_date` | Ausstellungsdatum |
| `expiry_date` | Ablaufdatum |
| `file_url` | Pfad der Zertifikatsdatei |

#### 4.2.4 Massenimport

Lieferantendaten lassen sich per Excel importieren. Dabei prüft das System automatisch:
- Name (`name`) und Kurzname (`short_name`) sind Pflicht
- Doppelte Namen oder Kurznamen sind nicht erlaubt (auch gegenüber vorhandenen Datensätzen)
- Die Zeilenzahl je Import ist durch `MAX_IMPORT_ROWS` begrenzt

### 4.3 Lieferantenbewertung

#### 4.3.1 Punktebewertung

Die Lieferantenbewertung (SupplierEvaluation) nutzt gewichtete Punkte und wird je Bewertungszeitraum (`eval_period`, z. B. `2026-Q1`) erfasst:

**Dimensionen und Gewichte:**

| Dimension | Gewicht | Punktebereich |
|------|:---:|---------|
| Qualitätspunkte `quality_score` | 35% | 0–100 |
| Lieferpunkte `delivery_score` | 30% | 0–100 |
| Servicepunkte `service_score` | 15% | 0–100 |

**Abzüge (je höchstens 10 Punkte):**

| Abzug | Abzug je Einheit | Beschreibung |
|--------|:---:|------|
| `capa_count` | 2 Punkte je Fall | Anzahl CAPAs |
| `finding_count` | 3 Punkte je Fall | Anzahl Auditfeststellungen |
| `premium_freight_count` | 5 Punkte je Fall | Anzahl Eilfrachten |
| `customer_disruption_count` | 5 Punkte je Fall | Anzahl Lieferunterbrechungen beim Kunden |

**Berechnungsformel:**

```
base = quality_score × 0.35 + delivery_score × 0.30 + service_score × 0.15
total_score = max(0, base - capa_penalty - finding_penalty - premium_freight_penalty - customer_disruption_penalty)
```

#### 4.3.2 Einstufungskriterien

| Gesamtpunktzahl | Einstufung |
|:---:|:---:|
| ≥ 72 | A |
| ≥ 60 | B |
| ≥ 48 | C |
| < 48 | D |

#### 4.3.3 Bewertungsarten

`eval_type` umfasst:
- `periodic`: regelmäßige Bewertung (z. B. quartalsweise, jährlich)
- `event`: ereignisgesteuerte Bewertung (z. B. nach schwerem Qualitätsproblem)

### 4.4 Qualitäts-Dashboard der Lieferanten

**Route:** `/suppliers/quality`

Das Dashboard zeigt folgende KPIs:

| Kennzahl | Berechnung |
|------|---------|
| Anzahl Lieferanten | `COUNT(suppliers)` |
| Gesamt-PPM | `SUM(defect_qty) / SUM(lot_qty) × 1,000,000` |
| Losannahmequote | `COUNT(accepted) / COUNT(total)` |
| Offene SCARs | `COUNT(scars WHERE status != 'closed')` |

Außerdem:
- **Einstufungsverteilung**: Anzahl Lieferanten je Stufe A/B/C/D
- **PPM-Trend**: monatliche Entwicklung der PPM
- **Lieferantenranking**: absteigend nach Gesamtpunktzahl, Top 20 mit PPM, Losannahmequote, Liefertreue, offenen SCARs

**Details eines Lieferanten** (`/suppliers/quality/:supplierId`) zeigen zusätzlich:
- Punkte je Dimension und Gesamtpunktzahl der letzten Bewertung
- PPM- und Losannahme-Trend des Lieferanten
- SCAR-Statistik (gesamt und offen)

### 4.5 Lieferanten-SCAR

Mit SCAR (Supplier Corrective Action Request) werden Korrekturmaßnahmen beim Lieferanten angefordert:

| Feld | Beschreibung |
|------|------|
| `scar_no` | SCAR-Nummer (automatisch) |
| `source_type` | Quellart (z. B. `iqc`, `risk_alert`) |
| `source_id` | ID des Quelldatensatzes |
| `description` | Problembeschreibung |
| `requested_action` | Geforderte Maßnahmen |
| `supplier_response` | Antwort des Lieferanten |
| `status` | Status: `open` → `in_progress` → `closed` |
| `due_date` | Fälligkeitsdatum |

SCARs können automatisch durch IQC-Rückweisung oder Lieferanten-Risikowarnungen ausgelöst werden.

---

## 5. Lieferantenrisiko

### 5.1 Modulübersicht

**Frontend-Routen:**

| Route | Funktion |
|------|------|
| `/supplier-risk` | Risiko-Dashboard |
| `/supplier-risk/config` | Konfiguration der Risikoregeln |

Das Modul Lieferantenrisiko bewertet Lieferanten mehrdimensional anhand konfigurierbarer Risikoregeln, erzeugt automatisch Risikowarnungen und ist mit SCAR / CAPA gekoppelt.

### 5.2 Konfiguration der Risikoregeln

**Route:** `/supplier-risk/config`

Risikoregeln werden über SupplierRiskConfig verwaltet und unterstützen vier Prioritätsebenen:

| Priorität | Ebene | Beschreibung |
|:---:|------|------|
| 1 (höchste) | Lieferant + Produktlinie | `supplier_id` und `product_line_code` angegeben |
| 2 | Lieferant global | `supplier_id` angegeben, `product_line_code` leer |
| 3 | Standard der Produktlinie | `supplier_id` leer, `product_line_code` angegeben |
| 4 (niedrigste) | Globaler Standard | `supplier_id` und `product_line_code` leer |

Jede Regelkonfiguration enthält:

| Feld | Beschreibung |
|------|------|
| `rule_id` | Regelkennung (z. B. `R01`) |
| `enabled` | Aktiviert ja/nein |
| `thresholds` | Schwellenparameter (JSONB, z. B. `{"ppm_limit": 1000, "window_days": 90}`) |
| `weight` | Gewicht für die gewichtete Gesamtpunktzahl |
| `category` | Risikokategorie: `quality` (Qualität), `delivery` (Lieferung), `compliance` (Compliance) |
| `product_line_code` | Produktliniencode (leer = global) |
| `supplier_id` | Lieferanten-ID (leer = global) |

### 5.3 Ablauf der Risikobewertung

Die Risikobewertung hat zwei Modi:

1. **Einzelner Lieferant** (`POST /supplier-risk/evaluate/{supplier_id}`): erfordert EDIT
2. **Alle Lieferanten** (`POST /supplier-risk/evaluate`): erfordert APPROVE

Schritte:

```
1. Gültige Regelkonfiguration ermitteln (nach Priorität)
2. Daten erfassen:
   ├── IQC Prüfdatensätze (PPM, Losannahmequote)
   ├── SCAR Datensätze
   ├── Lieferantenbewertungen
   └── Zertifizierungen
3. Alle Regeln ausführen → Liste von RuleResult
4. Gewichtete Risikopunktzahl berechnen → RiskScore
5. Risikowarnung anlegen/aktualisieren → SupplierRiskAlert
6. Bei neuer oder eskalierter Hochrisiko-Warnung benachrichtigen
```

### 5.4 Risikopunktzahl und -stufen

**Bewertungsdimensionen:**

| Dimension | Datenquelle |
|------|---------|
| `quality_score` | IQC-Prüf-PPM, Losannahmequote |
| `delivery_score` | Liefertreue (ERP- oder Bewertungsdaten) |
| `compliance_score` | Ablauf von Zertifizierungen, Anzahl offener SCARs |

**Risikostufen:**

| Risikopunktzahl | Stufe | Beschreibung |
|:---:|:---:|------|
| — | `low` | Geringes Risiko, keine Warnung |
| — | `medium` | Mittleres Risiko |
| — | `high` | Hohes Risiko, Benachrichtigung |
| — | `critical` | Kritisches Risiko, Benachrichtigung |

### 5.5 Risikowarnungen

Eine Risikowarnung (SupplierRiskAlert) enthält:

| Feld | Beschreibung |
|------|------|
| `risk_level` | Risikostufe |
| `risk_score` | Gesamtrisikopunktzahl |
| `quality_score` / `delivery_score` / `compliance_score` | Punkte je Dimension |
| `rule_results` | Ergebnisse der ausgelösten Regeln (JSONB) |
| `alert_type` | Warnungsart: `initial` (erstmalig) / `escalated` (eskaliert) |
| `status` | Status: `open` / `acknowledged` / `resolved` |
| `handled_by` | Bearbeiter |
| `handle_note` | Bearbeitungsnotiz |
| `linked_scar_id` | Verknüpfte SCAR |
| `linked_capa_id` | Verknüpftes CAPA |

**Ereignisarten von Warnungen:**

| Ereignis | Beschreibung |
|------|------|
| `new` | Neu erzeugte Warnung |
| `escalated` | Warnung mit gestiegener Risikostufe |
| `unchanged` | Aktualisierung mit gleicher oder niedrigerer Stufe |

Warnungen werden nach `(supplier_id, product_line_code, snapshot_date)` dedupliziert; je Tag, Lieferant und Produktlinie bleibt nur die neueste.

### 5.6 Benachrichtigungskanäle

Benachrichtigungen werden über SupplierRiskNotificationChannel konfiguriert:

| Feld | Beschreibung |
|------|------|
| `channel_type` | Kanalart (z. B. `email`, `webhook`) |
| `config` | Kanalkonfiguration (JSONB, z. B. E-Mail-Adresse, Webhook-URL) |
| `min_risk_level` | Mindestrisikostufe für Benachrichtigungen, Standard `high` |
| `enabled` | Aktiviert ja/nein |

---

## 6. Risikokarte der Lieferkette

### 6.1 Modulübersicht

**Route:** `/supply-chain-risk-map`

Die Risikokarte der Lieferkette zeigt als Heatmap ein Gesamtbild der Risiken mehrerer Lieferanten über mehrere Dimensionen, mit Zeitachse und Lieferantenvergleich.

### 6.2 Daten-Snapshots

Eine zeitgesteuerte Aufgabe aggregiert die Risikobewertungen je Lieferant zu Snapshots (SupplyChainRiskSnapshot); jeder Snapshot enthält die Risikodaten eines Monats:

| Feld | Beschreibung |
|------|------|
| `supplier_id` | Lieferant |
| `product_line_code` | Produktlinie |
| `snapshot_period` | Snapshot-Monat (z. B. `2026-01`) |
| `risk_score` | Gesamtrisikopunktzahl |
| `risk_level` | Risikostufe |
| `quality_score` | Qualitätspunkte |
| `delivery_score` | Lieferpunkte |
| `compliance_score` | Compliance-Punkte |
| `erp_on_time_rate` | Liefertreue laut ERP |
| `erp_on_time_rate_source` | Datenquelle (`evaluation` / `erp`) |
| `purchase_amount_pct` | Anteil am Einkaufsvolumen |
| `delivery_delay_days` | Mittlere Verzugstage |
| `open_scar_count` | Anzahl offener SCARs |
| `ppm_value` | PPM-Wert |
| `dimensions` | Details je Dimension (JSONB) |

Snapshots werden über den eindeutigen Constraint `(supplier_id, product_line_code, snapshot_period)` gegen Duplikate geschützt (PostgreSQL `NULLS NOT DISTINCT`).

### 6.3 Heatmap

Die Heatmap ist die zentrale Visualisierung der Risikokarte mit folgenden Spalten (Dimensionen):

| Spaltenkennung | Typ | Polarität | Beschreibung |
|--------|------|------|------|
| `quality_score` | score | `higher_is_risk` | Qualitätsrisiko |
| `delivery_score` | score | `higher_is_risk` | Lieferrisiko |
| `compliance_score` | score | `higher_is_risk` | Compliance-Risiko |
| `risk_score` | risk | `higher_is_risk` | Gesamtrisikopunktzahl |
| `ppm_value` | number | `higher_is_risk` | PPM-Wert |
| `erp_on_time_rate` | percent | `lower_is_risk` | Liefertreue |
| `purchase_amount_pct` | percent | `neutral_exposure` | Einkaufsanteil |
| `open_scar_count` | count | `higher_is_risk` | Offene SCARs |

Jede Zelle enthält:
- `value`: Rohwert
- `risk_index`: normierter Risikoindex (0–100)
- `level`: Risikostufe (low/medium/high/critical)
- `diff`: Differenz zur Vorperiode (rot/grün für Verschlechterung/Verbesserung)
- `source`: Kennung der Datenquelle

### 6.4 Zeitachse

Über einen Zeitachsen-Schieberegler lassen sich historische Snapshots je Monat ansehen. Das System liefert die Liste verfügbarer Monate und kennzeichnet den aktuellen Monat.

### 6.5 Lieferantenvergleich

Nach Auswahl mehrerer Lieferanten ist ein Vergleich (Comparison) möglich, der die Risikoindizes je Dimension wie Qualität, Lieferung und Compliance gegenüberstellt.

### 6.6 Lieferantendetails

Ein Klick auf eine Lieferantenzeile der Heatmap öffnet ein Detailpanel mit:

- Rohwerten und Risikoindizes je Dimension im aktuellen Monat
- Trenddiagramm (monatliche Entwicklung von `risk_score`, `quality_score`, `delivery_score`, `compliance_score`)
- Kennzeichnung der Datenquelle (Bewertungsdaten vs. tatsächliche ERP-Daten)

### 6.7 Snapshot-Erzeugung

Snapshots werden manuell über `POST /supply-chain-risk-map/generate` oder automatisch über eine Hintergrundaufgabe erzeugt. Dabei:
1. werden alle Lieferanten im Status `approved` durchlaufen
2. werden die Datenquellen (IQC, Bewertung, ERP, SCAR usw.) zusammengefasst
3. werden die Risikopunkte je Dimension berechnet und als Snapshot gespeichert
4. wird die Differenz zur Vorperiode (`diff`) berechnet

### 6.8 Kennzeichnung der Datenquelle

Die Datenquelle jeder Kennzahl steht im Feld `source`:

| Wert | Beschreibung |
|----|------|
| `evaluation` | Aus Lieferantenbewertungen |
| `erp` | Aus ERP-Daten |
| `iqc` | Aus IQC-Prüfdaten |
| `scar` | Aus SCAR-Datensätzen |
| `calculated` | Aus anderen Kennzahlen berechnet |

Sind keine ERP-Daten verfügbar, greift das System auf Lieferantenbewertungen zurück (`erp_on_time_rate_source` = `evaluation`).

---

## 7. Häufige Fragen

### 7.1 IQC

**F: Wie wird der AQL beim Anlegen eines Prüfloses bestimmt?**

A: Das System bestimmt den AQL in dieser Reihenfolge:
1. Vom Benutzer angegebenes `aql_level` → direkt verwenden
2. `current_aql` des AQL-Profils von Lieferant + Material → Profilwert verwenden (auch im Status `frozen`)
3. `default_aql` der Materialstammdaten → Materialstandard verwenden
4. Nichts davon vorhanden → AQL-Felder bleiben leer

**F: Was unterscheidet Detail- und Schnellprüfung?**

A: Die Schnellprüfung (`quick`) erfasst Gesamtfehlerzahl und Entscheid direkt am Prüflos, für einfache Wareneingangsprüfungen. Die Detailprüfung (`detailed`) verknüpft eine Prüfvorlage, erzeugt automatisch mehrere Prüfmerkmale und erlaubt eigene Messdaten je Merkmal – für kritische Materialien mit Einzelnachweis.

**F: Wie fordere ich eine Wiederholungsprüfung an?**

A: Für entschiedene Prüflose (Status `accepted` oder `rejected`) ist eine Wiederholungsprüfung möglich. Das System legt ein neues Prüflos mit `re_inspection = True` an, `parent_inspection_id` zeigt auf das ursprüngliche Los. Ist das aktuelle AQL-Profil `normal`, wird automatisch eine Bewertung für verschärfte Prüfung ausgelöst.

### 7.2 Lieferantenmanagement

**F: Wonach richtet sich die Einstufung A/B/C/D?**

A: Grundlage ist die gewichtete Gesamtpunktzahl: Qualität (35 %) + Lieferung (30 %) + Service (15 %) = Basispunkte, abzüglich der Abzüge (CAPA, Auditfeststellungen, Eilfracht, Lieferunterbrechungen beim Kunden, je höchstens 10 Punkte). ≥72 ergibt A, ≥60 B, ≥48 C, <48 D.

**F: Wie werden Zertifizierungen verwaltet?**

A: Je Lieferant können mehrere Zertifizierungen mit Art, Nummer, Zertifizierungsstelle und Gültigkeit erfasst werden. Ablaufinformationen nutzt das Modul Lieferantenrisiko für die Compliance-Dimension.

**F: Welche Prüfregeln gelten beim Massenimport von Lieferanten?**

A: Name und Kurzname sind Pflicht; Namen und Kurznamen dürfen weder vorhandene Datensätze noch Einträge desselben Imports duplizieren; die Zeilenzahl je Import ist durch `MAX_IMPORT_ROWS` begrenzt. Für fehlgeschlagene Zeilen werden Fehlerdetails geliefert.

### 7.3 Lieferantenrisiko

**F: Wie funktioniert die Priorität der Risikoregeln?**

A: Vier Ebenen: Lieferant + Produktlinie > Lieferant global > Standard der Produktlinie > globaler Standard. Wirksam ist die Konfiguration mit der höchsten Priorität. Beispielsweise überschreibt ein für einen Lieferanten eigens gesetztes `ppm_limit = 400` den globalen Standard `1000`.

**F: Wann werden Risikobenachrichtigungen versendet?**

A: Nur unter diesen Bedingungen:
- Ereignisart `new` (neu erzeugt) oder `escalated` (Risikostufe gestiegen)
- Risikostufe `high` oder `critical`

Bei `unchanged` (gleiche Stufe) oder `low` (geringes Risiko) wird nicht benachrichtigt.

**F: Wie werden Risikowarnungen bearbeitet?**

A: Ablauf: `open` (offen) → `acknowledged` (bestätigt) → `resolved` (erledigt). Dabei kann eine Bearbeitungsnotiz (`handle_note`) erfasst und zur Nachverfolgung eine SCAR oder ein CAPA verknüpft werden.

### 7.4 Risikokarte der Lieferkette

**F: Was bedeuten die Kennzeichnungen der Datenquelle in der Heatmap?**

A: Das Feld `source` jeder Zelle nennt die Datenquelle:
- `evaluation`: aus Lieferantenbewertungen (manuell erfasste Punkte)
- `erp`: aus tatsächlichen ERP-Daten (z. B. Liefertreue)
- `iqc`: aus IQC-Prüfdaten (z. B. PPM)
- `scar`: aus SCAR-Datensätzen
- `calculated`: aus anderen Kennzahlen berechnet

Ohne ERP-Daten fällt die Liefertreue auf `delivery_score` der Lieferantenbewertung zurück; `erp_on_time_rate_source` ist dann `evaluation`.

**F: Wie werden doppelte Snapshots verhindert?**

A: Die Datenbank hat auf `(supplier_id, product_line_code, snapshot_period)` einen Constraint `UNIQUE NULLS NOT DISTINCT`. Ist `product_line_code` NULL, gelten NULL-Werte als gleich, sodass es je Lieferant und Monat nur einen globalen Snapshot gibt. Eine Neuerzeugung für denselben Monat überschreibt die alten Daten.

**F: Wie wird der Einkaufsanteil (`purchase_amount_pct`) berechnet?**

A: Das System holt aus den ERP-Daten das Einkaufsvolumen je Lieferant im Zeitfenster und berechnet den prozentualen Anteil am Gesamteinkauf. Die Polarität ist `neutral_exposure` (neutrales Exposure): Der Anteil selbst bedeutet kein hohes oder niedriges Risiko, ein hoher Anteil zeigt aber eine starke Abhängigkeit an, die beachtet werden sollte.

**F: Nach welchen Regeln werden die Heatmap-Farben vergeben?**

A: Die Zellfarbe ergibt sich aus `risk_index` (normierter Wert 0–100) und Polarität:
- `higher_is_risk`: je höher, desto riskanter, roter Verlauf (0 = grün, 100 = rot)
- `lower_is_risk`: je niedriger, desto riskanter, umgekehrter roter Verlauf (z. B. niedrige Liefertreue = hohes Risiko)
- `neutral_exposure`: neutrale Farbe, beachtenswert, aber nicht direkt als Risiko gewertet

Die Differenz (`diff`) zeigt mit rotem/grünem Dreieck Verschlechterung/Verbesserung gegenüber der Vorperiode.