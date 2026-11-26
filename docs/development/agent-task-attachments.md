# Betriebsanleitung für private Anhänge von Agent-Aufgaben

## Umfang und Standardzustand

Anhänge aus R4b-2 sind standardmäßig deaktiviert: `AGENT_TASK_RUNTIME_ENABLED` und
`AGENT_TASK_ATTACHMENTS_ENABLED` müssen beide true sein, und es müssen ein absolutes privates
`AGENT_TASK_ATTACHMENT_STORAGE_ROOT` (Eigentümer ist die Dienstidentität, Modus 0700) sowie ein funktionsfähiger ClamAV host/port konfiguriert sein.
Fehlt etwas, wird geschlossen abgelehnt; im deaktivierten Zustand wird vor Mandantenauflösung, Authentifizierung, multipart-Lesen, Datenbank- und Scannerverbindung 404 geliefert.

Die Umsetzung ist auf private Volumes eines einzelnen Knotens beschränkt. clean-/staging-/runtime-Volumes werden nicht mit ClamAV oder Plugins geteilt; der Scanner hat keinen Host-Port. `AGENT_TASK_ATTACHMENT_STORAGE_ROOT` darf weder innerhalb eines tatsächlich von der Anwendung per `StaticFiles` eingehängten Verzeichnisses liegen noch ein solches enthalten; der Betrieb muss sicherstellen, dass dieses Wurzelverzeichnis von keinem Reverse-Proxy, statischen Webserver oder anderen öffentlichen Dateidienst eingebunden wird.
Produktiver Objektspeicher, vorsignierte URLs, S3/MinIO, gemeinsamer Speicher für mehrere Replikate und eine Aktivierung in der Produktion sind **noch nicht freigegeben**.

## Grenzen und Datengrenzen

- Höchstens 20 MiB pro Datei; pro Aufgabe höchstens 5 Anhänge in `scanning`, `promoting` oder `available`; pro Mandantenbenutzer aufgabenübergreifend höchstens 5 nicht abgelaufene Uploads in `scanning` oder `promoting`; Aufbewahrung 168 Stunden.
- Erlaubt sind nur `.pdf`, `.png`, `.jpg`, `.jpeg`, `.txt`, `.csv`, `.docx`, `.xlsx`; die Dateiendung ist keine Sicherheitsaussage.
- Nur fertig gescannte Dateien im Status `available` können über einen berechtigten Backend-Stream heruntergeladen werden. Die Antwort ist fest attachment, octet-stream, nosniff, no-store.
- Dateien, Pfade, Speicherschlüssel, Download-URLs, Parse-Ergebnisse und Bytes werden nie an Plugins, Modelle, Worker, Nachrichten, Ergebnisse, Checkpoints oder Browserspeicher gegeben.
- Das Frontend zeigt keine Vorschau, liest keine Inhalte und nutzt kein FileReader; einzige, vom Benutzer am 2026-10-18 ausdrücklich genehmigte Ausnahme ist eine einmalige Blob-URL beim authentifizierten Download, um den Download sofort auszulösen; danach werden Anker entfernt und die URL widerrufen, nie gespeichert oder wiederverwendet.

## Scannen, Fehler und Wartung

Das kontrollierte Profil verwendet `clamav/clamav:1.4.3_base@sha256:be37f82c9cccf6c2559a44b8fb537e6f11e8547b37988650b169c4540c2f298c`.
`docker/clamav/clamd.conf` legt Grenzen von 20 MiB für Stream/Datei/Scan, Warnungen bei Verschlüsselung und Überschreitung sowie Einzelthread/Queue fest. Die Abnahme muss Daemon- und Signaturversion erfassen und mit echtem `VERSIONCOMMANDS` und EICAR `FOUND` belegt werden; ein immer sauber meldender Fake ist kein Ersatz.

Ein Upload committet zuerst die Kontingentreservierung für Benutzer/Aufgabe und empfängt dann im privaten Staging die vollständigen Bytes mit Größen- und Zeitgrenzen. Während des Empfangs vom Client wird kein globaler Scanner-Slot belegt; erst nachdem der vollständige Staging-Deskriptor zurückgespult ist, wird der Slot angefordert und von der lokalen Datei an ClamAV gesendet. Ist der Slot belegt, folgt `503 ATTACHMENT_CAPACITY_BUSY`, Staging wird bereinigt und das Kontingent freigegeben; es gibt keine unbegrenzte Scan-Warteschlange. Abgleich und Anlage neuer Staging-Dateien werden über eine eigene kurze Metadatensperre koordiniert, die nicht abgelaufene Upload-Streams nicht sperrt; ein nach Ablauf zurückgewonnener Upload kann auch bei wieder aufgenommener Übertragung nicht mehr veröffentlicht werden.

