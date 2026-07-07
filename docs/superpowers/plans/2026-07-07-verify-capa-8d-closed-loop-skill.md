# verify-capa-8d-closed-loop skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a project-level skill that guides an agent to walk the US-E2E-01 CAPA 8D closed-loop user story end-to-end in a real browser and produce a markdown acceptance report.

**Architecture:** A single OpenQMS-specific technique/reference skill at `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`, plus a project-level sync rule in `CLAUDE.md` and report directories under `docs/e2e/reports/`. The skill is a fixed walk script (selectors, APIs, 8D state machine, defect taxonomy, report template) — not a generic method. Verification is a bash script that asserts every `data-e2e` selector referenced in the skill exists in `frontend/src`, plus manual grep checks for each backend API path.

**Tech Stack:** Markdown skill doc (Agent Skills format, YAML frontmatter), bash validation script, Playwright browser MCP (`browser_*`) at walk time.

## Global Constraints

- Skill name `verify-capa-8d-closed-loop` — letters/numbers/hyphens only.
- YAML frontmatter: `name` + `description`, ≤1024 chars total; `description` starts with "Use when", third person, describes **when to use only** (never summarizes workflow).
- All selectors written quoted: `[data-e2e="..."]`.
- **Never** use `make e2e` to bring up services — it runs the full Playwright spec suite (Makefile:75-77). Use `make e2e-up && make e2e-seed`; clean env via `make e2e-reset`.
- Default to the `:5174` e2e stack only. `/api/e2e/*` routes register only under `E2E_MODE=1` + non-production (`backend/app/main.py:450`), set only in `docker-compose.e2e.yml:21`.
- Account passwords come from `GET /api/e2e/seed-state` at walk time — never hardcoded.
- Reports land in `docs/e2e/reports/`, screenshots in `docs/e2e/reports/assets/`.
- Story version referenced by the skill: 定稿 v7 (2026-07-07) — must match `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md` header.
- CAPA response field is `status` (not `current_step`); initial value `D1_TEAM` (`backend/app/schemas/capa.py:34`, `models/capa.py:23`).
- The sync rule added to `CLAUDE.md` applies to **all** future `verify-*` skills, not just this one.

**Source of truth:** `docs/superpowers/specs/2026-07-07-verify-capa-8d-closed-loop-skill-design.md`.

---

### Task 1: Scaffold skill + report directories

**Files:**
- Create: `.claude/skills/verify-capa-8d-closed-loop/` (directory)
- Create: `.claude/skills/verify-capa-8d-closed-loop/scripts/` (directory)
- Create: `docs/e2e/reports/.gitkeep`
- Create: `docs/e2e/reports/assets/.gitkeep`

- [ ] **Step 1: Create the directories and .gitkeep files**

```bash
mkdir -p .claude/skills/verify-capa-8d-closed-loop/scripts
mkdir -p docs/e2e/reports/assets
touch docs/e2e/reports/.gitkeep docs/e2e/reports/assets/.gitkeep
```

- [ ] **Step 2: Verify they exist**

Run: `ls -R .claude/skills/verify-capa-8d-closed-loop && ls docs/e2e/reports docs/e2e/reports/assets`
Expected: `scripts` dir listed; both `.gitkeep` files listed.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/verify-capa-8d-closed-loop docs/e2e/reports
git commit -m "chore(e2e): scaffold verify-capa-8d-closed-loop skill + report dirs"
```

---

### Task 2: Add User Story ↔ Skill sync rule to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (append a new section after the `## Known Gaps` section, which ends the file at line 190 with "Some Alembic migration numbers overlap; needs normalization")

**Interfaces:**
- Produces: a project-level `## User Story ↔ Skill 同步规则` section in `CLAUDE.md`, referenced by the skill's maintenance section.

- [ ] **Step 1: Append the sync-rule section to CLAUDE.md**

Append exactly this to the end of `CLAUDE.md` (after the final "Some Alembic migration numbers overlap; needs normalization" line):

