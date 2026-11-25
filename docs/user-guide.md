# Benutzerhandbuch

Dieses Dokument beschreibt die allgemeine Bedienung von OpenQMS: Anmeldung, Navigation, Berechtigungen und häufige Abläufe.

---

## 1. Anmeldung

1. Die Systemadresse im Browser aufrufen. Die öffentliche Startseite ist `/`, die Anmeldung erreichen Sie unter `/login`; Dashboard und alle Fachseiten erfordern weiterhin eine Anmeldung und die passende Modulberechtigung.
2. Auf der Anmeldeseite Benutzername und Passwort eingeben.
3. Nach erfolgreicher Anmeldung erfolgt die Weiterleitung zum Dashboard.

**Sitzungsverlängerung**: Das Zugriffstoken ist 120 Minuten gültig. Der Browser verlängert es automatisch mit dem rotierenden Refresh-Token der aktuellen Browsersitzung und synchronisiert die neueste Sitzungsgeneration über mehrere Tabs; nach erfolgreicher Verlängerung werden der aktuelle Benutzer und seine Berechtigungen sicher neu geladen. Die Refresh-Gültigkeit wird ab der letzten erfolgreichen Verlängerung rollierend berechnet. Längere Inaktivität, das Wiederverwenden eines alten Tokens, eine Kontodeaktivierung oder ein Passwort-Reset durch den Administrator erfordern eine erneute Anmeldung. Ein Passwort-Reset widerruft die Refresh-Sitzungen, ein bereits ausgestelltes zustandsloses Zugriffstoken kann jedoch noch bis zu 120 Minuten gültig bleiben.

---

## 2. Navigation

Links befindet sich das Navigationsmenü, gruppiert nach Fachbereichen:

| Menügruppe | Module |
|--------|------|
| Planung & FMEA | FMEA, Produktionslenkungsplan, APQP, PPAP, besondere Merkmale |
| Problemmanagement | 8D/CAPA, SCAR |
| Wareneingang & Lieferanten | Wareneingangsprüfung (IQC), Lieferanten, Lieferantenrisiko |
| Prozess & Messung | SPC, MSA |
| Kundenqualität | Reklamationen, Kundenaudits |
| System & Bewertung | Managementbewertung, interne Audits, Qualitätsziele |
| Integration | ERP, MES, PLM |
| Konzern | Mehrwerks-Dashboard, Werksvergleich |

Menüeinträge werden je nach Berechtigung automatisch ausgeblendet: Fehlt dem Benutzer für ein Modul die Stufe VIEW, erscheint der Menüeintrag nicht.

---

## 3. Werk und Produktlinie wechseln

Oben rechts gibt es eine Auswahl für Werk und Produktlinie:

- **Werk wechseln**: Administratoren können zu einem anderen Werk wechseln und dessen Daten ansehen.
- **Produktlinienfilter**: Nach Auswahl einer Produktlinie zeigen Listenseiten nur noch deren Daten.

> Hinweis: Konzernadministratoren (groupadmin) sehen die Daten aller Werke, normale Benutzer nur die ihnen zugeordneten Werke.

---

## 4. Allgemeine Bedienung von Listenseiten

Alle Listenseiten folgen demselben Bedienmuster:

| Aktion | Beschreibung |
|------|------|
| Suchen | Suchfeld oben, unscharfe Suche nach Nummer/Titel |
| Blättern | Paginierung unten, Anzahl pro Seite umschaltbar |
| Neu | Schaltfläche „Neu“ oben rechts (erfordert CREATE) |
| Filtern | Filter nach Produktlinie, Status, Zeitraum usw. |
| Export | Einige Listen unterstützen den Excel-Export |

**Berechtigungen**:

- **VIEW**: Listen und Details ansehen; Schaltflächen für Neu/Bearbeiten sind ausgeblendet oder deaktiviert.
- **CREATE**: Neue Datensätze anlegen.
- **EDIT**: Bestehende Datensätze bearbeiten.
- **APPROVE**: Freigeben, abschließen, archivieren.

---

## 5. Freigaben und Statusübergänge

Die meisten Dokumente haben einen Status-Lebenszyklus:

| Modul | Statusübergänge |
|------|----------|
| FMEA | `draft` → `in_review` → `approved` |
| 8D/CAPA | `D1_TEAM` → `D2_DESC` → ... → `D7_PREVENT` → `D8_CLOSURE` |
| SCAR | `draft` → `open` → `in_progress` → `closed` → `verified` |
| APQP | `planning` → `design` → `process` → `product` → `feedback` |
| PPAP | `draft` → `under_review` → `approved` / `rejected` → `resubmit` |

**Allgemeine Regeln**:
- Schritte ohne Freigabe: mit CREATE/EDIT weiterschaltbar.
- Freigabeschritte (z. B. FMEA approved, CAPA D7/D8): nur ab APPROVE.
- Betrachter (VIEW) können nur ansehen, nicht bearbeiten oder weiterschalten.

---

## 6. Rollenübersicht

| Rolle | role_key | Typische Aufgaben |
|------|----------|----------|
| Systemadministrator | `admin` | Benutzerverwaltung, Berechtigungen, Vollzugriff auf alle Module |
| Qualitätsmanager | `manager` | FMEA/CAPA freigeben, 8D abschließen, Managementbewertung |
| Qualitätsingenieur Fertigung | `field_qe` | FMEA/SPC/MSA bearbeiten, CAPA-Schritte vorantreiben |
| Qualitätsingenieur Vorausplanung | `planning_qe` | FMEA, Produktionslenkungspläne, PPAP, besondere Merkmale bearbeiten |
| Lieferantenqualitätsingenieur | `supplier_qe` | Lieferanten, Wareneingangsprüfung (IQC), SCAR bearbeiten |
| Kundenqualitätsingenieur | `customer_qe` | Reklamationen und Kundenaudits bearbeiten |
| Nur-Lese-Benutzer | `viewer` | Alle Daten ansehen, kein Anlegen/Bearbeiten |

> Die vollständige Berechtigungsmatrix steht in der [Berechtigungsreferenz](permissions.md).

---

## 7. Häufige Fragen

### Passwort vergessen?

Ein Self-Service-Passwort-Reset wird derzeit nicht unterstützt. Bitte wenden Sie sich an den Administrator, der das Passwort in der Verwaltung zurücksetzt.

### Warum sehe ich ein Modul nicht?

Die Berechtigungsstufe für dieses Modul ist NONE (0). Bitten Sie den Administrator, Ihnen in der „Berechtigungsverwaltung“ mindestens VIEW zu geben.

### Nach dem Werkswechsel ändern sich die Daten nicht?

Einige Seiten filtern zusätzlich nach Produktlinie. Prüfen Sie, ob die Produktlinienauswahl auf die passende Produktlinie umgestellt ist.

### Wie exportiere ich Daten?

Einige Listenseiten (z. B. Lieferanten, SPC) bieten eine Schaltfläche für den Excel-Export. Seiten ohne Exportfunktion lassen sich direkt über die API exportieren, siehe [API-Dokumentation](http://localhost:8000/docs).
