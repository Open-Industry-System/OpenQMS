# Lokaler kontrollierter Versuch mit D4-Metadaten

R4a liest mit regulärer Administratorfreigabe, der Benutzer-Aufgaben-API und einem festen stdlib-Plugin auf einem **vertrauenswürdigen lokalen Host** die D4-Metadaten eines 8D. Es führt weder Code noch URLs oder Pfade aus dem Aufgabentext aus, liest weder Text noch Anhänge, ruft keine Modelle auf und schreibt keine fachlichen Datensätze. Die Aufgabenanweisung selbst bleibt `restricted/raw` und darf nicht als „Metadaten“ bezeichnet werden.

Diese Anleitung berechtigt nicht zur Aktivierung in Benutzerumgebungen oder zum Produktions-Deployment.

## 1. Zulassungsbedingungen und Standardwerte

- Nur in eigenen Entwicklungs-/Abnahmemandanten mit `TENANT_MODE=dev`; nicht für single oder production.
- Backend und Frontend binden nur an Loopback, das Backend mit **einem Worker**, ohne Vertrauen in Proxy-Header und ohne externen Reverse-Proxy. Bestehende Dienste dürfen vom Versuchsskript nicht neu gestartet oder zurückgesetzt werden.
- Der feste Starter akzeptiert nur `http(s)://127.0.0.1[:port]` oder `http(s)://[::1][:port]`, weder localhost noch Benutzerinformationen, Pfade, Query oder Fragment. Auch bei HTTPS wird das Zertifikat geprüft.
- Neue Aufgaben-, Laufzeit- und Plugin-Administrationspfade akzeptieren nur echte ASGI-Peers `127.0.0.1`/`::1` und lehnen `Forwarded` und jedes `X-Forwarded-*` ab. Das frühe 404 im deaktivierten Zustand hat Vorrang.
- Sicherheitsdateien und Grenzen der Unterprozesse sind mit der Dateisemantik von macOS/Linux umgesetzt; Windows, bösartige Prozesse auf demselben Rechner, OS-/Container-Sandboxen oder Produktions-Netzisolation gelten nicht als abgenommen.

Standardmäßig gilt weiterhin:

```text
AGENT_TASK_RUNTIME_ENABLED=false
AGENT_LOCAL_TRIAL_MODE=disabled
AGENT_LOCAL_TRIAL_POLICY_PATH=
```

