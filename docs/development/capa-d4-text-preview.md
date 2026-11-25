# Vorschau geschwärzter D4-Textkandidaten

Diese Funktion erlaubt aktuell berechtigten Mitarbeitenden, einen **eingeschränkten Schwärzungskandidaten** für D4-Texte zu prüfen. Formaterkennung und Literalersetzung garantieren nicht, dass Namen, Unternehmensidentitäten, Geschäftsgeheimnisse oder alle verschleierten Formen entfernt werden; die Ausgabe bleibt `restricted`, ist nicht für eine Herabstufung freigegeben und darf nicht an Plugins oder Modelle geliefert werden. Sie verändert weder Originaltext noch Verifizierungsergebnis oder Geschäftsstatus und ersetzt keine Freigabe von Originaltext-Ausnahmen.

Das eigenständige R4a-Plugin liest weiterhin nur die abgenommenen Metadaten; die Textfähigkeit ist weder im Plugin-Katalog noch in vertrauenswürdigen Weitergabe-Tupeln enthalten.

## 1. Standardmäßig deaktiviert, Einstieg für normale Mitarbeitende

`CAPA_D4_TEXT_PREVIEW_ENABLED=false` ist der Standard; im deaktivierten Zustand liefern die betreffenden Endpunkte vor Mandantenauflösung, Authentifizierung, Textzugriff und Datenbankabfrage 404. Andere CAPA-Schnittstellen und R4a-Schalter bleiben unverändert. Nur ausdrücklich freigegebene eigene Umgebungen setzen true und starten neu; diese Anleitung und die Abnahme berechtigen nicht zur Aktivierung in Benutzer- oder Produktionsumgebungen.

Mitarbeitende öffnen in der CAPA-Detailansicht im D4-Bereich „Vorschau geschwärzter Textkandidat“. Der Client ruft zuerst availability auf, das nur enabled liefert; ist die Funktion aus oder fehlt die Berechtigung, wird keine Vorschauanfrage gesendet. Erforderlich sind ein normales Benutzer-JWT sowie weiterhin CAPA VIEW und aktueller Werks-/Produktlinienzugriff; Installations-Secrets von Plugins, Lauf-JWTs, vom Client gelieferte owner/schema/classification oder die Seitenauswahl gewähren keinen Lesezugriff.

## 2. Felder und Quellumfang

Verarbeitet werden nur:

- 8D `d4_root_cause`.
- `root_cause_text` und `result` der Verifizierungsdatensätze desselben Berichts.

Notwendige Labels erzeugt der Server: Berichts-/Verifizierungs-UUID, feste Feldnamen, Quell-/Regelversion, eingeschränkte Klassifizierung und Quellstatus. Berichtstitel, Team, D2-/D5-Texte, Inhalt/Name/URL von Anhängen, Verifizierungsschluss/-methode/boolescher Verifizierungsstatus sowie FMEA-Graph/-Titel/-Text gelangen nicht in den Snapshot. Personen sowie Kunden-/Lieferantennamen werden nicht durch modulübergreifende Traversierung ermittelt.

Manuell ausgefüllte Felder ohne Referenz werden als „semantische Quelle unbestätigt“ markiert und bleiben restricted; das ist weder eine Quellenaussage noch eine Herabstufungsfreigabe. Ein nicht leeres `source_ref` muss eine vorhandene FMEA-/Ursachenknoten-Referenz mit zwei Schlüsseln sein; erneut geprüft werden aktuelle Verknüpfung, tatsächliches Werk/Produktlinie, Existenz des FailureCause-Knotens, aktuelles FMEA VIEW der Person und Objektbereich. Geprüft werden nur benötigte Metadaten/Existenz; FMEA-Text wird für die Ausgabe nicht gelesen.

Ist eine Quelle beschädigt, verschwunden oder die Berechtigung entzogen, wird **die gesamte Vorschau/Version abgelehnt**, ohne Felder, Zusammenfassung, Quell-ID, Trefferzahl oder Datensatzanzahl. Eine beim Schreiben geprüfte Referenz bedeutet nicht, dass sie beim Lesen noch sichtbar ist, und lässt sich nicht durch Clientangaben ersetzen.

## 3. Ausdrückliche Ersetzungsbegriffe und Regelgrenzen

