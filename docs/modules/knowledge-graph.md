# Modul Wissensgraph und Änderungsauswirkungsanalyse — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-06-13 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Das Modul Wissensgraph und Änderungsauswirkungsanalyse baut aus den FMEA-Graphdaten ein dokumentübergreifendes Wissensnetz auf und bietet Qualitätsingenieuren:

| Teilmodul | Route | Funktionsumfang |
|--------|------|----------|
| Wissensgraph | `/knowledge-graph` | FMEA-übergreifende Risikoübersicht, Stichwort-/Semantiksuche ähnlicher Knoten, Statistik der globalen Wissensbasis |
| Änderungsauswirkungsanalyse | `/change-impact` | Historie der Auswirkungsanalysen, Berichtsdetails, betroffene Knoten im Graphen finden |

Beide Teilmodule sind eng in den FMEA-Editor integriert: Im FMEA-Grapheneditor lässt sich direkt eine Auswirkungsanalyse starten (erfordert FMEA EDIT), aus dem Ergebnis kann zurück in den Graphen gesprungen werden.

---

## 2. Rollen und Berechtigungen

### 2.1 Wissensgraph (`knowledge_graph`)

Der Wissensgraph wird über einen eigenen ModuleKey gesteuert:

| Rolle | PermissionLevel | Beschreibung |
|------|:---------------:|------|
| admin | 1 (VIEW) | Kann produktlinienübergreifende globale Statistiken (geschwärzt) ansehen |
| manager | 1 (VIEW) | Kann Statistiken der eigenen Produktlinie und die Suche nach ähnlichen Knoten nutzen |
| quality_engineer | Keine Berechtigungszeile | Standardmäßig kein Zugriff (muss von admin manuell vergeben werden) |
| field_qe / planning_qe / supplier_qe / customer_qe | Keine Berechtigungszeile | Standardmäßig kein Zugriff |
| viewer | Keine Berechtigungszeile | Standardmäßig kein Zugriff |

> **Hinweis zu Berechtigungen:** Das Modul `knowledge_graph` gewährt derzeit nur admin und manager VIEW. Für andere Rollen muss admin in der Rollenberechtigungsverwaltung eine Berechtigungszeile für `knowledge_graph` ergänzen. Die Frontend-Route `/knowledge-graph` prüft keine Modulrechte, nur die Anmeldung; die API filtert jedoch nach Rollenrechten (z. B. verlangt der Endpunkt `global-stats` ADMIN, `similar-nodes` verkleinert ohne globale Berechtigung automatisch den Suchbereich).

**API-Berechtigungen:**

| API-Endpunkt | Mindestberechtigung | Beschreibung |
|----------|----------|------|
| `GET /api/graph/stats` | Nur Anmeldung | FMEA-übergreifende Aggregatstatistik (je Produktlinie) |
| `GET /api/graph/global-stats` | ADMIN | Produktlinienübergreifende globale Statistik (geschwärzt) |
| `GET /api/graph/similar` | Nur Anmeldung | Stichwortsuche ähnlicher Knoten (je Produktlinie) |
| `POST /api/graph/similar-nodes` | Nur Anmeldung (ohne KNOWLEDGE_GRAPH VIEW wird der scope automatisch verkleinert) | Semantische Ähnlichkeitssuche |
| `GET /api/graph/fmea/{id}/impact/{node}` | Nur Anmeldung | Nachgelagerte Auswirkungskette |
| `GET /api/graph/fmea/{id}/cause/{node}` | Nur Anmeldung | Vorgelagerte Ursachenkette |
| `POST /api/graph/rebuild` | ADMIN | Vollständigen Neo4j-Neuaufbau auslösen |

### 2.2 Änderungsauswirkungsanalyse (`change-impact`)

Die Auswirkungsanalyse hat keinen eigenen ModuleKey, sondern nutzt die Rechte des FMEA-Moduls:

