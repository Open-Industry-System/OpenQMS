# Task 2 Report — 19 verify-fmea-lifecycle Sub-story Skills

Date: 2026-07-25
Branch: fix/fmea-fixes
Status: DONE_WITH_CONCERNS

## Scope Delivered

Authored 19 sub-story verify skills under `.claude/skills/verify-fmea-lifecycle-<slug>/SKILL.md` (no product-logic changes; only Markdown walkthrough scripts). Total 2,950 lines across the 19 files.

## The 19 Files (with line counts)

### Wizard ×14 (PFMEA 7 + DFMEA 7)

| # | Slug | Lines | Spec version | AI_REQUIRED | Notes |
|---|---|---:|---|---|---|
| 02.1 | pfmea-step1-planning | 199 | 定稿 v3 | true | EXEMPLAR (wizard shape); wizardScope 5T (timeframe), `fmea-recommend` selector |
| 02.2 | pfmea-step2-structure | 151 | 定稿 v2 | false | derived from 02.1 |
| 02.3 | pfmea-step3-function | 136 | 定稿 v2 | false | derived from 02.1 |
| 02.4 | pfmea-step4-failure | 171 | 定稿 v3 | true | derived from 02.1 |
| 02.5 | pfmea-step5-risk | 161 | 定稿 v3 | true | derived from 02.1; 3-segment S (severity_plant/customer/user) + AP lookup (non-product) |
| 02.6 | pfmea-step6-optimization | 172 | 定稿 v4 | true | derived from 02.1; canonical RecommendedAction status enum (legacy → FAIL expected) |
| 02.7 | pfmea-step7-documentation | 145 | 定稿 v3 | false | derived from 02.1; wizard_completed in wizardScope |
| 02.8 | dfmea-step1-planning | 128 | 定稿 v3 | true | derived from 02.1 (PFMEA exemplar) |
| 02.9 | dfmea-step2-structure | 123 | 定稿 v2 | false | derived; shared `Process*` edge vocabulary (no HAS_SUBSYSTEM/HAS_COMPONENT) |
| 02.10 | dfmea-step3-function | 126 | 定稿 v2 | false | derived; reuse `Process*Function` node types; no CC/SC |
| 02.11 | dfmea-step4-failure | 138 | 定稿 v3 | true | derived; no 4M context (PFMEA-only) |
| 02.12 | dfmea-step5-risk | 136 | 定稿 v3 | true | derived; single S (no 3-segment); DFMEA 无 CC/SC |
| 02.13 | dfmea-step6-optimization | 126 | 定稿 v4 | true | derived; same canonical enum + FailureCause risk-disposition fields |
| 02.14 | dfmea-step7-documentation | 117 | 定稿 v3 | false | derived; same wizard_completed contract |

### Editor ×3

| # | Slug | Lines | Spec version | AI_REQUIRED | Notes |
|---|---|---:|---|---|---|
| 02.15 | editor-row-crud | 182 | 定稿 v2 | false | EXEMPLAR (editor shape); one row = FM×FC; multi-effect = FM-level shared list (no row-count fan-out); shared-node deletion rule; wizardScope preservation FAIL expected; IN_REVIEW PUT 409 FAIL expected |
| 02.16 | editor-ai-recommend | 164 | 定稿 v3 | true | derived; 5 SmartSuggestionDropdown triggers; 3 required_retrievers + context_execution + generation_execution → FAIL/MISSING expected; ADOPT_RECOMMENDATION MISSING; rate limit 5 req/s user + 24h cache |
| 02.17 | collaborative-editing | 181 | 定稿 v2 | false | derived; 409 + `confirmed_latest_lock_version` re-conflict (`lock_version_changed_again`); three-way diff preview; FORCE_SAVE_OVERRIDE audit; lock_version unchanged on no-op save |

### Version/CP ×1

| # | Slug | Lines | Spec version | AI_REQUIRED | Notes |
|---|---|---:|---|---|---|
| 02.18 | version-snapshot-cp-sync | 184 | 定稿 v4 | false | EXEMPLAR; FMEAVersion snapshot fields; **durable outbox** spec vs current direct two-phase sync call → FAIL expected; does NOT reference GraphSyncOutbox; idempotency keys (fmea_id, fmea_version_id, cp.sync_pending_set) + (outbox_id, cp_id); audit total = 2 + affected_cp_count; CP changed_fields only `sync_pending` + `trigger_fmea_version_id` (NOT source_fmea_version_id) |

