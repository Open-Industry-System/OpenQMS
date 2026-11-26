# OpenQMS – Entwicklungsstand

> Kompakter Statusbericht. Die ausführliche Entwicklungshistorie (Aufgabenprotokolle, CI-Messreihen, Abnahmeberichte bis 2026-11-22) ist in der Git-Historie dieser Datei erhalten.

## Aktueller Stand (2026-11-26)

- **Produktumfang**: Phase 1–4 und Phase 4+ abgeschlossen (siehe [ROADMAP](docs/ROADMAP.md)); Stabilisierungs-Gate des Release Candidate bestanden.
- **Oberfläche**: Deutsch (Standard) und Englisch umschaltbar; zh-CN entfernt. Texte ohne Übersetzungsschlüssel laufen über `tr()`/`useTr()` (`frontend/src/i18n/tr.ts`). Gespeicherte Datenwerte (Schweregrad, Auditergebnis, MSA-Typ, Perioden) bleiben unverändert und werden über Übersetzungen angezeigt.
- **Backend-Meldungen**: bleiben im Quelltext unverändert; `backend/app/i18n` übersetzt JSON-Antworten je `Accept-Language` (Katalog `backend/app/i18n/messages.json`), LLM-Prompts erhalten eine Ausgabesprach-Anweisung, der PPT-Export ist lokalisiert. Seed-Demodaten sind deutsch.
- **Dokumentation**: Betriebs-, Benutzer-, Architektur- und Moduldokumentation unter `docs/` auf Deutsch (`docs/en/` Englisch). Historische Planungsarchive (`docs/superpowers`), User Stories, chinesische Prüfabläufe sowie historische Entwicklungs- und E2E-Berichte wurden entfernt; noch referenzierte Anleitungen unter `docs/development/` wurden übersetzt.
- **Vorschau-Abnahme**: PR-Vorlage, Parser (`scripts/pr-preview-acceptance.py`) und Tests verwenden einheitlich englische Abschnitts-/Ergebnis-Token (`Scope`, `Acceptance steps`, `Permissions and regression`; `pass`/`fail`/`blocked`).
- **Sicherheit (2026-11-25)**: python-jose → PyJWT, FastAPI 0.116.2 / Starlette 0.48, python-multipart 0.0.34, aktualisierte Frontend-Abhängigkeiten, keine externen Schriftarten. Bericht: [docs/sicherheitspruefung.md](docs/sicherheitspruefung.md). Sicherheitskorrekturen vom 2026-11-16: [Protokoll](docs/development/2026-11-16-security-scan-fixes.md).
- **Deployment**: Oracle ARM64 über `./scripts/production-compose.sh` und `make deploy-release` ([Leitfaden](docs/deployment.md)); Raspberry Pi über `docker-compose.pi.yml` ([Anleitung](docs/raspberry-pi.md)).
- **CI**: Backend in zwei PostgreSQL-Shards mit Modul-Routing für PRs, vollständiger Lauf auf main; Dokumentations-Schnellpfad; Browser-, Live- und Scanner-Gates getrennt ([E2E/CI-Leitfaden](docs/e2e.md)).

## Zuletzt verifiziert

- Frontend: Typprüfung, Build und 936 Tests grün (2026-11-25).
- Backend: 480 Sicherheits-/Auth-Tests sowie 141 Seed-/PPT-/i18n-Tests grün; Seed auf frischer Datenbank und Live-Übersetzung der API geprüft (2026-11-25).
- Dokumentationstests (`backend/tests/test_production_documentation.py`, `backend/tests/ci`, Produktions-Vertragstests) und Root-`tests/` grün nach der Übersetzung der Dokumentation (2026-11-26).
- Ein vollständiger Backend-Lauf (`make check-backend`) wurde wegen Laufzeit (> 3 h in der Arbeitsumgebung) zuletzt nicht lokal abgeschlossen.

## Offene Punkte

- Vollständiger Backend-Lauf in CI; Docker-Image-Build auf dem Raspberry Pi (lokal wegen TLS-Proxy/Docker-Hub-Limit nicht testbar).
- Branch-Review und Entscheidung über die Integration des Stabilisierungsstands in `main`.
- Oracle: Remote-CI, Cloud-Rescan, Installation des eingeschränkten Controllers sowie echte Vorschau-/Produktions-Lebenszyklusabnahme sind nicht ausgeführt (Schalter standardmäßig aus).
- R5 (D5-Vorschläge mit Modellausgang): echte LOCAL-/CLOUD-Modellversuche und native macOS-Abnahme stehen aus; Linux-Sandbox nicht umgesetzt.
- Agent-Basis: Embedding-Worker für `agent_memory`, Kompatibilität alter Audit-Aufrufe mit zufälliger `record_id`, echte Mehrwerkzeug-LLM-Schleife, vollständiges Anthropic-`tool_result`-Shaping.
- Bekannte Lücken: Testabdeckung einzelner Altmodule (`factory_id`-Fixtures); Login-Rate-Limit pro Prozess nicht replikaübergreifend; Redis ohne Cache-Logik; Frontend-Bundle ~5,5 MB ohne Code-Splitting; überlappende Alembic-Nummern.
- Restliche chinesische Inhalte außerhalb von `backend/`/`frontend/`: nur Persona-Dateien unter `Agents/` (nicht Teil des Produkts).

## Nächste Schritte

1. Vollständige CI (Backend-Shards, Browser-Gate) auf dem aktuellen Stand ausführen und Ergebnisse hier festhalten.
2. Pi-Image-Build auf echter Hardware prüfen.
3. Mittelfristig: Starlette 1.x, React Router v7, Cookie-basierte Sitzung; Code-Splitting im Frontend.
4. Agent-/R5-Folgearbeiten nach den oben genannten offenen Punkten priorisieren.