```markdown

## User Story ↔ Skill 同步规则

每个 `verify-*` skill 是某条用户故事的**派生走查剧本**（单向派生）：

- 源头：`docs/user-stories/US-<id>-<name>.md`（含「状态: 定稿 vX（日期）」）
- 派生：`.claude/skills/verify-<name>/SKILL.md`（顶部声明依据的故事版本）

**规则**：当用户故事的版本号或日期变更，对应 skill 剧本必须重新核对并同步，
更新顶部版本声明后才能用于走查。agent 每次跑 `verify-*` skill 前先比对
skill 内记的故事版本与用户故事顶部实际版本——不一致则停下、提示用户先同步。
```

- [ ] **Step 2: Verify the section was added**

Run: `tail -12 CLAUDE.md`
Expected: the `## User Story ↔ Skill 同步规则` heading and the four bullet lines + rule paragraph are present.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add User Story ↔ Skill sync rule for verify-* skills"
```

---

### Task 3: Write the reference-validation script (RED)

**Files:**
- Create: `.claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`

**Interfaces:**
- Produces: `verify-refs.sh` — exits 0 if `SKILL.md` exists, its frontmatter has `name: verify-capa-8d-closed-loop` and a `description: Use when...` line, and every `[data-e2e="X"]` selector referenced in `SKILL.md` appears in `frontend/src`; exits non-zero otherwise.

- [ ] **Step 1: Create the validation script**

Write `.claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`:

```bash
#!/usr/bin/env bash
# Verify references in verify-capa-8d-closed-loop SKILL.md.
# Checks: SKILL.md exists, frontmatter valid, every [data-e2e="X"] in SKILL.md
# appears in frontend/src. Exit non-zero on any problem.
set -uo pipefail
SKILL=".claude/skills/verify-capa-8d-closed-loop/SKILL.md"
[ -f "$SKILL" ] || { echo "FAIL: $SKILL not found"; exit 1; }

# 1. frontmatter
head -20 "$SKILL" | grep -q '^name: verify-capa-8d-closed-loop' || { echo "FAIL: missing/wrong name frontmatter"; exit 1; }
head -20 "$SKILL" | grep -q '^description: Use when' || { echo "FAIL: missing/bad description frontmatter"; exit 1; }

# 2. every [data-e2e="X"] in SKILL.md must appear in frontend/src
status=0
for sel in $(grep -oE 'data-e2e="[^"]+"' "$SKILL" | sed -E 's/data-e2e="([^"]+)"/\1/' | sort -u); do
  # rec-dag-stage-<i> is a JSX template literal (data-e2e={`rec-dag-stage-${i}`}),
  # not a quoted attr — search the bare prefix, not data-e2e="rec-dag-stage-.
  if [[ "$sel" == "rec-dag-stage-"* ]]; then
    if ! grep -rqs 'rec-dag-stage-' frontend/src; then
      echo "MISSING selector in frontend/src: $sel"
      status=1
    fi
    continue
  fi
  if ! grep -rqs "data-e2e=\"$sel\"" frontend/src; then
    echo "MISSING selector in frontend/src: $sel"
    status=1
  fi
done
exit $status
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`

- [ ] **Step 3: Run it to verify it FAILS (RED — SKILL.md does not exist yet)**

Run: `bash .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`
Expected: `FAIL: .claude/skills/verify-capa-8d-closed-loop/SKILL.md not found` and non-zero exit.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh
git commit -m "test(skill): add verify-capa-8d skill reference-validation script"
```

---

### Task 4: Write SKILL.md (GREEN)

**Files:**
- Create: `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`

**Interfaces:**
- Consumes: the sync rule added in Task 2 (referenced in the maintenance section); the validation script from Task 3.
- Produces: `SKILL.md` — the complete walk playbook. Subsequent tasks verify its references.

- [ ] **Step 1: Write the full SKILL.md**

Write `.claude/skills/verify-capa-8d-closed-loop/SKILL.md` with exactly this content:

````markdown
---
name: verify-capa-8d-closed-loop
description: Use when asked to verify / walk through / 验收 / 走查 the OpenQMS CAPA 8D closed-loop user story (US-E2E-01) end-to-end in a real browser — e.g. "验收 US-E2E-01" / "walk through this user story" / "端到端测试这个用户故事". Symptoms include needing to confirm acceptance criteria pass, check the AI recommendation orchestration DAG, or produce an acceptance report for the 8D closed-loop story.
---

> 依据：docs/user-stories/US-E2E-01-capa-8d-closed-loop.md
> 故事版本：定稿 v7（2026-07-07）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-capa-8d-closed-loop

## Overview

把用户故事 US-E2E-01（8D 全程闭环 + AI 多源推荐 + 根因现场验证 + 流程可视化）在真实浏览器里走一遍，逐条验收每条验收标准，输出 markdown 验收报告。用浏览器 MCP（`browser_*`）驱动；账号从 `/api/e2e/seed-state` 动态取；断言走 UI selector + 回读 API + 审计 API。

这是 acceptance walk（人可读验收报告），不是 Playwright spec——spec 写在 `frontend/e2e/specs/`，本 skill 不写 spec。

## When to Use

**用**：用户说「验收 US-E2E-01」「走查这个用户故事」「端到端测试 CAPA 8D 闭环」等。
**不用**：测其他用户故事（另起 `verify-*` skill）；写/改 Playwright spec；AI 推荐准确率评测。

## 前置（开始前必须全部满足，否则停下）

1. **故事版本一致**：读本 skill 顶部「故事版本」，与 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md` 顶部「状态: 定稿 vX（日期）」比对；不一致 → 停下，提示用户先同步（见「维护」），不跑。
2. **e2e 栈在跑**：`curl -sf http://localhost:5174` 验证可达。
   - 不可达 → 跑 `make e2e-up && make e2e-seed` 拉起服务并 seed（**不**用 `make e2e`，它会跑整套 Playwright spec）。干净环境用 `make e2e-reset`。
   - 默认只用 `:5174`（e2e 栈）。`/api/e2e/seed-state` 和 `/api/e2e/cleanup` 只在 `E2E_MODE=1` 且非 production 注册（`backend/app/main.py:450`），只有 e2e compose 设了 `E2E_MODE=1`（`docker-compose.e2e.yml:21`）。
   - 用户强制 `:5173`（dev 栈）→ 必须先 `GET /api/e2e/seed-state` 验证可达；不可达 → 停下，提示改用 e2e 栈。
