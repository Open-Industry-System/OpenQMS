## Änderungsbeschreibung

Beschreiben Sie, welches Problem diese Änderung löst.

<!-- preview-test-plan:start -->
### Scope
Please fill in: betroffene Seiten, Rollen und Geschäftsprozesse sowie ausdrücklich nicht betroffene Bereiche.

### Acceptance steps
| ID | Check | Environment | Role | Scenario | Steps | Expected result |
| --- | --- | --- | --- | --- | --- | --- |
| Please fill in | Please fill in | Please fill in | Please fill in | Please fill in | Please fill in | Please fill in |

### Permissions and regression
Please fill in: Berechtigungsablehnung, Grenz-/Fehlerfälle und Regression bestehender Funktionen; falls nicht zutreffend, den konkreten Grund nennen.
<!-- preview-test-plan:end -->

## Manuelle Vorschau-Abnahme

Jede ID ist ein eindeutiger, kurzer Bezeichner in Kleinbuchstaben. Für reines Lesen `public / viewer / read-only` verwenden, für synthetische Geschäftsaktionen `shared / field_qe oder manager / write`. D4-Textauslieferung und Rechteentzug verwenden `d4-deliver` bzw. `d4-revoke` und benötigen einen eigenen Receiver sowie Browser-Nachweise. Im gemeinsamen Testplatz wird das Ergebnis je ID eingetragen, z. B. `report-read: pass` (erlaubt: `pass`, `fail`, `blocked`).

Nachdem CI bestanden hat und die Vorschau veröffentlicht ist, führen Sie die obigen Schritte in der echten Umgebung aus. Kopieren Sie aus dem automatischen Kommentar „Test environment is ready“ (oder der Summary des Workflows `PR preview acceptance`) den an Commit, Deployment und Plan gebundenen Befehl `/preview-accept`, posten Sie ihn als PR-Kommentar und hängen Sie tatsächliche Ergebnisse bzw. Screenshot-Links an. Der Bot ersetzt keine menschliche Bestätigung; nach neuen Commits oder Planänderungen ist eine erneute Bestätigung nötig.
