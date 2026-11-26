# Zugangsdaten und Ausgangsgrenzen externer Konnektoren

Die Sicherheitskorrekturen vom 2026-11-16 betreffen MES-REST, ERP-REST und den Test der KI-Konfiguration in der Administration.

## ERP-REST-Ausgang konfigurieren

Die ERP-Berechtigung APPROVE erlaubt nur die Verwaltung fachlicher Verbindungen, nicht die beliebige Nutzung des Backend-Netzes. Vor ERP-Tests
und zeitgesteuerter Synchronisation prüft das Backend mit der Deployment-Konfiguration `ERP_ALLOWED_ORIGINS` die exakte HTTP(S)-
Origin und alle ihre DNS-Auflösungen. Der Standard `{}` verbietet alle ERP-REST-Anfragen; mock und eingehende
ERP-Datenschnittstellen sind nicht betroffen. Das Backend startet normal; ein nicht konfigurierter REST-Ausgang unterbricht keine anderen Module.

In der Produktion wird in `.env.production` eine Zeile JSON **ohne äußere Anführungszeichen** ergänzt, zum Beispiel:

```dotenv
ERP_ALLOWED_ORIGINS={"https://erp.factory.example:443":["10.20.30.15/32"],"http://erp-gateway.internal:8080":["192.168.40.0/24"]}
```

Die Richtlinie pflegt der Betrieb; sie lässt sich nicht über die Konnektor-API ändern. Bevorzugt werden kleinstmögliche `/32`, `/128` oder dedizierte
Subnetze; ausdrückliche Ziele in öffentlichen Netzen, privaten RFC1918-Netzen und IPv6-ULA sind gleichermaßen erlaubt. Eine Origin umfasst Protokoll,
Hostname und effektiven Port; ein weggelassener Standardport ist gleichwertig, Hostnamen sind nicht case-sensitiv. Origin-Einträge sollten keine
fachlichen Pfade enthalten. CIDRs müssen normiert geschrieben sein; Netzadressen mit gesetzten Host-Bits sind nicht erlaubt.

`production-compose.sh` übernimmt diese optionale Einstellung nur aus der festen `.env.production` und ignoriert gleichnamige Werte der Shell;
fehlt der Eintrag in einer alten env-Datei, wird `{}` injiziert. Neu initialisierte Dateien und Beispiele verwenden ebenfalls standardmäßig `{}`.
Der vertrauenswürdige Controller `oracle-production-remote.py` akzeptiert diese Option ebenfalls und exportiert die tatsächliche Richtlinie aus der festen Datei;
fehlt der Eintrag oder ist er leer, wird `{}` exportiert, gleichnamige ambient gesetzte Werte des Aufrufers werden nicht übernommen.
Die `preview.env` der Vorschau enthält weiterhin nur ihre fünf ursprünglichen eigenen Werte; das vertrauenswürdige `compose.preview.yml`
setzt für backend/graph-worker fest `ERP_ALLOWED_ORIGINS: '{}'` und erbt keine ERP-Ziele der Produktion.

**Ein Oracle-Upgrade erfordert eine bewusste Neuinstallation des vertrauenswürdigen Controllers.** Python-Loader des Controllers,
Produktions-/Vorschau-Compose und Edge-Caddy-Konfiguration sind von root installierte eigene Kopien; normale Code-Releases aktualisieren sie
nicht. Der Betrieb führt im geprüften vertrauenswürdigen Checkout nach dem bestehenden Installationsablauf ausdrücklich
`sudo bash scripts/install-oracle-controller.sh` aus und nimmt danach das automatische Release wieder auf; die Installation nutzt die Deployment-Sperre und
erzeugt die Prüfliste des Controllers neu. Wer nur das Anwendungs-Image aktualisiert, übersieht den neuen env-Vertrag und die Body-Grenze am Edge.
Diese Codekorrektur hat weder installiert noch deployt und die echte `.env.production` weder gelesen noch geändert.

Das Backend übernimmt die zeitgesteuerte ERP-Synchronisation; graph-worker führt keine ERP-Ausgangsanfragen aus. Beim direkten Start des Python-Backends
kann der Wert in dessen kontrollierter Umgebung oder `.env` gesetzt werden; das Entwicklungs-Compose reicht dieses JSON aus `.env` bzw. kontrollierter Shell
an backend weiter, fehlend oder leer gilt `{}`, graph-worker erhält die Einstellung nicht.

Jede logische Anfrage löst zuerst DNS auf: Alle Ergebnisse müssen in den CIDRs dieser Origin liegen, sonst wird abgelehnt. Selbst bei
breiten CIDRs werden loopback, link-local (einschließlich Cloud-Metadatenadressen), unspecified,
multicast sowie auf solche IPv4-Adressen abgebildete IPv6-Adressen abgelehnt. Nach der Prüfung verbindet HTTPX mit der gewählten numerischen IP;
Wiederholungen derselben Anfrage behalten diese IP; Host und TLS-SNI behalten den genehmigten Hostnamen, die Zertifikatsprüfung bleibt aktiv.
Der Client deaktiviert Umgebungs-Proxys und Weiterleitungen, sodass Wiederholungen, zweite DNS-Auflösungen, Proxy-Umgebungen und Location
die Anfrage nicht zu einem anderen Ziel führen können. Die nächste logische Anfrage prüft DNS erneut. Das Deployment sollte das für das Dienstkonto
erreichbare Netz weiterhin begrenzen; die Allowlist drückt Vertrauen in das Ziel und in die Verwaltung seines DNS/CIDR aus.

