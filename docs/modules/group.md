# Modul Konzern-/Mehrwerksverwaltung — Benutzerhandbuch

> Zuletzt aktualisiert: 2026-06-13 | Gilt für: OpenQMS v1.0

---

## 1. Funktionsüberblick

Das Modul Konzern-/Mehrwerksverwaltung (ModuleKey: `group`) bietet der Konzernleitung werksübergreifende Aggregation, Vergleich und Steuerung von Qualitätsdaten. Bei Mehrwerksbetrieb sind die Daten standardmäßig nach Werk getrennt; dieses Modul erlaubt Konzernadministratoren und Managern, über die Grenzen eines Werks hinweg zentral zu steuern.

| Teilmodul | Route | Funktionsumfang |
|--------|------|----------|
| Konzern-Dashboard | `/group/dashboard` | Werksübergreifende Aggregation und Zusammenfassung der KPIs |
| Werksverwaltung | `/group/factories` | Werke anlegen, bearbeiten, deaktivieren; Produktlinien zuordnen |
| Werksvergleich | `/group/comparison` | Horizontaler Vergleich zentraler Kennzahlen der Werke |
| Konzernlieferanten | `/group/suppliers` | Werksübergreifende Sicht auf gemeinsame Lieferanten und Zusammenführung |
| Konzernaudits | `/group/audits` | Werksübergreifende Auditpläne und Verfolgung von Feststellungen |

Alle Routen sind über `ProtectedRoute` geschützt und verlangen mindestens VIEW im Modul `group`.

---

## 2. Rollen und Berechtigungen

Das Berechtigungsmodell ist dreistufig: **ModuleKey × PermissionLevel × Rolle**. Bedeutung von PermissionLevel: 0 = NONE (unsichtbar), 1 = VIEW (nur lesen), 2 = CREATE (anlegen), 3 = EDIT (bearbeiten), 4 = APPROVE (freigeben), 5 = ADMIN (Vollzugriff).

| ModuleKey | admin | manager | field_qe | planning_qe | supplier_qe | customer_qe | viewer |
|-----------|:-----:|:-------:|:--------:|:-----------:|:-----------:|:-----------:|:------:|
| group | 5 (ADMIN) | 3 (EDIT) | — | — | — | — | — |

> `—` in der Tabelle oben bedeutet, dass die Rolle keine Berechtigungszeile im Modul `group` hat (PermissionLevel = NONE) und weder Menü noch Daten der Konzernverwaltung sieht.

**Operationen und Mindestberechtigung:**

| Operation | Erforderliche PermissionLevel | Beschreibung |
|------|----------------------|------|
| Konzern-Dashboard/Vergleich/Lieferanten/Audits ansehen | VIEW (1) | Sichtbar für admin, manager |
| Werke anlegen/bearbeiten/deaktivieren | ADMIN (5) | Nur admin |
| Lieferanten zusammenführen | ADMIN (5) | Nur admin |
| Werke zu Auditplänen hinzufügen/entfernen | ADMIN (5) | Nur admin |

**Wichtige Designentscheidung:** ADMIN im Modul `group` bestimmt zugleich das Ergebnis von `FactoryScope` — Benutzer mit `group:ADMIN` haben `accessible_factory_ids` = `None` (alle Werke sichtbar), Benutzer ohne ADMIN sehen selbst mit VIEW nur die ihnen zugeordneten Werke.

---

## 3. Konzern-Dashboard

**Route:** `/group/dashboard`

### 3.1 Funktionsbeschreibung

Das Konzern-Dashboard fasst die Qualitäts-KPIs aller sichtbaren Werke zusammen und zeigt den Betriebszustand des Konzerns und der einzelnen Werke als Karten.

### 3.2 Kennzahlen

