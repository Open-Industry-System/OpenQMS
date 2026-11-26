# OpenQMS-Entwicklungsfahrplan

**Stand**: 2026-09-06
**Aktuelle Phase**: Stabilisierungs-Gate für den Release Candidate bestanden (Branch-Review und Integration ausstehend)
**Produktumfang**: Phase 1–4 + Phase 4+ abgeschlossen; Übergang zu Branch-Review und Pilotvorbereitung
**Versionsziel**: v3.0 (Release mit vollem Funktionsumfang)

---

## Überblick

```
Phase 1 (M1-M4)          Phase 2 (M5-M8)          Phase 3 (M9-M12)         Phase 4 (M13-M16)
Basisplattform + Kern     Lieferanten-/Kunden-      KI + Wissensgraph         Erweiterte Analytik +
module                    qualität                                            Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
██████████████████████████ █████████████████████████ █████████████████████████ █████████████████████████
    abgeschlossen              abgeschlossen              abgeschlossen              abgeschlossen
```

---

## Phase 1: Basisplattform + Kernmodule (Monat 1–4)

### MVP (M1–M2): geschlossener Kernkreislauf ✅ abgeschlossen

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| Docker-Compose-Entwicklungsumgebung | P0 | ✅ fertig | PostgreSQL + Redis + containerisiertes Front-/Backend |
| Authentifizierung (JWT + RBAC) | P0 | ✅ fertig | Anmeldung/Registrierung/Rollenrechte (admin/engineer/viewer) |
| Datenarchitektur Produktlinie | P0 | ✅ fertig | JSONB-Graphspeicherung, eine Produktlinie DC-DC-100 |
| PFMEA-Editor | P0 | ✅ fertig | Prozessablauf-Panel + Tabellenbearbeitung von Knoten/Kanten + RPN-Berechnung + Statusübergänge |
| 8D/CAPA-Workflow | P0 | ✅ fertig | D1–D8-Schritte + Phasenformulare + FMEA-Verknüpfung |
| Dashboard | P0 | ✅ fertig | 7 KPI-Karten + Datenübersicht |
| Basis-Audit-Log | P0 | ✅ fertig | Tabelle für das AuditLog-Modell |

### MVP-Fehlerbehebung und Bedienoptimierung ✅ abgeschlossen (2026-05)

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| Fachliche RBAC-Einschränkungen | P0 | ✅ fertig | Nur Admin/Manager geben FMEA/CAPA frei, Oberfläche für Nur-Lese-Benutzer ausgegraut |
| Entprellung häufiger Schreibzugriffe | P0 | ✅ fertig | Entprellung und Speichern beim Fokusverlust für 8D-/FMEA-Texteingaben, keine konkurrierenden Schreibzugriffe |
| Formular für das 8D-Team (D1) | P1 | ✅ fertig | Tabelle mit dynamischem Hinzufügen/Entfernen statt JSON-Textfeld |
| Automatisches Audit-Log | P1 | ✅ fertig | Anlegen/Ändern/Löschen und Statusübergänge von FMEA und CAPA erzeugen echte AuditLog-Einträge |

