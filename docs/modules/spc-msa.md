# SPC – Statistische Prozesslenkung & MSA – Messsystemanalyse — Benutzerhandbuch

## 1. Funktionsüberblick

OpenQMS bietet die Module SPC (Statistical Process Control, statistische Prozesslenkung) und MSA (Measurement Systems Analysis, Messsystemanalyse) und deckt damit die Kernanforderungen der IATF 16949 an Prozessüberwachung und Bewertung von Messsystemen ab.

Das **SPC-Modul** unterstützt Regelkarten für variable (X̄-R, I-MR) und attributive Merkmale (P, NP, C, U), meldet über 8 eingebaute Auffälligkeitsregeln automatisch Alarme, berechnet Prozessfähigkeitsindizes (Cp/Cpk/Pp/Ppk), verwaltet mehrere Versionen von Eingriffsgrenzen, warnt gestuft und ist mit 8D/CAPA gekoppelt. Frontend-Routen: `/spc` (Liste), `/spc/:id` (Detail).

Das **MSA-Modul** deckt die fünf Analysemethoden des AIAG-MSA-Handbuchs (4. Ausgabe) ab: GR&R (Mittelwert-Spannweiten-Methode), Bias, Linearität, Stabilität und attributive Kappa-Analyse, dazu Prüfmittelverwaltung und Kalibrierdatensätze. Frontend-Routen: `/msa/gauges` (Prüfmittelliste), `/msa/gauges/:id` (Prüfmitteldetail), `/msa/studies` (Studienliste), `/msa/studies/:type/:id` (Studiendetail, type ist grr / bias / linearity / stability / attribute).

---

## 2. Rollen und Berechtigungen

Das System nutzt ein Berechtigungsmodell mit 5 Stufen: NONE(0) / VIEW(1) / CREATE(2) / EDIT(3) / APPROVE(4) / ADMIN(5).

| Rolle | SPC (`spc`) | MSA (`msa`) | Beschreibung |
|------|:-----------:|:-----------:|------|
| Systemadministrator (`admin`) | 5 | 5 | Alle Rechte |
| Qualitätsmanager (`manager`) | 4 | 4 | Freigeben, bestätigen, anlegen, bearbeiten, ansehen |
| Qualitätsingenieur Fertigung (`field_qe`) | 3 | 3 | Bearbeiten, anlegen, ansehen |
| Qualitätsingenieur Vorausplanung (`planning_qe`) | 1 | 0 | SPC nur ansehen; MSA kein Zugriff |
| Lieferantenqualitätsingenieur (`supplier_qe`) | 1 | 0 | SPC nur ansehen; MSA kein Zugriff |
| Kundenqualitätsingenieur (`customer_qe`) | 1 | 0 | SPC nur ansehen; MSA kein Zugriff |
| Nur-Lese-Benutzer (`viewer`) | 1 | 1 | Nur ansehen |

> **Berechtigungsprüfung**: Alle API-Endpunkte prüfen über `get_user_permission(user, Module.SPC/MSA, db)`. Frontend-Seiten nutzen `<ProtectedRoute requiredModule="spc">` / `"msa"` als Routenschutz; die Sichtbarkeit von Schaltflächen steuert `canEdit` aus `usePermission()`.

---

## 3. SPC – Statistische Prozesslenkung

### 3.1 Regelkartentypen

| Regelkarte | Datentyp | Stichprobenanforderung | Einsatzbereich |
|--------|---------|---------|---------|
| X̄-R (`xbar_r`) | Variabel | Stichprobe 2–10 | Serienfertigung, geringe Streuung innerhalb der Stichprobe |
| I-MR (`imr`) | Variabel | Stichprobe = 1 | Zerstörende Prüfung, seltene Probenahme |
| P (`p`) | Attributiv | Variabler Stichprobenumfang | Fehleranteil |
| NP (`np`) | Attributiv | Fester Stichprobenumfang | Anzahl fehlerhafter Einheiten |
| C (`c`) | Attributiv | Feste Prüfeinheit | Anzahl Fehler |
| U (`u`) | Attributiv | Variable Prüfeinheit | Fehler je Einheit |