| Kennzahl | Datenquelle | Beschreibung |
|------|----------|------|
| Offene FMEAs (`open_fmea_count`) | `fmea_documents` | Anzahl FMEAs im Status `draft` oder `in_review` |
| Offene CAPAs (`open_capa_count`) | `capa_eightd` | Anzahl 8D-Berichte, die `D8_CLOSURE` oder `ARCHIVED` noch nicht erreicht haben |
| Überfällige CAPAs (`overdue_capa_count`) | `capa_eightd` | Anzahl offener 8D-Berichte mit `due_date < heute`, rot hervorgehoben |
| SPC-Alarme (`active_spc_alarms`) | `spc_alarms` | Anzahl SPC-Alarme im Status `open` |
| Offene IQC-Prüfungen (`pending_iqc_inspections`) | `iqc_inspections` | Anzahl Wareneingangsprüfungen im Status `pending` |
| Offene SCARs (`open_scars`) | `supplier_scars` | Anzahl SCARs mit Status weder `closed` noch `cancelled` |
| Lieferanten-Risikowarnungen (`open_supplier_risk_alerts`) | `supplier_risk_alerts` | Anzahl Risikowarnungen im Status `open` |
| Aktuelle Auditfeststellungen (`recent_audit_findings`) | `audit_findings` | Anzahl in den letzten 90 Tagen angelegter Auditfeststellungen |

### 3.3 Seitenaufbau

- **Summenzeile oben:** Konzernsumme (`factory_name` ist die Summenbezeichnung), 6 KPI-Karten nebeneinander
- **Zeilen je Werk:** Je sichtbarem Werk eine Karte mit den 6 Kennzahlen im 3×2-Raster
- Überfällige CAPAs > 0 werden automatisch rot markiert (`#cf1322`)

### 3.4 API

```
GET /api/group/dashboard
```

**Berechtigung:** mindestens VIEW im Modul `group`

**Antwort:**

```json
{
  "factories": [
    {
      "factory_id": "uuid",
      "factory_code": "DEFAULT",
      "factory_name": "Standardwerk",
      "open_fmea_count": 5,
      "open_capa_count": 3,
      "overdue_capa_count": 1,
      "active_spc_alarms": 2,
      "pending_iqc_inspections": 4,
      "open_scars": 1,
      "open_supplier_risk_alerts": 0,
      "recent_audit_findings": 7
    }
  ],
  "totals": {
    "factory_id": "00000000-0000-0000-0000-000000000000",
    "factory_code": "",
    "factory_name": "Summe",
    ...
  },
  "snapshot_date": null
}
```

`totals.factory_id` verwendet die Null-UUID (`00000000-0000-0000-0000-000000000000`) als Platzhalter.

---

## 4. Werksverwaltung

**Route:** `/group/factories`

### 4.1 Funktionsbeschreibung

Die Werksverwaltung pflegt die Stammdaten der Werke: anlegen, bearbeiten und deaktivieren. Das Werk ist die zentrale Trennungsdimension in OpenQMS — alle Geschäftsdatensätze (FMEA, CAPA, SPC usw.) gehören über das Feld `factory_id` zu einem Werk.

### 4.2 Datenmodell Werk

| Feld | Typ | Pflicht | Beschreibung |
|------|------|:----:|------|
| `code` | String(20) | Pflicht beim Anlegen | Werkscode, global eindeutig, z. B. `DEFAULT`, `SH-02`. Nach dem Anlegen nicht änderbar |
| `name` | String(100) | Ja | Werksname, z. B. `Standardwerk`, `Werk Shanghai` |
| `location` | String(200) | Nein | Werksadresse, z. B. `Pudong, Shanghai` |
| `is_active` | Boolean | Standard true | Kennzeichen aktiv/deaktiviert |

### 4.3 Werk anlegen

**API：** `POST /api/group/factories`

**Berechtigung:** ADMIN (5) im Modul `group`

Request-Body:

```json
{
  "code": "GZ-03",
  "name": "Werk Guangzhou",
  "location": "Huangpu, Guangzhou"
}
```

- `code` darf keinem vorhandenen Werkscode entsprechen, sonst `400`
- Neue Werke haben standardmäßig `is_active = true`

### 4.4 Werk bearbeiten

**API：** `PUT /api/group/factories/{fid}`

**Berechtigung:** ADMIN (5) im Modul `group`

Request-Body (nur zu ändernde Felder):

```json
{
  "name": "Werk Guangzhou (neuer Standort)",
  "location": "Nansha, Guangzhou",
  "is_active": true
}
```

- `code` kann beim Bearbeiten nicht geändert werden
- Jede Änderung wird in die Tabelle `audit_logs` geschrieben