### Approval ×1

| # | Slug | Lines | Spec version | AI_REQUIRED | Notes |
|---|---|---:|---|---|---|
| 02.19 | approval-cycle | 210 | 定稿 v3 | false | EXEMPLAR; 10 test cases A–J covering full permission matrix with expected FAILs: wizard_completed 422 gate absent, reject-reason 422 absent, REWORK APPROVE re-check absent, editable-state 409 on PUT absent, APPROVED→REWORK keeps approved_by/at |

## How the 4 Exemplars Were Used

1. **pfmea-step1-planning** — wizard shape (step navigation, data-e2e selector conventions, AI source_executions assertion block, 落库 contract). All 13 other wizard skills derived by substituting: node/edge types for the step, edge direction, acceptance-contract rows from the spec's 验收契约 table, AI_REQUIRED flag, and 故事版本 header.
2. **editor-row-crud** — editor shape (row model, shared-node deletion, save flow, wizardScope preservation). Drove 02.16 and 02.17.
3. **version-snapshot-cp-sync** — version + CP sync shape (snapshot assertion, outbox contract, audit-count contract).
4. **approval-cycle** — permission-matrix shape (per-case expected outcome table).

Every derived skill is a complete standalone SKILL.md (no "see step1" shortcuts); shared blocks (AI contract, defect taxonomy, report fragment, 维护 section) are inlined into each file.

## Validation Results

```
$ ls .claude/skills/ | grep -c '^verify-fmea-lifecycle'
20    # 19 sub-story + 1 epic orchestrator

$ bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh
exit=0    # no MISSING lines

$ comm -3 <(ls .claude/skills/ | grep '^verify-fmea-lifecycle-' | sed 's/^verify-fmea-lifecycle-//' | sort) \
          <(grep -rh 'verify-fmea-lifecycle-[a-z0-9-]*' docs/user-stories/US-E2E-02-fmea-lifecycle/ -o \
            | sed 's/verify-fmea-lifecycle-//' | sort -u | grep -v '^$')
# no output — all 19 real slugs match exactly
```

## Ambiguities Encountered

1. **comm -3 grep artifact**: The spec README's maintenance section contains the literal placeholder "对应 `verify-fmea-lifecycle-{name}` 子 skill 须重新核对同步". The regex `[a-z0-9-]*` matches zero characters after the trailing dash on `{name}`, producing a phantom slug `verify-fmea-lifecycle-` (bare prefix). Filtered via `grep -v '^$'` on the extracted slug. Anyone running the brief's literal `comm -3` command without this filter will see this artifact — it does NOT indicate a missing skill.
2. **Per-story versions**: not uniform. 02.6/02.13/02.18 = 定稿 v4; 02.2/02.3/02.9/02.10/02.15/02.17 = 定稿 v2; all others = 定稿 v3 (all dated 2026-07-25). Each SKILL.md header uses its OWN sub-story's version (not the epic README's).
3. **data-e2e coverage**: only `fmea-create` / `fmea-open` / `fmea-recommend` / `fmea-highlight-active` / `fmea-version-snapshot` / `row-<document_no>` exist in the codebase. Wizard step inputs (team/task/timeframe/tool/trend, process_number, classification, optimization fields) have NO data-e2e hooks — skills instruct locating via i18n text/placeholder and judging MISSING when controls are absent.
4. **02.18 CP sync**: spec mandates durable outbox but current code is direct two-phase call (fmea_service.py commit → mark_cp_sync_pending_on_fmea_approve → control_plan_service.py commit) → skills assert FAIL; GraphSyncOutbox is deliberately not referenced.

## Concerns

1. The `comm -3` artifact (item 1 above) will recur for anyone running the brief's literal validation command. Consider amending the README placeholder to avoid the trailing-dash match (e.g., wrap in quotes) or updating `verify-refs.sh` to filter it.
2. `.gitignore` has `!.claude/skills/` negation, so `git add .claude/skills/` would work without `-f`; the brief prescribes `git add -f .claude/skills/` — used as prescribed, harmless either way.
3. Expected-FAIL assertions (02.16 3-retriever contract, 02.17/02.19 permission matrix, 02.18 outbox, 02.6/02.13 canonical enum) are written as "当前预期 FAIL/MISSING" in each skill's 判定汇总 — these are contract-vs-implementation gaps, not skill authoring gaps.

