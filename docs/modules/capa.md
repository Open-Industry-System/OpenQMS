# Modul 8D / CAPA — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-07-09 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Das Modul 8D / CAPA (Corrective and Preventive Action) steuert den gesamten Problemlösungsprozess nach der 8D-Methode (Eight Disciplines), von der Teambildung bis zu Abschluss und Archivierung, über den vollständigen Lebenszyklus eines 8D-Berichts.

Kernfunktionen:

| Funktion | Beschreibung |
|------|------|
| Vollständiger 8D-Ablauf | D1 Team → D2 Problembeschreibung → D3 Sofortmaßnahmen → D4 Grundursachenanalyse → D5 Abstellmaßnahmen → D6 Umsetzung und Verifizierung → D7 Wiederholungsvermeidung → D8 Abschluss |
| Steuerung der Statusübergänge | Strikt in Reihenfolge; D7/D8 erfordern Freigabe durch Manager oder Administrator |
| FMEA-Verknüpfung | Berichte lassen sich mit FMEA-Dokumenten und konkreten Fehlerknoten verknüpfen, für Risikorückverfolgbarkeit |
| KI-Empfehlungen | D4/D5/D7 schlagen aus dem verknüpften FMEA-Graphen automatisch Grundursachen, Korrektur- und Vorbeugungsmaßnahmen vor |
| KI-Entwürfe | D2–D8 unterstützen KI-gestützte Textentwürfe |
| Lessons-Learned-Suche | Beim Anlegen eines Berichts können Lessons Learned aus historischen CAPAs/FMEAs gesucht werden |
| SCAR-Kopplung | Lieferantenverursachte CAPAs können über das SCAR-Modul Korrekturmaßnahmen beim Lieferanten anfordern |
| Produktlinientrennung | Daten sind nach Produktlinie und Werk getrennt; Benutzer sehen nur Berichte in ihrem autorisierten Bereich |

**Frontend-Routen:**

| Seite | Route | Beschreibung |
|------|------|------|
| 8D-Berichtsliste | `/capa` | Liste, Filter, Neu |
| 8D-Berichtsdetails | `/capa/:id` | Schritte bearbeiten, weiterschalten, FMEA verknüpfen |

---

## 2. Rollen und Berechtigungen

Das Berechtigungsmodell ist dreistufig: **ModuleKey × PermissionLevel × Rolle**. Der ModuleKey des CAPA-Moduls ist `capa`.

Bedeutung von PermissionLevel: 0 = NONE (unsichtbar), 1 = VIEW (nur lesen), 2 = CREATE (anlegen), 3 = EDIT (Inhalte bearbeiten), 4 = APPROVE (Weiterschalten von D7/D8 freigeben), 5 = ADMIN (Vollzugriff).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| capa | 5 | 4 | 3 | 1 | 2 | 2 | 1 |

**Operationen und Mindestberechtigung:**

| Operation | Erforderliche PermissionLevel | Beschreibung |
|------|---------------------|------|
| 8D-Liste/-Details ansehen | VIEW (1) | viewer, customer_qe, planning_qe können ansehen |
| 8D-Bericht anlegen | CREATE (2) | Ab supplier_qe, customer_qe |
| Berichtsinhalt bearbeiten | EDIT (3) | Ab field_qe können Felder aller Schritte bearbeitet werden |
| D1–D6 weiterschalten | EDIT (3) | Ab field_qe |
| D7 → D8 weiterschalten | APPROVE (4) | manager、admin |
| D8 → Archiv weiterschalten | APPROVE (4) | manager、admin |
| FMEA verknüpfen/wechseln | EDIT (3) | Ab field_qe |
| KI-Entwürfe | EDIT (3) | Ab field_qe |
| KI-Empfehlungen D4/D5/D7 | VIEW (1) + FMEA VIEW | Erfordert CAPA VIEW und FMEA VIEW |

> Hinweis: `planning_qe` hat nur VIEW und kann Berichte weder bearbeiten noch weiterschalten. `supplier_qe` und `customer_qe` können anlegen und bearbeiten, aber das Weiterschalten von D7/D8 nicht freigeben.

---

## 3. Der 8D-Ablauf im Detail

Die 8D-Methode gliedert die Problemlösung in acht Standardschritte mit klarem Zweck und definierten Ein-/Ausgaben. OpenQMS steuert die Übergänge streng in dieser Reihenfolge.

### 3.1 D1 — Team (D1_TEAM)

**Zweck:** Ein funktionsübergreifendes Team bilden, Verantwortlichkeiten festlegen und sicherstellen, dass die nötigen Kompetenzen und Befugnisse vorhanden sind.

