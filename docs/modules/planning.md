# Modul Vorausplanung — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-11-03 (Schwerpunkt strukturierte Merkmale; andere Module nicht erneut abgenommen) | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Das Modul Vorausplanung deckt die gesamte Produktqualitätsvorausplanung (APQP) nach IATF 16949 ab – von der Risikoerkennung (FMEA) über Produktionslenkungsplan und PPAP-Einreichung bis zur Verwaltung besonderer Merkmale – und bildet so einen geschlossenen Planungskreislauf:

| Teilmodul | Route | ModuleKey | Funktionsumfang |
|--------|------|-----------|----------|
| FMEA | `/fmea`, `/fmea/:id`, `/fmea/pfmea-wizard/:id` | fmea | DFMEA/PFMEA anlegen, bearbeiten, freigeben, archivieren; PFMEA-Assistent nach 7 Schritten |
| Produktionslenkungsplan | `/control-plans`, `/control-plans/:id` | planning | Import aus PFMEA, Bearbeitung, Freigabe, Versionsverwaltung |
| APQP | `/apqp`, `/apqp/:id` | planning | Gate-Verwaltung in 5 Phasen, Verknüpfung von Ergebnissen |
| PPAP | `/ppap`, `/ppap/:id` | ppap | Einreichung, Freigabe, Zurückweisung und erneute Einreichung der 18 Elemente |
| Besondere Merkmale | `/special-characteristics`, `/special-characteristics/matrix`, `/special-characteristics/traceability`, `/special-characteristics/:id` | special_characteristic | CC/SC-Erkennung, Abdeckungsmatrix, Rückverfolgungsansicht, Kopplung FMEA→CP |

Die fünf Teilmodule sind über Datenverknüpfungen durchgängig rückverfolgbar: FMEA-Fehlerarten identifizieren besondere Merkmale (CC/SC), der Produktionslenkungsplan importiert Prozessschritte und Merkmale aus der PFMEA, APQP-Projekte verknüpfen FMEA, Produktionslenkungsplan und PPAP als Ergebnisse, und die Matrix besonderer Merkmale zeigt die vollständige Abdeckung FMEA→Produktionslenkungsplan→MSA.

---

## 2. Rollen und Berechtigungen

Das Berechtigungsmodell ist dreistufig: **ModuleKey × PermissionLevel × Rolle**. Bedeutung von PermissionLevel: 0 = NONE (unsichtbar), 1 = VIEW (nur lesen), 2 = CREATE (anlegen), 3 = EDIT (bearbeiten), 4 = APPROVE (freigeben/abschließen), 5 = ADMIN (Vollzugriff).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| fmea | 5 | 4 | 3 | 3 | 1 | 1 | 1 |
| planning | 5 | 4 | 1 | 3 | 1 | 0 | 1 |
| ppap | 5 | 4 | 0 | 3 | 3 | 0 | 1 |
| special_characteristic | 5 | 4 | 0 | 3 | 0 | 0 | 1 |

**Wichtige Operationen und Mindestberechtigung:**

| Operation | Modul | Erforderliche PermissionLevel |
|------|------|----------------------|
| FMEA/CP/APQP-Listen und -Details ansehen | fmea / planning | VIEW (1) |
| FMEA anlegen | fmea | CREATE (2) |
| FMEA-Graph bearbeiten | fmea | EDIT (3) |
| FMEA freigeben/archivieren | fmea | APPROVE (4) |
| Produktionslenkungsplan anlegen/bearbeiten | planning | CREATE (2) / EDIT (3) |
| Produktionslenkungsplan freigeben | planning | APPROVE (4) |
| APQP-Projekt anlegen, Gate einreichen | planning | CREATE (2) |
| APQP-Gate freigeben/zurückweisen | planning | APPROVE (4) |
| APQP-Projekt abbrechen | planning | ADMIN (5) |
| PPAP-Einreichungen ansehen | ppap | VIEW (1) |
| PPAP-Einreichung anlegen/bearbeiten | ppap | CREATE (2) / EDIT (3) |
| PPAP freigeben/zurückweisen | ppap | APPROVE (4) |
| Besondere Merkmale ansehen | special_characteristic | VIEW (1) |
| Besondere Merkmale anlegen/bearbeiten | special_characteristic | EDIT (3) |
| Freigabe von Sicherheitsmerkmalen | special_characteristic | APPROVE (4) |

---

## 3. FMEA

### 3.1 Grundbegriffe

OpenQMS folgt der Methodik des AIAG-VDA-FMEA-Handbuchs (1. Ausgabe, 2019), unterstützt die Typen **DFMEA** und **PFMEA** und speichert die Fehleranalysedaten in einem Graphmodell (Graph Model).

#### 3.1.1 Die 7 Schritte nach AIAG-VDA

| Schritt | Name | Beschreibung |
|:----:|------|------|
| 1 | Umfang (Scope) | Analyseumfang, Grenzen und Verantwortlichkeiten festlegen |
| 2 | Strukturanalyse (Structure Analysis) | Systemstrukturbaum / Prozessablauf aufbauen |
| 3 | Funktionsanalyse (Function Analysis) | Funktionen je Strukturelement festlegen |
| 4 | Fehleranalyse (Failure Analysis) | Fehlerarten, Fehlerfolgen und Fehlerursachen ermitteln |
| 5 | Risikoanalyse (Risk Analysis) | Bedeutung S, Auftreten O und Entdeckung D bewerten |
| 6 | Optimierung (Optimization) | Vermeidungs- und Entdeckungsmaßnahmen festlegen |
| 7 | Dokumentation der Ergebnisse (Results Documentation) | Schlussfolgerungen und Verbesserungsmaßnahmen festhalten |

#### 3.1.2 Graphmodell (Graph Model)

FMEA-Daten werden als JSONB-Graph im Feld `graph_data` gespeichert, im Format `{ nodes: [...], edges: [...] }`.

**DFMEA-Knotenkette:**
```
System → Subsystem → Component → Function → FailureMode → FailureEffect / FailureCause → Controls
```

**PFMEA-Knotenkette:**
```
ProcessItem → ProcessStep → ProcessWorkElement → ProcessStepFunction / ProcessWorkElementFunction → FailureMode → FailureEffect / FailureCause → Controls
```

**Kantentypen:**

| Kantentyp | Bedeutung |
|--------|------|
| `HAS_PROCESS_STEP` | Zugehörigkeit des Prozessschritts |
| `FUNCTION_MAPPED_TO` | Funktionszuordnung |
| `HAS_FAILURE_MODE` | Verknüpfung der Fehlerart |
| `EFFECT_OF` | Fehlerfolge |
| `CAUSE_OF` | Fehlerursache |
| `PREVENTED_BY` | Vermeidungsmaßnahme |
| `DETECTED_BY` | Entdeckungsmaßnahme |
| `OPTIMIZED_BY` | Optimierungsmaßnahme |