Treffer bei EICAR, Verschlüsselung oder Überschreitungsheuristiken ergeben `422 ATTACHMENT_MALWARE_REJECTED`; Timeout, Nichterreichbarkeit oder Protokollfehler des Scanners ergeben `503 ATTACHMENT_SCANNER_UNAVAILABLE`. In beiden Fällen wird Staging gelöscht, ein minimaler Fehlschlagdatensatz zur Nachverfolgung bleibt erhalten, es gibt kein herunterladbares Objekt. Änderungen an Berechtigung/Aufgabe/Koordinaten führen zu Ablehnung oder Entzug des Zugriffs; Liste, Download, Löschen und Freigabe prüfen jeweils aktuelle Fakten erneut. Der Download liest nach der Integritätsprüfung der clean-Datei erneut aktuelle Identität, Berechtigung und Zielbindung und aktualisiert Anhangsstatus, Frist sowie Speicher-/Inhaltskennungen; bei parallelem Rechteentzug, Neubindung des Ziels, Ablauf oder Metadatenänderung wird kein Deskriptor ausgeliefert. Schlägt die abschließende Prüfung oder der Audit-Commit fehl oder wird die Anfrage abgebrochen, wird die geöffnete Datei geschlossen; bei Fehlern im Audit-Commit wird zudem die offene Transaktion zurückgerollt, damit kein Download fälschlich als erfolgreich erfasst wird.

Der Abgleich bereinigt nur nachweislich sichere Staging-Reste und Statusübergänge in live-Namespaces bestehender Datensätze; normale Wartung, failed/suspended/deactivated oder eine geänderte Generation müssen nicht abgelaufene Bytes erhalten. Datensätze mit `expires_at <= now` sind in Listen sofort unsichtbar, auch wenn die Bereinigung noch nicht gelaufen ist; der Abgleich löscht clean-Bytes nach dem committeten Status `available -> purging` und committet dann `purged` samt Systemaudit. Abgelaufene Objekte mit persistiertem Datensatz in einer historischen Generation können anhand dieses Datensatzes bereinigt werden, unbekannte historische Namespaces werden nur aufbewahrt und gemeldet. Das Löschen einer ganzen Generation erfordert eine exakte, committete Autorisierung `test_rebuild` (oder künftig `tenant_destroyed`) in der Plattformtabelle `tenant_attachment_storage_disposals`; jeder disposal ist ein append-only-Datensatz. Ablauf und Löschen durch Benutzer laufen zweistufig über `purging -> purged`; Datensätze werden nie hart gelöscht.

## Echte Abnahme und Ressourcenentsorgung

`make agent-attachment-e2e` ausführen. Es legt ein zufälliges Compose-Projekt, eine eigene Datenbank sowie benannte Volumes für storage/runtime/definitions an; ClamAV ist nur im Compose-Netz erreichbar. Die Browser-Bridge veröffentlicht nur `127.0.0.1:8008` für Backend-HTTP, Playwright auf dem Host nutzt das installierte Chromium; der Scanner wird nie veröffentlicht. Zuerst laufen echte API-/ClamAV-Prozesstests, dann Browsertests mit echter Anmeldung, default-off, Speichern und Herunterladen sauberer Bytes, EICAR, nicht verfügbarem Scanner, Rechteentzug und Bereinigung beim Schließen. Unabhängig von Erfolg oder Fehlschlag entfernt ein trap nur Container und Volumes dieses zufälligen Projekts; gemeinsame Entwicklungs-, Produktions- oder vom Elternprozess verwaltete Container/Verzeichnisse bleiben unberührt.

Nach der Abnahme werden Befehl, Exit-Code, Image-Digest, Scanner-/Signaturversion und Bereinigungsergebnis erfasst. Produktivspeicher, erneute Scan-Strategien, Mandantenzerstörung oder Mehrknoten-Designs brauchen ein eigenes Review.