Nur für einen ausdrücklichen Versuch werden Laufzeitschalter, `AGENT_LOCAL_TRIAL_MODE=local_metadata` und ein absoluter Richtlinienpfad gesetzt. Das eigene Backend auf einem selbst gewählten freien Port starten, zum Beispiel in der vorhandenen Python-Umgebung:

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port "$OWNED_BACKEND_PORT" --workers 1 --no-proxy-headers
```

Normale Datenbank, SECRET_KEY und Mandantenkonfiguration bleiben; der Port im Befehl ist keine Anweisung für gemeinsam genutzte Dienste. Das Frontend nutzt den bestehenden Vite-Entwicklungsserver, nur an Loopback gebunden und mit Proxy auf dieses eigene Backend.

## 2. Registrierung mit leerer Richtlinie und sichere Zugangsdateien

Der erste Start verwendet eine reguläre JSON-Datei im Besitz des aktuellen Dienstbenutzers, nur mit Modus `0400` oder `0600`:

```json
{"schema_version":1,"entries":[]}
```

Die Datei ist höchstens 128 KiB groß; Symlinks, doppelte Schlüssel oder unbekannte Felder werden nicht akzeptiert. Die Richtlinie wird nur einmal beim lifespan-Start geladen; ein Austausch der Datei aktualisiert den Server nicht im laufenden Betrieb, Sitzungen ohne interne Richtlinienreferenz erhalten standardmäßig eine leere Richtlinie. Ladefehler erzeugen nur konstante Diagnosecodes, der Versuch schlägt geschlossen fehl, andere bestehende Funktionen laufen weiter.

Mit regulärem Administrator-JWT und aktuellem Mandantenrouting aufrufen:

| Operation | Reguläre API |
|---|---|
| Registrieren | `POST /api/admin/agent-plugins` |
| Aktuelle Installation und Epoch abfragen | `GET /api/admin/agent-plugins/{installation_id}` |
| Langfristigen Grant anlegen | `POST /api/admin/agent-plugins/{installation_id}/grants` |
| Installation aktivieren | `PATCH /api/admin/agent-plugins/{installation_id}`, `{"enabled":true}` |
| Grant aktivieren/deaktivieren | `PATCH /api/admin/agent-plugins/{installation_id}/grants/{grant_id}` |
| Schlüssel rotieren | `POST /api/admin/agent-plugins/{installation_id}/rotate-secret` |

Der Registrierungs-Body ist fest:

```json
{
  "plugin_key":"openqms.local-d4-metadata",
  "plugin_version":"1.0.0",
  "manifest":{
    "protocol_versions":["1"],
    "required_capabilities":["capa.d4.summary.masked.v1"],
    "optional_capabilities":[],
    "supports_resume":false
  }
}
```

Installationen sind anfangs deaktiviert. Das Secret der Registrierungsantwort wird nur einmal geliefert und direkt in eine eigene reguläre Datei mit `0400/0600` gespeichert; die Antwort nicht ausgeben und die Datei nicht committen. Auch das Administrator-JWT liegt in einer separaten sicheren Datei; Installationsschlüssel oder Administrator-Token gehören nicht in argv, Screenshots, Shell-Historie oder Logs. Ein regulärer API-Client sollte die sichere Datei lesen und das JWT mit einer Anfrage ohne Proxy und ohne Weiterleitungen übergeben, damit der Authorization-Wert nicht in einer curl-Befehlszeile landet.

## 3. Exakte Erklärung, Prüfung und Neustart des eigenen Backends

Der Betrieb prüft tatsächliche Plattform-Mandanten-UUID/Generation, Installations-UUID/aktuellen Epoch, UUID der ausführenden Person sowie tatsächliche Berichts-UUID/Werk/Produktlinie. slug, Request-Header oder selbst angegebene JWT-Felder gelten nicht als Nachweis aktueller Fakten. Jeder Eintrag in entries entspricht genau einer ausführenden Person und einem Bericht; höchstens 20 Einträge.

Jeder Eintrag muss alle folgenden Felder enthalten:

```text
tenant_id, tenant_generation, installation_id, credential_epoch,
plugin_key, plugin_version, executor_user_id, report_id, factory_id,
product_line_code, expires_at, worker_sha256
```

- UUIDs müssen in normierter Kleinschreibung mit Bindestrichen vorliegen; Koordinaten dürfen weder leer noch Platzhalter sein.
- generation ist eine strikte ganze Zahl `0..2147483647`, epoch `0..2147483646`; boolesche Werte zählen nicht als ganze Zahl.
- product line ist der tatsächliche Code mit 1–50 Zeichen; `*`/`?` werden nicht akzeptiert.
- expires_at muss eine Zeitzone tragen, beim Laden in der Zukunft liegen und höchstens 24 Stunden entfernt sein; für die erste Runde werden 20 Minuten empfohlen, erzeugt aus der aktuellen UTC-Zeit statt aus historischen Beispieldaten.
- Plugin-key/-version wie im Registrierungs-Body.
- Aktueller fester Worker-SHA-256: `ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54`. Neue Hashes beliebiger Worker gelten nicht automatisch als freigegeben.
- `(tenant, generation, installation, executor, report)` darf sich nicht wiederholen; key/version/epoch/hash müssen für dieselbe Installation im selben Mandanten übereinstimmen.
- Die Datei darf weder Schlüssel, JWTs, Datenbank-/Modellzugangsdaten, Schemas, Modulauswahl noch ausführbare Pfade enthalten.

Im Verzeichnis backend mit der vorhandenen Python-Umgebung prüfen:

```sh
python -m app.cli.agent_local_trial check-policy --policy-file "$OWNED_POLICY_FILE"
```

Bei Erfolg werden nur `TRIAL_READY`, die Anzahl der Einträge und der Datei-SHA-256 des **gelesenen Snapshots** ausgegeben, keine Feldinhalte. Die CLI-Prüfung beweist nicht, dass der Server aktuell diese Richtlinie gewählt hat. Nur das eigene Backend neu starten und bestätigen, dass es tatsächlich die freigegebene Datei geladen hat.

## 4. Reguläre Grants, Installationskatalog und Aufgaben

Der aktuelle Administrator muss weiterhin ein aktiver admin mit `PERMISSION_MGMT >= ADMIN` sein; er muss nicht als ausführende Person in der Erklärung stehen. Aktivierbare langfristige Versuchs-Grants sind nur `capa.d4.summary.masked.v1`:

- factory_ids, object_ids und product_line_codes müssen ausdrücklich und nicht leer die tatsächlichen Koordinaten des freigegebenen Berichts enthalten; der Server prüft alle Objekte und Bereiche der Mengen und akzeptiert keine unbegrenzten Bereiche.
- expires_at muss endlich sein, in der Zukunft liegen und darf nicht nach der frühesten Gültigkeit der abdeckenden Erklärung liegen.
- Anweisungs-, Kandidaten- und fachliche Schreibfähigkeiten bleiben DENY; das Deaktivieren eines Grants hängt nicht von einer gültigen Richtlinie ab.

Nach Aktivierung von begrenztem Grant und Installation legt die ausführende Person über die bestehende CAPA-Seite „Aufgabe für diesen Bericht anlegen“ oder regulär per `POST /api/agent/tasks` eine Aufgabe mit festem Ziel an. Katalog und Anlage verwenden dieselbe aktuelle Autorisierungsprüfung. Die Richtlinie selbst gewährt keine fachlichen Rechte: Erforderlich ist weiterhin die vollständige Schnittmenge aus aktuellem CAPA VIEW, Werk/Produktlinie, Manifest, aktivierter Installation, langfristigem Grant und Aufgaben-Grant für den einzelnen Bericht.

Der Standard-Baseline-Fähigkeitskatalog bleibt DENY; der Server wählt `local_metadata_v1` nur bei exakter Übereinstimmung mit der aktuellen Erklärung. Request-DTO, Manifest, Lauf-Token und Plugin können das Profil nicht selbst wählen. Aufgaben ändern ihr Ziel nicht durch Seitenwechsel; ohne tatsächlich nutzbare Autorisierung entsteht blocked_capability ohne Lauf.

## 5. Fester Starter und Nur-Lese-Wiederaufnahme

Im Verzeichnis backend aufrufen:

```sh
python -m app.cli.agent_local_trial run \
  --installation-id "$INSTALLATION_ID" \
  --tenant-slug "$OWNED_TENANT_SLUG" \
  --api-base-url "$OWNED_API_ORIGIN" \
  --installation-secret-file "$OWNED_INSTALLATION_SECRET_FILE" \
  --claim-key "$OWNED_CLAIM_KEY" \
  --checkpoint save --finish off
