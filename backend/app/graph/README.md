# graph/

## Responsibility

Read-side abstraction over the FMEA graph. The same graph lives in two
places — embedded in each `fmea_documents.graph_data` JSONB column, and
projected into Neo4j by the graph sync worker — and this package
exposes one `FMEAGraphRepository` interface so callers do not care
which backend they are talking to. Operations are AIAG-VDA aware:
impact / cause chains, similar-node search across FMEAs, change-impact
analysis with AP (Action Priority) recomputation.

## File Organisation

- **`repository.py`** — `FMEAGraphRepository` ABC. The contract:
  `get_impact_chain`, `get_cause_chain`, `find_similar_nodes`,
  `find_similar_nodes_advanced`, `get_cross_fmea_stats`,
  `get_global_stats`, `analyze_change_impact`.
- **`jsonb_repository.py`** — `JSONBRepository` reads `graph_data`
  directly from PostgreSQL and traverses with BFS in Python. No Neo4j
  required; the default in dev and the fallback when Neo4j is
  unavailable.
- **`neo4j_repository.py`** — `Neo4jRepository` issues Cypher against
  the projection. Requires the graph sync worker to have caught up.
- **`neo4j_driver.py`** — async Neo4j driver singleton:
  `get_neo4j_driver`, `close_neo4j_driver`, and `ensure_constraints`
  (idempotent uniqueness constraints + indexes).
- **`deps.py`** — `get_graph_repository` Depends. Selects the backend
  from `settings.GRAPH_REPOSITORY` (`"neo4j"` or otherwise JSONB) and
  injects the appropriate session / driver.

## Public Interface

API routers (`api/fmea.py`, `api/change_impact.py`, `api/graph.py`,
`api/search.py`) and services (`graph_projection_service`,
`recommendation_*`) consume the repository through Depends:

```
repo: FMEAGraphRepository = Depends(get_graph_repository)
```

All methods are `async`. Inputs are typed (`uuid.UUID` for `fmea_id`,
plain `str` for node ids and product-line codes). Outputs are plain
`dict`s mirroring `{nodes: [...], edges: [...]}`, lists of node dicts
for similarity search, or the `ChangeImpactResult` Pydantic schema for
`analyze_change_impact`. The two implementations return structurally
identical payloads — switching backends does not change the API
response shape.

## Conventions & Constraints

- **Read-only.** This package never writes to PostgreSQL or Neo4j.
  Writes to `graph_data` happen in `services/fmea_service`; Neo4j
  writes happen in `services/graph_projection_service`. The repository
  is the read interface.
- **Backend selection is config-only.** Callers do not branch on
  `settings.GRAPH_REPOSITORY`; they always Depends-inject and accept
  whatever `get_graph_repository` returns.
- **`product_line_code` is mandatory** on `find_similar_nodes` and
  `get_cross_fmea_stats`. `find_similar_nodes_advanced` accepts
  `product_line_codes=None` for global search; pass a list to restrict.
- **AP recomputation flows through the state machine.** Both
  implementations import `compute_ap` from
  `state_machines/fmea_state` so JSONB and Neo4j produce identical
  scores.
- **Similarity is the shared utility.** Both repositories call
  `utils.similarity.compute_similarity`; do not inline a second
  scoring function in either backend.
- **Empty graph is not an error.** `get_impact_chain` /
  `get_cause_chain` return `{"nodes": [], "edges": []}` when the
  document has no `graph_data` yet.
- **Neo4j driver is a singleton** managed by `neo4j_driver.py`;
  acquire sessions per request, do not cache them.

## Dependencies

- **Depends on:** `models/fmea` (FMEADocument), `schemas/change_impact`,
  `state_machines/fmea_state`, `utils/similarity`, `database`
  (`get_db`), `config` (settings). Third-party: `neo4j` async driver,
  `sqlalchemy.ext.asyncio`.
- **Depended on by:** `api/fmea.py`, `api/change_impact.py`,
  `api/graph.py`, `api/search.py`, plus
  `services/graph_projection_service` (writes the projection that
  Neo4jRepository reads) and `cli/graph_rebuild` (full rebuild).