**Status:** `D1_TEAM` (Ausgangsstatus nach dem Anlegen)

**Bedienung:**

- Teammitglieder werden als Tabelle angezeigt, je Zeile **Name** und **Projektrolle**
- Rollenoptionen: Qualitätsingenieur, Prozessingenieur, Entwicklungsingenieur, Projektleiter, Produktionsleiter
- Mit „Mitglied hinzufügen“ ergänzen, über die Löschen-Schaltfläche am Zeilenende entfernen

**Datenstruktur:** `d1_team` ist ein JSONB-Array, Beispiel:

```json
[
  {"name": "Max Mustermann", "role": "Qualitätsingenieur"},
  {"name": "Erika Musterfrau", "role": "Prozessingenieur"}
]
```

**Übergangsbedingung:** Nach mindestens einem Teammitglied mit „Nächster Schritt“ zu D2 wechseln.

### 3.2 D2 — Problembeschreibung (D2_DESCRIPTION)

**Zweck:** Das Problem mit der 5W2H-Methode genau beschreiben: What (welches Problem), Who (wer hat es entdeckt/ist betroffen), When (wann), Where (wo), Why (warum ist es ein Problem), How (wie ist es aufgetreten), How many (Umfang).

**Bedienung:**

- Mehrzeiliges Textfeld (TextArea) im 5W2H-Format
- Schaltfläche KI-Entwurf: Die KI kann aus dem Kontext der Problembeschreibung einen D2-Entwurf erzeugen
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d2_description` (Text)

### 3.3 D3 — Sofortmaßnahmen zur Eindämmung (D3_INTERIM)

**Zweck:** Bevor die Grundursache feststeht, mit Sofortmaßnahmen (Interim Containment Action) eine Ausweitung verhindern und Kunden sowie Produktion schützen.

**Typischer Inhalt:** Fehlerhafte Teile sperren, 100-%-Prüfung, vorübergehender Wechsel zu einem Ersatzlieferanten usw.

**Bedienung:**

- Mehrzeiliges Textfeld (TextArea)
- Schaltfläche KI-Entwurf: Vorschläge für Sofortmaßnahmen auf Basis der Problembeschreibung aus D2
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d3_interim` (Text)

### 3.4 D4 — Grundursachenanalyse (D4_ROOT_CAUSE)

**Zweck:** Mit 5-Why, Ishikawa-Diagramm usw. die Grundursache (Root Cause) finden und technische von organisatorischen Ursachen unterscheiden.

**Bedienung:**

- **D4-KI-Empfehlungspanel** (`D4RecPanel`): schlägt anhand des verknüpften FMEA-Graphen und historischer CAPAs mögliche Fehlerursachen vor
  - Empfehlungsquellen: Abgleich verknüpfter FMEA-Knoten, Stichwortabgleich, Semantiksuche, ähnliche historische CAPA-Fälle
  - „Übernehmen“ hängt den Vorschlagstext an den Bereich der Grundursachenanalyse an
- Mehrzeiliges Textfeld (TextArea), beschriftet „Grundursachenanalyse (5-Why / Ishikawa)“
- Schaltfläche KI-Entwurf: D4-Entwurf aus dem Kontext
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d4_root_cause` (Text)

**D4-Empfehlungsschnittstelle:** `GET /api/capa/{report_id}/d4-fmea-recommendations`
- Erfordert CAPA VIEW und FMEA VIEW
- Gelieferte Felder: Name und Beschreibung der Fehlerursache, Abgleichsquelle, Konfidenz, Kennung der Quell-CAPA

### 3.5 D5 — Abstellmaßnahmen (D5_CORRECTION)

**Zweck:** Für die Grundursache dauerhafte Abstellmaßnahmen (Permanent Corrective Action) festlegen, die die Ursache beseitigen statt nur Symptome zu kontrollieren.

**Bedienung:**

- **D5-KI-Empfehlungspanel** (`D5RecPanel`): schlägt auf Basis des verknüpften FMEA-Graphen zwei Arten von Inhalten vor
  - **Bestehende Lenkungsmaßnahmen** (aus FMEA-Vermeidungs-/Entdeckungsmaßnahmen), direkt übernehmbar
  - **Allgemeine Vorschläge** (KI-erzeugte Vermeidungs-, Entdeckungs- und Korrekturmaßnahmen) mit Konfidenz
- Mehrzeiliges Textfeld (TextArea)
- Schaltfläche KI-Entwurf
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d5_correction` (Text)

**D5-Empfehlungsschnittstelle:** `GET /api/capa/{report_id}/d5-fmea-recommendations`
- Rückgabe getrennt in `existing_controls` (vorhandene FMEA-Maßnahmen) und `general_suggestions` (KI-Vorschläge)