Beim **Anlegen eines Prüfmerkmals** sind anzugeben:
- **Prozessname** (`process_name`): z. B. „Schweißen“, „Spritzgießen“
- **Merkmalsname** (`characteristic_name`): z. B. „Außendurchmesser 12,5±0,1 mm“
- **Regelkartentyp** (`chart_type`)
- **Stichprobenumfang** (`subgroup_size`): bei attributiven Merkmalen automatisch 0
- **Obere/untere Spezifikationsgrenze** (`spec_upper` / `spec_lower`): für die Prozessfähigkeit
- **Zielwert** (`target_value`): optional

### 3.2 Die acht Auffälligkeitsregeln

Bei jeder Dateneingabe prüft das System automatisch die folgenden Western-Electric-Regeln und erzeugt bei Auslösung einen `SPCAlarm`:

| Regel | Beschreibung | Schweregrad |
|------|------|---------|
| Regel 1 | 1 Punkt außerhalb der 3σ-Eingriffsgrenzen | critical |
| Regel 2 | 9 Punkte in Folge auf derselben Seite der Mittellinie | major |
| Regel 3 | 6 Punkte in Folge steigend oder fallend | major |
| Regel 4 | 14 Punkte in Folge abwechselnd auf und ab | minor |
| Regel 5 | 2 von 3 aufeinanderfolgenden Punkten außerhalb 2σ | major |
| Regel 6 | 4 von 5 aufeinanderfolgenden Punkten außerhalb 1σ | minor |
| Regel 7 | 15 Punkte in Folge innerhalb 1σ | minor |
| Regel 8 | 8 Punkte in Folge außerhalb 1σ | minor |

Die Regeln lassen sich je Prüfmerkmal in `rules_config` (JSONB) einzeln ein- und ausschalten, standardmäßig sind alle aktiv. Format:

```json
{
  "rule_1": true, "rule_2": true, "rule_3": true, "rule_4": true,
  "rule_5": true, "rule_6": true, "rule_7": true, "rule_8": true
}
```

### 3.3 Dateneingabe

#### 3.3.1 Manuelle Eingabe

Auf der Detailseite der Regelkarte (`/spc/:id`) auf „Daten erfassen“ klicken:

- **Variabel**: Chargennummer, Probenahmezeit und die Messwerte der Stichprobe (z. B. 5 Werte) eingeben
- **Attributiv**: Chargennummer, Probenahmezeit, Prüfmenge (`inspected_count`) und Fehleranzahl (`defect_count`) eingeben

#### 3.3.2 Massenimport

Auf „Import“ klicken, die Excel-Vorlage herunterladen, ausfüllen und hochladen:

- **Vorlage variabel**: Chargennummer*, Probenahmezeit*, Wert 1 bis Wert N (Spaltenzahl = Stichprobenumfang)
- **Vorlage attributiv**: Chargennummer*, Probenahmezeit*, Prüfmenge, Fehleranzahl

Das Backend parst die Excel-Datei, legt automatisch `SampleBatch` + `SampleValue` an und löst die Regelprüfung aus.

#### 3.3.3 Eingabe per API

```
POST /api/spc/inspection-characteristics/{ic_id}/samples
{
  "batch_no": "B001",
  "sampled_at": "2026-06-13T10:00:00+08:00",
  "values": [10.52, 10.48, 10.50, 10.49, 10.51]   // Variabel
  // oder "inspected_count": 100, "defect_count": 3    // Attributiv
}
```

API für Massenimport:

```
POST /api/spc/inspection-characteristics/{ic_id}/samples/import
Content-Type: multipart/form-data
```

### 3.4 Prozessfähigkeitsindizes

Beim Abruf der Fähigkeitsdaten berechnet das System automatisch:

| Kennzahl | Formel | Beschreibung |
|------|------|------|
| Cp | (USL - LSL) / (6σ_within) | Kurzzeitige Prozessfähigkeit |
| Cpk | min(CPU, CPL) | Kurzzeitige Fähigkeit unter Berücksichtigung der Lage |
| Pp | (USL - LSL) / (6σ_overall) | Langzeitige Prozessleistung |
| Ppk | min(PPU, PPL) | Langzeitige Leistung unter Berücksichtigung der Lage |
| Cm | (USL - LSL) / (6σ) | Maschinenfähigkeit (kurzzeitige Probenahme) |
| PPM_theoretical | Erwarteter Fehleranteil auf Basis der Normalverteilung | Theoretische ppm |
| PPM_actual | Tatsächlicher Anteil außerhalb der Spezifikation × 10⁶ | Tatsächliche ppm |

**Fähigkeitsstufen**:

| Cpk | Stufe | Empfehlung |
|-----|------|------|
| ≥ 1.67 | Sehr gut | Prozessfähigkeit ausreichend, Zustand halten |
| ≥ 1.33 | Akzeptabel | Prozessfähigkeit akzeptabel, weiter überwachen |
| ≥ 1.0 | Warnung | Prozessfähigkeit unzureichend, Streuungsquellen analysieren und verbessern |
| < 1.0 | Nicht akzeptabel | Prozessfähigkeit stark unzureichend, Produktion sofort stoppen und Korrektur einleiten |

API-Endpunkte:

```
GET /api/spc/inspection-characteristics/{ic_id}/capability
```

### 3.5 Versionen der Eingriffsgrenzen

Jedes Prüfmerkmal unterstützt versionierte Snapshots der Eingriffsgrenzen (`ControlLimitSnapshot`):

- **Automatische Berechnung**: Neue Prüfmerkmale haben standardmäßig `control_limits_locked = false`; die Grenzen werden bei jedem Abruf der Kartendaten dynamisch berechnet
- **Grenzen sperren**: `POST /api/spc/inspection-characteristics/{ic_id}/lock-limits` setzt `control_limits_locked` auf `true`; das aktuelle Ergebnis wird als Snapshot gespeichert und aktiviert
- **Version wechseln**: Mit `PATCH /api/spc/inspection-characteristics/{ic_id}/snapshots/{snapshot_id}/activate?change_reason=...` zu einer früheren Version zurückkehren
- **Inhalt des Snapshots**: `ucl`, `lcl`, `cl` (Hauptkarte), `r_ucl`, `r_lcl`, `r_cl` (Spannweitenkarte), dazu `version_no` und `is_active`

Die Listenseite zeigt den Status der Eingriffsgrenzen als Tag:
- 🟢 **Gesperrt** — Grenzen aus dem Snapshot
- 🟠 **Automatisch berechnet** — jedes Mal dynamisch berechnet

### 3.6 Gestufte Warnungen und 8D-Kopplung

Wird eine Auffälligkeitsregel ausgelöst:

1. Das System legt automatisch einen `SPCAlarm` mit `rule_no`, `severity` (critical / major / minor), `batch_id` und Auslösezeit an
2. Alarme erscheinen im Reiter „Alarme“ der Detailseite; Punkte außerhalb der Eingriffsgrenzen sind rot markiert
3. Für Alarme gibt es folgende Aktionen:
   - **Alarm bestätigen** (`POST /api/spc/alarms/{alarm_id}/acknowledge`): als bearbeitet markieren
   - **8D-Bericht anlegen** (`POST /api/spc/alarms/{alarm_id}/create-capa`): CAPA automatisch erzeugen und verknüpfen
   - **FMEA-Fehlerarten abgleichen** (`GET /api/spc/alarms/{alarm_id}/fmea-recommendations`): Abgleich über zwei Pfade
     - Pfad 1: exakte Verbindung über den Produktionslenkungsplan (ControlPlanItem.spc_chart_id → source_fmea_node_id)
     - Pfad 2: unscharfer Abgleich mit PFMEA-Fehlerarten über Prozess-/Merkmalsnamen
   - **FMEA-Verknüpfung bestätigen** (`POST /api/spc/alarms/{alarm_id}/confirm-fmea`): eine vorgeschlagene FMEA-Fehlerart bestätigen

