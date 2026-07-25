---
name: verify-fmea-lifecycle-pfmea-step2-structure
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.2（PFMEA Step2 结构分析：ProcessItem → ProcessStep(OP10/OP20) → ProcessWorkElement(4M)）end-to-end — e.g. "验收 02.2" / "走查 PFMEA Step2" / "verify pfmea-step2-structure". Symptoms include needing to confirm 结构树 3 层齐全、HAS_PROCESS_STEP/HAS_WORK_ELEMENT 边、process_number/classification 必填、4M 枚举（Man/Machine/Material/Environment）落库。
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.2-pfmea-step2-structure.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step2-structure

## Overview

本子 skill 走查 US-E2E-02.2：在 PFMEA 向导 Step2 录入过程结构树：`ProcessItem → ProcessStep(HAS_PROCESS_STEP) → ProcessWorkElement(HAS_WORK_ELEMENT)`，ProcessStep 必填 `process_number`（OP10/OP20 格式），ProcessWorkElement 必填 `classification`（4M 存储枚举 Man/Machine/Material/Environment，中文仅 UI 标签）。

核心验收点：

1. **三层结构 + 边**：ProcessItem/ProcessStep/ProcessWorkElement 节点齐 + `HAS_PROCESS_STEP`/`HAS_WORK_ELEMENT` 边方向正确。
2. **必填**：`ProcessStep.process_number` 非空；`ProcessWorkElement.classification ∈ {Man, Machine, Material, Environment}`（**英文枚举落库，中文仅 UI**）。
3. **门禁**：推进 Step3 前至少 1 个 ProcessStep + 1 个 ProcessWorkElement，且 process_number/classification 非空。
4. **审计**：保存写 `action=UPDATE` AuditLog（Outbox `fmea.updated`）。

## When to Use

**用**：用户说「验收 02.2」「走查 PFMEA Step2」等。
**不用**：其他子故事（调对应 `verify-fmea-lifecycle-*` 子 skill）。

## 前置

1. **epic 级前置**：见 `.claude/skills/verify-fmea-lifecycle/SKILL.md`「前置」节。
2. **AI_REQUIRED=false**，无需 LLM 凭证。
3. **02.1 已就绪**：Step1 5T 已落库（`wizardScope` 完整），文档处于 DRAFT；通常本走查直接续 02.1 的 PFMEA。
4. **engineer 账号**：从 `/api/e2e/seed-state` 拿密码。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入结构树 + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| 「+ 过程项」/「+ 过程步骤」/「+ 工作要素」 | 按钮文本（i18n `wizard.structure.addProcessItem`/`addProcessStep`/`addWorkElement`） | Step2 添加节点（`PFMEAWizardPage.tsx:326,351`） |
| ProcessStep `process_number` 输入 | Ant Input placeholder=`wizard.structure.processNumber`，无 data-e2e | Step2 行内（`PFMEAWizardPage.tsx:336`） |
| ProcessWorkElement `classification` Select | Ant Select placeholder=`wizard.structure.classification4M`，无 data-e2e | Step2 行内（`PFMEAWizardPage.tsx:340`） |
| 节点名 Input | Ant Input，无 data-e2e | 节点重命名 |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 启动 + 进入 Step2

1. **做**：engineer 登录 → 打开 02.1 已完成的 PFMEA → 进 `/fmea/pfmea-wizard/:id` → 左侧 WizardSidebar 点 Step2（或在 Step1 末尾点「下一步」）。
   - **期望**：Step2 结构分析视图渲染；已有初始 `ProcessItem` 节点（后端注入）。
   - **断言**：`GET http://localhost:8001/api/fmea/{id}` 回读 `graph_data.nodes` 含至少 1 个 `ProcessItem`。
   - **落库**：无。

### B. 录入 ProcessStep（OP10）