### 3.6 D6 — Umsetzung und Verifizierung (D6_VERIFICATION)

**Zweck:** Prüfen, ob die D5-Abstellmaßnahmen wirksam umgesetzt sind und das Problem beseitigt haben; Daten vor und nach der Verbesserung vergleichen.

**Typischer Inhalt:** Umsetzungsdatum, Verifizierungsmethode (Datenvergleich, Prozessaudit, Kundenrückmeldung), Verifizierungsergebnis.

**Bedienung:**

- Mehrzeiliges Textfeld (TextArea), beschriftet „Wirksamkeitsprüfung“
- Schaltfläche KI-Entwurf
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d6_verification` (Text)

### 3.7 D7 — Wiederholungsvermeidung (D7_PREVENTION)

**Zweck:** Die in D5/D6 als wirksam bestätigten Maßnahmen systematisieren und standardisieren, damit gleichartige Probleme in anderen Produktlinien, Prozessen oder Situationen nicht erneut auftreten.

**Typischer Inhalt:** FMEA aktualisieren, Produktionslenkungsplan ändern, Arbeitsanweisungen überarbeiten, Personal schulen, Prüfstandards aktualisieren.

**Bedienung:**

- Mehrzeiliges Textfeld (TextArea), beschriftet „Maßnahmen zur Wiederholungsvermeidung“
- **D7-FMEA-Knotenempfehlungen** (`D7RecPanel`): listet zu aktualisierende FMEA-Fehlerknoten
  - Jeder Knoten kann als „aktualisiert“ oder „keine Aktualisierung nötig“ markiert werden
  - Erst wenn alle empfohlenen Knoten bestätigt sind, ist „Nächster Schritt“ direkt verfügbar
  - Bei unbestätigten Knoten öffnet das System einen Dialog zum Überspringen mit Pflichtbegründung
- Schaltfläche KI-Entwurf
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d7_prevention` (Text)

**D7-Empfehlungsschnittstelle:** `GET /api/capa/{report_id}/d7-fmea-recommendations`
- Empfehlungsquellen: Abgleich verknüpfter FMEA-Knoten + Stichwortabgleich
- Gelieferte Felder: ID/Name des Fehlerartknotens, ID/Name des Fehlerursachenknotens, Knoten der Vermeidungsmaßnahme, Abgleichsquelle, vorgeschlagene Vorbeugungsmaßnahme

**Weiches Gate in D7 (Soft Gate):** Vor dem Weiterschalten nach D8 prüft das System, ob alle in D7 empfohlenen FMEA-Knoten bestätigt sind. Bei unbestätigten Knoten muss eine Begründung zum Überspringen angegeben werden; sie wird im Audit-Log (`D7_SKIP_CONFIRMATION`) erfasst.

> Das Weiterschalten von D7 erfordert APPROVE (Manager oder Administrator).

### 3.8 D8 — Abschluss (D8_CLOSURE)

**Zweck:** Die Teamleitung bestätigt die Wirksamkeit aller Maßnahmen, archiviert die Unterlagen, löst das Team auf und schließt den 8D-Bericht formal ab.

**Bedienung:**

- Mehrzeiliges Textfeld (TextArea), beschriftet „Abschlussbestätigung“
- Schaltfläche KI-Entwurf
- Inhalte werden bei `onBlur` automatisch gespeichert

**Datenfeld:** `d8_closure` (Text)

**Besonderes Verhalten:**

- Erreicht der Bericht D8_CLOSURE, schließt das System verknüpfte Lieferanten-Risikowarnungen automatisch (`SupplierRiskAlert.status → "closed"`)
- Das Weiterschalten von D8 zu ARCHIVED erfordert APPROVE

---

## 4. Statusübergänge

### 4.1 Statusdefinitionen

| Statuswert | Bezeichnung | Schrittnummer | Beschreibung |
|--------|----------|:--------:|------|
| `D1_TEAM` | D1 Team | 0 | Ausgangsstatus nach dem Anlegen |
| `D2_DESCRIPTION` | D2 Problembeschreibung | 1 | — |
| `D3_INTERIM` | D3 Sofortmaßnahmen | 2 | — |
| `D4_ROOT_CAUSE` | D4 Grundursachenanalyse | 3 | — |
| `D5_CORRECTION` | D5 Abstellmaßnahmen | 4 | — |
| `D6_VERIFICATION` | D6 Umsetzung und Verifizierung | 5 | — |
| `D7_PREVENTION` | D7 Wiederholungsvermeidung | 6 | Weiterschalten erfordert Freigabe durch Manager oder Administrator |
| `D8_CLOSURE` | D8 Abschluss | 7 | Weiterschalten erfordert Freigabe durch Manager oder Administrator |
| `ARCHIVED` | Archiviert | 8 | Endstatus, kein Zurück |

