# cli/

## Responsibility

Operational entry points run from the host (or inside the backend
container) rather than through HTTP. Each module is a standalone script
invoked with `python -m app.cli.<name>`, used for one-off maintenance
or recovery tasks that the API surface deliberately does not expose.

## File Organisation

Two scripts today:

- **`graph_rebuild.py`** — full Neo4j graph projection rebuild and
  `GraphSyncOutbox` recovery. `python -m app.cli.graph_rebuild` clears
  Neo4j and rebuilds from PostgreSQL via
  `GraphProjectionService.full_rebuild`; `--retry-failed` resets
  outbox rows stuck in `status="dead"` back to `pending`.
- **`tenant_migrate.py`** — runs `alembic upgrade tenant@head` against
  one or every active tenant schema, then records the outcome in
  `tenant_migrations`. Mutually exclusive flags `--all` and
  `--slug <slug>`.

## Public Interface

Invoked from the shell. Each script ships its own `argparse` parser and
a `main()` (or `asyncio.run(main(...))`) entry under
`if __name__ == "__main__"`. They are not imported by the API or the
service layer.

Typical invocations:

```
python -m app.cli.graph_rebuild
python -m app.cli.graph_rebuild --retry-failed
python -m app.cli.tenant_migrate --all
python -m app.cli.tenant_migrate --slug acme
```

## Conventions & Constraints

- **Use `async_session()` directly**, not `get_db()`. There is no
  FastAPI request, no `RequestScope`, no JWT. Scripts open their own
  session and commit explicitly.
- **Operator context, not user context.** No `factory_id` /
  `product_line_code` filtering — scripts run privileged maintenance.
  Do not call `check_factory_access` here.
- **Set `search_path` explicitly** when touching the `public` schema
  (e.g. `tenant_migrate.py` uses `SET search_path TO "public"` before
  reading the tenant registry). Tenant-scoped work must set the schema
  before each session block.
- **Shell out to `alembic` rather than calling its Python API** — the
  `subprocess` boundary keeps env-var and config resolution identical
  to the manual `alembic upgrade` workflow.
- **Idempotent on success, safe on partial failure.** `graph_rebuild`
  clears Neo4j and re-projects; `tenant_migrate` records every attempt
  as a `TenantMigration` row whether it succeeded or failed.

## Dependencies

- **Depends on:** `database` (`async_session`), `models/` (tenant,
  outbox, migration tables), `services/graph_projection_service`,
  `graph/neo4j_driver`. External: `alembic` (invoked as a subprocess).
- **Depended on by:** nothing in-process. Called by operators, the
  Makefile, container entrypoints, or scheduled jobs.