| Operation | Mindestberechtigung | Beschreibung |
|------|----------|------|
| Auswirkungsanalyse starten | FMEA EDIT (3) | Erfordert FMEA-Bearbeitungsrecht |
| Analysehistorie ansehen | FMEA VIEW (1) | Erfordert FMEA-Leserecht |
| Analysedetails ansehen | FMEA VIEW (1) | Erfordert FMEA-Leserecht |

> **Hinweis:** Die Frontend-Route `/change-impact` prüft keine Modulrechte, nur die Anmeldung. Die API steuert den Zugriff über die FMEA-Rechte. Auch die Werkstrennung (factory scope) gilt: Benutzer sehen nur Daten ihrer Werke.

---

## 3. Wissensgraph

### 3.1 Einstieg und Aufbau

In der Seitenleiste auf **„Wissensgraph“** klicken, um `/knowledge-graph` zu öffnen. Oben gibt es eine Produktlinienauswahl, der Hauptbereich hat drei Reiter:

| Tab | Symbol | Beschreibung |
|-----|------|------|
| Übersicht / Risikokarte | BarChartOutlined | FMEA-übergreifendes Statistikpanel |
| Historische Stichwortsuche | SearchOutlined | Suche nach Knotentyp und Stichwort |
| Semantische Suche | RobotOutlined | Intelligente Suche mit Ähnlichkeitsbewertung |

> Ohne gewählte Produktlinie zeigt die Seite den Leerzustand „Bitte zuerst eine Produktlinie wählen“.

### 3.2 Übersicht / Risikokarte

Nach Wahl einer Produktlinie ruft das System `GET /api/graph/stats?product_line_code=xxx` auf und erhält die Aggregatstatistik aller freigegebenen FMEAs dieser Produktlinie.

**Angezeigte Inhalte:**

| Kennzahl | Beschreibung |
|------|------|
| Anzahl FMEAs | Anzahl freigegebener FMEA-Dokumente der Produktlinie |
| Anzahl Knoten | Gesamtzahl der Knoten in allen FMEA-Graphen |
| Fehlerarten mit hoher Priorität (AP=H) | Anzahl Fehlerarten mit Action Priority „H“ (hoch), hervorgehoben mit rotem Flammensymbol |
| Mittlere RPN | Mittlere Risikoprioritätszahl aller Fehlerarten (jeweils Zeile mit höchster RPN) |

**Karte AP-Verteilung:** zeigt die Verteilung der AP-Stufen als Tags:
- Rotes Tag: hoch (H) — Anzahl Fehlerarten mit hoher Priorität
- Oranges Tag: mittel (M) — Anzahl Fehlerarten mit mittlerer Priorität
- Grünes Tag: niedrig (L) — Anzahl Fehlerarten mit niedriger Priorität

**Tabelle Top 10 der Fehlerarten mit hoher Priorität:** listet Fehlerarten mit AP=H in folgenden Spalten:

| Spalte | Beschreibung |
|----|------|
| Fehlerart | Knotenname |
| RPN | Risikoprioritätszahl |
| Quell-FMEA | Nummer des verknüpften FMEA-Dokuments; ein Klick springt zum Graph-Reiter dieser FMEA und hebt den Knoten hervor |
| Operation | Schaltfläche „Graph ansehen“, springt zum Graphen der FMEA |

**Karte Knotentypverteilung:** listet die Anzahl je Knotentyp als Tags, z. B. `ProcessStep: 15`, `FailureMode: 8`.

### 3.3 Historische Stichwortsuche

Im Reiter „Historische Stichwortsuche“ lassen sich FMEA-Knoten der aktuellen Produktlinie nach Knotentyp und Stichwort suchen.

**Schritte:**

1. Knotentyp im Auswahlfeld wählen:
   - Fehlerart (`FailureMode`)
   - Fehlerursache (`FailureCause`)
   - Fehlerfolge (`FailureEffect`)
   - Funktion (`Function`)
2. Stichwort ins Suchfeld eingeben
3. Auf Suchen klicken oder Enter drücken