### 4.2 Gültige Übergänge

```
D1_TEAM ──→ D2_DESCRIPTION ──→ D3_INTERIM ──→ D4_ROOT_CAUSE
                                              │         ↑
                                              │         │
                                              ↓         │
                                    D5_CORRECTION      │
                                              │         │
                                              ↓         │
                                    D6_VERIFICATION ──→ D5_CORRECTION(zurück)
                                              │
                                              ↓
                                    D7_PREVENTION
                                              │
                                              ↓
                                    D8_CLOSURE
                                              │
                                              ↓
                                        ARCHIVED
```

**Vorwärts (Standard):** D1 → D2 → D3 → D4 → D5 → D6 → D7 → D8 → ARCHIVED

**Erlaubte Rückschritte:**

| Aktueller Status | Zurück nach |
|----------|----------|
| D2_DESCRIPTION | D1_TEAM |
| D4_ROOT_CAUSE | D3_INTERIM |
| D6_VERIFICATION | D5_CORRECTION |

Rückschritte erfolgen über `PUT /api/capa/{report_id}` mit Änderung des Statusfelds (gültige Pfade nur D2→D1, D4→D3, D6→D5).

### 4.3 Berechtigungs-Gates

| Weiterschaltung | Mindestberechtigung | Prüflogik im Backend |
|----------|-------------|-------------|
| D1 → D2 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D2 → D3 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D3 → D4 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D4 → D5 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D5 → D6 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D6 → D7 | EDIT (3) | `advance_capa` — normales Weiterschalten |
| D7 → D8 | **APPROVE (4)** | Middleware `require_close_permission` prüft `user.role in [admin, manager]` |
| D8 → ARCHIVED | **APPROVE (4)** | Wie oben |

> Frontend: In den Status D7_PREVENTION oder D8_CLOSURE sehen nur Benutzer mit `canApprove('capa')` = true die Schaltfläche „Nächster Schritt“.

### 4.4 API zum Weiterschalten

**Anfrage:** `POST /api/capa/{report_id}/advance`

**Request-Body (optional):**

```json
{
  "d7_skip_reasons": [
    {
      "fmea_id": "uuid",
      "node_id": "string",
      "reason": "Begründung zum Überspringen"
    }
  ]
}
```

- `d7_skip_reasons` wird nur beim Übergang D7→D8 mit unbestätigten FMEA-Knoten verwendet
- Jede Weiterschaltung erzeugt automatisch ein Audit-Log vom Typ `TRANSITION` mit altem und neuem Status

**Response-Body:**

```json
{
  "capa": {
    "report_id": "uuid",
    "document_no": "8D-2026-001",
    "title": "...",
    "status": "D5_CORRECTION",
    "d4_retry_count": 3,
    "...": "..."
  },
  "warning": "Eskalation empfohlen (D4-Verifizierung 3-mal zurückgesetzt)"
}
```

- `capa` ist der CAPA-Bericht nach dem Weiterschalten (Struktur wie `GET /api/capa/{id}`)
- `warning` wird nur geliefert, wenn dieser Schritt von `D4_ROOT_CAUSE` nach `D5_CORRECTION` führt und `d4_retry_count >= 3`; sonst `null`

---

## 5. FMEA-Verknüpfung

### 5.1 Zweck der Verknüpfung

Die Verknüpfung eines 8D-Berichts mit einem FMEA-Dokument (und konkreten Fehlerknoten) ermöglicht:

1. **Intelligente Empfehlungen in D4/D5/D7** — das System entnimmt dem verknüpften FMEA-Graphen Fehlerursachen, Lenkungsmaßnahmen und zu aktualisierende Knoten
2. **Risikorückverfolgung** — aus der FMEA lassen sich verknüpfte CAPA-Berichte ansehen
3. **Weiches Gate in D7** — vor dem Übergang nach D8 wird bestätigt, dass relevante FMEA-Knoten aktualisiert sind

### 5.2 Verknüpfen

**Im Frontend:**

1. In den 8D-Berichtsdetails in der rechten Infoleiste auf „FMEA verknüpfen“ klicken
2. FMEA-Dokument aus der Auswahlliste wählen (mit Suche)
3. Nach erfolgreicher Verknüpfung erscheint das grüne Tag „FMEA verknüpft“
4. Zum Wechseln auf „FMEA-Verknüpfung ändern“ klicken und neu wählen

**Backend-API:**

