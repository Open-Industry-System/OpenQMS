# Module Managementbewertung / Qualitätsziele / Dashboard — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-06-13 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Dieses Dokument behandelt drei eng verbundene Module:

| Modul | ModuleKey | Kernaufgabe |
|------|-----------|---------|
| Managementbewertung | `management_review` | Gesamtablauf der Managementbewertung nach ISO 9001 §9.3, von der automatischen Datenzusammenstellung bis zum Bewertungsbericht und der Verfolgung der Ergebnisse |
| Qualitätsziele | `quality_goal` | Aufbau, Freigabe und KPI-Verfolgung eines dreistufigen Zielbaums (Unternehmen → Produktlinie → Prozess) |
| Dashboard | `dashboard` | Modulübergreifende KPI-Übersicht, Warnungen, letzte Aktionen, anpassbares Widget-Layout |

Zusammen bilden sie einen geschlossenen Kreislauf: Qualitätsziele legen fest, „was erreicht werden soll“, die Managementbewertung prüft, „ob es erreicht wurde“, und das Dashboard zeigt in Echtzeit „wie der aktuelle Stand ist“.

---

## 2. Rollen und Berechtigungen

Das Berechtigungsmodell ist dreistufig: **ModuleKey × PermissionLevel × Rolle**.

Bedeutung von PermissionLevel: 0 = NONE (unsichtbar), 1 = VIEW (nur lesen), 2 = CREATE (anlegen), 3 = EDIT (Inhalte bearbeiten), 4 = APPROVE (freigeben), 5 = ADMIN (Vollzugriff).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| management_review | 5 | 4 | 1 | 1 | 0 | 0 | 1 |
| quality_goal | 5 | 4 | 0 | 0 | 0 | 0 | 1 |
| dashboard | 5 | 4 | 1 | 1 | 1 | 1 | 1 |

**Operationen und Mindestberechtigung:**

### Managementbewertung (management_review)

| Operation | Erforderliche PermissionLevel | Beschreibung |
|------|---------------------|------|
| Bewertungsliste/-details ansehen | VIEW (1) | viewer, field_qe, planning_qe können ansehen |
| Bewertung anlegen | CREATE (2) | Praktisch nur manager (APPROVE=4) und admin |
| Bewertungsinformationen bearbeiten | CREATE (2) | Im Status Entwurf/Daten zusammengestellt bearbeitbar |
| Daten erfassen / aktualisieren | CREATE (2) | Datenpakete der Module automatisch zusammenstellen |
| Bewertung einreichen / schließen / wieder öffnen | APPROVE (4) | Statusweiterschaltung durch manager und admin |
| Bewertung löschen | ADMIN (5) | Nur admin kann Bewertungen im Entwurfsstatus löschen |
| Bewertungsergebnisse anlegen/bearbeiten | CREATE (2) | Im Status in_review Verbesserungsmöglichkeiten usw. ergänzen |
| Ergebnisse verifizieren | CREATE (2) | Ergebnis als verifiziert markieren |
| Bericht erzeugen/bearbeiten | CREATE (2) | Mit LLM-Unterstützung |
| Bericht final bestätigen | APPROVE (4) | manager und admin |

### Qualitätsziele (quality_goal)

| Operation | Erforderliche PermissionLevel | Beschreibung |
|------|---------------------|------|
| Zielliste/-details ansehen | VIEW (1) | viewer kann ansehen |
| Ziel anlegen | CREATE (2) | Praktisch nur manager (APPROVE=4) und admin |
| Ziel bearbeiten | CREATE (2) | Im Entwurfsstatus bearbeitbar |
| Zur Freigabe einreichen | CREATE (2) | draft → pending |
| Ziel freigeben/zurückweisen | APPROVE (4) | pending → active oder zurück auf draft |
| Einreichung zurückziehen | CREATE (2) | pending → draft |
| Ziel archivieren | APPROVE (4) | active → archived |
| Istwert aktualisieren | CREATE (2) | Istwert des Zielerreichungsgrads aktualisieren |
| Ziel löschen | CREATE (2) | Nur im Entwurfsstatus löschbar |

### Dashboard (dashboard)

| Operation | Erforderliche PermissionLevel | Beschreibung |
|------|---------------------|------|
| Dashboard ansehen | VIEW (1) | Für alle Rollen sichtbar |
| Layout bearbeiten | EDIT (3) | Nur manager und admin können das Layout anpassen |
| Bestimmte Widgets ansehen | Abhängig von den Rechten des verknüpften Moduls | Widget „FMEA mit hoher RPN“ braucht fmea VIEW, „überfällige CAPA“ braucht capa VIEW usw. |