Ein Literalbegriff pro Zeile, höchstens 50 Einträge, nach Entfernen von Leerraum 1–100 Zeichen, insgesamt höchstens 8 KiB UTF-8. Leere Begriffe, normalisierte Duplikate, Steuerzeichen, beliebige reguläre Ausdrücke, Ersetzungsvorlagen oder eigene Ausgabetexte werden nicht akzeptiert. `A+B`, `[A].*` usw. werden wörtlich behandelt und nicht als Ausdruck ausgeführt; längere Begriffe haben Vorrang. E-Mail-Adressen, gängige Mobil- und gekennzeichnete Telefonnummern, 18-stellige Ausweisnummernformate, HTTP/HTTPS-URLs, Bearer/JWT und offensichtliche Zugangsdaten-Schlüsselwertpaare werden über feste Regeln erkannt.

Der gesamte Trefferbereich wird durch eine feste Markierung ersetzt; Präfixe von Namen/Nummern bleiben nicht stehen. Überlappende Bereiche werden zusammengeführt und einmal behandelt; für unterstützte Unicode-/casefold-Formen werden nur Treffer und Positionszuordnung zum Original gebildet, nicht getroffene Spezifikationen, Einheiten und Nummern werden nicht durch Normalisierung verändert. Trefferzahlen werden nur je Regelkategorie gezählt; getroffene Originalbegriffe werden nicht zurückgegeben.

Namen, Organisationsbezeichnungen und vertrauliche Fachbegriffe passen möglicherweise zu keiner Formatregel und müssen von berechtigten Mitarbeitenden ausdrücklich angegeben werden. Auslassungen, Überschwärzung und manueller Prüfbedarf sind möglich; selbst bei 0 Treffern gibt es weder „vollständig geschwärzt“ noch internal noch eine Weitergabefreigabe.

Kandidaten werden als reiner Text angezeigt; HTML/URLs im Text werden weder ausgeführt noch verfolgt. Der Dialog hat keine Schaltflächen zum Speichern, Ersetzen des Originals, Übernehmen, Kopieren des Originals, Veröffentlichen oder Senden an Modelle/Plugins.

## 4. Budget, Version und Verfall

Die Quellmenge umfasst höchstens 200 Verifizierungen, 64 KiB UTF-8 pro Text, 256 KiB für alle Texte und 2 KiB je Referenz-JSON; das Budget wird vor dem Laden von Text/Referenzen geprüft. Bei Überschreitung wird der ganze Kandidat abgelehnt, ohne Kürzung oder halbe Seiten. Das Request-JSON ist vor dem Parsen auf 64 KiB begrenzt. Leere Felder erzeugen keinen Faktentext.

Der Server liest die ausdrücklichen Felder in einem RR/READ-ONLY-Snapshot des tatsächlich erfassten Mandanten/der Generation, prüft nach der Verarbeitung aktuelle Identität/Quellen und die vollständige Quellversion erneut und lehnt Kandidaten ab, die sich währenddessen geändert haben. Die Version ist ein domänengetrenntes HMAC-SHA256 des Servers und legt keinen schlüssellosen Digest kurzer Originaltexte offen; sie ersetzt keine Autorisierung. Kandidaten tragen fest `restricted/redaction_candidate/not_approved/external_delivery_allowed=false`.

Ein erfolgreicher Kandidat wird höchstens 30 Sekunden angezeigt. Solange der Dialog sichtbar ist, werden alle 2 Sekunden Quell- und Regelversion bestätigt; ein eigener lokaler Ablauf-Timer verlängert die 30 Sekunden weder durch Netzwartezeit noch durch eine nachgehende Clientuhr. Schließen/Ausblenden entfernt private Inhalte sofort und leert die Ersetzungsbegriffe; bei Wechsel von Identität, Mandant, Bericht, Werk/Produktlinie oder ungültig gewordenen alten Antworten werden alte Inhalte nicht wieder eingesetzt.