Das System sucht per Stichwortabgleich über `GET /api/graph/similar?node_type=xxx&name_keyword=xxx&product_line_code=xxx`.

**Ergebnistabelle:**

| Spalte | Beschreibung |
|----|------|
| Name | Name des gefundenen Knotens |
| Typ | Knotentyp |
| Quell-FMEA | Nummer des verknüpften FMEA-Dokuments, per Klick anspringbar |
| Operation | Schaltfläche „Ansehen“, springt zum FMEA-Graphen und hebt den Knoten hervor |

### 3.4 Semantische Suche

Der Reiter Semantische Suche (Komponente `SemanticSearchTab`) bietet eine intelligente Suche mit Ähnlichkeitsbewertung über den Endpunkt `POST /api/graph/similar-nodes`.

**Suchbereich:**

- **Aktuelle Produktlinie (`current_product_line`):** nur freigegebene FMEA-Knoten der Produktlinie des Benutzers
- **Global (`global`):** freigegebene FMEA-Knoten aller Produktlinien. Ohne VIEW in `knowledge_graph` wird eine globale Anfrage automatisch auf `current_product_line` verkleinert

**Ähnlichkeit:** `compute_similarity()` berechnet die Ähnlichkeit zwischen Suchtext und Knotenname (0,0–1,0); Ergebnisse unter `min_similarity` (Standard 0,3) werden gefiltert.

**Gelieferte Felder:**

| Feld | Beschreibung |
|------|------|
| node_id | Knoten-ID |
| name | Knotenname (bei produktlinienübergreifenden Knoten ohne globale Berechtigung geschwärzt) |
| type | Knotentyp |
| fmea_id | ID der Quell-FMEA |
| document_no | Nummer der Quell-FMEA |
| product_line_code | Produktliniencode |
| product_line_name | Produktlinienname |
| similarity_score | Ähnlichkeitswert (0–1) |
| match_reason | Begründung des Treffers |

> **Schwärzung:** Fehlt dem Benutzer die globale Berechtigung für `knowledge_graph`, werden Knotennamen in produktlinienübergreifenden Ergebnissen geschwärzt (die ersten 2 Zeichen bleiben, der Rest wird durch `***` ersetzt), um Informationsabfluss zu verhindern.

### 3.5 Globale Statistik (nur Admin)

Die Rolle admin kann über `GET /api/graph/global-stats` die Aggregatstatistik über alle Produktlinien abrufen. Der Endpunkt:

- akzeptiert keinen Parameter `product_line_code` (sonst Fehler 400)
- liefert Daten nach Whitelist-Neuaufbau und Namensschwärzung (Funktion `mask_name()`)
- Schwärzungsregel: die ersten 2 Zeichen bleiben, der Rest wird `***`; Namen mit höchstens 2 Zeichen behalten nur das erste Zeichen + `***`

### 3.6 Neuaufbau des Graphen

Die Rolle admin kann über `POST /api/graph/rebuild` einen vollständigen Neo4j-Neuaufbau auslösen. Dabei gilt:

- Ausführung als asynchrone Hintergrundaufgabe, sofortige Erfolgsantwort
- Alle vorhandenen Neo4j-Daten werden geleert
- Constraints und Indizes werden neu angelegt
- Alle FMEA-Dokumente in PostgreSQL werden durchlaufen und einzeln nach Neo4j projiziert
- Geeignet bei inkonsistenten Neo4j-Daten oder umfangreicher Datenreparatur

---

## 4. Änderungsauswirkungsanalyse

### 4.1 Funktionsbeschreibung

Die Änderungsauswirkungsanalyse bewertet, welchen möglichen Auswirkungsbereich und welche Risikoveränderung eine Änderung an einem einzelnen Knoten der FMEA-Graphdaten für verknüpfte Knoten hat. Typische Fälle:

- **Attributänderung:** Bedeutung (S), Auftreten (O) oder Entdeckung (D) einer Fehlerart ändern
- **Strukturänderung:** Knoten und Verbindungen hinzufügen, löschen oder verschieben