### M3–M4: Kernerweiterungen ✅ abgeschlossen

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| DFMEA-Editor | P0 | ✅ fertig | Aufgliederung System→Subsystem→Bauteil + Matrix der Konstruktionsparameter |
| DFMEA-Regel-Engine | P0 | ✅ fertig | Geführte Regeln nach den 7 Schritten AIAG-VDA: ① Umfang (5T) → ② Strukturanalyse (Blockdiagramm/Grenzdiagramm/Strukturbaum) → ③ Funktionsanalyse (Funktionsbaum/P-Diagramm) → ④ Fehleranalyse (Fehlerkette FE-FM-FC) → ⑤ Risikoanalyse (S/O/D + AP) → ⑥ Optimierung (Vermeidungs-/Entdeckungsmaßnahmen) → ⑦ Dokumentation. Kernregeln: Ableitung untergeordneter Funktionen aus der Strukturebene, Fehlerarten durch Negation von Funktionen, automatische Verknüpfung der Fehlerkette, AP-Tabelle bestimmt H/M/L und schlägt Optimierungsrichtungen vor |
| Produktionslenkungsplan-Editor + FMEA-Kopplung | P0 | ✅ fertig | Produktionslenkungsplan per Klick aus der PFMEA, bidirektionale Synchronisation |
| SPC-Regelkarten (v1.0+v1.1) | P0 | ✅ fertig | X-quer-R / I-MR / Histogramm / P/NP/C/U / 8 Auffälligkeitsregeln / Eingabe manuell, als Stapel oder per API / Prozessfähigkeit Cp/Cpk/Pp/Ppk / gestufte Warnungen → 8D / mehrere Versionen der Eingriffsgrenzen |
| SPC-Regelkarten für attributive Merkmale (v1.1) | P1 | ✅ fertig | P-, NP-, C-, U-Karte |
| Versionen der Eingriffsgrenzen (v1.1) | P1 | ✅ fertig | Automatische Versionsnummer + Umschaltung per Drawer |
| Durchgängige Verwaltung besonderer Merkmale | P0 | ✅ fertig | CC/SC-Kennzeichen + FMEA→CP-Kopplung + Abdeckungsmatrix + manuelles Anlegen + Warnung nach Bedeutung + MSA-Rückmeldung + dynamische Produktlinie |
| Verwaltung von Produktsicherheitsmerkmalen | P0 | ✅ fertig | Erkennung von Sicherheitsmerkmalen + besonderer Freigabeprozess + automatische FMEA-Vorschläge + Mitzeichnungsbenachrichtigung + Freigabe-Zustandsautomat + Dashboard-KPI |
| Qualitätsziele | P1 | ✅ fertig | Dreistufiger Zielbaum (Unternehmen→Produktlinie→Prozess) + Freigabeablauf + Dashboard |
| Interne Audits | P0 | ✅ fertig | System-/Prozess-/Produktaudit + Checklisten + Feststellungen + CAPA-Kopplung |
| FMEA/CP-Versionsverwaltung | P1 | ✅ fertig | Versionshistorie + Änderungsvergleich + hervorgehobene Unterschiede |
| Managementbewertung | P1 | ✅ fertig | Automatisch zusammengestelltes Datenpaket nach ISO 9001 §9.3 + Maßnahmenverfolgung (inkl. Wirksamkeitsprüfung) + manuelle Eingaben |
| MSA – Messsystemanalyse | P1 | ✅ fertig | Prüfmittelverwaltung und Kalibrierung + GR&R (Mittelwert-Spannweiten-Methode) + Bias + Linearität + Stabilität + attributive Analyse (Kappa), mit Rechenkern, API und Visualisierung, vollständig getestet |

**Abnahmekriterium**: Alle Kernmodule live, interne Beta nutzbar

---

