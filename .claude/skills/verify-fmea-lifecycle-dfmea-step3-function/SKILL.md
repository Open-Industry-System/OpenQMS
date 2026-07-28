---
name: verify-fmea-lifecycle-dfmea-step3-function
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.10（DFMEA Step3 功能分析：复用 Process*Function 类型，无独立 SystemFunction；HAS_FUNCTION + FUNCTION_MAPPED_TO 边；每个结构节点都有功能）end-to-end — e.g. "验收 02.10" / "走查 DFMEA Step3" / "verify dfmea-step3-function".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.10-dfmea-step3-function.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step3-function

## Overview

本子 skill 走查 US-E2E-02.10：在 DFMEA 向导 Step3 为每个结构节点（System/Subsystem/Component）录入功能。

核心验收点：

1. **复用 Process\*Function 类型**：DFMEA **无独立 SystemFunction 类型**（`schemas/fmea.py:6-9` 注释）；落库的功能节点 type 为 `ProcessItemFunction`/`ProcessStepFunction`/`ProcessWorkElementFunction`。若发现 SystemFunction 类型 → FAIL。
2. **每个纳入分析范围的结构节点都有功能节点**（`HAS_FUNCTION` 边），非仅"至少一个功能"。
3. **`FUNCTION_MAPPED_TO`**：不同层级功能之间的功能关系（**非功能→结构**）。
4. **DFMEA 无 CC/SC 列**（AIAG-VDA DFMEA 已移除，PFMEA 才有）——若 DFMEA UI 出现 CC/SC → FAIL。

## When to Use

**用**：用户说「验收 02.10」「走查 DFMEA Step3」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.9 已就绪**：Step2 结构树已落库。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入功能 + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step3 视图 = FunctionTreeEditor | 组件 | 功能树编辑 |
| 功能名 Input | Ant Input，无 data-e2e | — |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step3

1. **做**：engineer 登录 → 打开 02.9 已完成的 DFMEA → 向导 Step3。
   - **期望**：FunctionTreeEditor 渲染；显示 System/Subsystem/Component 挂载点。
   - **落库**：无。

### B. 为每个结构节点录入功能

2. **做**：分别为 System/Subsystem/Component 添加功能：
   - System 级：「将 24V 输入转换为稳定 12V 输出」；
   - Subsystem 级：「实现高频功率变换」；
   - Component 级：「提供电磁能量传递」。
   - **期望**：每个结构节点下挂 1 个功能节点。
   - **落库**：尚未保存。

### C. 保存 + 节点类型断言（关键）

3. **做**：点「保存草稿」→ `GET /api/fmea/{id}`。
   - **断言（关键）**：
     - 新增功能节点 `type` ∈ {`ProcessItemFunction`, `ProcessStepFunction`, `ProcessWorkElementFunction`}（**复用**）；
     - **不**存在 `SystemFunction` / `SubsystemFunction` / `ComponentFunction` 类型节点（若存在 → FAIL）；
     - `graph_data.edges` 含 3 条 `HAS_FUNCTION`（每个结构节点 1 条）；
     - `FUNCTION_MAPPED_TO` 边连接不同层级功能（若建了映射），方向功能↔功能（非功能→结构）。
   - **落库**：1 条 UPDATE 审计。

### D. DFMEA 无 CC/SC（对照断言）

4. **做**：检查 DFMEA Step3 UI 是否暴露 CC/SC Select。
   - **期望**：不出现 CC/SC 列（DFMEA 专有规则）。
   - **若出现** → FAIL。
   - **落库**：无。

### E. 推进 Step4

5. **做**：点「下一步」。
   - **期望**：跳到 Step4 失效分析。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 |
|---|---|
| 复用 Process*Function 类型 | 无 SystemFunction 等独立类型 |
| 每个结构节点有 HAS_FUNCTION | 3 个结构节点均有功能出边 |
| FUNCTION_MAPPED_TO 方向 | 功能↔功能 |
| DFMEA 无 CC/SC | UI 不暴露 CC/SC |
| UPDATE 审计 | 每次保存 1 条 |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | 出现 SystemFunction 类型；结构节点缺功能；FUNCTION_MAPPED_TO 误连功能→结构；DFMEA 出现 CC/SC；未审计 |
| **MISSING** | FunctionTreeEditor 不渲染 |
| **BLOCKED** | — |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.10 DFMEA Step3 功能分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 复用 Process*Function（无 SystemFunction）：<OK|FAIL>
- 每个结构节点有 HAS_FUNCTION：<OK|FAIL>
- FUNCTION_MAPPED_TO 方向：<OK|FAIL>
- DFMEA 无 CC/SC：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.10-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.10-dfmea-step3-function.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