3. **LLM 凭证齐**：读 `.env.e2e`，要 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL` 四项全有。
   - 缺 → 停下，提示用户配置（给字段清单），配好后再继续。**不自行降级跑**（AI 步骤是本故事头条验收项，缺凭证无法验收）。
4. **拿账号**：`GET /api/e2e/seed-state` 取 admin/engineer/manager/viewer 密码（不硬编码）。

## 账号 × 权限表

| 账号 | 角色 | 能推进的 D 步 | 不能 |
|---|---|---|---|
| engineer | field_qe | D1→D2…D6→D7（EDIT） | D7→D8（需审批） |
| manager | 8D 负责人 | D7→D8（审批） | — |
| viewer | 只读 | 无 | 任何编辑/推进 |
| admin | 全权 | 全部 | — |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| `[data-e2e="capa-create"]` | 点击 | 新建 8D |
| `[data-e2e="capa-advance"]` | 点击 | 推进下一步（D1→…→D8 共用；D7→D8 需 canApprove） |
| `[data-e2e="capa-ai-draft"]` | 点击 | AI 草拟（D2/D3/D4/D5/D6 label 上的草拟入口） |
| `[data-e2e="d4-adopt"]` | 点击 | D4 采纳推荐根因 |
| `[data-e2e="d4-verification-new"]` | 点击 | D4 新建现场验证表单 |
| `[data-e2e="verification-method"]` | 填 input | 验证方法 |
| `[data-e2e="verification-result"]` | 填 textarea | 测量/观察结果 |
| `[data-e2e="verification-evidence"]` | 点内「添加证据」→ 文件选择 | 证据附件（Ant Upload） |
| `[data-e2e="verification-form-is-verified"]` | 勾 Switch | **新建表单**的「已验证」 |
| `[data-e2e="verification-is-verified"]` | — | **不要点**——已有记录列表的切换开关 |
| `[data-e2e="verification-submit"]` | 点击 | 提交验证 |
| `[data-e2e="verification-status"]` | 读可见文本 | 验证状态 |
| `[data-e2e="d5-adopt-suggestion"]` | 点击 | D5 采纳推荐措施 |
| `[data-e2e="d5-adopt-control"]` | 点击 | D5 采纳为控制措施 |
| `[data-e2e="d7-auto-fill"]` | 点击 | D7 AI 预防提示自动填充 |
| `[data-e2e="d7-confirm"]` | 点击 | D7 确认预防项 |
| `[data-e2e="d7-skip"]` | 点击 | D7 跳过预防项（需填理由） |
| `[data-e2e="rec-dag-stage-<i>"]` | 读 `data-status` 属性 + 节点内可见文本 | 12 阶段 DAG 第 i 阶段（`source`/`hit_count`/`summary` 是 Tag/Badge/Text，不是属性） |

**无 data-e2e 的字段**：D1 团队表、D2/D3/D4/D5/D6 的 TextArea、登录表单——用可见 label/placeholder 定位（Ant Form）：`getByLabel("5W2H 问题描述")`、`getByPlaceholder("成员姓名")`、登录用 `getByLabel("用户名")` / `getByLabel("密码")` + 登录按钮文本。

## 8D 状态机

`D1_TEAM → D2_DESCRIPTION → D3_INTERIM → D4_ROOT_CAUSE → D5_CORRECTION → D6_VERIFICATION → D7_PREVENTION → D8_CLOSURE`（`backend/app/state_machines/eightd_state.py`）。回退边 `D4→D3`、`D6→D5`（验证不通过回到上一步）。不可跳步。D1–D6 推进需 EDIT（engineer 可）；D7→D8 需审批（manager 可，engineer 不可）。

## 走查剧本

### A. 启动（前置 4 项全过后）

- `browser_navigate("http://localhost:5174")` → `GET /api/e2e/seed-state` 拿账号密码。
- 记录走查开始 ISO 时间（audit 查询的 `start` 窗口用）。

### B. 8D 闭环（10 步，每步四段式）

#### B1 engineer 登录 + 新建 8D
- **做**：`browser_navigate` 登录页 → 按 label 填用户名/密码（engineer）→ 点登录 → 进 CAPA 列表 → 点 `[data-e2e="capa-create"]` → 填单号 `E2E-STORY-CAPA-001` / 标题「来料螺栓尺寸超差」/ 严重度「致命」/ 产品线 `DC-DC-100-E2E` → 提交。
- **期望**：列表出现该单号；详情页 Steps 高亮 D1。
- **断言**：`GET /api/capa/{report_id}` 回读 `status == "D1_TEAM"`、`title`/`severity`/`document_no`/`product_line_code` 正确。
- **落库**：审计 1 条 CREATE，`operated_by == "engineer"`。

#### B2 D1 团队组建
- **做**：D1 视图下用 `getByPlaceholder("成员姓名")` 填名 + Select 选 role（含一人为「8D 团队负责人」）→ 点「添加成员」加 2–3 人。
- **期望**：团队成员表出现新增行。
- **断言**：`GET /api/capa/{report_id}` 回读 `d1_team` 数组含所加成员。
- **落库**：UPDATE 审计（engineer）。

#### B3 D2 问题描述 + AI 草拟
- **做**：`getByLabel("5W2H 问题描述")` 填描述 → 点 `[data-e2e="capa-ai-draft"]` 触发 AI 草拟 → 确认/采纳后保存（onBlur 落库）。
- **期望**：AI 草拟返回文本；保存后字段落库。
- **断言**：回读 `d2_description` 非空。
- **落库**：UPDATE + AI 草拟留痕。

#### B4 D3 临时措施
- **做**：`getByLabel("临时遏制措施")` 填临时围堵 → onBlur 保存。
- **期望**：字段落库。
- **断言**：回读 `d3_interim` 非空。
- **落库**：UPDATE。

#### B5 D4 根因分析（含 AI 推荐 + 现场验证）
- **做**：点 `[data-e2e="capa-advance"]` 推进到 D4 → 触发 D4 AI 推荐（见 C1）→ 点 `[data-e2e="d4-adopt"]` 采纳一条候选根因 → 现场验证（见 C2）→ `getByLabel("根因分析 (5Why / 鱼骨图)")` 填根因 → 点 `[data-e2e="capa-advance"]` 推进 D4→D5。
- **期望**：D4 视图出现 D4RecPanel + D4VerificationCard + 根因 TextArea。
- **断言**：**未完成现场验证时 D4→D5 应被阻断**（advance 报错或禁用）；验证通过后才可推进。
- **落库**：审计 1 条 TRANSITION `D4_ROOT_CAUSE → D5_CORRECTION`，`operated_by == "engineer"`。

#### B6 D5 永久措施（含 AI 推荐）
- **做**：推进到 D5 → 触发 D5 AI 推荐（见 C1）→ 点 `[data-e2e="d5-adopt-suggestion"]`（或 `d5-adopt-control`）采纳 → `getByLabel("永久纠正措施")` 填措施 → 保存。
- **期望**：D5RecPanel + 措施 TextArea。
- **断言**：回读 `d5_correction` 非空；采纳留痕（审计 `action == "ADOPT_RECOMMENDATION"`）。
- **落库**：UPDATE + 采纳留痕。

#### B7 D6 实施验证
- **做**：`getByLabel("效果验证")` 填验证结果 → 保存 → 点 `[data-e2e="capa-advance"]` 推进 D6→D7。
- **期望**：字段落库；推进成功。
- **断言**：回读 `d6_verification` 非空；审计 1 条 TRANSITION `D6_VERIFICATION → D7_PREVENTION`，`operated_by == "engineer"`。

#### B8 D7 预防复发（含 AI 预防提示）
- **做**：D7 视图下对每个预防项用 `[data-e2e="d7-auto-fill"]`（AI 填充）/ `[data-e2e="d7-confirm"]`（确认）/ `[data-e2e="d7-skip"]`（跳过，填理由）。
- **期望**：D7 预防项全部确认或跳过后才可推进。
- **断言**：`d7_*` 字段落库；engineer 此时**不能**推进 D7→D8（见 B9）。

#### B9 manager 登录 + 审批 D7→D8 关闭
- **做**：登出 → manager 登录 → CAPA 列表见该 8D（待审批）→ 进详情 → 点 `[data-e2e="capa-advance"]`（D7→D8，需 canApprove）→ 关闭。
- **期望**：manager 能推进；engineer 不能（先切 engineer 验证 `capa-advance` 不可见/禁用，再切 manager 推进）。
- **断言**：审计 1 条 TRANSITION `D7_PREVENTION → D8_CLOSURE`，`operated_by == "manager"`。
- **落库**：D8 closure 字段。

#### B10 viewer 只读可见
- **做**：登出 → viewer 登录 → CAPA 列表见已关闭 8D → 进详情可读内容。
- **期望**：详情可见，但无 `[data-e2e="capa-create"]` / `capa-advance` / 编辑控件。
- **断言**：`capa-advance` 不存在或禁用；各 TextArea `disabled`。
- **落库**：viewer 不产生任何写审计。

### C. AI 推荐流程编排（D4/D5 各跑完整 12 阶段 DAG）

#### C1 触发 + 12 阶段断言

在 D4RecPanel / D5RecPanel 触发推荐。对 `i=1..12` 查 `[data-e2e="rec-dag-stage-<i>"]`：

| i | 阶段 | 期望状态 |
|---|---|---|
| 1 | 上下文采集 | done |
| 2 | 本产品 FMEA 检索 | done |
| 3 | 全局知识库 RAG（pgvector） | done |
| 4 | 同类型产品知识库 | done 或 skipped（注明） |
| 5 | 经验教训库 | done 或 skipped |
| 6 | SPC 异常关联 | done 或 skipped（无 SPC 数据） |
| 7 | MES 设备/过程数据 | done 或 skipped |
| 8 | IQC 来料检验（本批螺栓） | done |
| 9 | 供货历史 | done |
| 10 | 规则启发 | done |
| 11 | LLM 融合排序 | done（需 LLM 凭证） |
| 12 | 输出推荐列表 | done |

读 `data-status` 属性；`source`（Tag）/`hit_count`（Badge）/`summary`（Text）是节点可见文本，从渲染内容读（`frontend/src/components/capa/RecommendationDAG.tsx:45-51`）。

**断言**：
- 推荐列表非空、每条带 source provenance、`AP∈{H,M,L}`、`S/O/D∈1..10`。
- 阶段 `hit_count`/`summary` 可见（非黑盒）。
- D4、D5 各跑一遍，分别记录。

#### C2 真点接受 + 现场验证（D4）

- 点 `[data-e2e="d4-adopt"]` 采纳一条候选根因。
- 点 `[data-e2e="d4-verification-new"]` 打开新建验证表单：
  - 填 `[data-e2e="verification-method"]`（input）
  - 填 `[data-e2e="verification-result"]`（textarea）
  - 上传证据：点 `[data-e2e="verification-evidence"]` 内「添加证据」按钮触发文件选择 → `browser_file_upload` 传临时证据文件（`$CLAUDE_JOB_DIR/tmp/evidence-<n>.png`）
  - 勾 `[data-e2e="verification-form-is-verified"]`（**不要**点 `verification-is-verified`）
  - 点 `[data-e2e="verification-submit"]`
- **断言**：`[data-e2e="verification-status"]` 显示已验证；`GET /api/capa/{report_id}/root-cause-verifications` 回读验证记录含 method/result/evidence。
- **断言**：未验证时 D4→D5 阻断；验证通过后可推进。

### D. 收尾 + 报告

- **清理**：admin token（seed-state 取密码 → `POST /api/auth/login`）→ `POST /api/e2e/cleanup?prefix=E2E-STORY-`（只删本前缀走查记录，**不删 seed**）。
- 关浏览器。
- 写报告（见「报告模板」）。

## 缺陷分类（每步打一个标签）

| 标签 | 含义 | 例子 |
|---|---|---|
| **PASS** | 断言全满足 | D4→D5 推进成功、落库正确 |
| **PASS-NOTE** | 通过但有备注（不阻断） | SPC 阶段 skipped 且注明「无 SPC 数据」 |
| **FAIL** | 断言失败 = 缺陷 | FMEA 阶段 status=error、推荐列表空、provenance 缺失、未验证却放行 D4→D5 |
| **MISSING** | 故事要求的功能根本不存在 = 缺陷 | D4RecPanel 没渲染、`[data-e2e="rec-dag-stage-*"]` 找不到、无采纳按钮 |

**MISSING 和 FAIL 都算缺陷**，在报告「缺陷清单」单列。PASS-NOTE 不算缺陷。

**当作已实现去测**：找不到 selector / 面板没渲染 → 直接判 MISSING，**不**自行脑补「这功能可能还没做所以跳过」。

每个 FAIL/MISSING 用浏览器 MCP 截图存 `docs/e2e/reports/assets/US-E2E-01-<date>/step-<n>.png`。

## 报告模板

路径：`docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>.md`

```markdown
# US-E2E-01 验收报告 — <date>

