# cli/

## Responsibility

Host-invoked entry points use `python -m app.cli.<name>`. Maintenance scripts
operate with explicit operator authority; the local Agent trial CLI instead
uses normal authenticated HTTP and never performs privileged database writes.

## File Organisation

- **`graph_rebuild.py`** — full Neo4j projection rebuild and GraphSyncOutbox
  recovery; `--retry-failed` resets dead events.
- **`tenant_migrate.py`** — migrate one or every active tenant and record the
  outcome. Existing `--all`/`--slug` operator interface remains unchanged.
- **`rebuild_test_tenants.py`** — preview by default; explicitly authorized
  disposable-tenant reconstruction requires observed offline services.
- **`agent_local_trial.py`** — default-off trusted-host D4 metadata workflow:
  `check-policy`, fixed-worker `run`, and current-admin HTTP `revoke`. It accepts
  private credential-file paths, never secret/token argv values, arbitrary
  commands or a report selector. See the
  [local trial operating guide](../../../docs/development/agent-local-trial.md).
- **`agent_task_attachments.py`** — fixed `reconcile` maintenance command for
  already-configured private task attachment storage. It accepts no storage
  path, tenant selector, or wildcard; it reports aggregate safe counters only.

## Public Interface

Each module has its own parser and `main()` or async entry point under
`if __name__ == "__main__"`. Product API/service modules do not import these
CLI adapters.

```sh
python -m app.cli.graph_rebuild
python -m app.cli.tenant_migrate --slug acme
python -m app.cli.agent_local_trial check-policy --policy-file "$OWNED_POLICY_FILE"
python -m app.cli.agent_local_trial --help
python -m app.cli.agent_task_attachments reconcile
```

## Conventions & Constraints

Maintenance-only conventions below do **not** apply to `agent_local_trial`:

- Maintenance uses operator database sessions, not request JWTs or `get_db()`;
  tenant maintenance retains its own connection, binding and lock checks.
- Set the correct namespace when touching platform/tenant state; do not
  replace the maintenance gate with an unbound public business session.
- Existing Alembic subprocess entry points preserve normal config resolution.
- Recovery must remain safe on partial failure; record the actual outcome.
- Attachment reconciliation acts only on configured storage and durable metadata;
  it preserves unknown/historical namespaces. Startup defers while a live
  attachment pipeline owns the global lock, but validation/recovery failures
  leave attachments closed for that process.

For `agent_local_trial`:

- No SQL, database credentials or bypass of current user/admin business rules.
- Only dev, trusted local host, literal loopback and a single backend worker;
  no proxy-header trust, remote deployment, model or business-write commands.
- Policy is an immutable server startup declaration, not a client authorization
  claim. Baseline/command DENY and current grant intersections remain in force.
- `run` checks pinned worker bytes, copies them into an owned 0700 directory,
  uses `sys.executable -I` and a minimal environment, drains bounded pipes and
  reaps only its own child on overflow, timeout or interruption. It reads only
  an installation secret; an administrator token is needed only for `revoke`.
- `revoke` uses private token files, no proxy/redirect, bounded strict HTTP
  response proof and constant failure diagnostics. Retry keeps the observed
  expected epoch; version conflicts require rereading current state.
- Do not infer production readiness or automatic task-grant renewal from a
  successful local trial. No environment is enabled by importing the CLI.

## Dependencies

Maintenance retains existing database/models, graph services and Alembic
runtime dependencies. The local trial adapter uses plugin DTOs,
`agent_runtime.trial_policy`, `trial_launcher` and stdlib HTTP/subprocess/file
handling; it introduces no provider or SDK dependency. Both are host entry
points, not business capabilities exposed to a plugin.