- Verknüpfen: `POST /api/capa/{report_id}/link-fmea?fmea_id={fmea_id}&fmea_node_id={node_id}`
  - Erfordert CAPA EDIT
  - Die Ziel-FMEA muss im für den Benutzer zugänglichen Werksbereich liegen
  - Die Verknüpfung wird im Audit-Log `LINK_FMEA` erfasst
- Verknüpfung abfragen: `GET /api/capa/{report_id}/related-fmea`
  - Liefert `fmea_id`, `document_no`, `fmea_node_id`
- CAPA nach FMEA-Knoten abfragen: `GET /api/capa/by-fmea-node/{fmea_id}?fmea_node_id={node_id}`

### 5.3 Datenfelder

| Feld | Typ | Beschreibung |
|------|------|------|
| `fmea_ref_id` | UUID (nullable) | ID des verknüpften FMEA-Dokuments, Fremdschlüssel auf `fmea_documents.fmea_id` |
| `fmea_node_id` | String (nullable) | ID des konkreten Fehlerknotens, für präzise D7-Empfehlungen |

---

## 6. SCAR-Kopplung

### 6.1 Überblick

Weist die Grundursache eines 8D-Berichts auf ein Lieferantenproblem, kann über das SCAR-Modul (Supplier Corrective Action Request) eine formale Korrekturmaßnahme beim Lieferanten angefordert werden. SCAR und CAPA sind über den Fremdschlüssel `capa_ref_id` bidirektional verknüpft.

### 6.2 SCAR mit CAPA verknüpfen

**Backend-API:** `POST /api/scars/{scar_id}/link-capa`

**Request-Body:**

```json
{
  "capa_ref_id": "uuid-of-capa-report"
}
```

- Erfordert CREATE im SCAR-Modul
- Nach der Verknüpfung zeigt die SCAR-Detailseite Nummer und Link des 8D-Berichts

### 6.3 Statusübergänge der SCAR

| Aktueller Status | Operation | Zielstatus | Erforderliche Berechtigung |
|----------|------|----------|----------|
| open | start | in_progress | CREATE (2) |
| in_progress | respond | responded | CREATE (2) |
| responded | verify | verified | APPROVE (4) |
| responded | reject | open | APPROVE (4) |
| verified | close | closed | APPROVE (4) |
| verified | reopen | in_progress | APPROVE (4) |

### 6.4 Auslöser einer SCAR

SCARs können automatisch oder manuell aus folgenden Quellen ausgelöst werden:

| Quelle | source_type | Beschreibung |
|------|-------------|------|
| IQC-Fehler | `iqc` | Wareneingangsprüfung findet fehlerhafte Charge |
| Reklamation | `complaint` | Kundenreklamation weist auf Lieferantenverantwortung |
| RMA-Rücksendung | `rma` | Rücksendeanalyse weist auf Lieferantenproblem |
| Manuell | `manual` | Direkt im SCAR-Modul angelegt |

### 6.5 SCAR-Kopplung beim CAPA-Abschluss

Erreicht ein 8D-Bericht `D8_CLOSURE`, schließt das System automatisch alle verknüpften Lieferanten-Risikowarnungen, deren Status nicht `closed` ist:

```python
# capa_service.update_capa Interne Logik
if capa.status == "D8_CLOSURE":
    await db.execute(
        update(SupplierRiskAlert)
        .where(SupplierRiskAlert.linked_capa_id == capa.report_id)
        .where(SupplierRiskAlert.status != "closed")
        .values(status="closed", handled_at=func.now())
    )
```

---

## 7. KI-Unterstützung

### 7.1 KI-Entwürfe

Die Schritte D2–D8 unterstützen KI-gestützte Entwürfe und reduzieren den manuellen Schreibaufwand.

**Einstieg:** Oben rechts an jedem Textfeld die Schaltfläche „KI-Entwurf“

**Ablauf:**

1. „KI-Entwurf“ anklicken und Entwurfsformat wählen
2. Das System erzeugt den Entwurf über `POST /api/capa/{report_id}/draft/{step}`
3. Der Entwurf erscheint im Vorschaupanel
4. Mit „Ersetzen“ oder „Anhängen“ wird der KI-Entwurf ins Eingabefeld übernommen
5. „Änderung rückgängig“ stellt den Inhalt vor dem KI-Eintrag wieder her

**Schritte mit Entwurf:**