- 故事版本：定稿 v7（2026-07-07）
- skill 依据版本：v7（2026-07-07）
- 走查时间：<开始ISO> ~ <结束ISO>
- app commit：<git rev-parse HEAD>
- LLM 凭证状态：齐全 / 缺（哪几项）

## 总览
- PASS: N | PASS-NOTE: N | FAIL: N | MISSING: N
- 整体结论：PASS / 有缺陷 / BLOCKED

## B 段步骤表
| 步 | 做什么 | 期望 | 断言结果 | 标签 |
|---|---|---|---|---|
| B1 | 新建 8D | status=D1_TEAM | GET 回读 status=D1_TEAM | PASS |
| ... |

## C 段 DAG 阶段矩阵（D4）
| i | 名称 | 来源 | 状态 | 命中数 | 摘要 | 标签 |
|---|---|---|---|---|---|---|
| 1 | 上下文采集 | ... | done | ... | ... | PASS |
| ... |

## C 段 DAG 阶段矩阵（D5）
（同上）

## 审计轨迹核对
- 期望：1 CREATE + 7 TRANSITION（6 条 D1→D2…D6→D7 by engineer，末条 D7→D8 by manager）
- 实际：`GET /api/admin/logs/audit?table_name=capa_eightd&page=1&page_size=200&start=<开始ISO>` 按 record_id 过滤 → 列出每条 old_status/new_status/operated_by
- 结果：PASS/FAIL