`fmeaTable.ts` im Frontend wandelt bidirektional zwischen Graphdaten und der Tabellenansicht mit 20+ Spalten um.

#### 3.1.3 Risikobewertung: RPN und AP

Das System unterstützt zwei Kennzahlen:

- **RPN (Risikoprioritätszahl)**: `RPN = S × O × D`, Wertebereich 1–1000
- **AP (Action Priority)**: nach der S×O×D-Matrix aus AIAG-VDA Anhang C, Ergebnis H (hoch), M (mittel), L (niedrig)

Die AP berechnet die Backend-Funktion `compute_ap()` streng nach Anhang C1.5 des AIAG-VDA-Handbuchs.

#### 3.1.4 Kennzeichnung besonderer Merkmale

FMEA-Knoten kennzeichnen besondere Merkmale über das Feld `classification`:

- **CC (Critical Characteristic)**: kritisches Merkmal
- **SC (Special Characteristic)**: wichtiges Merkmal
- Hat ein Knoten eine Bedeutung (severity) ≥ 9, markiert das System den CC-Knoten automatisch als sicherheitsrelevant (`is_safety_suggested = true`)

### 3.2 Abläufe

#### 3.2.1 FMEA anlegen

1. FMEA-Liste `/fmea` öffnen und auf „Neu“ klicken
2. Grunddaten eingeben:
   - **Titel**: Pflicht
   - **FMEA-Typ**: DFMEA oder PFMEA
   - **Produktlinie**: Standard `DC-DC-100`
   - **Verknüpfte DFMEA** (nur bei PFMEA wählbar)
3. Das System erzeugt automatisch eine Dokumentnummer (`PFMEA-2026-XXX` oder `DFMEA-2026-XXX`)
4. Der Anfangsstatus ist `draft`

> Nach dem Anlegen kann die Modellierung auch über den Einstieg „Assistent öffnen“ in der Liste mit dem 7-Schritte-Assistenten (siehe 3.2.4) erfolgen.

#### 3.2.2 FMEA-Graph bearbeiten

1. In der FMEA-Liste auf die Dokumentnummer klicken, um die Bearbeitungsseite `/fmea/:id` zu öffnen
2. Der Editor zeigt eine Tabellenansicht mit 20+ Spalten; jede Zeile entspricht einer Fehlerkette
3. Alle Knotenoperationen (anlegen/löschen/ändern) übermitteln beim Speichern das gesamte `graph_data`
4. RPN und AP werden automatisch berechnet

#### 3.2.3 Freigabe und Statusübergänge

Der Zustandsautomat der FMEA ist wie folgt definiert:

```
draft ──→ in_review ──→ approved ──→ archived
  │           │             │
  │           ↓             ↓
  │        rework ←────────┘
  │           │
  ↓           ↓
archived    in_review
```

| Aktueller Status | Erlaubte Zielstatus | Erforderliche Berechtigung |
|----------|---------------|----------|
| draft | in_review, archived | EDIT (3) |
| in_review | approved, rework | APPROVE (4) kann nach approved freigeben; EDIT (3) kann nach rework zurückgeben |
| approved | rework, archived | APPROVE (4) |
| rework | in_review | EDIT (3) |

> **Freigabebeschränkung**: Nur die Rollen `admin` und `manager` können eine FMEA in den Status `approved` bringen.

#### 3.2.4 Erzeugungsassistent nach 7 Schritten

PFMEA und DFMEA bieten geführte Assistenten, die die 7 Schritte nach AIAG-VDA in schrittweise abzuarbeitende Interaktionen zerlegen und den manuellen Modellierungsaufwand senken.

**PFMEA-Assistent** (`/fmea/pfmea-wizard/:id`):

| Schritt | Name | Inhalt |
|:----:|------|------|
| 0 | Umfang | 5T-Werkzeug-/Trend-Tags + Zeitraum + Umfangsgrenzen |
| 1 | Strukturanalyse | Baum aus Prozesselementen / Arbeitsgängen / Arbeitselementen in `PFMEAWizardSidebar`; Sortieren des Strukturbaums per Drag & Drop (`@dnd-kit`) |
| 2 | Funktionsanalyse | Dreistufiger Funktionsbaum in `FunctionTreeEditor` + Kanten `FUNCTION_MAPPED_TO` + CC/SC-Kennzeichnung |
| 3 | Fehleranalyse | Fehlerkette FE-FM-FC an der ProcessStepFunction im 4M-Kontext (Mensch/Maschine/Material/Methode) |
| 4 | Risikoanalyse | `RiskTable`: severity als Maximum der Ebenen, CC/SC schreibgeschützt aggregiert, O/D-Gates; Kontext aus Schritt 4 vorab |
| 5 | Optimierung | Für Fehlerarten mit AP=H werden automatisch Maßnahmen vorgeschlagen; PC/DC vor dem Anlegen |
| 6 | Dokumentation der Ergebnisse | Abschluss-Gate (`usePfmeaWizardValidation`: 4M/OP-Gates, dreistufige Bedeutung, CC/SC-bewusst) |

Der Assistent enthält ein kaskadierendes Löschen (`wizardCascadeDelete`); beim Löschen gemeinsamer Maßnahmenknoten wird geprüft, ob andere Zeilen sie noch referenzieren.

Erweiterungen des **DFMEA-Assistenten**: Zeitraum als `DatePicker.RangePicker`; 5T-Werkzeuge/-Trends per KI-Empfehlung (Auslöser `pfmea_tool` / `pfmea_trend` + 4M-Regelinhalte); KI-Empfehlungen in Schritt 3 (`SmartSuggestionDropdown` an Backend-Auslösern); Risikoanalyse in Schritt 5 mit Kontext aus Schritt 4 und PC/DC vor dem Anlegen; KI-Empfehlungen für PC/DC; Strukturleitfaden `ToolStructureGuide`.

> **Berechtigung**: Schreibvorgänge des Assistenten erfordern `EDIT (3)` im Modul `fmea`; die Liste bietet „Assistent öffnen“ nur für Dokumente im Status `draft`.

#### 3.2.5 FMEA löschen

Nur FMEA-Dokumente im Status `draft` und `rework` können gelöscht werden:

- Die Liste (`FMEAListPage`) zeigt die Schaltfläche Löschen nur für diese Status
- Statusschutz im Backend: andere Status als `draft` / `rework` liefern 400 mit dem Hinweis, dass nur FMEAs im Entwurfs- oder Überarbeitungsstatus gelöscht werden können
- Vor dem Löschen setzt `_null_out_fmea_references` die FMEA-Fremdschlüssel verknüpfter Datensätze (`control_plan`, `capa_eightd` usw.) auf NULL, damit Fremdschlüssel-Constraints kein `IntegrityError` → 500 auslösen
- Das Löschen wird im Audit-Log erfasst

> **Berechtigung**: Löschen erfordert `EDIT (3)` im Modul `fmea`; freigegebene/archivierte Dokumente können nicht gelöscht werden und müssen zuerst nach `rework` zurückgegeben werden.

### 3.3 Versionsverwaltung

FMEAs unterstützen Versions-Snapshots: Bei jeder Freigabe entsteht automatisch ein Versionsdatensatz (Tabelle `fmea_versions`) mit:

- **Haupt- und Nebenversion** (z. B. 1.0, 1.1)
- **Vollständigem Graph-Snapshot** (`snapshot` JSONB)
- **SHA-256-Hash** (`sha256_hash`) zur Integritätsprüfung
- **Änderungszusammenfassung und -art** (`change_summary`, `change_type`)

**Schreibgeschützte Ansicht von Versions-Snapshots**: In der Versionshistorie oben im Editor lässt sich jede frühere Version im Nur-Lese-Modus ansehen (Zustand `viewingVersion`, Komponente `FMEAVersionSnapshot`); der Graph dieser Version wird vollständig wiederhergestellt, ohne den bearbeitbaren aktuellen Stand zu beeinflussen. Der Editor des Produktionslenkungsplans bietet entsprechend `CPVersionSnapshot`.

### 3.4 Verknüpfung FMEA und Produktionslenkungsplan

- Beim Anlegen eines Produktionslenkungsplans kann eine FMEA verknüpft werden (`fmea_ref_id`)
- Abgeleitet wird aus dem vom Benutzer ausdrücklich gewählten, tatsächlich freigegebenen PFMEA-Versions-Snapshot, nicht aus dem aktuellen Überarbeitungsgraphen. Je Merkmal eine Zeile: derselbe Schritt mit 2 Produkt- und 3 Prozessmerkmalen ergibt 5 Zeilen, kein kartesisches Produkt.
- Strukturknoten hängen Funktionen über `HAS_FUNCTION` an, `Function.characteristics[]` speichert die Merkmale. Funktionen eines Schritts sind product, Funktionen eines Arbeitselements process.
- `step_no/process_name` stammen aus dem tatsächlichen Schritt; `equipment` aus dem Arbeitselement; Name, Spezifikation und besondere Klassifizierung jeweils aus dem zugehörigen Merkmal – Messaktivitäten werden nicht als Objekt behandelt.

---

## 4. Produktionslenkungsplan

### 4.1 Überblick

Der Produktionslenkungsplan (Control Plan) ist das zentrale Ergebnis der APQP-Phase 3 und legt Lenkungsmethoden, Spezifikationen, Stichproben und Reaktionspläne für Produkt und Prozess fest.

### 4.2 Datenmodell

Der Produktionslenkungsplan besteht aus Kopf (`ControlPlan`) und Zeilen (`ControlPlanItem`):

**Kopffelder:**

| Feld | Beschreibung |
|------|------|
| document_no | Dokumentnummer, Format `CP-2026-XXX` |
| title | Titel |
| fmea_ref_id | Verknüpftes FMEA-Dokument |
| source_fmea_version_id | Verknüpfter FMEA-Versions-Snapshot |
| phase | Phase: `prototype` (Prototyp), `pre_launch` (Vorserie), `production` (Serie, Standard) |
| part_no / part_name | Teilenummer/-name |
| drawing_rev | Zeichnungsstand |
| org_factory | Verantwortliches Werk/Organisation |
| core_group | Kernteam |
| contact_info | Kontaktdaten |
| customer_requirements | Kundenanforderungen (JSONB) |
| status | Status: `draft` / `approved` |
| version | Versionsnummer |
| lock_version | Version für optimistische Sperre |

**Zeilenfelder:**

| Feld | Beschreibung |
|------|------|
| step_no | Prozessnummer |
| process_name | Prozessname |
| equipment | Anlage |
| product_characteristic | Produktmerkmal |
| process_characteristic | Prozessmerkmal |
| special_class | Klassifizierung besonderer Merkmale (CC/SC) |
| specification_tolerance | Spezifikation/Toleranz |
| evaluation_method | Bewertungsmethode |
| sample_size / sample_frequency | Stichprobenumfang/-häufigkeit |
| control_method | Lenkungsmethode |
| reaction_plan | Reaktionsplan |
| source_fmea_node_id | ID des Quell-FMEA-Knotens |
| item_source | Quellkennzeichen (`fmea` oder `manual`) |
| sop_ref | Nummer der Arbeitsanweisung |
| spc_chart_id | Verknüpfte SPC-Regelkarte |
| gauge_id | Verknüpftes Prüfmittel |

### 4.3 Import aus PFMEA

1. Im Entwurf auf „Aus PFMEA importieren“ klicken, eine PFMEA und einen historischen Snapshot ab v1.0 mit `change_type=approve` wählen, dann die Arbeitsgänge des Snapshots (`step_ids`).
2. Es entsteht eine schreibgeschützte Vorschau; Vorschau/Bestätigung binden `source_fmea_version_id`, `expected_lock_version` und `preview_digest`, die Bestätigung sendet `selected_candidate_keys`. Ein candidate_key unterscheidet verschiedene Lenkungszeilen derselben Quelle; stattdessen nackte Zeilen-UUIDs zu senden ist nicht zulässig.
3. Jedes Merkmal ergibt eine eigene CP-Zeile; die vollständige source_characteristic_ref ist serverseitige Nur-Lese-Metadaten (Dokument/Arbeitsgang/Funktion/Arbeitselement/Merkmals-UUID/mapping_version/accepted_source_version_id). Die Allowlist normaler Bearbeitung schreibt sie nicht zurück.
4. Nach Freigabe einer neuen Version meldet die dauerhafte CP-Outbox pending; Vorschau und Annahme erfolgen ausdrücklich. Ein 409 macht die alte Vorschau ungültig, ohne automatischen Neuversuch; eine Teilannahme bleibt pending, eine erneute Bestätigung braucht eine ausdrücklich neue Vorschau. Zeilen-UUIDs und manuelle Felder zu Methode/Stichprobe/Reaktion bleiben erhalten; unveränderte Zeilen erhalten keine künstliche neue Annahmeversion, erst bei vollständiger Abdeckung wird das source_fmea_version_id des Dokuments fortgeschrieben.
5. Wirksames Material aktiver CAPAs, Ausführungs-/SC-Referenzen, Konflikte und alte gemischte Zeilen werden konservativ geschützt und nicht automatisch gelöscht oder als erledigt markiert; diese Funktion schafft keinen neuen Überarbeitungspfad für freigegebene Produktionslenkungspläne.