### 4.2 Analyse starten

Es gibt zwei Einstiege:

**Einstieg 1: im FMEA-Editor**

Im FMEA-Grapheneditor (`/fmea/:id?tab=graph`) nach Auswahl eines Knotens die Auswirkungsanalyse starten. Das System füllt `fmea_id`, `node_id`, `node_type`, `node_name` usw. automatisch; nur Änderungsart und Änderungsfeld sind anzugeben.

**Einstieg 2: Seite Änderungsauswirkungsanalyse**

Auf `/change-impact` lassen sich historische Analysen ansehen; neue Analysen können dort nicht direkt gestartet werden.

### 4.3 API-Aufruf

```
POST /api/change-impact/analyze
```

**Anfrageparameter (`ChangeImpactAnalyzeRequest`):**

| Parameter | Typ | Pflicht | Beschreibung |
|------|------|:----:|------|
| fmea_id | UUID | Ja | ID des FMEA-Dokuments |
| node_id | string | Ja | ID des geänderten Knotens |
| node_type | string | Ja | Knotentyp (z. B. `FailureMode`, `FailureCause`) |
| node_name | string | Ja | Knotenname |
| change_type | string | Ja | Änderungsart: `attribute` (Attributänderung) oder `structural` (Strukturänderung) |
| field_name | string | Nein | Name des geänderten Felds (z. B. `severity`, `occurrence`, `detection`) |
| new_value | string | Nein | Neuer Wert |

**Berechtigung:** EDIT im FMEA-Modul (Stufe 3+).

### 4.4 Analyselogik

Je nach Änderungsart und Feld wählt das System unterschiedliche Traversierungsstrategien:

#### Änderungsart: Attributänderung (`attribute`)

| Geändertes Feld | Traversierungsrichtung | Beschreibung |
|----------|----------|------|
| `name` / `description` | Keine Traversierung | Änderungen an Name und Beschreibung beeinflussen die Risikostufe anderer Knoten nicht |
| `severity` / `occurrence` / `detection` | Beide Richtungen (downstream + upstream) | S/O/D-Änderungen wirken auf nachgelagerte Fehlerfolgen und Maßnahmen sowie auf vorgelagerte Fehlerursachen |
| Andere Felder | Nachgelagert (downstream) | Standardmäßig wird die nachgelagerte Auswirkungskette verfolgt |

#### Änderungsart: Strukturänderung (`structural`)

Nur die nachgelagerte Richtung (downstream) wird verfolgt.

#### Filter nach Kantentyp

**Kantentypen der Abwärtstraversierung (downstream):**

| Kantentyp | Beschreibung |
|--------|------|
| `HAS_FUNCTION` | Prozessschritt/Arbeitselement → Funktion |
| `FUNCTION_MAPPED_TO` | Funktion → Fehlerart |
| `HAS_FAILURE_MODE` | Strukturknoten → Fehlerart |
| `EFFECT_OF` | Fehlerart → Fehlerfolge |
| `HAS_PROCESS_STEP` | Prozesselement → Prozessschritt |
| `HAS_CHILD` | Elternknoten → Kindknoten |

**Kantentypen der Aufwärtstraversierung (upstream):**

| Kantentyp | Beschreibung |
|--------|------|
| `CAUSE_OF` | Fehlerursache → Fehlerart |
| `PREVENTED_BY` | Vermeidungsmaßnahme → Fehlerursache |
| `DETECTED_BY` | Entdeckungsmaßnahme → Fehlerursache/Fehlerart |
| `OPTIMIZED_BY` | Optimierungsmaßnahme → Fehlerart |

> Die BFS-Traversierung geht höchstens 5 Schritte tief.

### 4.5 Berechnung der Risikoveränderung

Für betroffene FailureMode- und FailureCause-Knoten berechnet das System die Veränderung der Risikostufe:

**Fall 1: S/O/D der FailureMode selbst geändert**