ERP-Base-URLs erlauben weder userinfo noch query, fragment oder verschleierte IP/authority.
Statische Endpunkte dürfen nur relative Pfade mit führendem `/` sein; `//`, query, fragment, Backslash,
Prozentkodierung und Pfadsegmente `.`/`..` sind verboten; fachliche Paginierung/Cursor baut der Konnektor über params. Erlaubte Methoden sind nur
GET und POST. Konto, Passwort, Token usw. gehören in die dafür vorgesehenen Felder von `auth_config`.

Unsichere URLs/Pfade aus historischen Konfigurationen werden VIEW-Benutzern nicht angezeigt und können nicht ausgeführt werden. Antworten serialisieren nur
typgeprüfte Allowlist-Felder; das fachliche field_mapping behält nur Zuordnungen tatsächlicher ERP-Spalten;
unbekannte Erweiterungen, auth_config, retention und andere Nicht-Allowlist-Inhalte werden nicht zurückgegeben. Vor dem Upgrade sollten verbliebene Verbindungen mit
Zugangsdaten in der URL inventarisiert, die Zugangsdaten unter einer genehmigten Origin neu erfasst und aus der URL entfernt werden; alte
URLs nicht in Logs oder Tickets kopieren. Die Korrektur entschlüsselt oder migriert keine echten externen Zugangsdaten automatisch.

## Zielbindung bei MES

Bei MES-Updates werden normierte Origin, Konnektortyp und Authentifizierungstyp verglichen. Werden diese Grenzen überschritten,
wird die gespeicherte auth_config verworfen und nur ausdrücklich neu eingegebene Klartext-Zugangsdaten werden akzeptiert; vom Client gesendete
`*_encrypted`, `*_hash` oder maskierte Werte werden nicht wiederverwendet. Normale Updates mit gleicher Origin behalten die Zugangsdaten.

Neu gespeicherte ausgehende REST-Zugangsdaten authentifizieren per Fernet den Origin-/Auth-Kontext zusammen mit dem Klartext.
Der Konnektor prüft die Bindung vor dem Senden; das Kopieren des Chiffrats zu einem anderen Ziel oder eine Änderung des Authentifizierungstyps wird abgelehnt.
Bearer, API-Key sowie Benutzername und Passwort bei Basic unterliegen dieser Regel. Weiterleitungen bleiben deaktiviert.

Alte ausgehende MES-REST-Chiffrate aus der Zeit vor dem Upgrade haben keine Zielbindung und **werden nach dem Upgrade abgelehnt**; berechtigte
Personen erfassen die Zugangsdaten nach Bestätigung des ursprünglichen Ziels neu. Das System erkennt alten Chiffraten nicht automatisch ein möglicherweise
verändertes Ziel zu. Hashes eingehender API-Keys müssen wegen des Upgrades nicht neu erzeugt werden; eine Änderung der Zielgrenze löscht die gesamte
gespeicherte auth_config einschließlich alter eingehender Hashes.

## KI-Konfiguration und Test

Nicht persistierende KI-Tests verwenden nur den in dieser Anfrage ausdrücklich eingegebenen API-Key; leere Werte oder `********` ergänzen keine verborgenen Schlüssel aus Datenbank
oder Umgebung. Das gilt für LLM und Embedding; auch der Rückfall des Embeddings auf den LLM-Key darf nur aus dieser ausdrücklichen Eingabe stammen. Das Testergebnis weist auf eine erneute Eingabe hin und speichert den Testwert nicht.

Beim Speichern der KI-Konfiguration muss bei schlüsselverbrauchenden Providern nach einer Änderung des wirksamen Providers bzw. der Origin der zugehörige
Schlüssel neu eingegeben werden; geprüft werden Embedding-Provider, Base-URL und der Rückfall des API-Keys auf die LLM-Einstellungen. Ein maskiertes Speichern mit dem ursprünglichen Ziel behält den Schlüssel; lokale Provider ohne API-Key lassen sich normal
konfigurieren. Die API liefert ein verständliches 400; die Prüfung erfolgt vor jedem Schreiben der Konfiguration oder Neuaufbau des Providers.

## Prüfeinstiege

Die rein isolierte Regression `backend/tests/test_connector_security.py` verwendet synthetische Schlüssel, Fernet im Speicher,
ersetzte DNS-Antworten und HTTPX MockTransport und prüft Senden an das ursprüngliche Ziel, Ablehnung einer Zielneubindung, Schwärzung von legacy-
Antworten, Host/TLS-SNI, feste IP bei Wiederholung und Ablehnung von Weiterleitungen, ohne echte Provider aufzurufen.
Regressionen für die Produktions-env liegen in `test_production_compose_wrapper.py` und `test_init_production_env.py`.
Zu den Datenbankregressionen gehören außerdem `test_ai_config_service.py`, `test_erp.py` und `test_mes_concurrency.py`;
sie laufen nur auf einer eigenen, registrierten Test-PostgreSQL.