> **Einschränkung**: Nur Dokumente vom Typ PFMEA können in Produktionslenkungspläne importiert werden; in freigegebene Produktionslenkungspläne kann nicht importiert werden.

### 4.4 Freigabe

Ablauf der Freigabe des Produktionslenkungsplans:

1. Status von `draft` → `approved`
2. Bei der Freigabe führt das System automatisch eine **Prüfmittelprüfung** aus: Alle verknüpften Prüfmittel müssen aktiv und innerhalb der gültigen Kalibrierung sein
3. Nach der Freigabe entsteht automatisch ein Versions-Snapshot (Tabelle `control_plan_versions`)
4. Der Versions-Snapshot enthält:
   - Snapshot des Kopfs (`header_snapshot`)
   - Snapshot der Zeilen (`items_snapshot`)
   - SHA-256-Hash (`sha256_hash`)
   - ID der verknüpften FMEA-Version (`source_fmea_version_id`)

> **Freigaberecht**: Nur die Rollen `admin` und `manager` können Produktionslenkungspläne freigeben.

### 4.5 Prüf-Engine für Produktionslenkungspläne

Das System enthält eine Prüf-Engine (`CPValidationEngine`) mit automatischer und manueller Auslösung:

- **Auslöser**: `manual` (manuell), `auto_on_save` (beim Speichern), `fmea_change` (bei FMEA-Änderung)
- **Prüfergebnisse**: jede Regel liefert error / warning / info
- **Prüfdatensätze**: gespeichert in den Tabellen `cp_validation_runs` und `cp_validation_findings`

Status eines Prüflaufs:

| Status | Beschreibung |
|------|------|
| running | Prüfung läuft |
| completed | Prüfung abgeschlossen |
| failed | Prüfung fehlerhaft |

---

## 5. APQP

### 5.1 Überblick

APQP (Advanced Product Quality Planning, Produktqualitätsvorausplanung) ist ein von IATF 16949 gefordertes Projektmanagement-Rahmenwerk, das sicherstellt, dass die Neuproduktentwicklung die Kundenanforderungen erfüllt.

### 5.2 Gate-Modell mit fünf Phasen

| Phase | Name | Wichtige Ergebnisse | Ergebnisprüfung |
|:----:|------|-----------|-----------|
| 1 | Planen und Definieren (Plan & Define) | Projektplan, Zielsetzung | Keine Pflichtprüfung |
| 2 | Produktdesign und -entwicklung (Product Design & Development) | DFMEA | DFMEA muss verknüpft sein |
| 3 | Prozessdesign und -entwicklung (Process Design & Development) | PFMEA, Produktionslenkungsplan | PFMEA und Produktionslenkungsplan müssen verknüpft sein |
| 4 | Produkt- und Prozessvalidierung (Product & Process Validation) | PPAP | PPAP-Einreichung muss verknüpft sein |
| 5 | Rückmeldung, Bewertung und Korrekturmaßnahmen (Feedback & Corrective Action) | Projektabschluss | Nach Abschluss von Phase 5 wird das Projekt als completed markiert |

> **Ergebnisprüfung**: Bei der Gate-Freigabe prüft das System, ob die aktuelle Phase die nötigen Ergebnisse verknüpft hat. Andernfalls wird die Freigabe abgelehnt.

### 5.3 Datenmodell

**Wichtige Felder von APQPProject:**

| Feld | Beschreibung |
|------|------|
| project_code | Projektnummer, Format `APQP-2026-XXX` |
| project_name | Projektname |
| product_name | Produktname |
| product_line_code | Produktliniencode |
| customer_name | Kundenname |
| target_sop_date | Ziel-SOP-Datum |
| team_members | Teammitglieder (JSONB) |
| current_phase | Aktuelle Phase (1–5) |
| phase_status | Phasenstatus: `in_progress` / `pending_approval` / `completed` |
| project_status | Projektstatus: `active` / `completed` / `cancelled` |
| dfmea_id / pfmea_id / control_plan_id / ppap_submission_id | Verknüpfte Ergebnisse |

### 5.4 Statusübergänge der Gates

```
in_progress ──submit_gate──→ pending_approval ──approve_gate──→ next phase (in_progress)
                                │
                                ├──reject_gate──→ in_progress
                                │
                                └──(phase 5 approve)──→ completed

In jeder Phase möglich cancel ──→ cancelled
```

| Aktion | Erforderlicher aktueller Status | Zielstatus | Erforderliche Berechtigung |
|------|-------------|---------|----------|
| submit_gate | in_progress | pending_approval | CREATE (2) |
| approve_gate | pending_approval | Nächste Phase in_progress oder completed | APPROVE (4) |
| reject_gate | pending_approval | in_progress | APPROVE (4) |
| cancel | Beliebig | cancelled | ADMIN (5) |

### 5.5 Gate-Historie

Jede Gate-Aktion wird im JSONB-Feld `gate_history` erfasst:

```json
{
  "phase": 2,
  "action": "approve",
  "user_id": "...",
  "user_name": "...",
  "comments": "DFMEA Freigabe abgeschlossen",
  "timestamp": "2026-06-13T08:30:00Z"
}
```

### 5.6 Projektlebenszyklus

```
Projekt anlegen (active, phase 1) 
  → Phase 1 abschließen → Gate einreichen → Freigabe → nächste Phase 2
    → DFMEA verknüpfen → Phase 2 abschließen → Gate einreichen → Freigabe → nächste Phase 3
      → PFMEA + Produktionslenkungsplan verknüpfen → Phase 3 abschließen → Gate einreichen → Freigabe → nächste Phase 4
        → PPAP verknüpfen → Phase 4 abschließen → Gate einreichen → Freigabe → nächste Phase 5
          → Phase 5 abschließen → Gate einreichen → Freigabe → Projekt completed
```

---

## 6. PPAP

### 6.1 Überblick

PPAP (Production Part Approval Process, Produktionsteil-Abnahmeverfahren) ist das Standardverfahren, mit dem Lieferanten in der Automobilindustrie dem Kunden ihre Prozessfähigkeit nachweisen. OpenQMS verwaltet PPAP-Einreichungen der Level 1–5 und deckt die 18 von AIAG festgelegten Elemente ab.