| Schritt | API-Pfad | Kontext-Eingabe |
|------|----------|-----------|
| D2 | `/draft/d2` | Gliederung der Problembeschreibung |
| D3 | `/draft/d3` | Inhalt D2 |
| D4 | `/draft/d4` | Inhalt D2 + D3 |
| D5 | `/draft/d5` | Grundursache D4 |
| D6 | `/draft/d6` | Abstellmaßnahmen D5 |
| D7 | `/draft/d7` | Inhalt D5 + D6 |
| D8 | `/draft/d8` | Zusammenfassung des Gesamtablaufs |

**Berechtigung:** erfordert CAPA EDIT

**Fähigkeitsabfrage:** `GET /api/capa/{report_id}/draft/capabilities`
- Liefert `{ ai_draft_enabled: bool, llm_provider: string | null }`
- In den Status D1_TEAM und ARCHIVED ist die Entwurfsfunktion nicht verfügbar

### 7.2 Lessons-Learned-Suche

Nach dem Anlegen eines 8D-Berichts öffnet das System automatisch das Lessons-Learned-Panel (`LessonsLearnedModal`) und sucht ähnliche Fälle und Erfahrungen aus historischen CAPAs und FMEAs.

**Auslöser:** automatisch beim Sprung von der Liste zur Detailseite nach dem Anlegen (mit Parameter `problemDescription`)

**API：** `POST /api/capa/{report_id}/lessons-learned`

**Berechtigung:** erfordert CAPA VIEW; FMEA-Quelldaten erfordern zusätzlich FMEA VIEW

### 7.3 KI-Empfehlungen D4/D5/D7

Siehe die Beschreibung der Empfehlungspanels in den einzelnen Schritten. Alle drei Empfehlungsschnittstellen erfordern CAPA VIEW und FMEA VIEW.

---

## 8. Berichtsliste und Filter

### 8.1 Listenseite

**Route:** `/capa`

**Listenfelder:**

| Spalte | Feld | Beschreibung |
|------|------|------|
| Berichtsnummer | `document_no` | Format: `8D-YYYY-NNN` |
| Titel | `title` | — |
| Aktueller Schritt | `status` | Schrittname als Tag |
| Schwere | `severity` | Farbige Tags: kritisch (rot), schwer (orange), mittel (blau), gering (grau) |
| Frist | `due_date` | Datum oder „-“ |
| Aktualisiert | `updated_at` | — |

**Farben der Schwerestufen:**

| Stufe | Farbe |
|------|------|
| kritisch | red |
| schwer | orange |
| mittel | blue |
| gering | default (grau) |

### 8.2 Filter und Sortierung

**API：** `GET /api/capa`

| Parameter | Typ | Beschreibung |
|------|------|------|
| `page` | int | Seitennummer (Standard 1) |
| `page_size` | int | Einträge pro Seite (Standard 20, höchstens 1000) |
| `status` | string | Filter nach Status |
| `product_line` | string | Filter nach Produktlinie |
| `overdue` | bool | Nur überfällige Berichte (Fälligkeit vor heute, nicht abgeschlossen/archiviert) |
| `pending_action` | bool | Nur offene Berichte (Status nicht D8_CLOSURE/ARCHIVED) |

**Produktlinientrennung:** Benutzer sehen nur Berichte in ihren autorisierten Produktlinien. Ohne autorisierte Produktlinie ist die Liste leer.

### 8.3 Bericht anlegen

**Felder des Dialogs:**

| Feld | Pflicht | Beschreibung |
|------|:----:|------|
| Titel | Ja | Berichtstitel |
| Berichtsnummer | Ja | Empfohlenes Format `8D-YYYY-NNN`, global eindeutig |
| Schwere | Nein | Standard ist die Stufe mittel; wählbar sind kritisch, schwer, mittel, gering (gespeichert als Altwerte) |
| Fälligkeitsdatum | Nein | Gewünschter Abschlusstermin |

**API：** `POST /api/capa`

**Berechtigung:** CAPA CREATE (2)

---

## 9. Häufige Fragen

### F1: Beim Weiterschalten erscheint „Freigaberecht nicht ausreichend“

Das Weiterschalten von D7 (Wiederholungsvermeidung) und D8 (Abschluss) erfordert APPROVE (4), also die Rollen `manager` oder `admin`. Die Rollen `field_qe`, `supplier_qe`, `customer_qe` können diese Schritte nicht weiterschalten. Bitte Manager oder Administrator ansprechen.

### F2: Beim Weiterschalten von D7 erscheint der Dialog „unbestätigte FMEA-Knoten“

Das ist das weiche Gate in D7. Findet das System in der verknüpften FMEA noch zu bestätigende Fehlerknoten, wird das direkte Weiterschalten verhindert. Sie müssen:

1. im D7-Empfehlungspanel jeden FMEA-Knoten einzeln bestätigen (als „aktualisiert“ oder „keine Aktualisierung nötig“ markieren), oder
2. eine Begründung eingeben und auf „Überspringen bestätigen und weiterschalten“ klicken

