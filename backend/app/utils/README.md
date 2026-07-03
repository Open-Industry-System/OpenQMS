# utils/

## Responsibility

Pure helper functions shared across services and api routes — Excel
import/export, FMEA graph row flattening, text tokenisation, similarity
scoring, and pgvector dimension parsing. Each module is leaf-level: no
DB, no HTTP, no FastAPI dependencies (one exception called out below).
A function here takes primitives or plain dicts and returns primitives;
that makes it safe to call from anywhere and easy to unit-test.

## File Organisation

Five modules plus an empty `__init__.py`. Callers import the symbol
directly (`from app.utils.text import extract_keywords`), not via the
package.

- `excel.py` — Excel I/O toolkit built on `openpyxl`. Workbook creation
  (`create_workbook`, `append_row`, `auto_width`, `workbook_to_bytes`),
  template generation (`create_template`), upload parsing
  (`parse_upload` with Chinese→internal header mapping,
  required-header check, per-row dict output keyed by `_row` line
  number), value coercion (`coerce_datetime`, `coerce_int_strict`), the
  `ImportError` / `ImportResult` dataclasses, the `ExcelParseError`
  exception, and `excel_response` — the one function that knows about
  FastAPI (returns a `StreamingResponse` with an RFC-5987-encoded
  `filename*=UTF-8''…` so Chinese filenames survive). Limits:
  `MAX_EXPORT_ROWS=10000`, `MAX_IMPORT_ROWS=5000`,
  `MAX_UPLOAD_BYTES=10 MiB`.
- `fmea_graph.py` — `build_rpn_rows(nodes, edges)`: walks the FMEA
  graph (`{nodes, edges}` JSONB shape) and emits one RPN row per
  FailureCause → FailureMode → FailureEffect chain, extracting
  `severity` from the effect node, `occurrence` from the cause node,
  `detection` from the first DETECTED_BY control. Used by services and
  exports that need a spreadsheet view of the graph.
- `text.py` — `extract_keywords(text, min_length=2)`: tokenises mixed
  Chinese/English text using stdlib `re` only (no `jieba`), splitting on
  CJK + ASCII punctuation, dropping pure-numeric tokens, dedup
  preserving order. Used by the CAPA D4/D7 keyword-match recommenders.
- `similarity.py` — `compute_similarity(query, candidate) -> (score,
  reason)`: hybrid scorer — substring hit returns `(0.75,
  "substring_match")`, otherwise bigram Jaccard returns `(score,
  "text_similarity")`. Used by the recommendation pipeline.
- `vector.py` — `parse_vector_dimensions(raw, default=1536)`: validates
  the `-x dimensions=…` argument passed to Alembic for the pgvector
  embedding column. Raises `ValueError` outside `1..2000`.

## Public Interface

Consumers are `services/` (most), `api/` (Excel response helpers,
template downloads), and Alembic migration scripts (`vector.py`).

- **Imports** — `from app.utils.excel import excel_response,
  parse_upload, coerce_int_strict`. The package `__init__.py` is empty
  on purpose; pick the submodule explicitly.
- **Conventions callers rely on:**
  - `parse_upload` returns `list[dict]`; every row carries a `_row` key
    with the 1-indexed Excel row number, so callers can produce
    actionable error messages (`"第 12 行：缺少必填字段"`).
  - `coerce_int_strict` raises `ValueError` (not `TypeError`) on every
    failure mode — services translate that into a Chinese
    `ImportError` row and continue, instead of aborting the whole
    import.
  - `compute_similarity` is symmetric on hit reasons but not on scores
    — substring is asymmetric by design (subset query in long
    candidate still scores 0.75).
  - `build_rpn_rows` tolerates partial graphs: missing effect → 0
    severity, missing cause → one row with `occurrence=0`, missing
    detection → 0 detection. It never raises.

## Conventions & Constraints

- **Stdlib first.** `text.py` deliberately avoids `jieba` so the
  container image stays slim and tokenisation is deterministic across
  versions. If you need higher-quality CJK segmentation, add it as a
  service-layer enrichment, not here.
- **`excel.py` is the only utils module allowed to import FastAPI**
  (`StreamingResponse`). It is the seam between in-memory `bytes` and
  the HTTP response; pushing it further out would force every Excel
  endpoint to repeat the encoded-filename dance.
- **No DB, no `AsyncSession`.** If a helper needs the DB, it belongs in
  `services/`. The point of `utils/` is callability from migrations,
  tests, and CLI commands without a live engine.
- **`coerce_*` functions raise `ValueError`** on every failure, matching
  the rest of the backend's "services raise ValueError, api translates"
  convention. Do not catch and return `None` here.
- **FMEA graph functions trust the schema.** `build_rpn_rows` uses
  `.get(...)` everywhere and never crashes on a malformed graph, but it
  also does not validate it — schema validation lives in
  `schemas/fmea.py` (`GraphNodeSchema`).
- **Similarity scores are not calibrated** across the two reasons —
  callers compare against a per-reason threshold, not a single global
  one.

## Dependencies

- **Depends on:** Python stdlib (`re`, `urllib.parse`, `zipfile`,
  `dataclasses`, `datetime`, `io`), `openpyxl` (Excel I/O), and
  `fastapi` (only for `excel_response`'s `StreamingResponse` type).
- **Depended on by:** most of `services/` (every Excel
  import/export service, the CAPA D4/D7 recommenders, the FMEA
  exporter), a handful of `api/` modules that return template
  downloads directly, and Alembic migrations that ship the pgvector
  embedding column.