```

Weder report-id noch beliebige Befehle, Benutzer-JWT oder Modellkonfiguration werden akzeptiert. Das Übernahmeziel bestimmt die Plattform. Die festen Bytes werden per Hash geprüft, in ein eigenes temporäres 0700-Verzeichnis kopiert und mit `sys.executable -I` ausgeführt; der Unterprozess erhält nur LANG/LC_ALL und sieben OPENQMS-Worker-Einstellungen und erbt weder Datenbank, JWT, Modell, Proxy, HOME, PATH noch Python-Konfiguration. stdin ist deaktiviert; stdout/stderr jeweils höchstens 1 MiB, Gesamtzeit 300 Sekunden; bei Fehlern/Abbruch werden eigene Unterprozesse und Verzeichnisse eingesammelt, Fehlschläge geben nur konstante Codes aus.

Bei Erfolg werden UUIDs von Aufgabe/Lauf, Ereignis/Ergebnis und optional Checkpoint ausgegeben. Nach Bestätigung der Nachrichten fragt das Plugin die beiden views Bericht- und Verifizierungsmetadaten ab und speichert mehrere serverseitige Receipts, den vollständigen Digest sowie ein quellgebundenes Ereignis bzw. eingeschränktes Ergebnis. Es zieht keine Schlussfolgerung zur Grundursache und ändert keine fachlichen Datensätze. `--finish completed` leert zuerst die Eingaben und fordert dann den Abschluss an; ein ACK belegt nur den Empfang.

Pausieren/Fortsetzen erfolgt über die reguläre Benutzer-API der Seitenleiste: Fortsetzen behält denselben run, Zugangsdaten des alten epoch werden aber ungültig. Ein Wiederöffnen per Checkpoint ist nur für den neuesten, wasserstandskonsistenten Checkpoint eines pausierten Laufs erlaubt und legt einen neuen run an; das Plugin liest bestätigte Eingaben und **aktuelle** fachliche Metadaten neu, stellt kein internes Gedächtnis wieder her, rollt keine Geschäftsdaten zurück und kopiert alte Receipts nicht als Quellen des neuen Laufs. Ein erneuter Start im selben aktiven epoch ist keine beliebige Wiederaufnahme einer Pipeline.

Übernahme-Lease und Lauf-JWT laufen höchstens bis zum Ablauf der Richtlinie; Wiederholungen mit dem aktuellen key verlängern die Lease nicht. Bei jeder Identitätsauffrischung, nach Sperren und bei der abschließenden Auslieferungsprüfung werden Hash der Erklärung, epoch, generation, ausführende Person und tatsächliches Ziel erneut abgeglichen. Ablauf oder geänderte Bindung lehnen neue Auslieferungen ab, ein gecachtes RuntimeIdentity umgeht das nicht; abgelaufene Aufgaben-Grants werden bei einer Verlängerung der Richtlinie nicht automatisch verlängert – dafür wird über reguläre Autorisierung eine neue Aufgabe angelegt.

## 6. Vorübergehendes disable und dauerhaftes revoke

Vorübergehendes Deaktivieren von Installation/Grant tauscht weder Schlüssel noch erhöht es den epoch; ob alte Zugangsdaten nach Wiederherstellung der Konfiguration noch gültig sind, hängt von allen aktuellen Fakten ab. **Dauerhaftes revoke** schließt die Installation atomar, ersetzt den Hash durch einen zufälligen, nicht zurückgegebenen Schlüssel, erhöht den epoch um eins und schreibt ein Sicherheitsaudit:

```sh
python -m app.cli.agent_local_trial revoke \
  --installation-id "$INSTALLATION_ID" \
  --expected-credential-epoch "$OBSERVED_EPOCH" \
  --tenant-slug "$OWNED_TENANT_SLUG" \
  --api-base-url "$OWNED_API_ORIGIN" \
  --admin-token-file "$OWNED_ADMIN_TOKEN_FILE"