### 4.5 Werk deaktivieren

**API：** `DELETE /api/group/factories/{fid}`

**Berechtigung:** ADMIN (5) im Modul `group`

- Das Deaktivieren setzt `is_active` auf `false`, statt physisch zu löschen
- Wird das Werk noch von aktiven Produktlinien referenziert (Datensätze mit `is_active = true` unter `product_lines.factory_id`), schlägt das Deaktivieren mit `400` fehl: Meldung, dass das Werk noch von N aktiven Produktlinien referenziert wird
- Zuerst die verknüpften Produktlinien deaktivieren oder in ein anderes Werk verschieben, dann das Werk deaktivieren
- Deaktivierte Werke erscheinen nicht mehr in aggregierten Daten wie Dashboard und Vergleich

### 4.6 Zuordnung von Produktlinien zu Werken

Produktlinien sind über `product_lines.factory_id` einem Werk zugeordnet. In der aktuellen Version wird die Zuordnung so festgelegt:

- In den Seed-Daten gehören `DC-DC-100` und `PCB-SMT-200` zum Werk `DEFAULT`, `SH-DC-200` zu `SH-02` (Werk Shanghai)
- Beim Anlegen einer Produktlinie leitet `resolve_create_factory_id` die `factory_id` automatisch ab: bevorzugt das an die Produktlinie gebundene Werk, sonst `default_factory_id` des Benutzers

---

## 5. Werksvergleich

**Route:** `/group/comparison`

### 5.1 Funktionsbeschreibung

Der Werksvergleich zeigt die zentralen Kennzahlen der Werke in einer horizontalen Tabelle, damit die Leitung Unterschiede und Problemwerke schnell erkennt.

### 5.2 Vergleichskennzahlen

Standardmäßig werden 8 Kennzahlen verglichen (wie die Dashboard-KPIs):

| Kennzahlschlüssel | Bezeichnung |
|--------|--------|
| `open_fmea_count` | Offene FMEAs |
| `open_capa_count` | Offene CAPAs |
| `overdue_capa_count` | Überfällige CAPAs |
| `active_spc_alarms` | SPC-Alarme |
| `pending_iqc_inspections` | Offene IQC-Prüfungen |
| `open_scars` | Offene SCARs |
| `open_supplier_risk_alerts` | Lieferanten-Risikowarnungen |
| `recent_audit_findings` | Aktuelle Auditfeststellungen |

Über den Abfrageparameter `metric_names` lassen sich bestimmte Kennzahlen wählen, zum Beispiel:

```
GET /api/group/comparison?metric_names=open_capa_count,overdue_capa_count,active_spc_alarms
```

### 5.3 Darstellung

Die linke Spalte zeigt fest `factory_code` und `factory_name`, die übrigen Spalten entstehen dynamisch aus den angefragten `metric_names`. Zellen mit `null` zeigen `-`.

### 5.4 Datenquelle

Der Vergleich nutzt die Aggregationslogik des Konzern-Dashboards (`get_group_dashboard`), berechnet die Kennzahlen der Werke aus denselben Quellen und extrahiert sie als Schlüssel-Wert-Paare. Der Filter `accessible_factory_ids` entspricht dem Dashboard.

---

## 6. Konzernlieferanten

**Route:** `/group/suppliers`

### 6.1 Funktionsbeschreibung

Die Seite Konzernlieferanten zeigt gemeinsame Lieferanten mit Datensätzen in mehreren Werken und bietet über `SupplierSharedProfile` (gemeinsames Lieferantenprofil) eine einheitliche Sicht und aggregierte Bewertung.

### 6.2 Liste gemeinsamer Lieferanten

**API：** `GET /api/group/suppliers`

**Berechtigung:** mindestens VIEW im Modul `group`

Die Liste zeigt nur gemeinsame Profile mit Lieferantendatensätzen in **2 oder mehr Werken**, also denselben Lieferanten mit unterschiedlicher `supplier_id` je Werk, verknüpft über `shared_profile_id`.

Gelieferte Felder:

| Feld | Beschreibung |
|------|------|
| `shared_profile_id` | UUID des gemeinsamen Profils |
| `unified_credit_code` | Einheitlicher Sozialkreditcode (Unternehmenskennung) |
| `name` | Lieferantenname |
| `short_name` | Kurzname |
| `industry` | Branche |
| `factory_evaluations` | Liste der Bewertungen je Werk |

Jeder Eintrag in `factory_evaluations` enthält:

| Feld | Beschreibung |
|------|------|
| `factory_id` | Werks-UUID |
| `factory_code` | Werkscode |
| `grade` | Bewertungsstufe/-status |
| `total_score` | Punktzahl |

### 6.3 Lieferanten zusammenführen

**API：** `POST /api/group/suppliers/merge`

**Berechtigung:** ADMIN (5) im Modul `group`

Stellt ein Konzernadministrator mehrere Datensätze desselben Lieferanten in verschiedenen Werken fest, können sie zu einem gemeinsamen Profil zusammengeführt werden.

Request-Body:

```json
{
  "supplier_ids": ["uuid-1", "uuid-2"],
  "shared_profile_id": null
}
```

- `supplier_ids`: mindestens 2 Lieferanten-IDs aus verschiedenen Werken
- `shared_profile_id`: optional; ohne Angabe wird automatisch ein neues gemeinsames Profil angelegt
- Alle Lieferantendatensätze müssen aus **verschiedenen Werken** stammen (unterschiedliche `factory_id`), sonst `400`
- Danach wird `shared_profile_id` aller Datensätze auf die ID des gemeinsamen Profils gesetzt

---

## 7. Konzernaudits

**Route:** `/group/audits`

### 7.1 Funktionsbeschreibung

Die Seite Konzernaudits zeigt Auditprogramme (`AuditProgram`) mit mehreren Werken und unterstützt die Koordination und Verfolgung werksübergreifender Audits.

### 7.2 Liste werksübergreifender Audits

**API：** `GET /api/group/audits`

**Berechtigung:** mindestens VIEW im Modul `group`

Es werden nur Auditprogramme mit **2 oder mehr Werken** angezeigt (ermittelt über die Tabelle `audit_program_target_factories`).

Gelieferte Felder:

| Feld | Beschreibung |
|------|------|
| `program_id` | UUID des Auditprogramms |
| `program_no` | Auditnummer |
| `audit_type` | Auditart |
| `status` | Status (`planned` / `in_progress` / `completed` / `cancelled`) |
| `target_factory_ids` | Liste der beteiligten Werks-IDs |
| `target_factory_codes` | Liste der beteiligten Werkscodes |
| `finding_count` | Anzahl Feststellungen des Auditprogramms |

Die Seite zeigt den Status mit der Ant-Design-Komponente `Tag`, Farbzuordnung:

| Status | Farbe |
|------|------|
| `planned` | Blau |
| `in_progress` | Orange |
| `completed` | Grün |
| `cancelled` | Rot |

### 7.3 Werke eines Auditprogramms verwalten

Konzernadministratoren können Zielwerke zu Auditprogrammen hinzufügen oder entfernen:

**Werk hinzufügen:**

```
POST /api/group/audits/{program_id}/factories
```

Request-Body:
```json
{
  "factory_id": "uuid"
}
```

**Werk entfernen:**

```
DELETE /api/group/audits/{program_id}/factories/{fid}
```

Beide Operationen erfordern ADMIN (5) im Modul `group`.

**Zielwerke eines Auditprogramms ansehen:**

```
GET /api/group/audits/{program_id}/factories
```

Liefert `AuditProgramFactoriesResponse` mit `program_id`, `factory_ids`, `factory_codes`.

---

## 8. Datentrennung nach Werk

### 8.1 Gestaltungsprinzipien

OpenQMS trennt Daten über ein **dreistufiges Scope-Modell**:

| Ebene | Klasse | Aufgabe | Auflösung |
|------|-----|------|----------|
| Werksbereich | `FactoryScope` | Steuert, auf welche Werke ein Benutzer zugreifen darf | `resolve_factory_scope()` |
| Produktlinienbereich | `ProductLineScope` | Steuert, auf welche Produktlinien ein Benutzer zugreifen darf | `resolve_product_line_scope()` |
| Berechtigungsbereich | `PermissionScope` | Steuert die erlaubte Operationsstufe | `get_user_permission()` |