---

## 4. MSA – Messsystemanalyse

### 4.1 Prüfmittelverwaltung und Kalibrierung

Das **Prüfmittel (Gauge)** ist die Messgerätebasis von MSA-Studien.

Eigenschaften:
- Prüfmittelnummer (`gauge_no`): automatisch vergeben, Format `G-0001`
- Name, Typ, Hersteller
- Auflösung (`resolution`): Messauflösung
- Messbereich (`measuring_range`): z. B. „0–150 mm“
- Abteilung, Standort
- Kalibrierintervall (`calibration_cycle_days`): Intervall in Tagen
- Nächste Kalibrierung (`next_calibration_date`)
- Status: active / inactive / out_of_service

**Kalibrierdatensätze** (`GaugeCalibration`):
- Kalibrierdatum, Ergebnis (pass / fail / conditional), Zertifikatsnummer
- Kalibriert von, Bemerkung, nächstes Kalibrierdatum

API-Endpunkte:

```
GET    /api/msa/gauges             # Prüfmittelliste (Filter nach status, department, search)
POST   /api/msa/gauges             # Prüfmittel anlegen
GET    /api/msa/gauges/{gauge_id}  # Prüfmitteldetails
PUT    /api/msa/gauges/{gauge_id}  # Prüfmittel aktualisieren
DELETE /api/msa/gauges/{gauge_id}  # Prüfmittel löschen
```

### 4.2 GR&R (Mittelwert-Spannweiten-Methode)

GR&R (Gauge Repeatability & Reproducibility) ist die zentrale MSA-Studie und bewertet Wiederholbarkeit und Vergleichbarkeit des Messsystems.

**Studie anlegen**:

```
POST /api/msa/grr
{
  "title": "GR&R-Studie Messschieber",
  "method": "average_range",           // Derzeit nur Mittelwert-Spannweiten-Methode
  "gauge_id": "uuid",                   // Optional, verknüpftes Prüfmittel
  "characteristic_name": "Außendurchmesser",
  "spc_characteristic_id": "uuid",      // Optional, verknüpftes SPC-Merkmal
  "unit": "mm",
  "tolerance_upper": 12.6,
  "tolerance_lower": 12.4,
  "reference_value": 12.5,
  "appraiser_count": 3,                 // Anzahl Prüfer
  "part_count": 10,                      // Anzahl Teile
  "trial_count": 3                       // Anzahl Messungen
}
```

**Messdaten erfassen**:

```
POST /api/msa/grr/{study_id}/measurements
{
  "measurements": [
    {"appraiser_name": "Max Mustermann", "part_no": "P1", "trial_no": 1, "value": 12.52},
    {"appraiser_name": "Max Mustermann", "part_no": "P1", "trial_no": 2, "value": 12.50},
    ...
  ]
}
```

**Berechnung** (`POST /api/msa/grr/{study_id}/compute`):

Liefert `GrrResult` mit:

| Kennzahl | Beschreibung |
|------|------|
| EV | Wiederholbarkeit (Equipment Variation) |
| AV | Vergleichbarkeit (Appraiser Variation) |
| GRR | Streuung des Messsystems = √(EV² + AV²) |
| PV | Teilestreuung (Part Variation) |
| TV | Gesamtstreuung = √(GRR² + PV²) |
| ndc | Anzahl unterscheidbarer Kategorien = 1,41 × (PV / GRR) |
| grr_percent_tol | GRR in Prozent der Toleranz = GRR / (USL - LSL) × 100 |
| grr_percent_tv | GRR in Prozent der Gesamtstreuung |
| conclusion | Akzeptabel / bedingt akzeptabel / nicht akzeptabel |

**Bewertungskriterien**:

| GRR % Toleranz | ndc | Ergebnis |
|----------|-----|------|
| < 10% | ≥ 5 | Akzeptabel |
| 10%–30% | ≥ 2 | Bedingt akzeptabel |
| > 30% | < 2 | Nicht akzeptabel |

Ohne Toleranz wird nach GRR%TV bewertet.

