# OpenQMS Agent SDK (0.1.0)

Independent Python >=3.11 src-layout package, distribution `openqms-agent-sdk`,
import `openqms_agent_sdk`. Runtime dependencies: none. No backend imports,
database access, implicit environment/profile credentials or model calls.

This source snapshot provides safe errors, immutable DTOs, a strict protocol
codec, bounded standard-library HTTP transport and installation/run clients for
the existing ten runtime operations. The developer gate below builds the actual
current SDK wheel and checks a fresh isolated installation. The installed-wheel
normal-policy QMS HTTP fixture gate has passed independently (14 SDK cases plus
3 unchanged fixed-CLI cases). Final combined regression and CI wiring acceptance
are still pending; these fixture results are not worker or production admission.
Frozen/slotted DTOs are containers, not runtime type validation: the codec performs
strict decoding. Configuration validates local budgets; transport validates origin.
Request budget is 1 MiB; response defaults to 4 MiB (64 KiB–16 MiB); timeout defaults
to 10 seconds (1–120). Clients create one deadline before encoding and check it
after decoding/binding. A possibly sent finish without complete valid confirmation
raises UnknownOutcome and is not automatically retried or called a remote failure.

## Authorization boundary

Examples and compatibility checks are **fixture-only** communication exercises.
This SDK is **not a newly admitted worker**, does not change the fixed worker,
hash, profile, catalog or official launch chain, and is not production admission.
Possession of credentials and successful HTTP communication do not grant worker
approval or additional authorization.

Business read-only does not mean no platform writes: message claim/ACK, receipts,
audit, events, restricted analysis results, checkpoints and terminal state are
platform records, not CAPA/FMEA business facts, approvals or adopted measures.
No new business writes, attachment/body access, model forwarding or execution of
message text is provided. Message and analysis text can still be sensitive.

## Safe errors

`SDKError(operation, *, kind, status=None, may_have_been_sent=False,
outcome_unknown=False)` is shared by all public error types. Only fixed internal
operation/kind names are retained; unrecognized values become `unknown`. HTTP
status is a strict integer in 100–599 or None. Raw exceptions, URLs, credentials,
headers and bodies must never be passed as messages or retained as original or
response objects. UnknownOutcome always sets outcome_unknown=True.

Internal diagnostic kinds (not server business codes): `unknown`,
`invalid_config`, `invalid_timeout`, `invalid_response_budget`, `invalid_url`,
`invalid_tenant`, `invalid_request`, `invalid_uuid`, `invalid_type`, `invalid_value`,
`request_too_large`, `timeout`, `dns`, `connection`, `tls`, `http_status`,
`redirect`, `invalid_response`, `invalid_json`, `invalid_utf8`, `duplicate_key`,
`schema`, `binding`, `unsupported_encoding`, `response_too_large`,
`outcome_unknown`, `client_closed`, `client_busy`, `transport`, `deadline`,
`dns_busy`, `connection_closed`.
Unknown-kind fallback is only safe diagnostics, never a basis for business flow.
Future wrappers must raise sanitized errors outside except blocks (or from None)
and must not echo underlying exception.args.

## Offline developer gates

Run from the repository root with a Python >=3.11 interpreter containing pytest,
pip and **actual setuptools==79.0.1**. The builder queries the selected interpreter
before building and fails closed on any other setuptools version; the gate does
not install or relax build requirements. Preserve a venv's Python entry point
(do not resolve its symlink to the base interpreter).

```sh
PY=/absolute/path/to/developer-venv/bin/python
"$PY" -I -B sdk/python/scripts/check-sdk.py --layer unit --artifacts /private/tmp/my-sdk-evidence
"$PY" -I -B sdk/python/scripts/check-sdk.py --layer loopback --artifacts /private/tmp/my-sdk-evidence
"$PY" -I -B sdk/python/scripts/check-sdk.py --layer wheel --artifacts /private/tmp/my-sdk-evidence
"$PY" -I -B sdk/python/scripts/check-sdk.py --artifacts /private/tmp/my-sdk-evidence  # default: all
```

The top-level Make targets use the same gates and an independent interpreter:

```sh
make check-sdk-unit SDK_PYTHON_BIN="$PY"
make check-sdk-loopback SDK_PYTHON_BIN="$PY"
make check-sdk-wheel SDK_PYTHON_BIN="$PY"
make check-sdk SDK_PYTHON_BIN="$PY"
```

`check-sdk` needs neither PostgreSQL nor backend dependencies. `make check` also
runs this gate; select `SDK_PYTHON_BIN` explicitly if the default `python3` lacks
the pinned developer tools. `check-backend` builds a fresh current-source wheel,
checks its actual JSON path and SHA256, and passes `OPENQMS_SDK_WHEEL` through the
controlled runner to the mandatory installed-wheel HTTP fixtures. It still needs
the separately verified disposable database; missing/invalid wheels do not skip.
`SDK_ARTIFACT_ROOT` overrides the private evidence parent (otherwise the configured
`OPENQMS_TEST_ARTIFACTS` SDK subdirectory or a temporary-directory parent is used).
No target installs tools into a shared interpreter or implicitly enables models.