## Phase 2: Lieferanten-/Kundenqualität (Monat 5–8) ✅ im Wesentlichen abgeschlossen

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| Lieferantenstammdaten | P0 | ✅ fertig | Stammdaten + Zertifikate + Freigabestatus + Zulassungsablauf + Leistungsbewertung (gemischte Kennzahlen + Einstufung A/B/C/D); Erweiterungspunkt: Phase-2-IQC ergänzt die n:m-Tabelle supplier_audit_links für mehrfache Wiederholungsaudits |
| Wareneingangsprüfung (IQC) | P0 | ✅ fertig | AQL-Stichprobenpläne + Prüflosverwaltung + Entscheid (AQL-Engine nach ISO 2859-1, mit Klonen zur Wiederholungsprüfung und Prüfdetails) |
| Dashboard Lieferqualität | P0 | ✅ fertig | Lieferanten-PPM / Losannahmequote / Liefertreue / Verteilung der Einstufung / Lieferantenranking / Vergleich / Excel-Export |
| SCAR + 8D-Kopplung | P1 | ✅ fertig | IQC-Rückweisung löst SCAR → geschlossenen 8D-Kreislauf aus; Lebenszyklus mit 5 Status + eigene Routen + Listen-/Detailseiten |
| Reklamationsmanagement | P0 | ✅ fertig | Erfassung + Klassifizierung/Schwere + Chargenrückverfolgung + Bearbeiter + Anhangsmetadaten + Überfälligkeitswarnung + CAPA/FMEA-Kopplung; SCAR-Schnittstelle vorbereitet |
| RMA – Rücksendungen | P0 | ✅ fertig | Rücksendeerfassung + Charge/Seriennummer + Sendungsnummer + Fehleranalyse + Verantwortungszuordnung + CAPA/FMEA-Kopplung; SCAR-Schnittstelle vorbereitet |
| Dashboard Kundenqualität | P0 | ✅ fertig | Reklamationen, Rücksendungen, Risikoampel, PPM-Schätzung; 0-km-PPM (Versandtabelle), SPC-CPK, Gewährleistungskosten, Kundenzufriedenheit, Zusammenfassung Kundenaudits |
| Lieferantenaudits und Leistungsbewertung | P1 | ✅ in Lieferantenstammdaten integriert | Teil des Lieferantenmoduls |
| Kundenaudits | P1 | ✅ fertig | Auditplanung + Verfolgung von Feststellungen + Abschluss der Korrekturen (nutzt die Routen audit_plan/audit_finding, Listen-/Detailseiten + Kundenbestätigung) |
| Massenimport/-export (Excel) | P2 | ✅ fertig | Kompatibel mit xls/xlsx (gemeinsames Werkzeug backend utils/excel.py + Frontend-Komponente ImportExcelDialog, eingesetzt bei Lieferanten/SPC/IQC) |
| APQP – Qualitätsvorausplanung | P1 | ✅ fertig | Fünf Phasen-Gates + Verkettung der Core Tools + Gantt-Diagramm + Checklisten der Phasenergebnisse |
| PPAP-Verwaltung | P1 | ✅ fertig | Einreichung und Freigabe der 18 AIAG-Elemente, Lebenszyklus mit 5 Status (draft/under_review/approved/rejected/resubmit), Pflichtelemente je Level 1–5, Statusübergänge pro Element, Listen-/Detailseiten |
| Produktlinienauswahl | P0 | ✅ fertig | Tabelle product_lines + globale Auswahl + einheitlicher Filter in allen Modulen + Prüfung in der Service-Schicht |
| SCAR über scar_ref_id | P1 | ✅ fertig | SCAR per Klick aus lieferantenverschuldeten Reklamationen/RMAs, bidirektionale Verknüpfung, transaktionssicher per savepoint |
| Versanddaten für 0-km-PPM | P1 | ✅ fertig | Tabelle shipment_records + CRUD + PPM-Fallback-Kette (Parameter → Summe der Versanddaten → Jahresversandmenge) |
| CSR/VOC → Produktionslenkungsplan | P1 | ✅ fertig | Kundenspezifische Anforderungen per Klick in das Feld customer_requirements des Produktionslenkungsplans, manuelle Einträge bleiben erhalten |
| Erweitertes Dashboard Kundenqualität | P2 | ✅ fertig | SPC-CPK/PPK, Gewährleistungskosten, Kundenzufriedenheit, Zusammenfassung Kundenaudits; Filter nach Kunde/Produktlinie |

**Dunkles Industrie-Dashboard (abgeschlossen 2026-06-01)**: ConfigProvider mit darkAlgorithm und eigenen Tokens (eine Quelle), neu geschriebenes Dashboard (KPI-Statusmatrix, offene Punkte, letzte Aktionen mit relativer Zeit, Schnellzugriffe – für viewer ausgeblendet), responsives Einklappen auf kleinen Bildschirmen, ARIA-Landmarken, Tastaturnavigation, prefers-reduced-motion, Kontrast nach WCAG AA; AppLayout ohne hartcodierte Farben.

**Abnahmekriterium**: Release GA v1.0 – Lieferanten-/Kundenmodule live

---