### 6.2 PPAP-Vorlagestufen

| Stufe | Beschreibung | Einsatzbereich |
|:----:|------|---------|
| 1 | Nur Teilevorlagebestätigung (PSW) | Nach Kundenvorgabe |
| 2 | PSW + Muster | Nach Kundenvorgabe |
| 3 | PSW + Muster + vollständige Daten | Erstvorlage neuer Teile (Standard) |
| 4 | PSW + vollständige Daten (ohne Muster) | Konstruktionsänderung |
| 5 | Keine Einreichung, nur Aufbewahrung am Fertigungsstandort | Schriftliche Genehmigung des Kunden |

### 6.3 Die 18 Vorlageelemente

| Nr. | Element | Englische Bezeichnung |
|:----:|---------|---------|
| 1 | Konstruktionsunterlagen | Design Records |
| 2 | Dokumente zu technischen Änderungen | Authorized Engineering Change Documents |
| 3 | Technische Freigabe des Kunden | Customer Engineering Approval |
| 4 | Design-FMEA | Design FMEA |
| 5 | Prozessablaufdiagramm | Process Flow Diagrams |
| 6 | Prozess-FMEA | Process FMEA |
| 7 | Produktionslenkungsplan | Control Plan |
| 8 | Messsystemanalyse | Measurement System Analysis |
| 9 | Maßliche Ergebnisse | Dimensional Results |
| 10 | Material-/Leistungsprüfergebnisse | Material / Performance Test Results |
| 11 | Vorläufige Prozessfähigkeitsuntersuchung | Initial Process Studies |
| 12 | Dokumentation qualifizierter Labore | Qualified Laboratory Documentation |
| 13 | Bericht zur Freigabe des Erscheinungsbilds | Appearance Approval Report |
| 14 | Musterteile | Sample Production Parts |
| 15 | Prüfmittel | Checking Aids |
| 16 | Kundenspezifische Anforderungen | Customer-Specific Requirements |
| 17 | Teilevorlagebestätigung (PSW) | Part Submission Warrant — PSW |
| 18 | Checkliste für Schüttgutanforderungen | Bulk Material Requirements Checklist |

Jedes Element enthält: `required` (Pflicht ja/nein), `status` (pending / approved / rejected), `file_url` (Anhang), `notes` (Notizen).

### 6.4 Lebenszyklus einer PPAP-Einreichung

```
draft ──submit──→ under_review ──approve──→ approved
                      │
                      └──reject──→ rejected ──resubmit──→ under_review
```

| Aktion | Aktueller Status | Zielstatus | Erforderliche Berechtigung | Zusätzliche Bedingungen |
|------|---------|---------|----------|---------|
| submit | draft | under_review | CREATE (2) | submission_date wird automatisch gesetzt |
| approve | under_review | approved | APPROVE (4) | Alle Pflichtelemente müssen approved sein |
| reject | under_review | rejected | APPROVE (4) | Zurückweisungsgrund ist Pflicht |
| resubmit | rejected | under_review | CREATE (2) | revision wird um 1 erhöht |

### 6.5 Datenmodell

**Wichtige Felder von SupplierPPAPSubmission:**

| Feld | Beschreibung |
|------|------|
| ppap_no | PPAP-Nummer, Format `PPAP-2026-XXX` |
| supplier_id | Lieferanten-ID |
| part_no / part_name | Teilenummer/-name |
| submission_level | Vorlagestufe (1–5) |
| submission_date | Einreichungsdatum |
| status | Status: draft / under_review / approved / rejected |
| revision | Revisionsnummer |
| rejection_reason | Zurückweisungsgrund |
| customer_name | Kundenname |
| product_line_code | Produktliniencode |

> **Freigaberegel**: Bei der Freigabe prüft das System, ob alle Elemente mit `required=True` `approved` sind; sonst wird die Freigabe abgelehnt.

---

## 7. Besondere Merkmale

### 7.1 Überblick

Die Verwaltung besonderer Merkmale erkennt, klassifiziert und verfolgt CC (Critical Characteristic, kritisches Merkmal) und SC (Special Characteristic, wichtiges Merkmal) und stellt die vollständige Abdeckung von FMEA über Produktionslenkungsplan bis MSA sicher.

### 7.2 Arten besonderer Merkmale

| Art | Kürzel | Beschreibung |
|------|:----:|------|
| Kritisches Merkmal | CC | Merkmal mit Einfluss auf Produktsicherheit/Einhaltung gesetzlicher Vorgaben |
| Wichtiges Merkmal | SC | Merkmal mit Einfluss auf Funktion/Qualität, aber nicht sicherheitsrelevant |

### 7.3 Erkennung besonderer Merkmale

1. **Synchronisation aus FMEA**: Neue strukturierte Quellen werden nur über ausdrückliches CC/SC in `characteristics[].classification` extrahiert; kind, Spezifikation und Einheit sind unabhängig; nicht klassifizierte Einträge oder [] werden weder nach Funktionsklassifizierung noch nach Bedeutung automatisch hochgestuft. Nur alte Graphen ohne Merkmalsmenge nutzen weiterhin die bisherigen Vorschlagsregeln über classification/severity des Knotens; diese Kompatibilität ist keine allgemeine Erkennungsregel für neue Quellen.
2. **Manuelles Anlegen**: direkt in der Liste besonderer Merkmale

#### 7.3.1 Logik der FMEA-Synchronisation

`sync_from_fmea` extrahiert neue strukturierte Quellen nach FMEA-Dokument + Merkmals-UUID; kind, classification und specification sind unabhängig. Ausdrückliche Arrays (auch []) haben Vorrang, nicht klassifizierte Einträge werden weder nach Funktionsklassifizierung noch nach Bedeutung hochgestuft; fehlen Arrays, werden alte Graphen weiterhin nach den Kompatibilitätsregeln gelesen, ohne Massenmigration. Umbenennungen behalten die Identität; DFMEA-Elternmerkmale werden nicht anhand gleicher Namen automatisch angelegt.

Material, Identität, Quellbindung und Freigabestatus von Sicherheits-SCs im Status submitted/approved werden nicht automatisch geändert oder gelöscht; Quelländerungen lösen nur einen Prüfhinweis aus. Der automatische CP-Einstieg neuer Quellen verfolgt nur schreibgeschützt exakt zurück und führt zur Synchronisation formaler Versionen, ohne freigegebene Produktionslenkungspläne oder manuelle Inhalte zu überschreiben. Die Rückverfolgung leitet aus vollständiger source_ref + RequestScope alle passenden Zeilen ab, nicht nur die letzte cp_item_id; ohne tatsächliche SPC-/Prüfmittel-/MSA-Studienergebnisse im selben Bereich wird „fehlt“ angezeigt, ein gecachtes PASS gilt nicht als Nachweis.