---

## 3. Managementbewertung

### 3.1 Grundlage ISO 9001 §9.3

ISO 9001 Abschnitt 9.3 verlangt Managementbewertungen in geplanten Abständen, um fortdauernde Eignung, Angemessenheit und Wirksamkeit des Qualitätsmanagementsystems sicherzustellen. Das Modul deckt die Normanforderungen vollständig ab:

| Normabschnitt | Umsetzung im System |
|----------|---------|
| 9.3.2 a) Umsetzung von Maßnahmen früherer Managementbewertungen | Datenpaket „previous_review_actions“, automatische Erfüllungsquote der früheren Bewertungsergebnisse |
| 9.3.2 b) Grad der Erreichung der Qualitätsziele | Datenpaket „quality_goals“, erreichte/zurückliegende Ziele automatisch aus dem Modul Qualitätsziele |
| 9.3.2 c) Auditergebnisse | Datenpaket „internal_audits“, Anzahl Auditfeststellungen und Abschlussquote |
| 9.3.2 d) Nichtkonformitäten und Korrekturmaßnahmen | Datenpaket „capa_stats“, Anzahl offener/geschlossener CAPAs |
| 9.3.2 e) FMEA-Risikoanalyse | Datenpaket „fmea_risks“, Anzahl Knoten mit hohem AP und Statusverteilung |
| 9.3.2 f) SPC-Prozessfähigkeit | Datenpaket „spc_capability“, Anzahl Regelkarten und Ereignisse außer Kontrolle |
| 9.3.2 g) Leistung externer Anbieter | Datenpaket „supplier_performance“, Verteilung der Lieferanteneinstufung und Lieferbewertung |
| 9.3.3 a) Verbesserungsmöglichkeiten | ReviewOutput category = `improvement_opportunity` |
| 9.3.3 b) Änderungsbedarf am Qualitätsmanagementsystem | ReviewOutput category = `system_change` |
| 9.3.3 c) Ressourcenbedarf | ReviewOutput category = `resource_need` |

### 3.2 Statusübergänge

Dokumente der Managementbewertung haben folgende Status:

```
draft → data_collected → in_review → closed
  ↑          │                │         │
  └──────────┘                │         │
       back_to_draft          │    reopen_review
                               └───────────────┘
```

| Status | Bezeichnung | Beschreibung | Mögliche Aktionen |
|------|------|------|-----------|
| `draft` | Entwurf | Ausgangsstatus, Grunddaten der Bewertung erfassen | Bearbeiten, löschen, Daten erfassen |
| `data_collected` | Daten zusammengestellt | Das System hat die Datenpakete der Module automatisch erfasst | Bearbeiten (inkl. manual_inputs), zurück auf Entwurf, Bewertung starten |
| `in_review` | In Bewertung | Bewertungssitzung läuft | Bewertungsergebnisse/Protokoll anlegen/bearbeiten, Bewertung schließen |
| `closed` | Geschlossen | Bewertung abgeschlossen | Wieder öffnen, Verfolgung der Ergebnisse ansehen |

**Wichtige Regeln:**
- Nur Bewertungen im Status `draft` können gelöscht werden
- Nur im Status `draft` können Daten erfasst werden (collect_data)
- Nur im Status `data_collected` ist Zurück auf Entwurf oder Bewertung starten möglich
- Das Schließen (close_review) erfordert mindestens ein Ergebnis oder ein Protokoll
- Im Status `closed` kann wieder geöffnet werden (reopen) → `in_review`

### 3.3 Automatische Zusammenstellung der Datenpakete

Nach Klick auf „Daten erfassen“ holt das System Daten aus den Modulen in das JSONB-Feld `data_package` mit sieben Datenbereichen:

| Datenbereich | Datenquelle | Kennzahlen |
|--------|---------|---------|
| `quality_goals` | Modul Qualitätsziele | total / achieved / on_track / behind |
| `internal_audits` | Auditmodul | total_findings / closed_findings / open_findings / closure_rate |
| `capa_stats` | CAPA-Modul | total / open / closed |
| `fmea_risks` | FMEA-Modul | total_documents / high_ap_count / status_distribution |
| `spc_capability` | SPC-Modul | total_control_charts / out_of_control_events |
| `supplier_performance` | Lieferantenmanagement | total_suppliers / rating_distribution / avg_delivery_score |
| `previous_review_actions` | Frühere Ergebnisse dieses Moduls | total_outputs / completed / verified / in_progress / pending / completion_rate |