```

Die Anfrage trägt nur den strikt erwarteten epoch; eine abgelaufene, leere oder ungültige Richtlinie hindert aktuelle Administratoren nicht am Widerruf. Parallele Anfragen mit gleichem expected erhöhen höchstens einmal; bei verlorener Antwort kann mit dem ursprünglichen Wert wiederholt werden. `already_fenced` bedeutet nur, dass die Installation bereits geschlossen ist und die Version über expected liegt – ohne erneutes Schreiben oder Audit; ist die Version neuer, die Installation aber aktiv, oder liegt expected über dem aktuellen Wert, folgt 409: Status neu lesen und dann entscheiden, nicht blind mit anderem expected wiederholen.

Weder eine alte Richtlinie noch erneutes enabled **stellt alte secret/JWT/epoch-Erklärungen wieder her**. Für einen neuen Versuch regulär per rotate-secret einen neuen Schlüssel holen, eine Richtlinie für den neuen epoch ausdrücklich freigeben, das eigene Backend neu starten, rechtmäßige Autorisierungen aktivieren und danach durch die Benutzerin bzw. den Benutzer übernehmen oder wiederaufnehmen lassen; abgelaufene Grants werden nicht automatisch verlängert, Checkpoints nicht zwischen Aufgaben kopiert.

Ein Widerruf bricht keine Aufgaben stellvertretend ab und ändert weder queued/claimed noch Annahmepositionen oder Geschäftsdaten; aktuell berechtigte Benutzer können weiterhin die Historie ansehen, pausieren und abbrechen. Die Historie prüft jedes Mal die tatsächlichen fachlichen Quellrechte; bei Rechteentzug werden weder Text noch Zusammenfassung noch Anzahl geliefert. Bereits committete Auslieferungen können nicht zurückgeholt werden, und ein serverseitiger Widerruf garantiert kein sofortiges Ende lokaler Berechnungen; nach dem Commit des Widerrufs bestehen alte Zugangsdaten keine spätere Übernahme bzw. abschließende Prüfung der Plattform mehr, vor dem Widerruf committete rechtmäßige Auslieferungen bleiben gültig.

## 7. Prüfung und verbleibende Grenzen

Die Abnahme der Normalkonfiguration nutzt eine vollständige eigene zufällige Testdatenbank, echte Transaktionen, einen separaten CLI-Prozess, zugewiesene Loopback-Ports und das installierte Chromium und ersetzt weder DIRECT-Katalog noch vertrauenswürdigen Auslieferungskatalog, authorize oder delivery. Die bestehenden echten R2/R3-Prozesse und acht Browser-Szenarien werden unabhängig erneut geprüft. Befehle, eingefrorene Hashes, Ergebnisse, skip/xfail/xpass und Nachweise der Ressourcenbereinigung werden einheitlich im Umsetzungsprotokoll erfasst.

Textschwärzung aus R4b, Klassifizierung/Scan/Speicherung von Anhängen, allgemeines SDK, eigenständige Modellweitergabe, OS-/Container-/Netzisolation und vertrauenswürdiges Produktions-Deployment sind weiterhin nicht geliefert. R4a hat keine Datenbankmigration, ersetzt den alten AgentSession-Einstieg nicht und bleibt standardmäßig deaktiviert; ein bestandener lokaler Versuch ist keine Freigabe für ein Produktions-Release.