RPN und AP (Action Priority) werden neu berechnet und die AP-Stufen vor und nach der Änderung verglichen.

**Fall 2: O/D einer FailureCause ändert sich und betrifft die verknüpfte FailureMode**

Die mit der Cause verknüpfte FailureMode wird ermittelt, O/D/AP der Zeile mit höchster RPN neu berechnet und vor/nach verglichen.

**Fall 3: design_parameter einer Component/ProcessStep geändert**

Verknüpfte FailureModes erhalten `needs_reassessment: true` als Hinweis auf eine nötige manuelle Neubewertung.

### 4.6 Algorithmus der Auswirkungsbewertung

Die Bewertung wird zentral in der Service-Schicht berechnet (0–10 Punkte):

```
score = failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)
score = min(score, 10)  // Höchstens 10 Punkte
```

| Faktor | Gewicht | Beschreibung |
|------|------|------|
| Betroffene Fehlerarten | 2 Punkte je Stück | Anzahl direkt betroffener FailureModes |
| AP-Anstiege | 3 Punkte je Stück | Anzahl AP-Anstiege (L→M, M→H usw.) |
| Fernwirkung | +2 Punkte | Zusatzpunkte bei maximaler Schrittzahl > 2 |

**Farben der Bewertungsstufen:**

| Bewertung | Stufe | Farbe |
|:----:|------|------|
| 0–3 | Niedrig | Grün |
| 4–6 | Mittel | Orange |
| 7–10 | Hoch | Rot |

### 4.7 Ergebnisseite

Auf `/change-impact` zeigt links eine Tabelle die Analysehistorie, rechts ein Panel die Details des gewählten Eintrags.

**Tabelle der Analysehistorie (`ChangeHistoryTable`):**

| Spalte | Beschreibung |
|----|------|
| Zeit | Erstellzeit der Analyse |
| Knotenname | Name des geänderten Knotens |
| Änderungsart | „Attribut“ oder „Struktur“ |
| Auswirkungsbewertung | Tag der Auswirkungsbewertung (farbcodiert) |
| Anzahl betroffener Knoten | summary.total_affected |

**Detailpanel (`ImpactReportPanel`):**

1. **Karte Änderungsinformationen:** Knotenname, Typ, Änderungsart (Tag Attribut/Struktur), Feldname, neuer Wert
2. **Zeile mit Statistikkarten:**
   - Auswirkungsbewertung (ImpactScoreTag)
   - Anzahl betroffener Knoten
   - Anzahl FailureModes
   - AP-Anstiege
3. **Liste betroffener Knoten (`AffectedNodeList`):** ausklappbare Liste, je Knoten:
   - Knotenname und -typ
   - Tag der Auswirkungsart (upstream/downstream/direct)
   - Schrittabstand (hop_distance)
   - Pfadvisualisierung
   - Details der Risikoveränderung (old_ap → new_ap)
4. **Schaltfläche „Im Graphen ansehen“:** springt zu `/fmea/{fmea_id}?tab=graph&highlightNode={node_id}`

### 4.8 API-Abfrageendpunkte

| Endpunkt | Methode | Beschreibung | Berechtigung |
|------|------|------|------|
| `/api/change-impact/analyze` | POST | Auswirkungsanalyse starten | FMEA EDIT |
| `/api/change-impact` | GET | Alle Analysen abfragen (mit Paginierung und Filter product_line_code) | FMEA VIEW |
| `/api/change-impact/fmea/{fmea_id}` | GET | Analysen einer bestimmten FMEA abfragen | FMEA VIEW |
| `/api/change-impact/{analysis_id}` | GET | Details einer einzelnen Analyse abrufen | FMEA VIEW |

**Parameter der Listenabfrage:**

| Parameter | Beschreibung |
|------|------|
| `product_line_code` | Optional, Filter nach Produktlinie |
| `page` | Seitennummer, Standard 1 |
| `page_size` | Einträge pro Seite, Standard 20, höchstens 1000 |

---

