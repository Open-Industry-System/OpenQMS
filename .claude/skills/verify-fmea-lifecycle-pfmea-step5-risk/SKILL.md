---
name: verify-fmea-lifecycle-pfmea-step5-risk
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.5（PFMEA Step5 风险分析：三段式 S severity_plant/customer/user 取 max + O + D + AP 查表非乘积 + CC/SC 写 Function.classification + AI PC/DC 推荐 3 required_retrievers）end-to-end — e.g. "验收 02.5" / "走查 PFMEA Step5" / "verify pfmea-step5-risk".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.5-pfmea-step5-risk.md
> 故事版本：定稿 v3（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-pfmea-step5-risk

## Overview

本子 skill 走查 US-E2E-02.5：在 PFMEA 向导 Step5 录入风险评分（S/O/D + AP）+ CC/SC 特殊特性。

核心验收点：

1. **三段式 S**（PFMEA 专有）：`severity_plant` / `severity_customer` / `severity_user` 三字段均 >0（门禁要求三字段非 0，避免退化为单 S）；`severity = max(三者)`。
2. **AP 查表**：AP 是 S/O/D 组合的**查表结果**（`utils/fmea.ts calculateAP` 查 AIAG-VDA AP 表），**非 S×O×D 乘积**（乘积是 RPN）。
3. **CC/SC** 写入 `ProcessStepFunction`/`ProcessWorkElementFunction.classification`（PFMEA 专有列，DFMEA 无）。
4. **AI 触发器**：`prevention_control` / `detection_control`，3 required_retrievers 可观测。

## When to Use

**用**：用户说「验收 02.5」「走查 PFMEA Step5」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **LLM 凭证齐**（AI_REQUIRED=true）：缺 → BLOCKED。
3. **02.4 已就绪**：失效链已落库（FE/FC/PC/DC 节点就绪）。
4. **engineer 账号**。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 录入 S/O/D + 保存 |

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| Step5 视图 = `RiskTable` | 组件（`PFMEAWizardPage.tsx:535`） | 风险评分表 |
| 三段式 S 三个 InputNumber | Ant InputNumber，无 data-e2e | severity_plant/customer/user |
| O / D InputNumber | Ant InputNumber | occurrence / detection |
| AP Tag | Ant Tag 文本 H/M/L | 查表结果展示 |
| CC/SC Select | Ant Select | Function.classification |
| 「保存草稿」/「下一步」 | 按钮文本 | 页脚 |

## 走查剧本

### A. 进入 Step5

1. **做**：engineer 登录 → 打开 02.4 已完成的 PFMEA → 向导 Step5。
   - **期望**：RiskTable 渲染；每行对应一条失效链。
   - **断言**：表格行数 == 失效链数。
   - **落库**：无。

### B. 三段式 S 录入（关键）

2. **做**：在某行录入三段式 S：
   - severity_plant = 7
   - severity_customer = 8
   - severity_user = 9
   - **期望**：UI 显示 S = 9（max(7,8,9)）。
   - **断言**：UI read-back 严重度 = 9。
   - **落库**：尚未保存。

3. **做**：另起一行，把 severity_customer 留 0（其他两段非 0）。
   - **期望**：向导门禁拦截——step5Complete=false，或该行高亮提示「三段式 S 三字段必须均 >0」。
   - **断言**：UI 警告可见；保存后 `validation.step5Complete == false`。
   - **清理**：删除该行，或补齐三段。
   - **若系统允许单段 >0 即通过（退化为单 S）** → FAIL。

### C. O + D 录入

4. **做**：在第一行录入 occurrence = 5，detection = 6。
   - **期望**：UI 显示 O=5, D=6。
   - **断言**：UI read-back。
   - **落库**：尚未保存。

### D. AP 查表断言（关键）