## AI 采纳留痕核对
- `action == "ADOPT_RECOMMENDATION"` 条数、changed_fields.source / stage_index / operated_by
- 结果：PASS/FAIL

## 落库抽查
- `GET /api/capa/{report_id}`：document_no / title / severity / status / 各 D 步字段
- `GET /api/capa/{report_id}/root-cause-verifications`：验证记录
- 结果：PASS/FAIL

## 缺陷清单
| 步 | 期望 | 实际 | 严重度 | 截图 |
|---|---|---|---|---|
| ... |

## 证据附件
- 上传文件名 + 详情页是否可见
```

## 维护（同步）

本 skill 是用户故事的**单向派生剧本**。每次跑前：

1. 读 skill 顶部「故事版本」。
2. 读 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md` 顶部「状态: 定稿 vX（日期）」。
3. 版本号/日期一致 → 直接跑。
4. 不一致 → 停下，提示用户：「用户故事已更新到 vX，skill 剧本仍停在 vY，需同步后再跑。要我现在同步吗？」
   - 同步 = 重读故事 → 逐条核对剧本（步骤/断言/selector/状态机）→ 改 SKILL.md → 更新顶部版本声明 → 重跑。

`CLAUDE.md` 里有项目级同步规则（对所有 `verify-*` skill 通用）。引用校验脚本：`bash .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`。
````

