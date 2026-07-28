# US-E2E-02 FMEA Lifecycle — Verify-Skill Conversion & E2E Acceptance Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the approved user-story epic `docs/user-stories/US-E2E-02-fmea-lifecycle/` (README v3 + 19 sub-stories) into a suite of `verify-fmea-lifecycle-*` skills, then use those skills to walk the **actual product** end-to-end in a real browser and produce an acceptance report that labels every criterion PASS / PASS-NOTE / FAIL / MISSING / BLOCKED.

**Architecture:** This is a **verification** effort, not a build effort. Each verify skill is a *derived walkthrough script* (单向派生剧本) from its user story — it drives the running product via browser MCP (`browser_*`) and asserts via UI selectors + read-back API + audit API, exactly like the existing `verify-capa-8d-closed-loop` skill for US-E2E-01. Skills **detect and honestly report** gaps; they never modify product logic. Where the spec requires something the product doesn't expose (e.g. `source_executions` on the recommend response), the skill asserts it and records **FAIL/MISSING** — that failure is the deliverable that drives a *future* backfill (tracked separately in `2026-07-25-fmea-lifecycle-contract-backfill.md`, marked out-of-scope).

**Tech Stack:** Claude verify skills (`.claude/skills/*/SKILL.md`), browser MCP (`browser_navigate/click/type/evaluate/...`), the repo E2E harness (`docker-compose.e2e.yml`, `Makefile` `e2e-*` targets, `backend/app/seed_e2e.py`, `/api/e2e/seed-state` + `/api/e2e/cleanup`), markdown acceptance reports under `docs/e2e/reports/US-E2E-02-<date>/`.

## Global Constraints