## 5. Technische Architektur

### 5.1 Zwei Speicher-Backends

Der Wissensgraph folgt dem **Repository-Muster** mit zwei umschaltbaren Graph-Backends:

| Backend | Klasse | Einsatzbereich | Konfiguration |
|------|-----|----------|------|
| PostgreSQL JSONB | `JSONBRepository` | Entwicklungs-/Testumgebung oder Rückfall bei nicht verfügbarem Neo4j | `GRAPH_REPOSITORY=jsonb` (Standard) |
| Neo4j | `Neo4jRepository` | Produktion mit dokumentübergreifender Graphtraversierung und komplexen Abfragen | `GRAPH_REPOSITORY=neo4j` |

Die Auswahl erfolgt in `app/graph/deps.py` anhand von `settings.GRAPH_REPOSITORY`, die passende Repository-Implementierung wird automatisch injiziert.

### 5.2 Datenprojektion nach Neo4j

FMEA-Graphdaten liegen in der JSONB-Spalte `graph_data` von PostgreSQL und werden über das Outbox-Muster asynchron nach Neo4j projiziert:

```
FMEA Anlegen/Ändern/Statuswechsel
        ↓
  GraphSyncOutbox Einreihen (event_type: fmea.created / fmea.updated / fmea.status_changed)
        ↓
  GraphSyncWorker Polling (alle 5 s, FOR UPDATE SKIP LOCKED)
        ↓
  GraphProjectionService Cypher-Anweisungen erzeugen (idempotente Projektion DELETE + CREATE)
        ↓
  Neo4j Ausführung in Schreibtransaktion
```

**Projizierte Knotenattribute:**

| Attribut | Quelle |
|------|------|
| `node_id` | `id` des Graphknotens |
| `name` | `name` des Graphknotens |
| `type` | `type` des Graphknotens |
| `process_number` / `classification` / `requirement` / `specification` | Fachliche Knotenattribute |
| `severity` / `occurrence` / `detection` / `ap` / `rpn` | Risikoparameter |

**Kantenprojektion:** Nur Kantentypen aus der Whitelist (`ALLOWED_EDGE_TYPES`) werden projiziert, um Cypher-Injection über Benutzereingaben zu verhindern.

**Zuordnung der Knotenlabels:** `PreventionControl` und `DetectionControl` werden in Neo4j auf das Label `Control` abgebildet.

### 5.3 Zuverlässigkeit der Outbox

Die Tabelle `GraphSyncOutbox` sorgt für zuverlässige asynchrone Projektion:

| Feld | Beschreibung |
|------|------|
| `status` | `pending` → `processing` → `completed` / `dead` |
| `attempt_count` | Anzahl Wiederholungen, höchstens 5 |
| `next_attempt_at` | Nächster Wiederholungszeitpunkt (exponentieller Backoff: 10 s → 30 s → 90 s → 270 s) |
| `last_error` | Letzte Fehlermeldung |

**Worker-Mechanismus:**

- Polling-Intervall: 5 Sekunden
- Stapelgröße: 10
- Nebenläufigkeit: atomare Übernahme über PostgreSQL `FOR UPDATE SKIP LOCKED`
- Hängende Aufgaben: beim Start werden Aufgaben im Status `processing` älter als 10 Minuten bereinigt
- Deduplizierung: je `aggregate_id` (FMEA-ID) bleibt nur das neueste Ereignis

### 5.4 Datenmodell

#### Kernentitäten des Wissensgraphen

```
FMEADocument (PostgreSQL)
  ├── fmea_id: UUID (PK)
  ├── document_no: str (Nummer, z. B. PFMEA-2026-001)
  ├── product_line_code: str
  ├── status: str (draft/submitted/approved/rejected)
  ├── graph_data: JSONB        ← Hauptspeicher der Graphdaten
  │     ├── nodes: [{id, name, type, severity, occurrence, detection, ap, ...}]
  │     └── edges: [{source, target, type}]
  └── ...
```