Datenpakete lassen sich nach Produktlinie filtern (Parameter `product_line_code`), damit sich die Bewertung auf eine bestimmte Linie konzentriert.

### 3.4 Bewertungsergebnisse (Review Output)

Bewertungsergebnisse sind das Kernergebnis der Managementbewertung und entsprechen den drei Entscheidungsarten aus ISO 9001 §9.3.3. Jedes Ergebnis enthält:

| Feld | Beschreibung |
|------|------|
| `category` | Ergebnisart: `improvement_opportunity` (Verbesserungsmöglichkeit), `system_change` (Systemänderung), `resource_need` (Ressourcenbedarf) |
| `description` | Beschreibung des Ergebnisses |
| `responsible_id` | Verantwortliche Person |
| `due_date` | Fälligkeitsdatum |
| `status` | Ergebnisstatus: `pending` → `in_progress` → `completed` → `verified` |
| `completion_notes` | Erledigungsnotiz |
| `verified_by` / `verified_at` / `verification_notes` | Verifizierungsinformationen |

Statusübergänge der Ergebnisse:

```
pending → in_progress → completed → verified
```

- Status `completed` bedeutet: umgesetzt, wartet auf Verifizierung
- Status `verified` bedeutet: von der verifizierenden Person als wirksam abgeschlossen bestätigt

### 3.5 Bewertungsbericht

Die Managementbewertung unterstützt automatische Berichtserzeugung:

| Funktion | Beschreibung |
|------|------|
| Bericht erzeugen (generate_report) | Erstellt den Bericht automatisch aus data_package und manual_inputs, optional mit LLM-Zusammenfassung |
| Berichtsentwurf speichern (save_report_draft) | Bericht in Bearbeitung speichern |
| Bericht finalisieren (finalize_report) | Endfassung bestätigen, danach nicht mehr bearbeitbar |
| Bericht wieder öffnen (reopen_report) | Nach der Finalisierung wieder zur Bearbeitung öffnen |
| Bericht exportieren (export_report) | Export im Markdown-Format |
| Versionshistorie (report/versions) | Bewahrt jede finalisierte Version auf |

Berichtsstatus (report_status): `none` → `draft` → `final`; nach der Finalisierung ist reopen nötig, um neu zu erzeugen.

### 3.6 Frontend-Seiten

| Seite | Route | Beschreibung |
|------|------|------|
| Bewertungsliste | `/management-reviews` | Liste, Filter, neue Bewertung |
| Bewertungsdetails | `/management-reviews/:id` | Bewertungsinformationen, Datenpaket, Ergebnisverwaltung, Berichtserzeugung |

### 3.7 Nummerierung

Managementbewertungen haben das Format `MR-{YYYY}-{NNN}`, z. B. `MR-2026-001`, vom System automatisch hochgezählt.

---

## 4. Qualitätsziele

### 4.1 Dreistufiger Zielbaum

Qualitätsziele bilden einen dreistufigen Baum (Selbstreferenz über parent_id) mit strenger Prüfung der Ebenen:

| Ebene (level) | Name | Beschreibung | parent_id |
|:---:|------|------|-----------|
| 1 | Unternehmensziel | Gesamtziel der Organisation, ohne übergeordnetes Ziel | `null` |
| 2 | Produktlinienziel | Nach Produktlinie aufgeschlüsseltes Ziel | goal_id einer Ebene 1 |
| 3 | Prozessziel | Ziel auf Ebene eines konkreten Prozesses/Arbeitsgangs | goal_id einer Ebene 2 |

**Regeln der Ebenenprüfung:**
- Bei level = 1 muss parent_id null sein (Unternehmensziele haben kein übergeordnetes Ziel)
- Bei level > 1 muss parent_id die ID des Ziels der darüberliegenden Ebene sein
- Das level des übergeordneten Ziels muss dem aktuellen level - 1 entsprechen

### 4.2 Felder eines Ziels

