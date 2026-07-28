---
name: verify-fmea-lifecycle-dfmea-step2-structure
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.9（DFMEA Step2 结构分析：System → Subsystem → Component；共享 Process* 边词汇 HAS_PROCESS_STEP/HAS_WORK_ELEMENT，不新增 HAS_SUBSYSTEM/HAS_COMPONENT）end-to-end — e.g. "验收 02.9" / "走查 DFMEA Step2" / "verify dfmea-step2-structure".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.9-dfmea-step2-structure.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-dfmea-step2-structure

## Overview

本子 skill 走查 US-E2E-02.9：在 DFMEA 向导 Step2 录入系统结构树 `System → Subsystem → Component`，**共享 Process\* 边词汇**（DFMEA 的 System/Subsystem/Component 仅为语义/UI 名称，`graphPresentation.ts:239-240` 将 HAS_PROCESS_STEP 映射为 hasSubsystem、HAS_WORK_ELEMENT 映射为 hasComponent）。

核心验收点：

1. **三层结构**：System / Subsystem / Component 节点齐。
2. **共享边词汇**：System→Subsystem 用 `HAS_PROCESS_STEP`；Subsystem→Component 用 `HAS_WORK_ELEMENT`（**不新增 HAS_SUBSYSTEM/HAS_COMPONENT**；若发现这类边 → FAIL）。
3. **门禁**：推进 Step3 前至少 1 个 Subsystem + 1 个 Component。
4. **审计**：UPDATE。

## When to Use

**用**：用户说「验收 02.9」「走查 DFMEA Step2」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.8 已就绪**：Step1 wizardScope 已落库；DFMEA draft 含初始 System 节点。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入结构树 + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| 「+ 系统」/「+ 子系统」/「+ 零部件」 | 按钮文本 `wizard.structure.addSystem`/`addSubsystem`/`addComponent` | Step2 添加节点 |
| 节点名 Input | Ant Input，无 data-e2e | 重命名 |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step2

1. **做**：engineer 登录 → 打开 02.8 已完成的 DFMEA → 向导 Step2。
   - **期望**：结构树渲染；初始 System 节点已注入。
   - **断言**：`GET /api/fmea/{id}` 回读 System 节点 ≥1。
   - **落库**：无。

### B. 录入 Subsystem + Component

2. **做**：选中 System → 「+ 子系统」→ 命名「功率变换子系统」；选中该 Subsystem → 「+ 零部件」→ 命名「变压器 T1」。
   - **期望**：UI 显示三层结构。
   - **断言**：UI read-back 三节点。
   - **落库**：尚未保存。

### C. 保存 + 边词汇断言（关键）

3. **做**：点「保存草稿」。
   - **期望**：保存成功。
   - **断言（关键）**：`GET /api/fmea/{id}`：
     - `graph_data.edges` 含 `System ─HAS_PROCESS_STEP→ Subsystem`；
     - `graph_data.edges` 含 `Subsystem ─HAS_WORK_ELEMENT→ Component`；
     - **不**存在 `HAS_SUBSYSTEM` / `HAS_COMPONENT` 类型边（若存在 → FAIL）；
     - 节点 type 字段为 `System`/`Subsystem`/`Component`（数据层用 UI 语义名存储，UI 再通过 graphPresentation 映射）。
   - **落库**：1 条 UPDATE 审计。

### D. 门禁（缺 Subsystem/Component）

4. **做**：另起一 System 但**不**加 Subsystem/Component → 尝试推进 Step3。
   - **期望**：门禁拦截或 step2Complete=false。
   - **清理**：删除该 System 或补齐后保存。
   - **落库**：无。

### E. 推进 Step3

5. **做**：点「下一步」。
   - **期望**：跳到 Step3 功能分析。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 |
|---|---|
| 三层结构 | System/Subsystem/Component 齐 |
| 共享边词汇 | HAS_PROCESS_STEP + HAS_WORK_ELEMENT；无 HAS_SUBSYSTEM/HAS_COMPONENT |
| 门禁 | 缺 Subsystem/Component 时 step2Complete=false |
| UPDATE 审计 | 每次保存 1 条 |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | 用了 HAS_SUBSYSTEM/HAS_COMPONENT 边；层级断裂；未审计 |
| **MISSING** | 添加按钮不存在 |
| **BLOCKED** | — |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.9 DFMEA Step2 结构分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 三层结构：<OK|FAIL>
- 共享 Process* 边（无 HAS_SUBSYSTEM/HAS_COMPONENT）：<OK|FAIL>
- UPDATE 审计：<OK|FAIL>
- 截图：screenshots/02.9-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.9-dfmea-step2-structure.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