**Wichtige Designentscheidung:** `bypass_row_level_security` umgeht nur den Produktlinienfilter, nicht den Werksbereich. Werksübergreifende Sichtbarkeit wird **ausschließlich durch ADMIN in `Module.GROUP` bestimmt**.

### 8.2 Auflösungsregeln von FactoryScope

`resolve_factory_scope()` bestimmt den Werksbereich in dieser Reihenfolge:

| Priorität | Bedingung | Ergebnis | Beschreibung |
|:------:|------|------|------|
| 1 | Berechtigung `group:ADMIN` vorhanden | `accessible_factory_ids = None` | `None` bedeutet: alle Werke sichtbar, kein Werksfilter |
| 2 | Einträge in Tabelle `user_factories` vorhanden | `accessible_factory_ids = [Liste der zugeordneten Werks-IDs]` | Nur zugeordnete Werke sichtbar |
| 3 | Keine Einträge in `user_factories`, aber `users.factory_id` gesetzt | `accessible_factory_ids = [Standardwerk des Benutzers]` | Einzelwerksbenutzer bleibt auf sein Werk beschränkt |
| 4 | Weder `user_factories` noch `factory_id` | `accessible_factory_ids = []` | Kein Datenzugriff |

### 8.3 Zuordnung Benutzer–Werk

Benutzer und Werke werden über die Tabelle `user_factories` (Modell `UserFactory`) verknüpft:

```python
class UserFactory(Base):
    __tablename__ = "user_factories"
    __table_args__ = (UniqueConstraint("user_id", "factory_id"),)
    id: Mapped[uuid.UUID]        # Primärschlüssel
    user_id: Mapped[uuid.UUID]    # Fremdschlüssel → users.user_id
    factory_id: Mapped[uuid.UUID] # Fremdschlüssel → factories.id
```

- Ein Benutzer kann mehreren Werken zugeordnet sein (n:m)
- Zusätzlich hat jeder Benutzer ein Feld `factory_id` als Standardwerk (Standardzugehörigkeit neuer Datensätze)
- `default_factory_id` dient in `FactoryScope` zum automatischen Befüllen neuer Datensätze

### 8.4 Werksfilter in Datenabfragen

Alle APIs des Konzernmoduls übergeben den Werksfilter über `accessible_factory_ids`:

- Bei `accessible_factory_ids = None`: kein Werksfilter im SQL, Daten aller Werke
- Bei `accessible_factory_ids = [id1, id2, ...]`: SQL erhält die Bedingung `WHERE factory_id IN (...)`
- Bei `accessible_factory_ids = []`: leeres Ergebnis

In anderen Modulen wendet `apply_scope_filter()` zwei Filterebenen an:
1. **Werksebene**: `model.factory_id == effective_factory_id` bzw. `IN accessible_factory_ids`
2. **Produktlinienebene**: Filter auf `product_line_code` je nach Modus von `ProductLineScope`

### 8.5 Ableitung der factory_id neuer Datensätze

Beim Anlegen bestimmt `resolve_create_factory_id()` die `factory_id` in dieser Reihenfolge:

1. Ist `product_line_code` angegeben, wird `ProductLine[code].factory_id` verwendet
2. Sonst `scope.effective_factory_id` (in der Anfrage angegebenes Werk)
3. Sonst `scope.factory_scope.default_factory_id` (Standardwerk des Benutzers)
4. Lässt sich nichts davon bestimmen, wird ein Fehler gemeldet

Danach prüft `check_factory_access()`, ob das Werk im sichtbaren Bereich des Benutzers liegt.

### 8.6 Werkskonfiguration in den Seed-Daten

| Werk | Code | Produktlinien | Beschreibung |
|------|------|--------|------|
| Standardwerk | `DEFAULT` | DC-DC-100, PCB-SMT-200 | Hauptwerk der ursprünglichen Seed-Daten |
| Werk Shanghai | `SH-02` | SH-DC-200 | Zweites Werk |