| Feld | Typ | Beschreibung |
|------|------|------|
| `doc_no` | string | Vom System erzeugte Nummer im Format `QG-{YYYY}-{NNN}` |
| `name` | string | Zielname |
| `target_value` | string | Zielwert, auch mit Vergleichsoperator wie `≥99%`, `≤50ppm` |
| `actual_value` | string? | Tatsächlich erreichter Wert (z. B. `98.5%`), anfangs leer |
| `unit` | string | Maßeinheit (z. B. `%`, `ppm`, Stück) |
| `period` | string | Zeitraum: monatlich, vierteljährlich, jährlich (als gespeicherte Altwerte hinterlegt) |
| `owner_id` | UUID | Zielverantwortliche Person |
| `product_line_code` | string? | Verknüpfte Produktlinie (üblich bei Ebene 2/3) |
| `data_source_formula` | string? | Formel der Datenquelle, beschreibt die Ermittlung des Istwerts |
| `description` | string? | Ausführliche Zielbeschreibung |

### 4.3 Freigabeablauf und Statusübergänge

```
draft → pending → active
  ↑       │          │
  └───────┘          │
  (Zurückweisen/Zurückziehen)         ↓
                   archived
```

| Status | Bezeichnung | Beschreibung | Mögliche Aktionen |
|------|------|------|-----------|
| `draft` | Entwurf | Ausgangsstatus, bearbeitbar | Bearbeiten, löschen, zur Freigabe einreichen |
| `pending` | Wartet auf Freigabe | Wartet auf Freigabe durch Manager/Administrator | Freigeben, zurückweisen (mit Begründung), zurückziehen |
| `active` | Aktiv | Freigegeben, Verfolgung beginnt | Istwert aktualisieren, archivieren |
| `archived` | Archiviert | Historisches Archiv | Ansehen |

**Wichtige Rechte:**
- Zur Freigabe einreichen (draft → pending): ab CREATE (2)
- Freigeben (pending → active): ab APPROVE (4)
- Zurückweisen (pending → draft, reject_reason erforderlich): ab APPROVE (4)
- Zurückziehen (pending → draft): ab CREATE (2)
- Archivieren (active → archived): ab APPROVE (4)
- Löschen nur im Status draft

### 4.4 KPI-Verfolgung

Ist ein Ziel aktiv (status = `active`), aktualisiert die verantwortliche Person regelmäßig `actual_value`. Das Datenpaket der Managementbewertung holt `quality_goals` automatisch und berechnet:

- `total`: Anzahl aktiver Ziele
- `achieved`: Anzahl erreichter Ziele (nach dem Vergleichsoperator in target_value)
- `on_track`: Anzahl planmäßig verlaufender Ziele
- `behind`: Anzahl hinter dem Zielwert zurückliegender Ziele

Das System bewertet Zielwerte mit Vergleichsoperatoren wie `≥` / `<=` (bei target_value = `≥99%` gilt actual_value >= 99 als erreicht).

### 4.5 Frontend-Seiten

| Seite | Route | Beschreibung |
|------|------|------|
| Liste der Qualitätsziele | `/quality-goals` | Baumdarstellung, Filter, anlegen/bearbeiten/freigeben |

---

## 5. Dashboard

### 5.1 Überblick

Das Dashboard ist die Startseite von OpenQMS und zeigt in Widget-Karten modulübergreifende Qualitäts-KPIs, Warnungen und Aktionsprotokolle in Echtzeit. Nach der Anmeldung gelangen Benutzer automatisch auf das Dashboard (Route `/dashboard`); es braucht keinen zusätzlichen Modulschutz (nur Anmeldung), die Sichtbarkeit einzelner Widgets hängt aber von den Rechten der verknüpften Module ab.

### 5.2 KPI-Karten

Standardmäßig zeigt das Dashboard vier KPI-Übersichtskarten:

| Widget | widget type | Datenquelle | Beschreibung |
|------|-------------|---------|------|
| Offene Aufgaben | `kpi_pending_actions` | `/api/dashboard/kpi` | Anzahl offener Aufgaben zu FMEA/CAPA/Bewertungen usw. |
| Überfällige Aufgaben | `kpi_overdue_tasks` | `/api/dashboard/kpi` | Anzahl überfälliger Aufgaben |
| Hochrisikopunkte | `kpi_high_risk_items` | `/api/dashboard/kpi` | FMEA-Knoten mit RPN ≥ 100, überfällige CAPAs usw. |
| Monatstrend | `kpi_month_trend` | `/api/dashboard/kpi` | Veränderung zentraler Kennzahlen dieses Monats gegenüber dem Vormonat |

### 5.3 Warn-Widgets