Erkennt der Server Rechteverlust, Quelländerung oder eine netzwerkbedingte Unsicherheit bei der Versionsprüfung, werden Kandidat und ausdrückliche Begriffe gemeinsam zurückgezogen. Eine Änderung der Begriffe leert zuerst den alten Kandidaten; eine Neuerzeugung muss ausdrücklich angestoßen werden. Es gibt kein Polling verborgener Seiten im Hintergrund, keinen Browserspeicher, keinen geteilten Zustand und keinen Textcache. Ein Zurückziehen kann nicht löschen, was Mitarbeitende bereits gesehen haben, und behauptet keine globale Sperre fachlicher Schreibvorgänge; es verhindert, dass neue Komponenten weiterhin einen nicht aktuell bestätigten Kandidaten zeigen.

## 5. Schnittstellen und Sicherheitsaudit

| Schnittstelle | Bedeutung |
|---|---|
| `GET /api/capa/{id}/d4-text-preview/availability` | Liefert nach bestandener Prüfung von Mitarbeitenden- und CAPA-Objektrechten nur enabled; liest keinen Text und listet keine Quellen. |
| `POST /api/capa/{id}/d4-text-preview` | Nimmt nur replacement_terms entgegen; liefert einen eingeschränkten Kandidaten und schreibt bei Erfolg ein sicheres Vorschau-Audit. |
| `GET /api/capa/{id}/d4-text-preview/version` | Liefert unter aktuellen Rechten Quell-/Regelversion ohne Text; schreibt kein Erfolgsaudit. |

Der Client injiziert für diese drei festen Berichtsendpunkte kein factory_id und sendet Anfragen mit privaten Begriffen nach 401/403 nicht per Refresh erneut; andere CAPA-/Fachanfragen behalten ihr bisheriges Verhalten.

Fehler sind Konstanten: deaktiviert 404; nicht authentifiziert 401; Zugriffs- oder Quellablehnung 403; Ziel nicht vorhanden 404; Eingabevalidierung 422 `PREVIEW_INPUT_INVALID` (ohne die Standarddetails, die input zurückspiegeln würden); Rohanfrage zu groß 413 `PREVIEW_INPUT_LIMIT`; Quellbudget 409 `PREVIEW_SOURCE_LIMIT`; Konflikt während des Lesens 409 `PREVIEW_SOURCE_CHANGED`; unerwarteter Fehler 500 `PREVIEW_UNAVAILABLE`. Originaltext, Begriffe, SQL oder Ausnahmedetails gelangen weder in Fehlerantworten noch in Logs.

Der einzige dauerhafte Schreibvorgang ist ein erfolgreiches AuditLog `PREVIEW_CAPA_D4_TEXT`: Akteur, Bericht/Werk, Regel-/Quellversion und outcome. Nicht erfasst werden Originaltext, Kandidat, Begriffe/Begriffsdigests, getroffene Originalbegriffe oder freie Fehlertexte. Abschließende Autorisierungs-/Quellkonflikte, fehlgeschlagene Commits oder fehlgeschlagene Anfragen erzeugen kein Erfolgsaudit; es werden keine fachlichen Felder, Anhänge, Outbox oder Embeddings geschrieben, keine Migration und keine eigene Vorschautabelle benötigt.

## 6. Abnahme und verbleibende Gates

Dieser Abschnitt verwendet echte Regeln/DTOs, einen echten committeten eigenen Mandanten/Snapshot, aktuelle CAPA/FMEA-Autorisierung und eine normale Mitarbeiteranmeldung. Der Browser nutzt zugewiesene Loopback-Ports, installiertes Chromium und die echte neue API; nur Netzwerkfehler werden an der Transportgrenze simuliert, gefälschte Erfolgsantworten für Schwärzung oder Rechte ersetzen keine Abnahme. Der alte R4a-Metadatenprozess und die acht R3-Szenarien laufen als eigene Regression.

Anhänge, Volltextsuche/Indexierung, Freigabe von Originaltext-Ausnahmen, Herabstufung/Veröffentlichung von Kandidaten, Textauslieferung an Plugins/Modelle, allgemeines SDK, Container-/Netzwerkisolation und vertrauenswürdiges Produktions-Deployment sind weiterhin nicht geöffnet. Eine erfolgreiche interne Vorschau gilt nicht als Bestehen dieser Gates; Kandidaten dürfen formale Grundursache, Verifizierungsnachweise oder fachliche Schlussfolgerungen nicht überschreiben.