| Benutzer | Sichtbare Werke | Standardwerk | Rolle |
|------|----------|----------|------|
| admin | DEFAULT, SH-02 | DEFAULT | admin |
| manager | DEFAULT, SH-02 | DEFAULT | manager |
| engineer | DEFAULT | DEFAULT | field_qe |
| viewer | DEFAULT | DEFAULT | viewer |
| groupadmin | DEFAULT, SH-02 | Keine (Konzernsicht) | admin |

Der Benutzer `groupadmin` (`GroupAdmin@2026`) ist ein eigenes Konto für die Konzernverwaltung mit `group:ADMIN` und sieht die Daten aller Werke.

---

## 9. Häufige Fragen

### F1: Warum sehen manche Benutzer das Menü der Konzernverwaltung nicht?

**A:** Das Menü ist nur für Rollen mit Rechten im Modul `group` sichtbar. Standardmäßig haben nur `admin` (ADMIN) und `manager` (EDIT) dieses Recht. Andere Rollen (z. B. `field_qe`, `viewer`) haben für `group` NONE und sehen keinen Menüeintrag.

### F2: Sieht die Rolle manager die Daten aller Werke?

**A:** Nicht unbedingt. manager hat EDIT (3) im Modul `group` und sieht Seiten wie das Konzern-Dashboard, der `FactoryScope` hängt aber von der Zuordnung in `user_factories` ab. Nur Manager, die dort mehreren Werken zugeordnet sind, sehen Daten mehrerer Werke; bei nur einem Werk nur dessen Daten. Erst `group:ADMIN` (5) ergibt `accessible_factory_ids = None` (alle Werke sichtbar).

### F3: Wie deaktiviere ich ein Werk?

**A:** `/group/factories` öffnen und in der Aktionsspalte auf „Deaktivieren“ klicken. Das Werk darf nicht mehr von aktiven Produktlinien referenziert werden, sonst meldet das System einen Fehler. Verknüpfte Produktlinien zuvor deaktivieren oder verschieben. Das Deaktivieren erfordert `group:ADMIN`.

### F4: Beim Zusammenführen von Lieferanten erscheint „mindestens zwei Lieferantendatensätze erforderlich“ – was heißt das?

**A:** Die Zusammenführung vereinigt mehrere Datensätze desselben Lieferanten aus verschiedenen Werken in einem `SupplierSharedProfile`. Dafür müssen mindestens 2 Lieferanten-IDs aus **verschiedenen Werken** gewählt werden. Datensätze desselben Werks können nicht zusammengeführt werden.

### F5: Lassen sich die Kennzahlen des Werksvergleichs anpassen?

**A:** Ja. Der URL-Parameter `metric_names` legt die zu vergleichenden Kennzahlen fest, z. B. `/api/group/comparison?metric_names=open_capa_count,overdue_capa_count`. Das Frontend verwendet derzeit standardmäßig alle Kennzahlen; eine Auswahl durch Benutzer ist künftig möglich.

### F6: Wie wird die Summenzeile im Konzern-Dashboard berechnet?

**A:** Die Summenzeile ist die einfache Summe der jeweiligen Kennzahlen aller sichtbaren Werke. `factory_id` ist die Null-UUID (`00000000-0000-0000-0000-000000000000`), `factory_code` ist leer, `factory_name` ist die Summenbezeichnung. Das ist kein eigener Werksdatensatz, sondern dient nur der aggregierten Anzeige.

### F7: Was unterscheidet werksübergreifende von normalen Audits?

**A:** Die Seite Konzernaudits (`/group/audits`) zeigt nur Auditprogramme mit 2 oder mehr Werken (werksübergreifende Audits). Auditprogramme eines einzelnen Werks erscheinen dort nicht, sind aber weiterhin in der Auditverwaltung der Module sichtbar. Der Kernnutzen werksübergreifender Audits liegt in zentraler Planung und werksübergreifender Verfolgung von Feststellungen.

### F8: Kann ein Benutzer mehreren Werken angehören?

**A:** Ja. Über die Verknüpfungstabelle `user_factories` kann ein Benutzer mehreren Werken zugeordnet werden. `users.factory_id` ist das Standardwerk (zum automatischen Befüllen neuer Datensätze), `user_factories` bestimmt, auf welche Werke zugegriffen werden darf. Benutzer mit `group:ADMIN` sehen alle Werke auch ohne Einträge in `user_factories`.