**Offene Folgepunkte**: Der Sicherheitsschutz für Aktualisierung/Löschen alter manueller SCs und der Fehler im allgemeinen create-Audit sind mit dieser Funktion nicht behoben; der Schutz der automatischen Synchronisation ist keine Zertifizierung eines globalen Sicherheitsprozesses.

### 7.4 Freigabeablauf für Sicherheitsmerkmale

Bei `is_safety_suggested = true` oder `is_safety_related = true` ist eine Sicherheitsfreigabe nötig:

```
pending ──submitted──→ submitted ──approved──→ approved ──(Neu bewerten)──→ pending
                          │
                          └──rejected──→ rejected ──(Erneut einreichen)──→ submitted
```

| Status | Beschreibung | Mögliche Aktionen |
|------|------|-----------|
| pending | Einzureichen | Zur Freigabe einreichen (submit) |
| submitted | Eingereicht | Freigeben (approve) oder zurückweisen (reject) |
| approved | Freigegeben | Nach Änderung zurück auf pending zur Neubewertung |
| rejected | Zurückgewiesen | Erneut einreichen (submit) |

> **Freigaberecht für Sicherheitsmerkmale**: Nur die Rollen `admin` und `manager` können Sicherheitsmerkmale freigeben.

Zusatzfelder von Sicherheitsmerkmalen:

| Feld | Beschreibung |
|------|------|
| is_safety_related | Sicherheitsmerkmal ja/nein |
| is_safety_suggested | Vom System als Sicherheitsmerkmal vorgeschlagen (CC mit severity ≥ 9) |
| safety_approval_status | Status der Sicherheitsfreigabe |
| safety_regulation_ref | Rechtsgrundlage |
| safety_verification_method | Verifizierungsmethode |
| safety_approval_comment | Freigabekommentar |

### 7.5 Abdeckungsmatrix

Die Seite Abdeckungsmatrix (`/special-characteristics/matrix`) zeigt die Abdeckung besonderer Merkmale in FMEA, Produktionslenkungsplan und MSA:

- **Zeilen**: je besonderes Merkmal
- **Spalten**: FMEA-Knoten, Zeilen des Produktionslenkungsplans, MSA-Studien
- **Kennzeichnung**: abgedeckt ✓ / nicht abgedeckt ✗

Prüflogik der Abdeckung:
- Ist das Merkmal mit einem FMEA-Knoten verknüpft (`source_fmea_id` + `source_node_id`)
- Ist das Merkmal mit einer Zeile des Produktionslenkungsplans verknüpft (`cp_item_id`)
- Ist das Merkmal mit einer MSA-Studie verknüpft (`msa_study_id`) und deren Status

### 7.6 Rückverfolgungsansicht

Die Seite Rückverfolgbarkeit (`/special-characteristics/traceability`) bietet die durchgängige Kette FMEA → besonderes Merkmal → Produktionslenkungsplan → MSA:

```
DFMEA Fehlerartknoten
  └→ Besondere Merkmale (SC/CC)
      └→ Zeile des Produktionslenkungsplans (ControlPlanItem)
          └→ MSA Studie (GRG/Linearity/Stability)
```

Die Rückverfolgungsansicht unterstützt:
- Filter nach Produktlinie
- Filter nach Merkmalsart (CC/SC)
- Nur sicherheitsrelevante Merkmale
- Nur Sicherheitsmerkmale mit offener Freigabe

### 7.7 Nummerierung besonderer Merkmale

Das System erzeugt Codes automatisch im Format `SC-{Jahr}-{Nummer}`, z. B. `SC-2026-001`.

### 7.8 Kopplung FMEA → Produktionslenkungsplan

Die Kopplung besonderer Merkmale zwischen FMEA und Produktionslenkungsplan erfolgt über:

1. **FMEA-Kennzeichnung**: neue Quellen über `characteristics[].classification`, das alte Function.classification nur zur Kompatibilität
2. **Synchronisation zu besonderen Merkmalen**: „Aus FMEA synchronisieren“ legt `SpecialCharacteristic`-Datensätze an bzw. aktualisiert sie automatisch
3. **Import in den Produktionslenkungsplan**: Bei „Aus PFMEA importieren“ übernimmt das Feld `special_class` der Zeile automatisch die Klassifizierung des zugehörigen Merkmals
4. **Manuelle Verknüpfung**: In den Details eines besonderen Merkmals kann eine Zeile des Produktionslenkungsplans (`cp_item_id`) manuell verknüpft werden

---

## 8. Häufige Fragen

### 8.1 FMEA

**F: Ändert sich die Versionsnummer, wenn eine freigegebene FMEA zur Überarbeitung zurückgegeben wird?**

A: Bei der Freigabe entsteht automatisch ein Versions-Snapshot (z. B. 1.0). Nach Rückgabe auf rework und erneuter Freigabe entsteht ein neuer Haupt-Snapshot (z. B. 2.0). Die Versionshistorie ist auf der Detailseite einsehbar.

**F: Kann eine freigegebene FMEA bearbeitet werden?**

A: Eine freigegebene (approved) FMEA kann nicht direkt bearbeitet werden; sie muss zuerst auf rework zurückgesetzt und nach der Bearbeitung erneut freigegeben werden.

**F: Können DFMEA und PFMEA verknüpft werden?**

A: Beim Anlegen einer PFMEA kann eine DFMEA verknüpft werden. Neue Quellen legen Eltern-Kind-Beziehungen besonderer Merkmale nicht anhand gleicher Namen automatisch an; bestehende ausdrückliche Elternbeziehungen bleiben erhalten.

**F: Wie wird die AP berechnet?**

A: Das System berechnet die Action Priority streng nach der S×O×D-Matrix in Anhang C1.5 des AIAG-VDA-FMEA-Handbuchs. Bei S=9–10 ist die Priorität höher; bei S=1–3 überschreitet die AP selbst bei hohem O und D nicht M. Die vollständige Tabelle zeigt die AP-Abfrage im FMEA-Editor.

### 8.2 Produktionslenkungsplan

**F: Hat der Produktionslenkungsplan nur die Status draft und approved?**

A: Ja. Derzeit gibt es nur `draft` und `approved`. Nach der Freigabe ist keine Bearbeitung mehr möglich; für Änderungen wird eine neue Version angelegt.

