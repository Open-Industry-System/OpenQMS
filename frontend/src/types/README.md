# types/

## Responsibility

TypeScript type definitions for everything the frontend exchanges with the
backend API and passes between components. These types mirror the backend
Pydantic schemas at the wire boundary: field names use `snake_case` to
match the JSON the API actually sends, and shapes follow the
`PaginatedResponse<T>` convention for every list endpoint.

## File Organisation

`index.ts` is the single canonical barrel — ~1800 lines, ~165 exported
interfaces and types covering auth, FMEA, CAPA, dashboard, control
plans, audits, suppliers, customer quality, RMA, SCAR, product lines,
factories, tenants, users, role/permission editing, audit/login/system
logs, and more. Keeping these in one file is intentional (per
`CLAUDE.md`): pages do `import type { Foo } from "../types"` regardless
of domain.

Domain-specific siblings that are large enough to warrant their own
file:

- `spc.ts` — SPC chart data points, subgroup stats, control limits.
- `msa.ts` — Gauge R&R, bias, linearity, stability, attribute analysis.
- `erp.ts`, `mes.ts`, `plm.ts` — External-connector configs and sync
  payloads. Each re-declares its own `PaginatedResponse<T>` so the
  module is consumable in isolation.
- `cpValidation.ts` — Control Plan import / validation result rows.
- `specialCharacteristic.ts` — Special-characteristic catalog and
  linkage.
- `collaboration.ts` — Comments, mentions, activity feed entries.

There is no `models/` vs `responses/` split. Request and response
shapes sit side by side (`LoginRequest` next to `TokenResponse`,
`UserUpdateRequest` next to `User`).

## Public Interface

- **Import path** — almost every consumer writes
  `import type { … } from "../types"` (or deeper, e.g. `"../../types"`).
  The barrel re-exports nothing else; just the type declarations.
- **`PaginatedResponse<T>`** — the canonical list-endpoint envelope:
  ```ts
  interface PaginatedResponse<T> { items: T[]; total: number; page: number; page_size: number; }
  ```
  Per-module list aliases use it directly:
  `type FMEAListResponse = PaginatedResponse<FMEADocument>`,
  `type CAPAListResponse = PaginatedResponse<CAPAReport>`,
  `type SupplierListResponse = PaginatedResponse<Supplier>`, etc.
- **`GraphNode` / `GraphEdge` / `GraphData`** — the FMEA JSONB graph
  shape. `GraphNode` carries the full AIAG-VDA 7-step property set
  (S/O/D, revised S/O/D, AP, P-diagram, design parameters, interfaces).
  Shared by every FMEA component and by `utils/fmeaTable.ts` /
  `utils/structureTree.ts`.
- **`User`, `FactoryScope`, `TokenResponse`** — the auth payload the
  Zustand auth store hydrates from.

## Conventions & Constraints

- **Field names are `snake_case`** to match the backend JSON exactly.
  Components that need camelCase do the rename at use-site; this layer
  does not transform.
- **`null` and `undefined` are kept distinct.** Backend uses `null` for
  "explicitly absent"; optional `?` fields are reserved for "may be
  omitted from the payload entirely". Don't collapse them.
- **No runtime code, no Zod schemas, no classes.** Every export is
  `interface` or `type` only. The file is compiled away.
- **One file by intent.** Resist the urge to split `index.ts` into
  per-domain modules — pages cross domain boundaries constantly
  (dashboard pulls FMEA + CAPA + audit + supplier types) and a single
  barrel keeps imports flat. New domains that grow their own complex
  sub-types (SPC, MSA, ERP, MES, PLM, CP validation) get their own
  file; everything else lands in `index.ts`.
- **`PaginatedResponse<T>` is the only list envelope.** If a new list
  endpoint returns something different, fix the backend, don't add a
  second envelope.
- **Document the AIAG-VDA origin in comments** where a field name is
  not self-explanatory (`ap`, `revised_ap`, the S/O/D variants on
  `GraphNode`).

## Dependencies

- **Depends on:** nothing. Pure declarations.
- **Depended on by:** `pages/`, `components/`, `api/`, `store/`,
  `hooks/`, `utils/` — essentially every other directory under
  `frontend/src/`.