Die Begründung wird im Audit-Log erfasst.

### F3: Wie verknüpfe ich CAPA mit FMEA?

In den 8D-Berichtsdetails in der rechten Infoleiste auf „FMEA verknüpfen“ klicken und ein FMEA-Dokument aus der Liste wählen. Danach kann zusätzlich der konkrete Fehlerknoten (`fmea_node_id`) angegeben werden. Zum Wechseln „FMEA-Verknüpfung ändern“ wählen.

### F4: Anforderungen an die Berichtsnummer

`document_no` muss global eindeutig sein. Empfohlen ist das Format `8D-YYYY-NNN` (z. B. `8D-2026-001`). Doppelte Nummern ergeben einen Fehler 400.

### F5: Die Schaltfläche KI-Entwurf ist ausgegraut/nicht verfügbar?

Die Entwurfsfunktion erfordert einen im Backend konfigurierten LLM-Provider. Den Status prüft `GET /api/capa/{report_id}/draft/capabilities`. Ist `ai_draft_enabled` `false`, ist kein LLM-Provider konfiguriert. In den Status D1_TEAM und ARCHIVED ist sie ebenfalls nicht verfügbar.

### F6: Der Produktlinienfilter wirkt nicht?

Der Produktlinienfilter der Liste unterliegt den Berechtigungen. Sind dem Benutzer nur einzelne Produktlinien zugewiesen (`pl_scope.mode = EXPLICIT`), sieht er nur deren Berichte. Ohne Produktlinienberechtigung (`pl_scope.mode = NONE`) ist die Liste leer.

### F7: Wie löse ich bei einem Lieferantenproblem eine SCAR aus?

SCARs werden nicht im CAPA-Modul ausgelöst. Im Lieferantenmanagement (`/scars`) beim Anlegen der SCAR `source_type` angeben (z. B. `complaint`, `iqc`, `rma`) und die SCAR dann über `POST /api/scars/{scar_id}/link-capa` mit dem CAPA-Bericht verknüpfen. Details in der Dokumentation des SCAR-Moduls.

### F8: Was passiert nach dem D8-Abschluss mit verknüpften Risikowarnungen?

Erreicht ein 8D-Bericht D8_CLOSURE, markiert das System alle verknüpften offenen Lieferanten-Risikowarnungen (`SupplierRiskAlert`) als `closed`. Das erledigt das Backend automatisch.

### F9: Wie gehe ich einen Schritt zurück?

Der 8D-Ablauf erlaubt begrenzte Rückschritte:

- D2 → D1
- D4 → D3
- D6 → D5

Rückschritte erfolgen über `PUT /api/capa/{report_id}` mit Änderung des Felds `status`. Das Frontend bietet derzeit keine Zurück-Schaltfläche, ein API-Aufruf ist nötig.

### F10: Welche Operationen erfasst das Audit-Log?

Jede Operation erzeugt automatisch ein Audit-Log (Tabelle `audit_logs`, `table_name = capa_eightd`):

| action | Beschreibung |
|--------|------|
| CREATE | 8D-Bericht anlegen |
| UPDATE | Berichtsinhalt bearbeiten |
| TRANSITION | Statusweiterschaltung mit `old_status` und `new_status` |
| LINK_FMEA | FMEA verknüpfen/wechseln mit `old_fmea_ref_id` und `new_fmea_ref_id` |
| D7_SKIP_CONFIRMATION | Überspringen unbestätigter FMEA-Knoten in D7 mit `skipped_nodes` |

---

## Anhang: Datenmodell

### Tabelle CAPAEightD (`capa_eightd`)

| Feld | Typ | Beschreibung |
|------|------|------|
| `report_id` | UUID (PK) | Eindeutige Kennung des Berichts |
| `document_no` | String(50) | Berichtsnummer, global eindeutig |
| `title` | String(200) | Berichtstitel |
| `product_line_code` | String(20) | Produktliniencode, Standard `DC-DC-100` |
| `factory_id` | UUID (FK) | Werk |
| `status` | String(20) | Aktueller Status, Standard `D1_TEAM` |
| `severity` | String(20) | Schwere, Standard ist die Stufe mittel (gespeicherter Altwert) |
| `d1_team` | JSONB | Array der Teammitglieder `[{name, role}]` |
| `d2_description` | Text | Problembeschreibung |
| `d3_interim` | Text | Sofortmaßnahmen zur Eindämmung |
| `d4_root_cause` | Text | Grundursachenanalyse |
| `d5_correction` | Text | Abstellmaßnahmen |
| `d6_verification` | Text | Wirksamkeitsprüfung |
| `d7_prevention` | Text | Maßnahmen zur Wiederholungsvermeidung |
| `d8_closure` | Text | Abschlussbestätigung |
| `d4_retry_count` | Integer, NOT NULL DEFAULT `0` | Zähler für Rückschritte der D4-Verifizierung |
| `fmea_ref_id` | UUID (FK, nullable) | Verknüpftes FMEA-Dokument |
| `fmea_node_id` | String(36, nullable) | Verknüpfter FMEA-Fehlerknoten |
| `due_date` | Date (nullable) | Fälligkeitsdatum |
| `created_by` | UUID (FK, nullable) | Angelegt von |
| `created_at` | DateTime(TZ) | Angelegt am |
| `updated_at` | DateTime(TZ) | Aktualisiert |