- **Branch:** `fix/fmea-fixes`. **Blocker to resolve first (Task 0):** this branch lacks the E2E walk harness (`Makefile` e2e targets, `docker-compose.e2e.yml`, `seed_e2e.py`, `/api/e2e/seed-state`) which already exists on `origin/main`. Skills cannot run until the branch is synced with main.
- **Spec of record:** `docs/user-stories/US-E2E-02-fmea-lifecycle/` (README v3, 19 sub-stories). Each skill's top must declare the exact story version+date it derives from; on version drift the skill stops and asks to re-sync (per the repo's User Story ↔ Skill 同步规则 in `CLAUDE.md`).
- **Skill template:** mirror `verify-capa-8d-closed-loop/SKILL.md` structure: front-matter (`name`, `description`), 依据/版本/同步规则 header, Overview, When to Use, 前置 (preconditions incl. version check + e2e-stack reachability + LLM creds for AI steps), selector 表, 状态机, 走查剧本 (numbered steps, each 做/期望/断言/落库), 缺陷分类 (PASS/PASS-NOTE/FAIL/MISSING), 报告模板, 维护. **Judge-as-implemented:** a missing selector/panel/field = **MISSING**, never "skip because maybe not built".
- **No product-logic changes.** The only tolerated product edits are `data-e2e` selector additions *if the user later opts in*; by default (chosen) missing selectors → MISSING.
- **AI steps assert per spec, fail honestly.** For AI_REQUIRED=true sub-stories (02.1/02.4/02.5/02.6/02.8/02.11/02.12/02.13/02.16): assert the recommend response carries `source_executions` with the 3 required retrievers (`graph`/`semantic_search`/`lessons_learned`) + `context_execution` + `generation_execution`. The current backend does not return these → record **FAIL/MISSING**. No LLM credentials → **BLOCKED** (do not degrade-run).
- **Verify-only audit assertions:** skills *read* `/api/admin/logs/audit` to confirm expected `AuditLog` rows (CREATE/UPDATE/TRANSITION/ADOPT_RECOMMENDATION/...). They never write product state except through the UI under test.
- **Reports:** one dated folder per walk: `docs/e2e/reports/US-E2E-02-<YYYY-MM-DD>/report.md` + `screenshots/` + `evidence/`.
- **Skill slugs are fixed** (from the spec's 子故事索引); do not invent new ones.

## File Structure

| Path | Responsibility |
|---|---|
| `.claude/skills/verify-fmea-lifecycle/SKILL.md` | Epic orchestrator: preconditions, account×permission table, runs the 19 sub-skills in lifecycle order, aggregates PASS/FAIL/MISSING/BLOCKED, epic report |
| `.claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh` | Reference/link validator (mirrors the capa skill's `scripts/verify-refs.sh`) |
| `.claude/skills/verify-fmea-lifecycle-<slug>/SKILL.md` | One per sub-story (19 total): the walkthrough for that step/capability |
| `docs/e2e/reports/US-E2E-02-<date>/report.md` | Acceptance report output (product of running, not of this plan) |

The 19 sub-skill slugs (exact — copy verbatim):
`pfmea-step1-planning`, `pfmea-step2-structure`, `pfmea-step3-function`, `pfmea-step4-failure`, `pfmea-step5-risk`, `pfmea-step6-optimization`, `pfmea-step7-documentation`, `dfmea-step1-planning`, `dfmea-step2-structure`, `dfmea-step3-function`, `dfmea-step4-failure`, `dfmea-step5-risk`, `dfmea-step6-optimization`, `dfmea-step7-documentation`, `editor-row-crud`, `editor-ai-recommend`, `collaborative-editing`, `version-snapshot-cp-sync`, `approval-cycle` — each prefixed `verify-fmea-lifecycle-`.

Reference material to read before writing (exact paths):
- Template skill: `.claude/worktrees/us-e2e-01.4-fmea-linkage/.claude/skills/verify-capa-8d-closed-loop/SKILL.md` (285 lines — copy its section skeleton and conventions).
- Template ref-validator: same dir `scripts/verify-refs.sh`.
- Spec: `docs/user-stories/US-E2E-02-fmea-lifecycle/README.md` + the 19 `US-E2E-02.*.md` files.
- Sync rule: `CLAUDE.md` §"User Story ↔ Skill 同步规则".

---

---

## Task 0: Sync E2E harness onto fix/fmea-fixes (BLOCKER)

**Files:**
- Modify: branch `fix/fmea-fixes` (merge/sync from `origin/main`)

**Interfaces:**
- Consumes: `origin/main` E2E harness — `Makefile` (`e2e`, `e2e-up`, `e2e-seed`, `e2e-reset`), `docker-compose.e2e.yml`, `backend/app/seed_e2e.py`, `/api/e2e/seed-state` + `/api/e2e/cleanup` (registered only when `E2E_MODE=1`), `.env.e2e.example`.
- Produces: a `fix/fmea-fixes` branch on which `make e2e-up && make e2e-seed` brings up the E2E stack and `curl -sf http://localhost:5174` + `curl -sf http://localhost:8001/api/e2e/seed-state` both succeed.

**Why this is first:** the verify skills drive the product through the E2E harness. `fix/fmea-fixes` predates that harness, so the skills cannot run until the branch has it. This is a branch-sync, not a feature change.

- [ ] **Step 1: Confirm the harness is absent on this branch**

Run: `git ls-tree -r HEAD --name-only | grep -E "^Makefile$|docker-compose.e2e.yml|backend/app/seed_e2e.py"`
Expected: little/no output (harness missing on `fix/fmea-fixes`), while `git ls-tree -r origin/main --name-only | grep -E "^Makefile$|docker-compose.e2e.yml|backend/app/seed_e2e.py"` lists all three.

- [ ] **Step 2: Sync the branch with main**

Run: `cd /Users/sam/Documents/Code/OpenQMS && git merge origin/main --no-edit` (or `git rebase origin/main` if the team prefers a linear history — pick one and state it).
Expected: merge completes; resolve any conflicts in `docs/`, `backend/app/`, `frontend/src/` favoring the branch's FMEA work while keeping main's harness files. If conflicts are non-trivial, stop and surface them rather than guessing.

- [ ] **Step 3: Verify the harness is present and the app still builds**

Run: `cd /Users/sam/Documents/Code/OpenQMS && git ls-tree -r HEAD --name-only | grep -E "^Makefile$|docker-compose.e2e.yml|backend/app/seed_e2e.py"`
Expected: all three now listed.
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`
Expected: suite passes (or only pre-existing failures unrelated to the merge — record them).

- [ ] **Step 4: Smoke the E2E stack**

Run: `cp .env.e2e.example .env.e2e` (fill LLM creds if absent), then `make e2e-up && make e2e-seed`
Run: `curl -sf http://localhost:5174 >/dev/null && echo FRONTEND_OK; curl -sf http://localhost:8001/api/e2e/seed-state >/dev/null && echo SEEDSTATE_OK`
Expected: `FRONTEND_OK` and `SEEDSTATE_OK`. If the stack can't come up in this environment, record it as a precondition note in the epic skill and proceed to skill authoring (skills are validated structurally in Task 2 even if a live walk must wait).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(e2e): sync E2E walk harness from main onto fix/fmea-fixes (Makefile e2e-*, docker-compose.e2e, seed_e2e, /api/e2e/seed-state)"
```

---

## Task 1: Author the epic orchestrator skill

**Files:**
- Create: `.claude/skills/verify-fmea-lifecycle/SKILL.md`
- Create: `.claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`

**Interfaces:**
- Consumes: spec README v3 (`docs/user-stories/US-E2E-02-fmea-lifecycle/README.md`); template `verify-capa-8d-closed-loop/SKILL.md`; the 19 sub-skill slugs (Task 2).
- Produces: `.claude/skills/verify-fmea-lifecycle/SKILL.md` with front-matter `name: verify-fmea-lifecycle`, a `description` that triggers on "验收/走查 US-E2E-02 / FMEA 生命周期 / 端到端测试 FMEA", and a body containing: 依据+版本(定稿 v3 2026-07-25)+同步规则 header; Overview (browser-MCP walk of PFMEA+DFMEA wizard → editor → approval, assert via selector + read-back API + audit API); When to Use; 前置 (story-version match; `:5174` reachable else `make e2e-up && make e2e-seed`; LLM creds present else AI steps BLOCKED; accounts from `/api/e2e/seed-state`); 账号×权限表 (admin L5 / manager L3 approve / quality_engineer L2 edit / viewer L1 read); 生命周期状态机 (DRAFT→IN_REVIEW→APPROVED/REWORK, editable only DRAFT/REWORK); the ordered list of the 19 sub-skills (wizard 02.1–02.7 PFMEA, 02.8–02.14 DFMEA, then editor 02.15–02.18, then 02.19); aggregation rule (epic PASS = conjunction of sub-story PASS; AI_REQUIRED-no-creds=BLOCKED; functional error=FAIL); 缺陷分类 table; 报告模板 (`docs/e2e/reports/US-E2E-02-<date>/`); 维护.

- [ ] **Step 1: Read the template and the spec README**

Run: read `.claude/worktrees/us-e2e-01.4-fmea-linkage/.claude/skills/verify-capa-8d-closed-loop/SKILL.md` and `docs/user-stories/US-E2E-02-fmea-lifecycle/README.md` in full.
Expected: you can name the template's sections and the README's 19 sub-stories, state machine, permission matrix, and AI contract.

- [ ] **Step 2: Write the epic SKILL.md**

Create `.claude/skills/verify-fmea-lifecycle/SKILL.md` following the template skeleton, with this front-matter and header:

```markdown
---
name: verify-fmea-lifecycle
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS FMEA lifecycle user-story epic (US-E2E-02) end-to-end in a real browser — PFMEA + DFMEA 7-step creation wizards, in-editor editing, and the submit/approve/reject approval closed-loop. Symptoms: "验收 US-E2E-02" / "走查 FMEA 生命周期" / "端到端测试 FMEA".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/README.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。
```

Body sections (fill each from the spec, mirroring the template): Overview; When to Use; 前置 (4 items: version match, e2e stack `:5174` + `/api/e2e/seed-state` reachable else `make e2e-up && make e2e-seed`, LLM creds for AI steps else those steps BLOCKED, accounts from seed-state); 账号×权限表; FMEA 状态机 (5 states, editable only DRAFT/REWORK, approval matrix); 子 skill 索引 (the 19 slugs in lifecycle order); 走查编排 (run order + how to invoke each sub-skill + collect per-story verdicts); 缺陷分类 (PASS/PASS-NOTE/FAIL/MISSING/BLOCKED — define BLOCKED = environment/LLM-creds precondition unmet, FAIL = functional assertion failed, MISSING = required feature/selector absent, PASS-NOTE = pass with note); 报告模板 (folder `docs/e2e/reports/US-E2E-02-<date>/` with report.md + screenshots/ + evidence/, and the aggregate table columns 子故事/期望/断言结果/标签); 审计轨迹核对 approach (read `/api/admin/logs/audit`, verify CREATE/UPDATE/TRANSITION/ADOPT_RECOMMENDATION separation); 维护.

- [ ] **Step 3: Write verify-refs.sh**

Create `.claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh` modeled on the capa skill's `scripts/verify-refs.sh`: it greps the spec directory for every `verify-fmea-lifecycle-*` slug and asserts each has a matching `.claude/skills/<slug>/SKILL.md`, exiting non-zero on any miss. Make it executable (`chmod +x`).

- [ ] **Step 4: Validate structure**

Run: `test -f .claude/skills/verify-fmea-lifecycle/SKILL.md && test -x .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh && echo OK`
Expected: `OK`.
Run: `bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`
Expected: reports the 19 sub-skills as MISSING (they don't exist until Task 2) but finds the epic skill — confirms the validator works.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/verify-fmea-lifecycle/
git commit -m "feat(e2e): verify-fmea-lifecycle epic orchestrator skill + verify-refs validator"
```

---

## Task 2: Author the 19 sub-story verify skills

**Files:**
- Create: `.claude/skills/verify-fmea-lifecycle-<slug>/SKILL.md` for each of the 19 slugs listed in File Structure.

**Interfaces:**
- Consumes: each sub-story spec file `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.<n>-<slug>.md` (its 关联 skill name, 主流程, 业务规则/验收标准, and 验收契约 field-table); the epic skill (Task 1) for shared preconditions/accounts/report conventions.
- Produces: 19 skills. Each: front-matter (`name: verify-fmea-lifecycle-<slug>`, `description` triggering on验收/走查 that sub-story); 依据+版本+同步规则 header matching its sub-story's version; Overview; When to Use; 前置 (reference epic + any sub-story-specific seed/凭证 needs, e.g. AI steps need LLM creds else BLOCKED); the sub-story's 验收契约 rendered as a runnable 走查剧本 — each acceptance row becomes numbered steps with 做 (browser/API action) / 期望 / 断言 (selector read-back + `GET` API + audit) / 落库; AI sub-stories additionally assert `source_executions` covers `graph`/`semantic_search`/`lessons_learned` + `context_execution` + `generation_execution` (FAIL/MISSING if absent); 缺陷分类 + 报告片段 (append to the epic report).

**Method — generate by category, not 19× by hand.** The 19 split into 4 shapes; write one full exemplar per shape, then derive the rest:

1. **Wizard-step (×14: 02.1–02.14)** — exemplar `pfmea-step1-planning`. Walk: create draft → drive that wizard step in the browser → assert落库 (graph nodes/edges/wizardScope per the sub-story 验收契约) via `GET /api/fmea/{id}` + audit. DFMEA mirrors PFMEA with its node types/edge semantics.
2. **Editor capability (×3: 02.15 row-crud, 02.16 ai-recommend, 02.17 collaborative)** — exemplar `editor-row-crud`. Walk: open a completed draft in the editor → row CRUD → assert graph sync + wizardScope preserved (02.15); 02.16 adds the AI source_executions assertion (likely FAIL/MISSING today); 02.17 asserts optimistic-lock 409 + FORCE_SAVE_OVERRIDE audit.
3. **Version + CP sync (×1: 02.18)** — assert submit/approve snapshots (`FMEAVersion.snapshot`/`major_no`/`minor_no`/`sha256_hash`/`change_type`) and PFMEA-only CP `sync_pending`. Per spec, CP sync must be a durable outbox; current code does a direct synchronous set → assert per spec, expect FAIL/MISSING, and do NOT reuse GraphSyncOutbox in the assertion.
4. **Approval cycle (×1: 02.19)** — drive submit→approve→reject→rework→(re-approve) across roles; assert permission matrix (EDIT vs APPROVE), non-empty reject reason (422), wizard_completed 422 gate, editable-state 409 on PUT, APPROVED→REWORK keeps approved_by/at. Several are spec-marked gaps → expect FAIL.

- [ ] **Step 1: Write the 4 exemplar skills**

Create `verify-fmea-lifecycle-pfmea-step1-planning`, `verify-fmea-lifecycle-editor-row-crud`, `verify-fmea-lifecycle-version-snapshot-cp-sync`, `verify-fmea-lifecycle-approval-cycle` in full (each a complete SKILL.md per the Interfaces above, derived from its sub-story spec file).

- [ ] **Step 2: Derive the remaining 15 skills**

From the exemplars, generate the other 13 wizard skills (02.2–02.7, 02.8–02.14) and `editor-ai-recommend` + `collaborative-editing`, substituting each sub-story's node types / edge directions / 验收契约 rows / AI_REQUIRED flag / version header. Each must be a complete standalone SKILL.md (no "see step1" shortcuts — an implementer reads one skill at a time).

- [ ] **Step 3: Validate all 20 skills resolve**

Run: `ls .claude/skills/ | grep -c '^verify-fmea-lifecycle'`
Expected: `20` (1 epic + 19 sub).
Run: `bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`
Expected: exit 0 — every slug referenced in the spec has a SKILL.md.

- [ ] **Step 4: Cross-check slugs against the spec**

Run: `comm -3 <(grep -rho 'verify-fmea-lifecycle-[a-z0-9-]*' docs/user-stories/US-E2E-02-fmea-lifecycle/ | sed 's#.*skills/##' | sort -u) <(ls .claude/skills/ | grep '^verify-fmea-lifecycle-' | sort -u)`
Expected: no output (spec-referenced slugs and on-disk skills match exactly).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/
git commit -m "feat(e2e): 19 verify-fmea-lifecycle sub-story skills (wizard×14, editor×3, version-cp×1, approval×1)"
```

---

## Task 3: Dry-run the walk and produce the acceptance report

**Files:**
- Create (output): `docs/e2e/reports/US-E2E-02-<date>/report.md` (+ `screenshots/`, `evidence/`)

**Interfaces:**
- Consumes: the running E2E stack (Task 0) + all 20 skills (Tasks 1–2) + LLM creds.
- Produces: an acceptance report labeling every sub-story criterion. **This task runs the skills; it does not edit product code.** Expected outcome today: many AI/CP/approval criteria = FAIL/MISSING (the spec-marked gaps) — that is the correct, intended result.

- [ ] **Step 1: Bring up the stack and confirm preconditions**

Run: `make e2e-up && make e2e-seed`; `curl -sf http://localhost:5174`; `curl -sf http://localhost:8001/api/e2e/seed-state`
Expected: all reachable; accounts retrieved. If LLM creds are absent, mark AI sub-stories BLOCKED and proceed with the non-AI ones.

- [ ] **Step 2: Run the epic walk via the orchestrator skill**

Invoke `verify-fmea-lifecycle` (browser MCP). Walk PFMEA wizard (02.1–02.7) → DFMEA wizard (02.8–02.14) → editor (02.15–02.18) → approval (02.19), letting each sub-skill drive its steps and record verdicts + screenshots for FAIL/MISSING.
Expected: a verdict per sub-story criterion. Do not "fix" the product mid-walk; record exactly what the product does.

- [ ] **Step 3: Write the acceptance report**

Create `docs/e2e/reports/US-E2E-02-<date>/report.md` per the epic 报告模板: 总览 (counts of PASS/PASS-NOTE/FAIL/MISSING/BLOCKED + overall conclusion), per-子故事 table, AI source_executions matrix, CP-sync verdict, approval-matrix verdict, 审计轨迹核对, and a 缺陷清单 listing every FAIL/MISSING with screenshot links.
Expected: report written; the 缺陷清单 honestly enumerates the spec-marked gaps (RAG/lessons + source_executions, adoption audit, canonical status, CP durable outbox, approval gates).

- [ ] **Step 4: Commit the report**

```bash
git add docs/e2e/reports/US-E2E-02-*/
git commit -m "test(e2e): US-E2E-02 FMEA lifecycle acceptance report — <N> PASS / <N> FAIL / <N> MISSING / <N> BLOCKED"
```

---

## Sequencing & Dependencies

```
Task 0 (branch sync — BLOCKER) ──> Task 1 (epic skill) ──> Task 2 (19 sub-skills) ──> Task 3 (walk + report)
```

Task 0 must land first (skills can't run without the harness). Tasks 1→2 are sequential (sub-skills reference the epic's shared conventions). Task 3 requires Tasks 0–2 and a live stack; if the stack can't run in the current environment, Tasks 1–2 still deliver fully-validated skills and Task 3 is deferred to an environment with Docker + LLM creds.

## Definition of Done

- `fix/fmea-fixes` carries the E2E harness; `make e2e-up && make e2e-seed` succeeds (or a recorded environment blocker).
- 20 `verify-fmea-lifecycle*` skills exist, each structurally valid, slugs matching the spec exactly (`verify-refs.sh` exit 0).
- An acceptance walk has been run (or is credibly staged) and `docs/e2e/reports/US-E2E-02-<date>/report.md` exists, honestly labeling every sub-story criterion PASS/PASS-NOTE/FAIL/MISSING/BLOCKED — including FAIL/MISSING for the spec-marked gaps.
- **No product-logic changes** were made; the only edits are skills, the report, and (Task 0) the branch sync.
