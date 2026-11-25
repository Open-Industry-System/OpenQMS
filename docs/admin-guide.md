# Administratorhandbuch

Dieses Dokument richtet sich an Systemadministratoren von OpenQMS und behandelt Benutzerverwaltung, Berechtigungskonfiguration, Zuordnung von Werken und Produktlinien sowie das Audit-Log.

---

## 1. Benutzerverwaltung

### 1.1 Benutzer anlegen

Nach der Anmeldung mit dem Konto `admin`:

1. Die Seite **Benutzerverwaltung** öffnen (erfordert ADMIN im Modul `user_mgmt`).
2. Auf „Neuer Benutzer“ klicken.
3. Benutzername, Anzeigename, E-Mail und Passwort eingeben und eine Rolle wählen.
4. Nach dem Speichern kann sich der neue Benutzer sofort anmelden.

### 1.2 Passwort zurücksetzen

Administratoren können das Passwort direkt über die Benutzerbearbeitung ändern. Ein Self-Service-Passwort-Reset wird derzeit nicht unterstützt.

### 1.3 Benutzer deaktivieren/aktivieren

In der Benutzerliste auf „Deaktivieren“ klicken. Deaktivierte Benutzer können sich nicht anmelden, ihre Daten bleiben erhalten.

---

## 2. Rollen und Berechtigungen

### 2.1 Rollen

Das System bringt 7 vordefinierte Rollen mit:

| Rolle | role_key | Beschreibung |
|------|----------|------|
| Systemadministrator | `admin` | Vollzugriff, nicht änderbar |
| Qualitätsmanager | `manager` | Freigaberechte, kann die meisten Module bearbeiten |
| Nur-Lese-Benutzer | `viewer` | Nur ansehen, kein Anlegen/Bearbeiten |
| Kundenqualitätsingenieur | `customer_qe` | Bearbeitet Reklamationen, Kundenaudits, SCAR |
| Lieferantenqualitätsingenieur | `supplier_qe` | Bearbeitet Lieferanten, Wareneingangsprüfung (IQC), SCAR |
| Qualitätsingenieur Fertigung | `field_qe` | Bearbeitet FMEA, SPC, MSA |
| Qualitätsingenieur Vorausplanung | `planning_qe` | Bearbeitet FMEA, Produktionslenkungspläne, PPAP, besondere Merkmale |

### 2.2 Berechtigungen konfigurieren

Die Seite **Berechtigungsverwaltung** öffnen (erfordert ADMIN im Modul `permission_mgmt`):

1. Rolle auswählen.
2. Für jedes Modul die Berechtigungsstufe festlegen (NONE / VIEW / CREATE / EDIT / APPROVE / ADMIN).
3. Nach dem Speichern sofort wirksam.

> ⚠️ Die Rollen `admin` und `viewer` sind als `is_system=True` markiert; ihre Berechtigungen sollten nicht geändert werden.

### 2.3 Berechtigungsstufen

| Stufe | Konstante | Bedeutung |
|:----:|------|------|
| 0 | NONE | Keine Berechtigung, Modulmenü ausgeblendet |
| 1 | VIEW | Nur lesen: Listen und Details ansehen |
| 2 | CREATE | Neue Datensätze anlegen |
| 3 | EDIT | Bestehende Datensätze bearbeiten |
| 4 | APPROVE | Freigeben, abschließen, archivieren |
| 5 | ADMIN | Vollzugriff einschließlich Löschen und Konfiguration |

---

## 3. Werke und Produktlinien

### 3.1 Werksverwaltung

Die Seite **Konzernverwaltung → Werksverwaltung** öffnen (erfordert ADMIN im Modul `group`):

1. Werk anlegen: Werkscode, Name und Adresse eingeben.
2. Werke bearbeiten oder deaktivieren.
3. Benutzer Werken zuordnen: In der Benutzerbearbeitung die Werke auswählen, auf die der Benutzer zugreifen darf.

### 3.2 Produktlinien

Produktlinien sind logische Gruppen innerhalb eines Werks:

- Jede Produktlinie gehört zu genau einem Werk.
- Benutzer können mehreren Produktlinien zugeordnet werden.
- Listenseiten filtern standardmäßig nach der aktuellen Produktlinie.

### 3.3 Datentrennung zwischen Werken

Die Datentrennung erfolgt über `factory_scope`:

- Normale Benutzer sehen nur die Daten ihrer eigenen Werke.
- Konzernadministratoren sehen Daten werksübergreifend.
- Der Produktlinienfilter wirkt innerhalb des Werksbereichs.

---

## 4. Audit-Log

Alle CRUD-Operationen werden automatisch im Audit-Log erfasst, mit:

| Feld | Beschreibung |
|------|------|
| `table_name` | Betroffene Tabelle |
| `record_id` | UUID des Datensatzes |
| `action` | CREATE / UPDATE / DELETE / TRANSITION |
| `changed_fields` | Geänderte Felder mit altem und neuem Wert (JSON) |
| `operated_by` | UUID der ausführenden Person |
| `operated_at` | Zeitpunkt der Operation |

Audit-Log-Einträge können weder geändert noch gelöscht werden.

---

## 5. Empfehlungen zu Sicherung und Wiederherstellung

> Für den Produktivbetrieb auf Oracle gilt der Sicherungsablauf aus [deployment.md](deployment.md#16-postgresql-sicherung). Die folgenden Befehle beziehen sich auf den lokalen Docker-Compose-Stack.

### 5.1 Datenbanksicherung

```bash
# Logische PostgreSQL-Sicherung
docker compose exec db pg_dump -U qms qms > backup_$(date +%Y%m%d).sql

# Wiederherstellung
docker compose exec -T db psql -U qms qms < backup_20260613.sql
```

### 5.2 Neo4j-Sicherung (Wissensgraph)

```bash
# Logische Neo4j-Sicherung
docker compose exec neo4j neo4j-admin database dump neo4j --output-path=/data/backup.dump

# Wiederherstellung (neo4j vorher stoppen)
docker compose exec neo4j neo4j-admin database load neo4j --from-path=/data/backup.dump
```

### 5.3 Empfehlungen für regelmäßige Sicherungen

- In der Produktion PostgreSQL und Neo4j täglich automatisch sichern.
- Sicherungsdateien mindestens 30 Tage aufbewahren.
- Den Wiederherstellungsablauf regelmäßig testen.