## Phase 3: KI + Wissensgraph (Monat 9–12) ✅ abgeschlossen

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| Neo4j-Infrastruktur für den Wissensgraphen | P1 | ✅ fertig | Neo4j-Docker-Dienst + Repository-Abstraktion (Neo4j/JSONB) + API-Routen |
| Visualisierung des Wissensgraphen (G6 v5) | P1 | ✅ fertig | Reiter „Graph“ in der FMEA (Kräfte-/Hierarchie-Layout, Klick/Doppelklick/Kontextmenü, Hervorhebung von Auswirkungs-/Ursachenpfaden) + globale Seite `/knowledge-graph` (Risikokarte, FMEA-übergreifende Statistik, Stichwortsuche, Sprung zu Knoten) |
| Globale Wissensbasis | P1 | ✅ fertig | FMEA-übergreifende Knotenstatistik (AP-Verteilung, Knoten mit hohem AP, mittlere RPN, Top-Fehlerarten) + Stichwortsuche nach ähnlichen Knoten + Schwärzung per Pydantic-Antwort-Whitelist |
| LLM-RAG-Semantiksuche | P2 | ✅ fertig | pgvector + hybride Suche (Vektor-Kosinus + tsvector-Volltext) + RRF-Fusion + RAG-Fragen mit Quellenangaben + 6 Entitätstypen (FMEA/CAPA/Audit/Reklamation/SCAR/RMA) + Produktlinientrennung + Vorfilter nach Modulrechten + asynchroner Embedding-Worker + Nachfüllbefehl |
| Intelligente Empfehlungen im FMEA-Editor | P2 | ✅ fertig | Hybrides Empfehlungssystem (Regel-Engine + Ähnlichkeit im Wissensgraphen + optionales LLM) + PostgreSQL-Cache + Inline-Dropdown SmartSuggestionDropdown (5 Auslöser × 6 Spalten, 500 ms Entprellung, Tastaturnavigation, Rückfallhinweis) + Produktlinien-Zugriffskontrolle + Rate-Limit; mehrere LLM-Anbieter (Claude/OpenAI/lokal) + Quellenkennzeichnung |
| 8D-Empfehlungen für Grundursachen und Maßnahmen | P2 | ✅ fertig | Hybride Pipeline D4/D5 (HybridRecommendationPipeline): D4 mit vier Quellen (FMEA-Graphabgleich + RAG-Semantiksuche + historische CAPA + Regel-Engine), D5 mit drei Quellen + Erweiterung um Lenkungsmaßnahmen; FusionEngine dedupliziert/sortiert, LLMFusionLayer verfeinert; Empfehlungspanel (übernehmen/überspringen) + Nur-Lese-Rechte |
| Änderungsauswirkungsanalyse (Graphtraversierung) | P2 | ✅ fertig | Änderung von Konstruktionsparametern → automatische Ermittlung des Auswirkungsbereichs; BFS auf Neo4j/JSONB + AP-Prognose + Auswirkungsbewertung + Audit-Log + Bericht/Graph im Frontend |
| SPC-FMEA-Empfehlungen bei Auffälligkeiten | P2 | ✅ fertig | Auffälligkeit in der Regelkarte → zugehörige FMEA → 8D-Vorschlag; zwei Abgleichpfade (über Produktionslenkungsplan + unscharfer Namensabgleich) + Anreicherung (RPN/AP/Pfad/Ursache/Anzahl Maßnahmen) + Empfehlungsdialog + automatische CAPA-Verknüpfung |
| D7-Hinweise zur Wiederholungsvermeidung | P2 | ✅ fertig | D7 schlägt verknüpfte FMEA-Fehlerarten vor (Graphabgleich + Stichwortsuche) + Sprung per Klick + automatisches Übernehmen von D5-Maßnahmen + weiches Gate vor D8 (Dialog für unbestätigte Punkte, Überspringgrund im Audit-Log); Produktlinientrennung + doppelte CAPA/FMEA-Rechteprüfung |
| Gemeinsames Bearbeiten | P2 | ✅ fertig | Optimistische Sperre + kurzes Polling der Anwesenheit: Liste der anwesenden Benutzer in FMEA/Produktionslenkungsplan + Bearbeitungsanzeige je Zeile + 409-Konflikterkennung + Drei-Wege-Diff + sicheres Überschreiben; CAPA/APQP usw. nur mit Anwesenheitsanzeige |

Ergänzt bis 2026-06-03: Anbindung der FMEA-Empfehlungen an die Ähnlichkeit im Wissensgraphen samt Quellenkennzeichnung, Ausbau der D4/D5-Pipeline (historische CAPA, LLM-Verfeinerung, RAG statt Teilzeichenkettenabgleich) und Schwärzung der globalen Wissensbasis bei produktlinienübergreifender Aggregation.

**Abnahmekriterium**: Release GA v2.0 – KI + Wissensgraph live

---

## Phase 4: Erweiterte Analytik + Integration (Monat 13–16) ✅ abgeschlossen