### Tabelle CapaRootCauseVerification (`capa_root_cause_verification`)

Verifizierungsdatensätze der D4-Grundursache: Jeder Datensatz entspricht der Vor-Ort-Verifizierung einer möglichen Grundursache.

| Feld | Typ | Beschreibung |
|------|------|------|
| `verification_id` | UUID (PK) | Eindeutige Kennung des Verifizierungsdatensatzes |
| `capa_id` | UUID (FK) | Zugehöriger 8D-Bericht (`capa_eightd.report_id`) |
| `factory_id` | UUID (FK) | Werk |
| `root_cause_text` | Text, NOT NULL | Gebundener Grundursachentext |
| `method` | Text, nullable | Verifizierungsmethode, nur `measurement` / `observation` / `reproduction` (DB CHECK) |
| `result` | Text, nullable | Beschreibung des Verifizierungsergebnisses |
| `is_verified` | Boolean, NOT NULL DEFAULT `false` | Verifiziert ja/nein (aus `conclusion` abgeleitet, beibehalten) |
| `conclusion` | String(20), NOT NULL DEFAULT `'pending'` | Verifizierungsschluss: `pending` / `passed` / `failed` (DB CHECK) |
| `evidence_attachments` | JSONB, NOT NULL DEFAULT `[]` | Liste der Nachweisanhänge |
| `source_ref` | JSONB, nullable | Quellreferenz (z. B. verknüpfter Empfehlungseintrag) |
| `verified_by` | UUID (FK, nullable) | Verifiziert von |
| `verified_at` | DateTime(TZ, nullable) | Verifiziert am |
| `created_at` | DateTime(TZ) | Angelegt am |
| `updated_at` | DateTime(TZ) | Aktualisiert |

**Constraints:**
- `chk_verification_method`: `method IS NULL OR method IN ('measurement','observation','reproduction')`
- `chk_verification_conclusion`: `conclusion IN ('pending','passed','failed')`

---

### Übersicht der API-Endpunkte

| Methode | Pfad | Berechtigung | Beschreibung |
|------|------|------|------|
| GET | `/api/capa` | VIEW | Liste (mit Paginierung und Filtern) |
| POST | `/api/capa` | CREATE | Bericht anlegen |
| GET | `/api/capa/{id}` | VIEW | Berichtsdetails |
| PUT | `/api/capa/{id}` | EDIT | Berichtsinhalt aktualisieren |
| POST | `/api/capa/{id}/advance` | D1-D6: EDIT, D7-D8: APPROVE | Zum nächsten Schritt weiterschalten |
| POST | `/api/capa/{id}/link-fmea` | EDIT | FMEA verknüpfen |
| GET | `/api/capa/{id}/related-fmea` | VIEW | Verknüpfte FMEA abfragen |
| GET | `/api/capa/by-fmea-node/{fmea_id}` | VIEW | CAPA nach FMEA-Knoten abfragen |
| GET | `/api/capa/{id}/d4-fmea-recommendations` | VIEW + FMEA VIEW | KI-Empfehlungen D4 |
| GET | `/api/capa/{id}/d5-fmea-recommendations` | VIEW + FMEA VIEW | KI-Empfehlungen D5 |
| GET | `/api/capa/{id}/d7-fmea-recommendations` | VIEW + FMEA VIEW | FMEA-Knotenempfehlungen D7 |
| GET | `/api/capa/{id}/draft/capabilities` | VIEW | Abfrage der KI-Entwurfsfähigkeit |
| POST | `/api/capa/{id}/draft/{step}` | EDIT | KI-Entwurf erzeugen |
| GET | `/api/capa/capabilities` | VIEW | Abfrage der KI-Fähigkeiten des Moduls |
| POST | `/api/capa/{id}/lessons-learned` | VIEW | Lessons-Learned-Suche |