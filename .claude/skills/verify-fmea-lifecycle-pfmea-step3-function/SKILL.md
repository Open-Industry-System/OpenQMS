---
name: verify-fmea-lifecycle-pfmea-step3-function
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.3（PFMEA Step3 功能分析：为每个结构节点录入 ProcessItemFunction/ProcessStepFunction/ProcessWorkElementFunction + HAS_FUNCTION 边 + FUNCTION_MAPPED_TO 边 + CC/SC 写 Function.classification）end-to-end — e.g. "验收 02.3" / "走查 PFMEA Step3" / "verify pfmea-step3-function".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.3-pfmea-step3-function.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step3-function

## Overview

本子 skill 走查 US-E2E-02.3：在 PFMEA 向导 Step3 为每个结构节点录入功能树（产品特性 / 过程特性），并维护 CC/SC 特殊特性。

核心验收点：

1. **每个纳入分析范围的结构节点都有功能节点**（`HAS_FUNCTION` 边），**非仅"至少一个功能"**（README 评审决议）。
2. **功能节点类型**：`ProcessItemFunction`（产品特性）/ `ProcessStepFunction`（产品特性，CC/SC 可设）/ `ProcessWorkElementFunction`（过程特性，CC/SC 可设）。
3. **`FUNCTION_MAPPED_TO`**：不同层级功能之间的功能关系（**非功能→结构**）。
4. **CC/SC 写入 Function.classification 字段**（复用现有字段），**不写** `FailureCause.special_characteristic`。
5. **门禁**：推进 Step4 前每个结构节点都有功能节点。

## When to Use

**用**：用户说「验收 02.3」「走查 PFMEA Step3」等。
**不用**：其他子故事。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.2 已就绪**：Step2 结构树已落库（ProcessItem/ProcessStep/ProcessWorkElement）。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入功能树 + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step3 视图 = `FunctionTreeEditor` | 组件（`PFMEAWizardPage.tsx:367-369`） | 功能树编辑 |
| 功能名 Input | Ant Input，无 data-e2e | 按 placeholder/i18n 定位 |
| CC/SC Select | Ant Select，无 data-e2e | Function.classification |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step3

1. **做**：engineer 登录 → 打开 02.2 已完成的 PFMEA → 向导 Step3。
   - **期望**：FunctionTreeEditor 渲染；显示 02.2 录入的 ProcessItem/ProcessStep/ProcessWorkElement 挂载点。
   - **断言**：`GET /api/fmea/{id}` 回读结构节点 ≥3。
   - **落库**：无。

### B. 为每个结构节点录入功能

2. **做**：分别为 ProcessItem/ProcessStep/ProcessWorkElement 添加功能节点：
   - ProcessItemFunction：「提供稳定 12V 输出」（产品特性）；
   - ProcessStepFunction：「精确贴装 IC 至焊盘」（产品特性，CC 设「CC」）；
   - ProcessWorkElementFunction：「按规程操作贴片机」（过程特性，SC 设「SC」）。
   - **期望**：每个结构节点下挂 1 个功能节点；UI 显示功能树。
   - **断言**：UI read-back 三个功能节点均可见。
   - **落库**：尚未保存。

### C. FUNCTION_MAPPED_TO 边（层级功能关系）

3. **做**：在 FunctionTreeEditor 中把 ProcessItemFunction 与 ProcessStepFunction 关联（通常通过拖拽或显式"映射"操作）。
   - **期望**：两个功能节点之间出现一条边，类型 `FUNCTION_MAPPED_TO`。
   - **断言**：保存后回读 `graph_data.edges` 含 `type == "FUNCTION_MAPPED_TO"`，且 source/target 均为功能节点（**非功能→结构**）。
   - **若 FUNCTION_MAPPED_TO 误连功能→结构** → FAIL。

### D. CC/SC 写 Function.classification

4. **做**：把 ProcessStepFunction 的 CC/SC Select 设为「CC」；ProcessWorkElementFunction 设为「SC」→ 保存。
   - **期望**：保存成功。
   - **断言（回读，关键）**：`GET /api/fmea/{id}`：
     - ProcessStepFunction 节点 `classification == "CC"`；
     - ProcessWorkElementFunction 节点 `classification == "SC"`；
     - **不**在 `FailureCause.special_characteristic` 写 CC/SC（若写了 → FAIL，字段错位置）。
   - **落库**：1 条 UPDATE 审计。

### E. 每个结构节点都有功能（门禁）

5. **做**：保存后 `GET /api/fmea/{id}`，对每个结构节点（ProcessItem/ProcessStep/ProcessWorkElement）查 `graph_data.edges` 中是否存在 `type == "HAS_FUNCTION"` 且 source == 该结构节点 id。
   - **期望**：**每个**结构节点都至少有 1 条 HAS_FUNCTION 出边。
   - **断言**：3 个结构节点均有 HAS_FUNCTION 出边。
   - **若只挂了一个功能（其他结构节点裸奔）** → FAIL（评审决议要求"每个纳入分析范围的结构节点都有功能节点"）。

### F. 推进 Step4

6. **做**：点「下一步」。
   - **期望**：跳到 Step4 失效分析；FunctionTreeEditor 已建立的功能树作为 FM 挂载点。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 |
|---|---|
| 每个结构节点有 HAS_FUNCTION | 3 个结构节点均有功能出边 |
| FUNCTION_MAPPED_TO 方向 | 功能↔功能，非功能→结构 |
| CC/SC 写 Function.classification | 字段正确，不写 FailureCause.special_characteristic |
| UPDATE 审计 | 1 条/次保存 |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 功能树 + 边 + CC/SC 全满足 |
| **FAIL** | 结构节点缺功能；CC/SC 写错字段；FUNCTION_MAPPED_TO 误连功能→结构；未审计 |
| **MISSING** | FunctionTreeEditor 不渲染；CC/SC Select 不存在 |
| **BLOCKED** | — |

## 报告片段

```markdown
### 02.3 PFMEA Step3 功能分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 每个结构节点有 HAS_FUNCTION：<OK|FAIL>
- FUNCTION_MAPPED_TO 方向正确：<OK|FAIL>
- CC/SC 写 Function.classification：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.3-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.3-pfmea-step3-function.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