| Funktion | Priorität | Status | Beschreibung |
|------|--------|------|------|
| MES-Konnektor | P2 | ✅ fertig | Mock- und REST-Konnektor; 9 Tabellen; zuverlässiges Senden per Outbox; 3 Datenarten (Fertigungsaufträge/Anlagenstatus/Ausschuss); SPC-Alarme; API-Key-Authentifizierung; verschlüsselte Zugangsdaten; 4 Frontend-Seiten; Echtzeit-Aggregation im Dashboard; Produktlinientrennung; 33 Nebenläufigkeitstests |
| PLM-Konnektor | P2 | ✅ fertig (2026-06-09) | Abfrage des PLM-Stücklistenbaums/Import in die FMEA + Bestätigung besonderer Merkmale Part→SC; Mock-Konnektor; 9 PLM-Tabellen; 4 Frontend-Seiten (Dashboard/Connections/Parts/ChangeOrders); doppelte Rechteprüfung; 46 Backend-Regressionstests + 11 Frontend-Rechtetests |
| ERP-Konnektor | P2 | ✅ fertig (2026-06-11) | Integration der Geschäfts- und Lieferkettendaten; 9+1 Synchronisationsobjekte; 12 Tabellen; Mock- und REST-Konnektor; DAG-Synchronisation in 4 Phasen; doppelte Verknüpfung (suppliers/shipments); vier Kostenarten der COQ; Schwärzung auf Feldebene; bidirektionale Chargenrückverfolgung; 6 Frontend-Seiten; 30 Tests grün |
| KI-Entwurf für 8D-Berichte | P3 | ✅ fertig | LLM-gestütztes Ausfüllen von D2–D8; strukturiertes oder Fließtextformat; Formatpräferenz in localStorage; Vorschau mit Bestätigung (ersetzen/anhängen/abbrechen); Rückgängig; Rechteprüfung (nur der aktuelle Schritt); eigenes Audit-Log; Rate-Limit; FMEA-Kontext; Produktlinientrennung |
| KI-Interpretation von Qualitätstrends | P3 | ✅ fertig | Dashboard-Widget: Regelzusammenfassung + LLM-Tiefenanalyse auf Abruf; Aggregation aus SPC/CAPA/FMEA; Filter nach Modulrechten; Cache über Evidenz-Hash; Rate-Limit + Audit-Log; Veraltungserkennung im Frontend |
| Intelligente Zustellung von Lessons Learned | P3 | ✅ fertig (2026-06-10) | 5 Quelladapter (FMEA-Stichworte, CAPA-Semantik, Auditfeststellungen, Semantiksuche, Regel-Engine) + Fusionsranking + rechtegetrennter Cache + Modal im Frontend; 14 Unit-Tests |
| Intelligente Prüfung von Produktionslenkungsplänen | P3 | ✅ fertig (2026-06-11) | Regel-Engine mit 4 Regeln (fehlende Lenkungsmethode/Reaktionsplan, FMEA-Konsistenz, Abdeckung besonderer Merkmale) + Zwei-Tabellen-Modell (findings mit stabiler Identität + occurrences als Snapshot) + Sammel-API + Prüfpanel/Badges + automatische Auslösung; 30 Tests |
| Intelligente Optimierung der IQC-Stichprobenpläne | P3 | ✅ fertig | Dynamische AQL-Anpassung nach Qualitätshistorie; kombinierte Regel-Engine (10 Regeln) + mehrstufige Freigabe (engineer/manager) + Qualitätsprofil + Auslöser PPM/SCAR/Sicherheitsfehler; 4 neue Tabellen + konfigurierbare Parameter; 4 Frontend-Seiten; 18 Unit-Tests |
| Intelligente Lieferanten-Risikowarnung | P3 | ✅ fertig (2026-06-11) | Regel-Engine mit 10 Regeln (Qualität/Lieferung/Compliance) + gewichtete Bewertung + 4 Risikostufen + Stapelbewertung + tägliche Auslösung + inkrementelle Auslösung durch IQC-Entscheide + geschlossener Kreislauf mit SCAR/CAPA + Benachrichtigung per E-Mail/Webhook (SSRF-Schutz + Fernet-Verschlüsselung) + Risikomatrix + Regelkonfiguration + Kanalverwaltung; 45 Tests grün |
| Automatischer Bericht zur Managementbewertung | P3 | ✅ fertig (2026-06-12) | Eingangsdaten zusammenfassen → Berichtsentwurf, mit KI-Erzeugung, manueller Bearbeitung, Finalisierung/Archivierung und Versionshistorie |
| Risikokarte der Lieferkette | P3 | ✅ fertig (2026-06-12) | Mehrdimensionale Heatmap der Lieferrisiken + Produktlinientrennung + Vormonatsvergleich + Lieferantendetail/-vergleich + 6-Monats-Trend + zeitgesteuerte Snapshots (pg_try_advisory_lock) + CSV-/Excel-Export |
| Eigene Dashboards (Drag & Drop) | P3 | ✅ fertig | Layout per react-grid-layout, Widget-Bibliothek (18 Widgets), Layout je Benutzer gespeichert, Produktlinienfilter, Rechteprüfung |
| Mehrwerksbetrieb | P3 | ✅ fertig (2026-06-12) | Eine Datenbank + zeilenweise Trennung über factory_id + dreistufiges Scope-Modell + Konzernauswertung |
| SaaS-Mandantenarchitektur | P3 | ✅ fertig (2026-06-13) | Schema-per-tenant + getrennte Plattform-/Mandanten-Basis + JWT-Domänentrennung + API zur Mandantenanlage |