| Widget | widget type | Verknüpftes Modul | Beschreibung |
|------|-------------|---------|------|
| FMEA mit hoher RPN | `alert_high_rpn_fmea` | fmea | Listet FMEA-Fehlerknoten mit RPN ≥ 100 |
| Überfällige CAPA | `alert_overdue_capa` | capa | Listet CAPA-Berichte über due_date |
| Lieferanten mit hoher PPM | `alert_high_ppm_suppliers` | supplier | Lieferanten mit PPM über Grenzwert |

Die Sichtbarkeit richtet sich nach VIEW im verknüpften Modul: Ohne VIEW im Modul fmea wird das Widget „FMEA mit hoher RPN“ nicht angezeigt.

### 5.4 Weitere optionale Widgets

Neben dem Standardlayout können Benutzer folgende Widgets aus der Bibliothek ergänzen:

| Widget | widget type | Verknüpftes Modul | Beschreibung |
|------|-------------|---------|------|
| SPC-Ereignisse außer Kontrolle | `spc_abnormal_count` | spc | Anzahl Punkte außer Kontrolle in SPC-Regelkarten |
| SPC-Prozessfähigkeit | `spc_capability_summary` | spc | Statistik der mittleren Cpk |
| MSA-Prüfmittelfälligkeit | `msa_gauge_expiry` | msa | Anzahl Prüfmittel mit Kalibrierfälligkeit in 30 Tagen |
| Offene IQC-Prüfungen | `iqc_pending_inspections` | iqc | Anzahl offener Wareneingangsprüflose |
| MES-Anlagenstatus | `mes_equipment_status` | mes | Anzahl Anlagen in Betrieb/Stillstand/Leerlauf |
| PPM-Trend der Lieferanten | `supplier_ppm_trend` | supplier | PPM-Trenddaten der Lieferanten |
| KI-Qualitätstrend | `quality_trend_ai_summary` | dashboard | KI-gestützte Zusammenfassung der Qualitätstrends |
| Letzte Aktionen | `recent_actions` | dashboard | Die letzten 20 Audit-Log-Einträge |

### 5.5 KPIs der Managementbewertung

Die Dashboard-KPIs enthalten zentrale Kennzahlen der Managementbewertung (Knoten `kpi.management_review` von `/api/dashboard`):

| Kennzahl | Feld | Beschreibung |
|------|------|------|
| Bewertungen gesamt | `total_reviews` | Anzahl aller Managementbewertungen |
| Geschlossene Bewertungen | `closed_reviews` | Anzahl abgeschlossener Bewertungen |
| Ergebnisse gesamt | `total_outputs` | Anzahl aller Bewertungsergebnisse |
| Verifizierte Ergebnisse | `verified_outputs` | Anzahl verifiziert abgeschlossener Ergebnisse |
| Zu verifizierende Ergebnisse | `pending_verification` | Anzahl Ergebnisse im Status completed, die auf Verifizierung warten |
| Erledigungsquote | `completion_rate` | (completed + verified) / total_outputs |

### 5.6 Layout anpassen

- Über „Layout bearbeiten“ gelangt man in den Bearbeitungsmodus (erfordert EDIT, also PermissionLevel ≥ 3)
- Der Bearbeitungsmodus erlaubt: Position und Größe per Drag & Drop ändern, Widgets hinzufügen/entfernen, Standardlayout wiederherstellen
- Die Layoutkonfiguration wird über `/api/dashboard/layout` gespeichert
- Widget-Filter: `WIDGET_MODULE_MAP` im Backend definiert die je Widget nötigen Modulrechte, die Frontend-Funktion `filterLayoutByPermission` filtert unsichtbare Widgets nach Benutzerrechten
- Produktlinienfilter: Das Dashboard filtert Daten nach Produktlinie (URL-Parameter `?product_line=xxx`)

### 5.7 Schnellzugriffe

Das Dashboard zeigt je nach Rollenrechten dynamisch Schnellzugriffe auf die Module. Die Rolle viewer sieht nur Lesezugriffe; ab CREATE erscheinen Einstiege zum Anlegen. Für Module ohne VIEW werden Schnellzugriffe automatisch ausgeblendet.

### 5.8 Frontend-Routen

| Seite | Route | Beschreibung |
|------|------|------|
| Qualitäts-Dashboard | `/dashboard` | Nur Anmeldung erforderlich, kein eigener Modulschutz |

---

## 6. Häufige Fragen

### F1: Warum kann ich keine Managementbewertung anlegen?