**F: Können importierte Zeilen manuell geändert werden?**

A: Ja. Importierte Zeilen sind mit `item_source = "fmea"` gekennzeichnet, lassen sich aber manuell ändern. Zusätzliche Zeilen können manuell ergänzt werden (`item_source = "manual"`).

**F: Was tun, wenn die Prüfmittelprüfung bei der Freigabe fehlschlägt?**

A: Vor der Freigabe prüft das System alle verknüpften Prüfmittel. Ist ein Prüfmittel nicht aktiv oder außerhalb der gültigen Kalibrierung, wird die Freigabe abgelehnt. Zuerst die Kalibrierdaten aktualisieren oder die ungültige Prüfmittelverknüpfung entfernen.

**F: Wie hängen Versionen von Produktionslenkungsplan und FMEA zusammen?**

A: source_fmea_version_id des Dokuments zeigt die vollständig abgedeckte Synchronisationsverfolgung; accepted_source_version_id in der source_characteristic_ref jeder Zeile zeigt den tatsächlich angenommenen freigegebenen Snapshot dieser Zeile. Bei teilweiser Synchronisation ersetzt das Dokumentfeld nicht die Basis der einzelnen Zeilen.

### 8.3 APQP

**F: Bei der Gate-Freigabe erscheint „DFMEA muss verknüpft sein“ – was tun?**

A: Die Gate-Freigabe von Phase 2 verlangt ein nicht leeres `dfmea_id`. Im Projekt eine DFMEA im Status approved verknüpfen und dann erneut einreichen.

**F: Kann eine Phase übersprungen werden?**

A: Nein. Das APQP-Gate-Modell verlangt die strikte Reihenfolge 1 → 2 → 3 → 4 → 5. Erst nach Freigabe der aktuellen Phase geht es weiter.

**F: Können abgebrochene APQP-Projekte wiederhergestellt werden?**

A: Derzeit nicht. Der Abbruch (cancel) ist ein Endstatus und nur Administratoren vorbehalten. Vor dem Abbruch bitte bestätigen.

**F: Welches Format hat die APQP-Projektnummer?**

A: Automatisch erzeugt im Format `APQP-2026-XXX`; das Jahr ist das aktuelle Jahr, die Nummer wird hochgezählt.

### 8.4 PPAP

**F: Bei der PPAP-Freigabe erscheint „nicht freigegebene Pflichtelemente vorhanden“ – was tun?**

A: Die PPAP-Freigabe verlangt, dass alle Elemente mit `required=True` `approved` sind. Die Elemente einzeln prüfen und freigeben, dann die Gesamtfreigabe der PPAP einreichen.

**F: Kann eine zurückgewiesene PPAP erneut eingereicht werden?**

A: Ja. Eine PPAP im Status rejected kehrt nach resubmit in den Status under_review zurück, revision (Revisionsnummer) wird automatisch um 1 erhöht.

**F: Wie wird die Vorlagestufe gewählt?**

A: Die Vorlagestufe bestimmt der Kunde. Level 3 ist der häufigste Standard (Erstvorlage neuer Teile), Level 1 gilt, wenn der Kunde nur das PSW verlangt, Level 5, wenn der Kunde schriftlich auf eine Einreichung verzichtet.

**F: Welches Format hat die PPAP-Nummer?**

A: Automatisch erzeugt im Format `PPAP-2026-XXX`.

### 8.5 Besondere Merkmale

**F: Kann die Kennzeichnung als Sicherheitsmerkmal bei Knoten mit severity ≥ 9 wieder aufgehoben werden?**

A: Sicherheitsmerkmale (`is_safety_related = true`) werden durch die FMEA-Synchronisation nicht automatisch aufgehoben. Sinkt die Bedeutung eines Knotens in der FMEA (von ≥9 auf <9), protokolliert das System eine Warnung im Audit-Log, entfernt das Sicherheitskennzeichen aber nicht; eine manuelle Bewertung ist nötig.

**F: Was bedeutet „nicht abgedeckt“ in der Abdeckungsmatrix?**

A: Das besondere Merkmal ist noch mit keiner Zeile des Produktionslenkungsplans oder keiner MSA-Studie verknüpft. IATF 16949 verlangt für alle besonderen Merkmale passende Lenkungsmethoden und Nachweise; die Matrix hilft, Lücken zu finden.

**F: Überschreibt die Synchronisation aus FMEA manuell angelegte besondere Merkmale?**

A: Nein. Die Synchronisation aktualisiert nur vorhandene Datensätze derselben FMEA-Knotenquelle und überschreibt keine manuell angelegten. Wird ein Knoten aus der FMEA entfernt, werden normale Merkmale automatisch gelöscht, sicherheitsrelevante aber mit Warnung erhalten.

**F: Warum werden aus der PFMEA synchronisierte besondere Merkmale automatisch mit DFMEA-Merkmalen verknüpft?**

A: Neue strukturierte Quellen legen parent_sc_id nicht anhand gleicher Namen an; ein gleicher Name ist kein Beleg für eine Design-Vererbung. Bestehende ausdrückliche Elternbeziehungen bleiben; die tatsächliche Designquelle muss fachlich bestätigt werden.

---

> **Dokumentpfad**: `/docs/modules/planning.md`
## Kompatibilität und Abnahme strukturierter Merkmale (2026-11-03)

Fehlt Function.characteristics oder ist es null, bleibt der alte Freitext-Referenzhinweis ohne automatische Umwandlung; ein ausdrückliches [] bestätigt „keine Merkmale“ und fällt nicht auf das alte Feld zurück. Jeder Eintrag enthält stabile UUID, kind, name, specification, unit, optional classification, reference und related_product_characteristic_ids. Prozessmerkmale von PFMEA-Arbeitselementen dürfen nur auf Produkte desselben Arbeitsgangs verweisen; gemeinsame Process*Function, die tatsächlich zu DFMEA System/Subsystem/Component gehören, sind stets product. kind und CC/SC sind unabhängig, eine besondere Klassifizierung wird nicht automatisch vergeben. Leere Namen melden ein Pflichtfeld, persistierte Namen sind nicht leer; Umbenennen ändert die ID nicht.

Standardspalten, Gruppierung und Strukturkanten-Enums des Produktionslenkungsplans bleiben unverändert. Es gibt kein neues Excel-/PDF-/Druckformat für Produktionslenkungspläne; Lücken bei der Umwandlung von Handbuch/CSR bleiben offen. Fehlende Spezifikation (R005) und doppelte legacy-Objekte (R006) erzeugen nur warnings, kein neues Freigabe-Gate. Dieser Schwerpunkt ist keine Zertifizierung für KI, PPAP, CSR, Scanner oder Live-Neo4j insgesamt.