### Umsetzungsdetails Phase 4 (Kurzfassung)

- **MES (2026-06-05)**: Migration mit 9 Tabellen und CHECK-Constraints (alembic/030); Konnektor-ABC mit Mock/REST (Paginierung, Retry, Auth, Feldzuordnung); SHA-256-Hash der API-Keys, Fernet-verschlüsselte ausgehende Zugangsdaten; Ingestion inkl. Messwert→SPC; Synchronisation mit SKIP LOCKED und claim_token; Outbox mit 3 kurzen Transaktionen, at-least-once und idempotenter event_id; 7-Tage-Archivierung; 13 Endpunkte; 33 pytest-Nebenläufigkeitstests.
- **PLM (2026-06-09)**: 9 Tabellen (alembic/031); Stücklistenimport in die FMEA und Bestätigung besonderer Merkmale; gleiche Muster für Zugangsdaten, Synchronisation und Outbox wie MES; 13 Endpunkte; 46 Backend- und 11 Frontend-Tests.
- **ERP (2026-06-10)**: Modul `Module.ERP`; 12 Tabellen mit 8 CHECK-Constraints (alembic/032); Mock-Konnektor für 9 Datenarten + REST; DAG-Synchronisation in 4 Phasen; bidirektionale Rückverfolgung; Schwärzung von bank_info/tax_id unterhalb Berechtigungsstufe 4; über 20 Endpunkte; 6 Frontend-Seiten; 5 Code-Review-Runden.
- **Eigene Dashboards (2026-06-09)**: Tabelle user_dashboard_layouts (JSONB, je Benutzer); GET/PUT des Layouts; WidgetLibraryPanel + WidgetWrapper; viewer ohne Bearbeitungsschaltflächen, Backend-403.
- **KI-Qualitätstrend (2026-06-10)**: QualityTrendService, normierter scope_hash, LLM-Timeout-Behandlung, Audit-Typ ai_interpretation, Endpunkt POST /dashboard/quality-trend/interpret.
- **Lieferanten-Risikowarnung (2026-06-11)**: 3 Tabellen mit partiellen eindeutigen Indizes; 10 reine Regelfunktionen (R01–R10); Gewichtung über alle aktiven Regeln + kritischer Bypass; Konfigurationsauflösung in 4 Ebenen; E-Mail (aiosmtplib) und Webhook (httpx + HMAC-SHA256); 14 Endpunkte.
- **IQC-Stichprobenoptimierung (2026-06-11)**: 4 Tabellen + 2 Spalten, AQL-Stufenabbildung, Qualitätsprofil, über 20 Endpunkte, dynamische AQL-Injektion, Bereinigungs-Coroutine.
- **SaaS-Mandanten (2026-06-13)**: PlatformBase (public) + TenantBase; getrennte Alembic-Zweige; TenantContextMiddleware mit dreistufiger Auflösung (Subdomain → X-Tenant-ID nur dev → JWT) und Statuscodes 503/410/400; search_path pro Anfrage; Plattform-API unter /api/platform/*; issuer/audience-Trennung von Mandanten- und Plattform-JWT; `run_for_each_tenant()` für Hintergrundaufgaben; 5 Sicherheitsaudit-Runden.
- **Risikokarte der Lieferkette (2026-06-12)**: Tabelle supply_chain_risk_snapshots (UNIQUE NULLS NOT DISTINCT); Aggregation aus ERP-Liefertreue, Einkaufsanteil, SCAR und IQC-PPM; 6 Endpunkte; Modul `SUPPLY_CHAIN_RISK_MAP` mit VIEW/EDIT.
- **Mehrwerksbetrieb (2026-06-12)**: Tabellen Factory/UserFactory/SupplierSharedProfile, `factory_id` mit Nachfüllung und NOT NULL in ~50 Geschäftstabellen; FactoryScope/ProductLineScope/PermissionScope; Modul `GROUP`; Konzernrouten /api/group/*; automatische factory_id-Injektion in Axios und Werksauswahl.

**Abnahmekriterium**: Release GA v3.0 – voller Funktionsumfang

---

## Phase 4+: FMEA-Assistenten und Bedienoptimierung (2026-06-14 bis 2026-06-25) ✅ abgeschlossen

Nach Phase 4 wurden FMEA-Editor und Erzeugungsassistenten weiterentwickelt: geführte Modellierung nach den 7 Schritten AIAG-VDA, schreibgeschützte Ansicht von Versions-Snapshots, sicheres Löschen und Stammdaten für Produkttypen – jeweils mit Front- und Backend-Tests.

| Funktion | Status | Beschreibung |
|------|------|------|
| PFMEA-Assistent nach 7 Schritten | ✅ fertig | `PFMEAWizardPage`: Schritt 0 Umfang → 1 Strukturbaum → 2 Funktionsbaum (`FunctionTreeEditor`, 3 Funktionsebenen + `FUNCTION_MAPPED_TO` + CC/SC) → 3 Fehlerkette (4M-Kontext) → 4 Risikotabelle (`RiskTable`, Bedeutung als Maximum der Ebenen, CC/SC schreibgeschützt aggregiert, O/D-Gates) → 5 Optimierung (AP=H + empfohlene Maßnahmen) → 6 Abschluss-Gate; dazu `usePfmeaWizardValidation` (4M/OP-Gates, dreistufige Bedeutung, CC/SC-bewusst) + `PFMEAWizardSidebar` + `PFMEAGuidanceCard` + `wizardCascadeDelete` |
| Erweiterungen des DFMEA-Assistenten | ✅ fertig | Zeitraum als `DatePicker.RangePicker`; KI-Empfehlungen für 5T-Werkzeuge/-Trends (Auslöser `pfmea_tool` / `pfmea_trend` + 4M-Regeln); KI-Empfehlungen in Schritt 3 (`SmartSuggestionDropdown` an Backend-Auslöser statt Regel-Stub); Risikoanalyse in Schritt 5 mit Kontext aus Schritt 4 + PC/DC vor dem Anlegen; KI-Empfehlungen für PC/DC; Strukturleitfaden (`ToolStructureGuide`) + `ScopeTagField` |
| Schreibgeschützte Ansicht von FMEA-Versionen | ✅ fertig | Im Editor über den Zustand `viewingVersion` eingebettete Vorschau historischer Versionen (`FMEAVersionSnapshot` / `CPVersionSnapshot`) statt Platzhalterseite; die aktuelle Bearbeitbarkeit bleibt unverändert |
| FMEA löschen | ✅ fertig | Listenseite erlaubt das Löschen in `draft` / `rework`; das Backend lehnt andere Status ab; vor dem Löschen setzt `_null_out_fmea_references` Fremdschlüssel verknüpfter Datensätze (`control_plan`, `capa` usw.) auf NULL, um IntegrityError → 500 zu vermeiden; mit FK-Regressionstests |
| Stammdaten Produkttyp | ✅ fertig | Tabelle `product_types` (code als Schlüssel + name + Beschreibung + is_active) + Fremdschlüssel `product_lines.product_type_code` (`ondelete=RESTRICT`) + Backend-API (list/create/update/delete) + Verwaltungsseiten `ProductTypePage` / `ProductLinePage` (Schutz `requireAdmin`) + Filter `product_type` in der Semantiksuche; werksübergreifend geteilte Stammdaten |
| Übersichtlicheres FMEA-Graphlayout | ✅ fertig | Richtung von `CAUSE_OF` korrigiert + standardmäßig hierarchisch von oben nach unten + Kantenfarbe je Zweig + Legende der Kantentypen + Richtungsumschaltung per Segmented + PNG-Export mit Hintergrund; `toG6Data` / `graphLayoutOptions` / `GraphDirection` nach utils ausgelagert |
| Drag & Drop im Strukturbaum mit @dnd-kit | ✅ fertig | Das native HTML5-DnD stieß nach 8 Iterationen bei n≥2 Schritten an architektonische Grenzen; Umstieg auf `@dnd-kit` (`FMEAEditorDragSort`) für stabiles mehrstufiges Sortieren |
| Empfehlungs-Cache und Gültigkeitsbereich | ✅ fertig | Upsert in `recommendation_cache` korrigiert + Trennung der Vorbedingungen der KG-Ansicht (stabile CI) + engerer `recommendation_scope` |

**Abnahmekriterium**: Der gesamte FMEA-Ablauf (manuelle Modellierung + Assistent + Versionsrückblick + sicheres Löschen) funktioniert durchgängig, Front- und Backend-Regression grün.

---

## Projektkennzahlen (Stand 2026-06-25)

| Kennzahl | Anzahl |
|------|------|
| Git-Commits | 1.060+ |
| Python-Dateien im Backend | 215+ |
| TS/TSX-Dateien im Frontend | 195+ |
| API-Routenmodule | 37 (auth/fmea/capa/dashboard/iqc/scar/supplier/customer/spc/msa/ppap/apqp/audit/management_review/erp/group/supply_chain_risk_map/platform …) |
| Frontend-Seiten | 75+ TSX-Seiten |
| Datenbanktabellen | 109+ (inkl. 12 ERP-Tabellen, Werks-/Konzernverknüpfungen, Snapshot der Lieferkettenrisiken, 4 Plattformtabellen, 114 Geschäftstabellen je Mandant) |
| Zustandsautomaten | 2 (FMEA mit 5 Status, 8D) |
| Seed-Daten | 5 Benutzer + 2 Werke + Demodaten für mehrere Module |

---

## Meilensteine

```
2026 M2   ── ✅ MVP fertig (FMEA + 8D + Dashboard)
2026 M4   ── ✅ Kernmodule live (interne Beta)
2026 M5   ── ✅ Lieferanten-/Kundenmodule fertig (inkl. Erweiterungen)
2026 M5   ── ✅ Infrastruktur und Visualisierung des Wissensgraphen live
2026 M6   ── ✅ Phase 3 KI + Wissensgraph vollständig
2026 M6   ── ✅ Phase 4 erweiterte Analytik + Integration fertig
2026 M6.5 ── ✅ Risikokarte der Lieferkette live
2026 M6   ── ✅ Phase 4+ FMEA-Assistenten und Bedienoptimierung (PFMEA/DFMEA-Assistent nach 7 Schritten, Versionsansicht, sicheres Löschen, Produkttyp-Stammdaten)
2026 M12  ── 🔲 Release GA v2.0
2027 M4   ── 🔲 Release mit vollem Funktionsumfang (GA v3.0)
```

---

## Umsetzungsstand von Teilfunktionen

- **D3 – vorläufige Eindämmungsmaßnahmen**: Umsetzungsstand v4 (2026-07-12) – Import von 4 Datenarten, Bericht zum betroffenen Umfang, KI-Vorschläge zur Eindämmung, Erfassung von Übernahme/Ausführung und Gate D3→D4 sind fertig.

---

## Nächste Schritte

**Stabilisierungs-Gate für den Release Candidate: bestanden**

1. ✅ Abschließender frischer DB-Reset/Migration/Seed: `qms_e2e` mit einzigem Head `20260727_warranty_factory_id`;
2. ✅ Abschließendes `make check`: Backend `1975 passed / 5 skipped / 5 xfailed / 0 failed` (181,95 s), Frontend tsc und Vite-Build bestanden (7,61 s);
3. ✅ Abschließendes Playwright (ohne Retries): 44 insgesamt, `42 passed / 0 failed`, nur zwei erlaubte inverse Skips;
4. ✅ Abschließendes CAPA-PPT: `f3f5753b-cbd6-45ba-818b-c51df70a9d83` Runde 1 `passed`, 11 Folien/Träger/DB/Audit bestanden, `issues=[]`, nicht leere suggestions sind nur Hinweise;
5. ✅ Kein werksübergreifendes Datenleck und keine Seiteneffekte beim gemeinsamen Bearbeiten; abschließender Ausschnitt des Integrationsmenüs `2/2 passed`;
6. ⏳ Review des Stabilisierungsbranches und Entscheidung über die Integration in `main` stehen noch aus.

**Erlaubte Skips im abschließenden Playwright-Lauf**: `no creds: advice endpoint 422 blocked + import still 200 blocked`; `no-LLM: D8 close is blocked (422 outcome=blocked)`. Darüber hinaus keine Fehlschläge und keine unerwarteten Skips.

Den aktuellen Arbeitsstand und offene Punkte führt [PROGRESS.md](../PROGRESS.md).