5. **做**：观察 UI 上 AP 列；同时本地用 `utils/fmea.ts calculateAP` 对 (S=9, O=5, D=6) 算一次。
   - **期望**：UI 显示 AP 与 `calculateAP(9, 5, 6)` 返回值一致（H/M/L 之一）。
   - **断言（关键）**：
     - UI AP 标签 == `calculateAP(S, O, D)`；
     - **不**等于 `S*O*D` 简单映射的某个阈值（如 S*O*D=270 不直接决定 AP=H——AP 是查表，H 也可能落在低 RPN 组合，反之亦然）；
     - 抽 3 组 (S, O, D)（含 S=9-10 高严重度 + 低 O/D）验证 AP 查表非线性。
   - **若发现 AP == 简单 RPN 阈值映射** → FAIL。

### E. CC/SC 写 Function.classification（PFMEA 专有）

6. **做**：把该失效链所属 ProcessStepFunction 的 CC/SC 设为「CC」；ProcessWorkElementFunction 设为「SC」→ 保存。
   - **期望**：保存成功。
   - **断言**：`GET /api/fmea/{id}` 回读 ProcessStepFunction `classification == "CC"`；ProcessWorkElementFunction `classification == "SC"`；**不**在 FailureCause.special_characteristic 写。
   - **落库**：1 条 UPDATE 审计。

### F. AI 触发（prevention_control / detection_control）

7. **做**：在 PC/DC 字段触发 AI → 抓 `POST /api/fmea/{id}/recommend` 响应。
   - **期望**：响应含 3 required_retrievers + context_execution + generation_execution。
   - **断言**：同 02.4 §C。
   - **当前预期 FAIL/MISSING**：同 02.4。

### G. 保存 + 落库断言

8. **做**：点「保存草稿」。
   - **期望**：保存成功。
   - **断言**：`GET /api/fmea/{id}`：
     - FE 节点 `severity_plant == 7`、`severity_customer == 8`、`severity_user == 9`、`severity == 9`；
     - FC 节点 `occurrence == 5`；
     - DC 节点 `detection == 6`；
     - AP 由前端查表写入对应字段（若节点存 AP 字段）。
   - **落库**：1 条 UPDATE 审计。

### H. 推进 Step6

9. **做**：点「下一步」→ 跳到 Step6 优化。
   - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 三段式 S 三字段均 >0 | 任一 0 → step5Complete=false | PASS |
| severity = max(三者) | 9 | PASS |
| AP 查表非乘积 | 与 calculateAP 一致；抽 3 组验证非线性 | PASS |
| CC/SC 写 Function.classification | 字段正确 | PASS |
| AI 3 required_retrievers | source_executions 可观测 | **FAIL/MISSING** |
| UPDATE 审计 | 每次保存 1 条 | PASS |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 三段式 + AP 查表 + CC/SC + AI 契约全满足 |
| **FAIL** | 三段式任一 0；AP 写成乘积；CC/SC 写错字段；AI 未查 #2/#3；未审计 |
| **MISSING** | RiskTable 不渲染；三段式 S 输入不存在 |
| **BLOCKED** | LLM 凭证缺 |

### 浏览器控制台断言（收尾必做）

走查剧本全部步骤完成后、返回判定前，执行一次控制台检查（判定规则见总 skill `.claude/skills/verify-fmea-lifecycle/SKILL.md`「缺陷分类 → 浏览器控制台断言」）：

- **做**：`browser_console_messages(level="error")`。
- **期望**：无 error 级消息。
- **断言**：无 error → 通过；有与本子故事相关的 error → 本故事判 **FAIL**（error 文本记入缺陷清单 + 截图）；仅有无关噪声 error → **PASS-NOTE** 并附文本。多标签/多账号走查对每个标签页分别检查。

## 报告片段

```markdown
### 02.5 PFMEA Step5 风险分析 — <PASS|PASS-NOTE|FAIL|MISSING>

- 三段式 S 均 >0 且 severity=max：<OK|FAIL>
- AP 查表非乘积：<OK|FAIL>
- CC/SC 写 Function.classification：<OK|FAIL>
- AI 3 required_retrievers：<OK|FAIL|MISSING>
- 截图：screenshots/02.5-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v3（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.5-pfmea-step5-risk.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