- [ ] **Step 2: Run the validation script to verify it now PASSES (GREEN)**

Run: `bash .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh`
Expected: exit 0, no output (all selectors found in `frontend/src`, frontmatter valid).

If any selector is reported MISSING: fix the selector in `SKILL.md` to match the real `data-e2e` value from `frontend/src`, then re-run until it passes.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/verify-capa-8d-closed-loop/SKILL.md
git commit -m "feat(skill): add verify-capa-8d-closed-loop acceptance-walk skill"
```

---

### Task 5: Verify backend API references in SKILL.md

Every `/api/...` path in `SKILL.md` must correspond to a real backend route. Confirm each with a concrete grep.

**Files:**
- Modify (only if a path is wrong): `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`

- [ ] **Step 1: Verify /api/e2e/seed-state and /api/e2e/cleanup exist (e2e router)**

Run: `grep -rn "seed-state\|cleanup" backend/app/api/e2e.py`
Expected: both route names present.

- [ ] **Step 2: Verify /api/auth/login exists**

Run: `grep -n 'prefix="/api/auth"\|router.post("/login")\|access_token' backend/app/api/auth.py`
Expected: `router = APIRouter(prefix="/api/auth")` (~line 39), `@router.post("/login")` (~line 113), `access_token` in the token response. Full path is `POST /api/auth/login`.

- [ ] **Step 3: Verify /api/admin/logs/audit exists**

Run: `grep -n 'router.get("/audit")\|table_name\|prefix' backend/app/api/admin/logs.py`
Expected: `router = APIRouter(prefix="/api/admin/logs")`, `@router.get("/audit")`, a `table_name` param (route at ~line 20). The audit endpoint is `GET /api/admin/logs/audit`.

- [ ] **Step 4: Verify /api/capa/{report_id} and sub-paths exist**

Run: `grep -n 'router.get("/{report_id}"\|root-cause-verifications\|adopt-recommendation' backend/app/api/capa.py`
Expected: lines for `/{report_id}` (GET, ~147), `/{report_id}/root-cause-verifications` (GET ~653), `/{report_id}/adopt-recommendation` (POST ~616).

- [ ] **Step 5: If any path is missing or misnamed, fix SKILL.md and re-run Task 4 Step 2**

If a grep above misses, correct the path in `SKILL.md` to the real route, then re-run `bash .claude/skills/verify-capa-8d-closed-loop/scripts/verify-refs.sh` (still passes — selector check unaffected) and commit:

```bash
git add .claude/skills/verify-capa-8d-closed-loop/SKILL.md
git commit -m "fix(skill): correct backend API paths in verify-capa-8d skill"
```

If all paths verified and no changes needed, skip the commit (nothing staged).

---

### Task 6 (optional, env-gated): Live smoke walk

Only run this if the e2e stack is up AND `.env.e2e` has all four LLM credentials. Otherwise skip — note "live walk deferred: env not ready" and stop.

**Goal:** Prove a real agent can follow `SKILL.md` end-to-end and produce a report.

- [ ] **Step 1: Confirm env is ready**

Run: `bash -c 'curl -sf http://localhost:5174 >/dev/null || exit 1; missing=0; for k in LLM_PROVIDER LLM_API_KEY LLM_MODEL LLM_BASE_URL; do grep -qE "^${k}=.+" .env.e2e || missing=1; done; [ "$missing" -eq 0 ] && echo READY || echo NOT_READY'`
Expected: `READY`. If `NOT_READY`, stop this task and record "live walk deferred". (A missing field sets `missing=1` instead of short-circuit-exiting, so the final `[ ]` always prints READY or NOT_READY; `bash -c` wraps it so the `exit 1` on curl failure and the `&&`/`;` precedence are unambiguous.)

- [ ] **Step 2: Dispatch a fresh subagent to execute the skill**

Use the Agent tool with a prompt: "Use the `verify-capa-8d-closed-loop` skill (at `.claude/skills/verify-capa-8d-closed-loop/SKILL.md`) to walk US-E2E-01 end-to-end. Follow the skill exactly: run the preflight checks, execute the B/C/D walkthrough, and write the report to `docs/e2e/reports/US-E2E-01-$(date +%F).md`. Report back the pass/fail counts and any FAIL/MISSING defects."

- [ ] **Step 3: Review the produced report**

Read `docs/e2e/reports/US-E2E-01-<date>.md`. Confirm it has all 9 sections from the report template and the B/C matrices are filled.

- [ ] **Step 4: Commit the report**

```bash
git add docs/e2e/reports/US-E2E-01-<date>.md
git commit -m "docs(e2e): US-E2E-01 acceptance walk report <date>"
```

- [ ] **Step 5: If defects were found, file them**

For each FAIL/MISSING in the report, surface it to the user (do not silently fix — the skill's job is to report defects, not patch them). If the defect is a skill error (wrong selector/path), fix the skill per Task 4/5 and re-run.

---

## Self-Review (run after writing this plan)

**Spec coverage:** Every section of the design doc maps to a task — skill identity/前置 → SKILL.md body; sync mechanism → Task 2 (CLAUDE.md) + SKILL.md maintenance section; report dirs → Task 1; defect taxonomy + report template → SKILL.md; selector/API correctness → Task 3 (script) + Task 5 (greps); live proof → Task 6. ✓

**Placeholder scan:** No TBD/TODO; SKILL.md content is complete inline; all greps have expected outputs. ✓

**Type consistency:** Skill name `verify-capa-8d-closed-loop` consistent across frontmatter, script, CLAUDE.md section, commit messages. Selector names match `frontend/src` (verified during planning: `capa-create`, `capa-advance`, `capa-ai-draft`, `d4-adopt`, `d4-verification-new`, `verification-method/result/evidence/form-is-verified/is-verified/submit/status`, `d5-adopt-suggestion/control`, `d7-auto-fill/confirm/skip`, `rec-dag-stage-`). API paths match `backend/app/api/capa.py` (147/616/633/653), `e2e.py`, `auth.py`, `admin.py`. ✓