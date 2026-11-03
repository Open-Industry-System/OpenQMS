# PR 28 Remote CI Follow-up

## Goal and boundary

Continue from `aeaf7fb2`: fix the confirmed Chromium runner incompatibility and SDK test-fixture incompatibility, then locate the remaining backend hang without skipping tests or relaxing acceptance. Push only the existing PR branch; do not merge main, configure repository secrets/protection, run live providers/scanner, or deploy.

## Evidence and hypotheses

- Run `41585162399`: frontend installation/types/build passed. Browser installation failed before tests because Playwright 1.60 does not support the Ubuntu 26.04 selected by `ubuntu-latest`.
- Backend exceeded the six-hour job limit. Uploaded evidence was only a 1920-byte progress log, stopping around 47%; it contained four earlier failures around collection indices1407–1410. A six-hour timeout is not proof of an assertion-free run.
- Four failures reproduced with CI's SDK versions: Anthropic2.4 rejects the old `httpx.AsyncClient` injected by the fixture and requires `httpx2`. Actual URL strings are unchanged. Production adapters do not inject this old client, so do not pin SDKs or change production behavior to hide the fixture assumption.
- Actual Linux/Python3.12 diagnostic group (provider adapter, attachment recovery, attachment storage) passed37 tests. This does not prove a full-order or remote hang is fixed.

## Tasks and results

- [x] Pin only Chromium jobs (`browser-protection`, `live-capa`, `scanner`) to `ubuntu-24.04`. Workflow contract first RED3failed/10passed, then GREEN13passed. Do not change unrelated job runners or workflow authority.
- [x] Use each SDK's public `DefaultAsyncHttpxClient` and matching MockTransport in the existing default-URL test. Preserve exact official URL, ambient removal, and request-is-failure assertions. Both old local SDKs and CI SDKs: target4passed/module20passed; RED4failed preserved outside source.
- [x] Add real-child RED/GREEN for progress before a blocked test, hiding parameter IDs and captured body. Mirror only already-redacted diagnostic lines. Enable pytest's120-second stack dump; it does not abort/skip tests or change their success criteria. Existing markers, JUnit/hook counting and private evidence rules remain.
- [x] Pure CI contracts:198passed/3existing warnings on both Python3.11 old SDKs and Python3.12 CI dependency versions.
- [ ] Complete full-order reproduction with CI dependencies and inspect last start/finish if blocked. Native reproduction is macOS3.12.16; Linux diagnostic is3.12.16, whereas GitHub used Linux3.12.15. Do not equate either to the actual remote run.
- [x] Independent review and targeted verification. Review found raw prefix collisions; a real-child RED was fixed by exact JSON/source-ID validation, paired monotonic indices, value-only redaction and canonical reconstruction. Final pure matrix198passed in both environments; scoped rereview found no important remaining issue. Commit/push is a diagnostic iteration, not a declaration that the backend hang is solved.
- [ ] Read actual GitHub results. If backend remains blocked, use named test/stack evidence to reproduce and repair the real lifecycle/lock problem before claiming success.

## Relevant files

- `.github/workflows/test.yml`, `.github/workflows/acceptance.yml`: browser OS contract.
- `backend/tests/ci/test_workflow_contract.py`: supported runner regression.
- `backend/tests/e2e/test_capa_outcome_runner.py`: SDK-native fixture clients.
- `backend/tests/ci/gate_results.py`, `backend/tests/e2e/capa_outcome_runner.py`: non-parameter live progress and thread-dump diagnostics.
- `backend/tests/ci/test_gate_progress.py`: real subprocess/blocking and no-body/no-parameter disclosure regressions.

Only this task's labelled diagnostic containers/databases are writable test resources; other containers, environments, worktrees and profiles remain untouched.