Statusübergänge der Studie: `draft` → `ongoing` (automatisch nach Dateneingabe) → `completed` (über den complete-Endpunkt)

### 4.3 Bias-Analyse

Die Bias-Analyse bewertet die systematische Abweichung des Mittelwerts der Messergebnisse vom Referenzwert.

**Studie anlegen**:

```
POST /api/msa/bias
{
  "title": "Bias-Studie Bügelmessschraube",
  "gauge_id": "uuid",
  "characteristic_name": "Innendurchmesser",
  "spc_characteristic_id": "uuid",
  "unit": "mm",
  "reference_value": 25.000,
  "sample_size": 10
}
```

**Berechnung** (`POST /api/msa/bias/{study_id}/compute`):

| Kennzahl | Beschreibung |
|------|------|
| mean | Stichprobenmittelwert |
| bias | Bias = mean - reference_value |
| bias_percent | Bias in Prozent des Referenzwerts |
| std_dev | Stichprobenstandardabweichung |
| t_statistic | t-Statistik |
| p_value | Zweiseitiger p-Wert |
| lower_ci / upper_ci | 95-%-Konfidenzintervall des Bias |
| conclusion | Akzeptabel / nicht akzeptabel |

**Bewertungskriterium**: Bei |bias%| < 5 % und p > 0,05 ist der Bias akzeptabel.

### 4.4 Linearitätsanalyse

Die Linearitätsanalyse prüft, ob der Bias über den Messbereich konstant ist (lineare Regression Bias vs. Referenzwert).

**Studie anlegen**:

```
POST /api/msa/linearity
{
  "title": "Linearitätsstudie Messschieber",
  "gauge_id": "uuid",
  "characteristic_name": "Länge",
  "unit": "mm",
  "tolerance_upper": 150.0,
  "tolerance_lower": 0.0,
  "sample_size_per_reference": 5
}
```

Für jeden Referenzpunkt werden mehrere Messungen erfasst; das System berechnet den Bias (measured_value - reference_value) und passt eine lineare Regression an.

**Berechnung**:

| Kennzahl | Beschreibung |
|------|------|
| slope | Steigung der Regression |
| intercept | Achsenabschnitt der Regression |
| r_squared | Bestimmtheitsmaß |
| linearity | Linearität = |slope| × Prozessstreuung |
| linearity_percent | Linearität in Prozent der Prozessstreuung |
| bias_at_lower / bias_at_upper | Bias am unteren/oberen Referenzwert |
| conclusion | Akzeptabel / nicht akzeptabel |

**Bewertungskriterium**: Bei linearity% < 5 % und R² > 0,8 akzeptabel.

### 4.5 Stabilitätsanalyse

Die Stabilitätsanalyse bewertet mit einer X̄-R-Regelkarte die zeitliche Drift des Messsystems.

**Studie anlegen**:

```
POST /api/msa/stability
{
  "title": "Stabilitätsstudie Bügelmessschraube",
  "gauge_id": "uuid",
  "characteristic_name": "Außendurchmesser",
  "reference_value": 25.000,
  "subgroup_size": 5
}
```

Je Stichprobe werden `sample_mean` und `sample_range` erfasst; das System berechnet die Eingriffsgrenzen.

**Berechnung**:

| Kennzahl | Beschreibung |
|------|------|
| ucl_mean / lcl_mean / cl_mean | Eingriffsgrenzen der X̄-Karte |
| ucl_range / lcl_range / cl_range | Eingriffsgrenzen der R-Karte |
| cpk | Prozessfähigkeitsindex (sofern Toleranz vorhanden) |
| conclusion | Akzeptabel / nicht akzeptabel |

**Bewertungskriterium**: Liegen alle Stichprobenmittelwerte innerhalb der Eingriffsgrenzen, ist das Ergebnis akzeptabel.

### 4.6 Attributive Kappa-Analyse

Die attributive Analyse bewertet die Wirksamkeit der Gut-/Schlecht-Entscheide der Prüfer.

**Studie anlegen**:

```
POST /api/msa/attribute
{
  "title": "Kappa-Analyse Sichtprüfung",
  "gauge_id": "uuid",
  "characteristic_name": "Optische Fehler",
  "method": "risk_analysis",
  "sample_size": 50,
  "known_standard_count": 25
}
```

**Daten erfassen**: mehrere Entscheide je Prüfer und Teil, mit:
- `appraiser_name`: Name des Prüfers
- `part_no`: Teilenummer
- `known_standard`: bekannter Standard (Annehmen/Ablehnen bzw. "1"/"0")
- `appraiser_decision`: Entscheid des Prüfers
- `trial_no`: Versuchsnummer

**Berechnung**:

| Kennzahl | Beschreibung |
|------|------|
| effectiveness | Wirksamkeit = korrekte Entscheide / alle Entscheide × 100 % |
| miss_rate | Schlupfrate = übersehene Fehler / gute Teile laut Standard × 100 % |
| false_alarm_rate | Fehlalarmrate = Fehlentscheide / schlechte Teile laut Standard × 100 % |
| kappa_within | Interne Übereinstimmung (Übereinstimmung mehrfacher Entscheide desselben Prüfers) |
| kappa_vs_standard | Übereinstimmung mit dem Standard |
| kappa_between | Übereinstimmung zwischen Prüfern |
| conclusion | Akzeptabel / bedingt akzeptabel / nicht akzeptabel |

**AIAG-Bewertungskriterien**:

| Wirksamkeit | Schlupfrate | Fehlalarmrate | Ergebnis |
|--------|--------|--------|------|
| ≥ 90% | ≤ 2% | ≤ 5% | Akzeptabel |
| ≥ 80% | — | — | Bedingt akzeptabel |
| < 80% | — | — | Nicht akzeptabel |

### 4.7 Prüfmittelliste und -details

**Prüfmittelliste** (`/msa/gauges`):
- Tabelle aller Prüfmittel, Filter nach Status und Abteilung, Stichwortsuche
- Spalten: Prüfmittelnummer, Name, Typ, Status, Auflösung, nächste Kalibrierung
- Aktionen: Prüfmittel anlegen, Details ansehen, bearbeiten, löschen

**Prüfmitteldetails** (`/msa/gauges/:id`):
- Grunddaten und Kalibrierdatensätze
- Liste der verknüpften MSA-Studien

### 4.8 Studienliste und -details

**Studienliste** (`/msa/studies`):
- Einheitliche Übersicht aller fünf Studientypen (GR&R, Bias, Linearität, Stabilität, attributiv)
- Filter nach Typ (type) und Status (status)
- Spalten: Studiennummer, Typ, Titel, verknüpftes Prüfmittel, Status, Studiendatum

**Studiendetails** (`/msa/studies/:type/:id`):
- Der Parameter `type` entspricht grr / bias / linearity / stability / attribute
- Je nach `type` werden unterschiedliche Formulare und Berechnungen geladen
- Gemeinsame Statusübergänge: `draft` → `ongoing` → `completed`
- Typspezifische Eingabetabellen und Ergebnisdarstellung

| Typ | Präfix der Studiennummer | Typspezifischer Inhalt der Detailseite |
|------|------------|--------------|
| GR&R | GRR-{Jahr}-*** | Messdatentabelle (appraiser × part × trial), Diagramm der Varianzkomponenten, Bewertung |
| Bias | BIAS-{Jahr}-*** | Messwerttabelle, Ergebnis des t-Tests auf Bias, Konfidenzintervall |
| Linearität | LINEAR-{Jahr}-*** | Messtabelle je Referenzpunkt, Regressionsdiagramm des Bias |
| Stabilität | STAB-{Jahr}-*** | Tabelle der Stichprobenmittelwerte/-spannweiten, X̄-R-Regelkarte |
| Attributiv | ATTR-{Jahr}-*** | Entscheidungsmatrix, Wirksamkeits-/Kappa-Kennzahlen |

---

## 5. Häufige Fragen