2. **做**：选中 ProcessItem 行 → 点「+ 过程步骤」→ 在新 ProcessStep 行：
   - 名称输入「DC-DC 电路板贴装」；
   - `process_number` 输入「OP10」。
   - **期望**：UI 出现 ProcessStep 行；process_number 显示 OP10。
   - **断言**：UI read-back process_number 值。
   - **落库**：尚未保存。

### C. 录入 ProcessWorkElement（4M）

3. **做**：选中 ProcessStep 行 → 点「+ 工作要素」→ 在新 ProcessWorkElement 行：
   - 名称输入「贴片机操作员」；
   - `classification` 选「人 Man」。
   - **期望**：Select 显示「人 Man」（UI 标签）；classification 实际值 `Man`。
   - **断言**：UI read-back classification 选中项。
   - **落库**：尚未保存。

### D. 保存 + 落库断言

4. **做**：点顶部「保存草稿」。
   - **期望**：保存成功。
   - **断言（回读，关键）**：`GET /api/fmea/{id}`：
     - `graph_data.nodes` 含 ProcessItem/ProcessStep/ProcessWorkElement 三层节点；
     - ProcessStep 节点 `process_number == "OP10"`；
     - ProcessWorkElement 节点 `classification == "Man"`（**英文枚举落库**，若为中文「人」→ FAIL）；
     - 边 `HAS_PROCESS_STEP`：ProcessItem → ProcessStep（方向正确）；
     - 边 `HAS_WORK_ELEMENT`：ProcessStep → ProcessWorkElement（方向正确）；
     - `wizardScope` 5T 字段不变（保留）。
   - **落库（审计）**：1 条 `action=UPDATE` AuditLog，`operated_by=engineer`；Outbox `fmea.updated`。

### E. 必填校验（负面）

5. **做**：再添加一个 ProcessStep 但**不填 process_number**；再添加一个 ProcessWorkElement 但**不选 classification** → 尝试点「下一步」推进到 Step3。
   - **期望**：向导门禁拦截——validation.warnings 含 Step2 相关警告，或虽能跳到 Step3 但 Step6 汇总显示 Step2 未完成。
   - **断言**：`validation.step2Complete == false`（前端逻辑）；UI 警告可见。
   - **清理**：删除刚才未填字段的节点（保持文档干净），或补齐后保存。
   - **落库**：无新增。

### F. 4M 枚举完整性

6. **做**：在 ProcessWorkElement 的 classification Select 下拉里，确认 4 个选项分别是「人 Man」「机 Machine」「料 Material」「环 Environment」。
   - **期望**：4 个选项可见；value 为英文枚举。
   - **断言**：UI 选项 4 项齐全；选「机 Machine」→ 保存 → 回读 `classification == "Machine"`。
   - **落库**：UPDATE 审计 +1。

### G. 推进 Step3

7. **做**：点「下一步」。
   - **期望**：跳到 Step3 功能分析。
   - **断言**：URL 不变；`graph_data` 结构节点齐。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 三层结构 + 边 | ProcessItem/ProcessStep/ProcessWorkElement + HAS_PROCESS_STEP/HAS_WORK_ELEMENT | PASS |
| process_number 必填 | ProcessStep.process_number 非空 | PASS |
| classification 4M 枚举 | 落库值为英文枚举（非中文） | PASS |
| 门禁 | 未填字段时 step2Complete=false | PASS |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 三层结构 + 必填 + 4M 枚举 + 审计全满足 |
| **PASS-NOTE** | 通过但有备注 |
| **FAIL** | 层级断裂；process_number 缺失；classification 落库为中文标签（非 4M 英文枚举）；未审计 |
| **MISSING** | 添加按钮不存在；classification Select 不存在 |
| **BLOCKED** | —（AI_REQUIRED=false） |

## 报告片段

```markdown
### 02.2 PFMEA Step2 结构分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 三层结构 + 边方向：<OK|FAIL>
- process_number 必填落库：<OK|FAIL>
- classification 4M 英文枚举落库：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.2-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.2-pfmea-step2-structure.md` 顶部「状态: 定稿 vX（日期）」。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