### Task 11 r1: Einheiten und verspätete Benachrichtigungen

Die bestehende CP-Spalte „Produkt/Prozess/Spezifikation/Toleranz“ zeigt specification + unit des Objekts, mit ausdrücklich genau einer Einheit; Text mit bereits enthaltener Einheit erhält keine zweite, None/Leerraum wird nicht durch eine Einheit zu einem Kriterium ergänzt, Mengen werden nicht umgerechnet. Reine Einheitenänderungen und ausdrückliches Leeren gehen ebenfalls in die gleichartige import/sync/stale-Projektion des freigegebenen Snapshots ein. Neue automatische SCs verwenden dieselbe kleine Formatierungsfunktion; geprüftes Sicherheitsmaterial erhält nur einen Prüfhinweis und wird nicht automatisch umgeschrieben; Altfehler der manuellen Einstiege werden hier nicht behoben.

Der CP-Worker markiert eine bereits vollständig verarbeitete gleiche oder neuere freigegebene Basis nicht erneut als pending. Er schließt sich in der Reihenfolge scope → CP-Elternzeile gegenseitig aus, liest nach dem Warten frische Zeilen neu und prüft Quelle/Werk/Hash, tatsächliche Basis je Zeile und vollständige Abdeckung; ein Dokumentzeiger allein beweist keinen Abschluss. Teilweise/unbekannte/tatsächlich neuere Stände bleiben konservativ needs-update; der Worker benachrichtigt nur und ändert keine fachlichen Felder. Frühere Aussagen zu einem direkten zweistufigen Ablauf bzw. „noch umzusetzen“ sind historisch und nicht der aktuelle Stand.


### Korrekturen aus der abschließenden Prüfung (2026-11-07)

- Werden beim ersten Import aus einem freigegebenen Snapshot nur einige Merkmale importiert, wird in derselben Transaktion `sync_pending=true` gespeichert; selbst wenn das Freigabeereignis vor dem neuen CP lag und bereits zugestellt wurde, kann nach dem Aktualisieren die formale Synchronisationsvorschau geöffnet werden. Nicht importierte Merkmale schreiben keine accepted-Basis je Zeile; erst bei vollständiger Abdeckung wird pending gelöscht.
- Anwendbare Löschkandidaten ohne Schutz/Konflikt sind in der formalen Synchronisation standardmäßig nicht ausgewählt, können aber nach ausdrücklicher Auswahl bestätigt werden; geschützte oder nicht anwendbare Kandidaten bleiben deaktiviert. Schließen oder Wechseln des Vorschaukontexts löscht lokales busy; ein Abschluss alter Anfragen aktualisiert den neuen Drawer nicht; alte Schreibvorgänge können bereits committet sein, daher neu voranzeigen – das ist kein Rollback.
- Beim Löschen eines Funktions-/Struktur-Teilbaums wird zuerst auf betroffene Verknüpfungen weiterhin vorhandener Prozessmerkmale hingewiesen, dann bestätigt, dass nur Referenzen auf UUIDs gelöschter Produktmerkmale bereinigt werden; gemeinsame Fehler-/Maßnahmenknoten bleiben nach überlebenden Zeilen geschützt. Produkt-SC und Prozess-CC sind beide zulässig; die Aggregation zugehöriger strukturierter Mengen folgt CC vor SC und verwirft Klassifizierungen nicht nach kind; die Kompatibilitätsautorität von fehlend/null gegenüber ausdrücklichem [] bleibt.
- Im DC-DC-Beispielentwurf eines Produktionslenkungsplans sind `source_fmea_node_id` und ref.step_id beide der Strukturarbeitsgang `ps_1`, function_id bleibt `psf_1` / `wef_1`, accepted source ist weiterhin null – eine Freigabe wird nicht vorgetäuscht. Die Quellprüfung automatischer SCs verwendet dieselbe Projektion aus Spezifikation + Einheit wie die Extraktion (bei leerer Spezifikation Rückfall auf reference) und erweitert den Umfang der manuellen Sicherheitsmerkmal-API nicht.
- Temporäre Schema-Fixtures normaler pytest-Läufe verwenden das isolierte `qms_test` aus ausdrücklichem `TEST_DATABASE_URL` und nicht die Autorisierungsregeln der Browserinstanz; der dedizierte Browser verlangt weiterhin streng dieselbe URL `127.0.0.1:55432/qms_test` für beide Variablen. Die normale Playwright-Discovery schließt die opt-in characteristic-Spec aus; dedizierte Konfiguration und Autorisierung bleiben unverändert.


### Auswahl historischer Quellen und noch nicht verarbeitete neue Freigaben (2026-11-08)

Import und Synchronisation aus historischen, tatsächlich freigegebenen Snapshots sind erlaubt; gewählte Version und tatsächliches accepted_source_version_id je Zeile bleiben wahrheitsgemäß erhalten. Der Abschluss einer gewählten historischen Version erfüllt nicht die aktuelle Quellverpflichtung: Erstimport, formale Synchronisation und ACK ohne Kandidaten prüfen unter den bestehenden scope- sowie CP/FMEA-Elternsperren zugleich die höchste tatsächlich freigegebene Version derselben Quelle/desselben Werks (Hauptversion der Freigabe, Hash/Zugehörigkeit, vollständige accepted-Abdeckung; bei Mehrdeutigkeit konservativ pending). Gibt es eine noch nicht vollständig angenommene neuere Freigabe, bleibt sync_pending true, auch wenn deren Benachrichtigung längst zugestellt ist; nach ausdrücklicher Vorschau/Abschluss des aktuellen Freigabeziels kann es gelöscht werden – kein dauerhaftes pending, kein Verbot historischer Auswahl, kein veränderlicher Graph als vorgetäuschte Freigabe.

Die verbleibenden Korrekturen der Abnahmeskripte dieser Runde sind nur statisch/pure/mock/syntaktisch geprüft: Teilimport wählt nur Kandidatentabellen und schließt ausdrücklich den Hinweis auf verbleibende Punkte; Funktionen von Arbeitselementen ohne Fehlerzeilen werden über echte Assistentenbearbeitung angelegt; unvollständige Entwürfe durchlaufen zuerst regulär den Assistenten und werden dann im Haupteditor gelöscht. Bestehende Ablehnungen von Laufzeitschreibvorgängen/Worker bleiben wirksam; Browser-Gates wurden in dieser Runde weder gestartet noch nachgeholt.