---

## Review Fix — Inline AI-Contract + Selector Tables (2026-07-25, post-review)

Reviewer flagged 4 DFMEA sub-skills as violating the "complete standalone SKILL.md" rule via pointer references. Fixed mechanically — no other content touched.

### Files fixed

1. **`.claude/skills/verify-fmea-lifecycle-dfmea-step4-failure/SKILL.md` (02.11)**
   - Inlined AI-contract block into §C step 3 (replaced pointer "断言：同 02.4 §C" / "当前预期 FAIL/MISSING：同 02.4").
   - Block asserts: `source_executions` covering graph/semantic_search/lessons_learned (status ∈ {success, empty, unavailable, error}); `context_execution.current_product_structure` ∈ {assembled, unavailable}; `generation_execution.llm` ∈ {success, unavailable, error}; `rule` NOT a required retriever; healthy-env E2E → each retriever success|empty else FAIL; absent field → FAIL/MISSING.
   - Trigger names adjusted to 02.11's 5 triggers: `failure_mode` / `failure_effect` / `failure_cause` / `prevention_control` / `detection_control`.
   - Added explicit step 4 covering FE/FC/PC/DC trigger fan-out.

2. **`.claude/skills/verify-fmea-lifecycle-dfmea-step5-risk/SKILL.md` (02.12)**
   - Inlined AI-contract block into §E step 5 (replaced "当前预期 FAIL/MISSING：同 02.4").
   - Same assertion shape as above; trigger names = 02.12's 2 triggers: `prevention_control` / `detection_control`.

3. **`.claude/skills/verify-fmea-lifecycle-dfmea-step6-optimization/SKILL.md` (02.13)**
   - Inlined AI-contract block into §C step 3 (replaced "断言：3 required_retrievers 可观测" stub + "当前预期 FAIL/MISSING" bare).
   - Trigger name = 02.13's single trigger: `optimization`.
   - Preserved the "写入 name 非 action_taken" key check (02.13-specific).
   - Inlined selector table from 02.6 (PFMEAWizardPage.tsx refs → DFMEAWizardPage.tsx).

4. **`.claude/skills/verify-fmea-lifecycle-dfmea-step7-documentation/SKILL.md` (02.14)**
   - Inlined selector table from 02.7 (PFMEAWizardPage.tsx refs → DFMEAWizardPage.tsx).
   - No AI contract in this file (AI_REQUIRED=false), so no AI-contract change needed.

### Validation outputs

```
=== CHECK 1: source_executions present in all 3 ===
.claude/skills/verify-fmea-lifecycle-dfmea-step4-failure/SKILL.md
.claude/skills/verify-fmea-lifecycle-dfmea-step5-risk/SKILL.md
.claude/skills/verify-fmea-lifecycle-dfmea-step6-optimization/SKILL.md

=== CHECK 2: residual "参照 02.|同 02." pointers ===
.claude/skills/verify-fmea-lifecycle-dfmea-step4-failure/SKILL.md:18:1. **失效链边方向**（同 02.4）：HAS_FAILURE_MODE / EFFECT_OF / CAUSE_OF / PREVENTED_BY / DETECTED_BY。
.claude/skills/verify-fmea-lifecycle-dfmea-step5-risk/SKILL.md:19:2. **AP 查表**：同 02.5，非 S×O×D 乘积。

=== CHECK 3: verify-refs.sh ===
exit 0
```

CHECK 2 residuals are Overview-section cross-refs (not pointer-stubs): the operative edge list is fully inlined in step4 §D lines 90-94 and the AP lookup assertion is fully inlined in step5 §C lines 67-69. These are the same kind of "见 epic" legitimate cross-refs the brief allows.

Field-literal coverage check across the 3 files (counts of `source_executions` / `context_execution` / `generation_execution` / `current_product_structure` / `semantic_search` / `lessons_learned` / `success, empty, unavailable, error` / `assembled, unavailable`): all 3 files contain all 8 literal markers.

### Branch note

`.claude/skills/` is tracked in this repo (`.gitignore` has `!.claude/skills/` negation); `git add .claude/skills/...` works without `-f`. Used `git add` with explicit paths.