Use a non-symlink artifact parent outside the SDK source. Each invocation makes a
new private directory (0700), never overwrites an existing file or changes the
parent's permissions. Receipts and filtered count-only logs are 0600. stdout
contains only layer status and receipt paths; raw pytest/pip output is discarded.
No raw JUnit failure content is exported. Pytest hooks record actual selected,
passed, failed, errors, skipped, xfailed, xpassed, deselected, warnings, exit and
elapsed; receipts bind these to HEAD plus the SDK source manifest/hash. Zero
selection, nonzero exit, skip, xfail or xpass cannot pass. Warnings are counted,
not suppressed. Missing/malformed receipts and controlled child timeouts fail.
On Linux/macOS POSIX, every test/build/venv/install/probe command runs in its own
new session/process group. On exit, timeout or exception, the gate terminates only
that group (bounded TERM grace, then KILL) and waits for its direct child, including
when the leader exited before its descendants. Non-POSIX execution fails closed
without launching children. This is cleanup for trusted tools, not containment of
hostile descendants that deliberately escape their group; orphan reaping belongs
to the OS. The builder CLI's metadata capture is bounded to 64 KiB and private.

- `unit`: only `tests/unit`; no conftest, no ambient pytest plugins, empty pytest
  config and no cache provider. `check-sdk-pure.py` sets plugin autoload off before
  pytest/SDK imports, installs a stdlib Python audit hook denying supported
  socket connect/DNS/bind/sendto/sendmsg events, then loads the source package.
  **This is not an OS/native-code sandbox**; an audit hook does not propagate to
  subprocesses. Builder tests constrain their pip subprocesses with fixed offline
  arguments. Contract tests fake children to test faults; those are not real
  wheel or full-suite acceptance evidence. Separate synthetic Python process-tree
  tests use only their own temporary heartbeat/marker files to prove termination;
  neither kind recursively runs this suite.
- `loopback`: explicitly **non-pure**, separate `tests/loopback` invocation with
  its guarded fixtures. Only fixture-owned numeric 127.0.0.1/::1 random ports;
  no ambient proxy, DNS, shared service or backend bootstrap.
- `wheel`: existing offline builder snapshots only README/pyproject/src from this
  actual SDK, checks the pinned tool and builds without index/build isolation.
  A fresh venv (pip included, system site packages excluded) installs that wheel
  using `--isolated --disable-pip-version-check install --no-index --no-deps`.
  The `-I -B` probe runs outside the repo with curated HOME and no PYTHONPATH;
  verifies site-packages import, 0.1.0 / Python >=3.11 / no Requires-Dist, exact
  exports and ten methods, absence of backend/HTTP/model dependency packages,
  hidden internal DTO/routes and forbidden generic client methods. Constructing
  and closing a client is audited against sockets, not a live HTTP call. Receipts
  retain builder source manifest, wheel SHA256 and actual install/probe exits.
  Wheel counts describe **one isolated probe**, not pytest test cases. Private
  venv/build evidence is retained; no shared interpreter is changed.

Children receive a curated environment, private HOME/TMPDIR and
`PIP_CONFIG_FILE=/dev/null`; no caller credentials, `.env`, profiles, proxy or
ambient plugin variables are passed. These gates do not contact external DNS,
HTTP, models or databases and do not prove production readiness.

## Fixture-only stdin example

Install the wheel into your own environment, then run
`python -B sdk/python/examples/metadata_session.py` with one explicit JSON object
on stdin. Do not put secrets in argv, shell history, environment or saved public
fixtures. Required keys: `origin`, `tenant`, `installation_id`, `secret`,
`request_key`. The default performs claim + capabilities exactly once and closes
locally. **claim_run is a platform write**: it creates/occupies a platform run and
its short-lived run lease, even when only capabilities are read afterwards.
Local close is **not remote finish** and does not release the lease. Use this
sample only with fixture tasks you own; the parent test or user must separately
manage remote run/lease cleanup under normal server policy. This is not a
no-platform-write example, and it deliberately adds no automatic ACK or finish.
Optional `operations` is a list of
`{"operation":"get_capa_context","params":{"view":"report"}}` (or
`"verifications"`, with optional `report_id`) and
`{"operation":"message_history","params":{"after_sequence":0,"limit":20}}`.
Normal server policy must still grant access. Output is only safe status, counts
and receipt IDs, never tokens, bodies, messages or payloads.

This deliberately minimal example does not claim messages or ACK: it has no safe
message-body delivery channel to the caller. It does not automate events,
results, checkpoints or finish, execute messages, call models, grant a profile,
retry failures or resolve an unknown finish. Full ten-operation fixture HTTP
compatibility is tested separately, not by silently expanding this example into
an official worker. No real QMS server is started by these developer gates.