#### Projektionsstruktur in Neo4j

```
(:FMEDocument {fmea_id, document_no, product_line_code})
(:GraphNode {node_id, name, type, severity, occurrence, detection, ap, rpn, ...})
(:Control {node_id, name, type, ...})  ← PreventionControl / DetectionControl einheitliches Label

(:FMEDocument)-[:HAS_NODE]->(:GraphNode)
(:GraphNode)-[:HAS_PROCESS_STEP]->(:GraphNode)
(:GraphNode)-[:HAS_FAILURE_MODE]->(:GraphNode)
(:GraphNode)-[:EFFECT_OF]->(:GraphNode)
(:GraphNode)-[:CAUSE_OF]->(:GraphNode)
(:GraphNode)-[:PREVENTED_BY]->(:Control)
(:GraphNode)-[:DETECTED_BY]->(:Control)
...
```

#### Entitäten der Änderungsauswirkungsanalyse

```
ChangeImpactAnalysis (PostgreSQL)
  ├── id: UUID (PK)
  ├── fmea_id: UUID (FK → fmea_documents)
  ├── product_line_code: str
  ├── factory_id: UUID (FK → factories)
  ├── node_id: str           ← geänderter Knoten ID
  ├── node_type: str         ← Typ des geänderten Knotens
  ├── node_name: str         ← Name des geänderten Knotens
  ├── change_type: str       ← "attribute" oder "structural"
  ├── field_name: str?       ← Name des geänderten Felds
  ├── old_value: str?        ← Wert vor der Änderung
  ├── new_value: str?        ← Wert nach der Änderung
  ├── scope: str             ← Analysebereich (derzeit "single_fmea"）
  ├── status: str            ← Analysestatus ("completed"）
  ├── impact_score: int      ← Auswirkungsbewertung (0-10)
  ├── impact_result: JSONB   ← ChangeImpactResult vollständiges Ergebnis
  ├── created_by: UUID (FK → users)
  └── created_at: datetime
```

### 5.5 Docker-Deployment

`docker-compose.yml` enthält folgende Dienste:

| Dienst | Beschreibung | Port |
|------|------|------|
| `neo4j` | Neo4j 5 Community | 7474 (HTTP), 7687 (Bolt) |
| `graph-worker` | GraphSyncWorker-Prozess | Kein externer Port |

**Neo4j-Konfiguration:**

| Umgebungsvariable | Standardwert | Beschreibung |
|----------|--------|------|
| `NEO4J_URI` | `bolt://localhost:7687` | Verbindungsadresse (Bolt-Protokoll) |
| `NEO4J_USER` | `neo4j` | Benutzername |
| `NEO4J_PASSWORD` | `openqms2026` | Passwort |
| `NEO4J_DATABASE` | `neo4j` | Datenbankname |
| `GRAPH_REPOSITORY` | `jsonb` | Auswahl des Graph-Backends |

**Befehl für manuellen vollständigen Neuaufbau:**

```bash
# Docker in der Umgebung
docker compose exec backend python -m app.cli.graph_rebuild

# mit Zurücksetzen fehlgeschlagener Aufgaben
docker compose exec backend python -m app.cli.graph_rebuild --retry-failed
```

---

## 6. Häufige Fragen

### F1: Der Wissensgraph zeigt „Bitte zuerst eine Produktlinie wählen“

Statistik und Suche des Wissensgraphen hängen vom Produktlinienkontext ab. Bitte oben auf der Seite eine Produktlinie wählen.

### F2: Können Rollen außer admin/manager auf den Wissensgraphen zugreifen?

Die Frontend-Route `/knowledge-graph` prüft nur die Anmeldung, keine Modulrechte; alle angemeldeten Benutzer können die Seite öffnen. Die API ist jedoch geschützt:

- Der Endpunkt `global-stats` erfordert ADMIN
- Bei `similar-nodes` werden Anfragen ohne VIEW in `knowledge_graph` automatisch auf die aktuelle Produktlinie beschränkt
- Produktlinienübergreifende Knotennamen werden geschwärzt