### F1: Warum darf der Stichprobenumfang beim Anlegen einer Regelkarte nicht 1 sein?
X̄-R-Karten verlangen einen Stichprobenumfang von 2–10. Bei Stichprobe 1 die I-MR-Karte (`imr`) verwenden; das System setzt `subgroup_size` dann automatisch auf 1.

### F2: Wie unterscheidet sich die Dateneingabe attributiver Regelkarten (P/NP/C/U) von variablen?
Variable Karten brauchen die Messwerte der Stichprobe (Array `values`), attributive nur `inspected_count` (Prüfmenge) und `defect_count` (Fehleranzahl). Auch die Importvorlagen unterscheiden das automatisch.

### F3: Die NP-Karte verlangt einen „festen Stichprobenumfang“ – was, wenn die Prüfmenge je Charge schwankt?
Die Berechnung der Eingriffsgrenzen der NP-Karte setzt gleiche Prüfmengen voraus; sonst wird ein Fehler 400 geliefert. Stattdessen die P-Karte (variabler Stichprobenumfang) oder die U-Karte verwenden.

### F4: Was unterscheidet „gesperrte“ von „automatisch berechneten“ Eingriffsgrenzen?
- **Automatisch berechnet**: UCL/LCL/CL werden bei jedem Abruf aus den vorhandenen Stichproben berechnet und ändern sich mit neuen Daten
- **Gesperrt**: Das aktuelle Ergebnis wird als Snapshot (`ControlLimitSnapshot`) gespeichert, spätere Karten verwenden feste Grenzen. Geeignet für stabile Prozesse mit Referenzvergleich

### F5: Wie sind SPC-Alarme mit 8D/CAPA gekoppelt?
In den Alarmdetails auf „8D-Bericht anlegen“ klicken; das System legt einen CAPAEightD-Datensatz an und verknüpft `linked_capa_id` mit dem Alarm. Das Format der 8D-Nummer ist `8D-{Jahr}-***`.

### F6: Wie funktioniert der Abgleich mit FMEA-Fehlerarten?
Das System gleicht über zwei Pfade ab:
1. **Verbindung über den Produktionslenkungsplan**: Ist das SPC-Merkmal in einem Produktionslenkungsplan referenziert (`ControlPlanItem.spc_chart_id`), wird über dessen `source_fmea_node_id` exakt die PFMEA-Fehlerart ermittelt
2. **Unscharfer Namensabgleich**: Mit Prozess-/Merkmalsnamen als Suchbegriff werden im PFMEA-Graphen ähnliche FailureMode-Knoten gesucht (Ähnlichkeit > 0,3 bzw. 0,5)

Die Ergebnisse werden im Feld `fmea_recommendations` gecacht; mit „Verknüpfung bestätigen“ wird eine Zuordnung festgelegt.

### F7: Was bedeutet ein ndc-Wert von 999 bei GR&R?
Geht GRR gegen 0 (Messsystem nahezu ohne Streuung), strebt ndc = 1,41 × (PV / GRR) gegen sehr große Werte. Das System setzt solche Fälle auf 999, also eine sehr hohe Unterscheidungsfähigkeit.

### F8: Kann ich eine MSA-Studie anlegen, wenn das Prüfmittel den Status „out_of_service“ hat?
Nein. Beim Anlegen prüft `validate_gauge_for_use()` den Prüfmittelstatus; nur Prüfmittel mit `active` sind für MSA-Studien zulässig.

### F9: Warum ist das Bias-Ergebnis „nicht akzeptabel“, obwohl p > 0,05?
Das Kriterium verlangt |bias%| < 5 % **und** p > 0,05 gleichzeitig. Auch ohne statistische Signifikanz (p > 0,05) gilt ein Bias von mindestens 5 % des Referenzwerts als nicht akzeptabel.

### F10: planning_qe / supplier_qe / customer_qe haben keinen Zugriff auf MSA?
Das ist so beabsichtigt. Diese drei Rollen haben für MSA die Stufe NONE(0), die API liefert 403. Für Zugriff muss der Administrator die MSA-Berechtigung in der Berechtigungsverwaltung anpassen.