**A:** Das Anlegen erfordert mindestens CREATE (2) im Modul `management_review`. In der Standardkonfiguration haben field_qe und planning_qe nur VIEW (1), supplier_qe und customer_qe keine Rechte. Bitte die Berechtigungen vom Administrator anpassen lassen.

### F2: Können Daten nach „Daten erfassen“ noch geändert werden?

**A:** Nach dem Erfassen ist die Bewertung im Status `data_collected`; `manual_inputs` (manuelle Eingaben wie Kundenzufriedenheit, Änderungen interner/externer Themen) und `attachments` (Anhänge) bleiben bearbeitbar. Das automatisch erfasste Datenpaket (`data_package`) selbst ist nicht manuell änderbar, lässt sich aber über „Daten aktualisieren“ (refresh_data) neu laden.

### F3: Nach dem Schließen einer Bewertung fällt eine Lücke auf – was tun?

**A:** Geschlossene Bewertungen lassen sich „wieder öffnen“ (reopen_review); der Status wechselt von `closed` zurück auf `in_review`, Ergebnisse und Protokoll können ergänzt und die Bewertung erneut geschlossen werden.

### F4: Wie werden die drei Zielebenen verknüpft?

**A:** Beim Anlegen eines Ziels der Ebene 2 (Produktlinie) muss parent_id die ID eines Ziels der Ebene 1 sein; bei Ebene 3 (Prozess) muss parent_id auf ein Ziel der Ebene 2 zeigen. Das System prüft, ob das level des übergeordneten Ziels dem aktuellen level - 1 entspricht, und liefert sonst einen Fehler.

### F5: Die Freigabe eines Qualitätsziels wurde zurückgewiesen – was nun?

**A:** Nach einer Zurückweisung ist das Ziel wieder `draft`, die `reject_reason` der freigebenden Person wird am Ziel gespeichert. Nach Überarbeitung kann es erneut eingereicht werden (draft → pending).

### F6: Warum sehe ich manche Widgets nicht?

**A:** Die Sichtbarkeit hängt von den Rechten der verknüpften Module ab, zum Beispiel:
- „FMEA mit hoher RPN“ erfordert VIEW im Modul `fmea`
- „Überfällige CAPA“ erfordert VIEW im Modul `capa`
- SPC-Widgets erfordern VIEW im Modul `spc`

Ist ein Modulrecht NONE (0), wird das Widget automatisch herausgefiltert und nicht im Layout angezeigt.

### F7: Lassen sich Dashboard-Daten nach Produktlinie filtern?

**A:** Ja. Oben auf der Seite gibt es eine Produktlinienauswahl; danach tragen alle Datenanfragen den Parameter `product_line`, und das Backend liefert nur Statistiken dieser Produktlinie.

### F8: Wie kann der Bericht der Managementbewertung erzeugt werden?

**A:** Es gibt zwei Modi:
- **Regelbasiert** (use_llm = false): füllt die Abschnitte anhand der Vorlage aus dem Datenpaket, ohne KI
- **KI-gestützt** (use_llm = true): ergänzt die regelbasierte Erzeugung um eine LLM-Zusammenfassung und Verbesserungsvorschläge

In beiden Modi ist der erzeugte Bericht im Status `draft`, kann manuell bearbeitet und dann zu `final` finalisiert werden.

### F9: Welche Formate unterstützt target_value?

**A:** `target_value` ist eine Zeichenkette in folgenden Formaten:
- Mit Vergleichsoperator: `≥99%`, `≤50ppm`, `>=95%`, `<=3.4`
- Reine Zahl: `100`, `0.5%`
- Bei der Zusammenstellung des Datenpakets parst das System den Vergleichsoperator automatisch und beurteilt, ob actual_value das Ziel erreicht

### F10: Wie läuft die Verifizierung von Bewertungsergebnissen?

**A:** Der Status verläuft `pending` → `in_progress` → `completed` → `verified`:
1. Beim Anlegen `pending` (offen)
2. Nach Beginn der Umsetzung durch die verantwortliche Person `in_progress` (in Bearbeitung)
3. Nach Abschluss der Umsetzung `completed` (wartet auf Verifizierung)
4. Bestätigt die verifizierende Person die Wirksamkeit, setzt verify den Status `verified` (verifiziert) und erfasst `verified_by`, `verified_at` und `verification_notes`

---

> **Nummerierungsregeln:** Managementbewertung `MR-{YYYY}-{NNN}`, Qualitätsziele `QG-{YYYY}-{NNN}`