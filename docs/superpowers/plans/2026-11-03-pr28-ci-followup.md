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
- [x] Native Python3.12/CI-dependency full-order diagnostic reached last START index1764: `test_scan_stream_sends_newline_instream_and_zero_terminator`, then was cancelled after a separate Linux single-case reproduction confirmed the same hang (30-second bound exit124, eight-second event-loop stack). This interrupted diagnostic is not a full suite pass. The fake StrictClamd version/held-stream branches returned at peer EOF without closing the accepted writer; Python3.12 `Server.wait_closed` then waited on the still-open server half. Two new strong-reference real-TCP closure regressions were RED2failed, without hanging their own cleanup. Whole-handler finally now closes/waits on every exit, with all original protocol assertions and production scanner unchanged. Full scanner module GREEN16passed on Linux3.12 and native3.11; scoped independent review found no important issue. Native/Linux reproduction used3.12.16 versus GitHub3.12.15, so actual remote validation remains required.
- [x] Independent review and targeted verification. Review found raw prefix collisions; a real-child RED was fixed by exact JSON/source-ID validation, paired monotonic indices, value-only redaction and canonical reconstruction. Final pure matrix198passed in both environments; scoped rereview found no important remaining issue. Commit/push is a diagnostic iteration, not a declaration that the backend hang is solved.
- [ ] Read actual GitHub results. If backend remains blocked, use named test/stack evidence to reproduce and repair the real lifecycle/lock problem before claiming success.

## Relevant files

- `.github/workflows/test.yml`, `.github/workflows/acceptance.yml`: browser OS contract.
- `backend/tests/ci/test_workflow_contract.py`: supported runner regression.
- `backend/tests/e2e/test_capa_outcome_runner.py`: SDK-native fixture clients.
- `backend/tests/ci/gate_results.py`, `backend/tests/e2e/capa_outcome_runner.py`: non-parameter live progress and thread-dump diagnostics.
- `backend/tests/ci/test_gate_progress.py`: real subprocess/blocking and no-body/no-parameter disclosure regressions.

Only this task's labelled diagnostic containers/databases are writable test resources; other containers, environments, worktrees and profiles remain untouched.