Für vollen Zugriff muss admin der Rolle in der Rollenberechtigungsverwaltung VIEW auf `knowledge_graph` geben.

### F3: Die Seite Änderungsauswirkungsanalyse zeigt keine Einträge

Die Auswirkungsanalyse läuft nicht automatisch, sondern wird im FMEA-Grapheneditor manuell ausgelöst. Den Graph-Reiter eines FMEA-Dokuments öffnen, einen Knoten wählen und die Analyse starten.

### F4: Bedeutet eine Auswirkungsbewertung von 0 „keine Auswirkung“?

Die Formel `failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)` kann 0 ergeben, obwohl die Liste betroffener Knoten nicht leer ist. 0 bedeutet nur: keine betroffene FailureMode, kein AP-Anstieg und maximale Schrittzahl ≤ 2. Die Liste betroffener Knoten sollte trotzdem geprüft werden.

### F5: Was unterscheidet die Backends Neo4j und JSONB?

| Eigenschaft | JSONB | Neo4j |
|------|-------|-------|
| Deployment-Abhängigkeit | Keine zusätzlichen Abhängigkeiten | Neo4j-Dienst erforderlich |
| Dokumentübergreifende Abfrage | Durchläuft die JSONB-Daten aller FMEAs | Cypher-Graphabfrage |
| Aktualität | Liest die neuesten Daten aus PostgreSQL | Abhängig von asynchroner Outbox-Synchronisation (ca. 5 s Verzögerung) |
| Performance | Langsamer bei vielen Dokumenten | Bessere Traversierungsleistung |
| Einsatzbereich | Entwicklung, Test, kleine Deployments | Produktion, große Datenmengen |

Für die Produktion wird das Neo4j-Backend empfohlen. Mit `GRAPH_REPOSITORY=jsonb` werden alle Graphabfragen direkt aus den JSONB-Feldern in PostgreSQL berechnet, ohne Neo4j und Worker.

### F6: Welche Wiederholungsstrategie nutzt der GraphSyncWorker?

Der Worker nutzt exponentiellen Backoff: nach dem 1. Fehlschlag 10 Sekunden, nach dem 2. 30, nach dem 3. 90, nach dem 4. 270 Sekunden; nach dem 5. Fehlschlag wird `dead` gesetzt und nicht weiter versucht. `python -m app.cli.graph_rebuild --retry-failed` setzt dead-Aufgaben zurück.

### F7: Sind die Daten der globalen Statistik sicher?

Der Endpunkt `global-stats` ist nur für admin zugänglich, die Daten werden per Whitelist neu aufgebaut und Namen geschwärzt. Knotennamen behalten nur die ersten 2 Zeichen, der Rest wird `***`, um produktlinienübergreifenden Abfluss sensibler Daten zu verhindern. `similar-nodes` schwärzt produktlinienübergreifende Knoten ohne globale Berechtigung ebenso.

### F8: Was unterscheidet „Attributänderung“ und „Strukturänderung“?

- **Attributänderung (`attribute`):** ändert Feldwerte bestehender Knoten, etwa S/O/D einer Fehlerart. Die Traversierungsrichtung hängt vom Feld ab – S/O/D in beide Richtungen, Name/Beschreibung gar nicht.
- **Strukturänderung (`structural`):** fügt Knoten und Verbindungen hinzu, löscht oder verschiebt sie. Es wird nur die nachgelagerte Auswirkungskette verfolgt.

### F9: Wie gelangen FMEA-Knoten in den Wissensgraphen?

Alle Knoten im JSONB-Feld `graph_data` der FMEA-Dokumente (über Neo4j-Projektion oder direkte JSONB-Abfrage) bilden die Knotenmenge des Wissensgraphen. Die Kanten (`edges`) definieren die Beziehungen zwischen Knoten. Suche und Statistik des Wissensgraphen aggregieren dokumentübergreifend über diese Knoten und Kanten.