---
name: verify-fmea-lifecycle-collaborative-editing
description: Use when asked to verify / walk through / 验收 / 走查 OpenQMS 子故事 US-E2E-02.17（协同编辑 + 冲突检测：乐观锁 409 + confirmed_latest_lock_version 二次冲突 + 三方 diff 预览 + 在线用户列表 + 行级指示器 + FORCE_SAVE_OVERRIDE 审计 + wizardScope 保留）end-to-end — e.g. "验收 02.17" / "走查协同编辑" / "verify collaborative-editing".
---

> 依据：docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.17-collaborative-editing.md
> 故事版本：定稿 v2（2026-07-25）
> 同步规则：当用户故事版本号或日期变更，本剧本必须重新核对并同步（见「维护」）。

# verify-fmea-lifecycle-collaborative-editing

## Overview

本子 skill 走查 US-E2E-02.17：两用户同时编辑同一 FMEA 时的协同行为。

核心验收点：

1. **乐观锁**：`lock_version` 不匹配 → 409 + `conflict.latest_lock_version`。
2. **二次冲突**：`confirmed_latest_lock_version` 仍不匹配 → 409 + `lock_version_changed_again`。
3. **lock_version 仅在有实际变更时递增**（无变更不递增）。
4. **协同可见性**：在线用户列表（短轮询）+ 行级编辑指示器（他人正在编辑的行高亮）。
5. **三方 diff 预览**：覆盖前必须预览 A 版本 / B 版本 / 基线的 diff（不可盲覆盖）。
6. **FORCE_SAVE_OVERRIDE 审计**：覆盖写 `action=FORCE_SAVE_OVERRIDE` AuditLog（reason: "User confirmed overwrite after conflict detection"）。
7. **wizardScope 保留**：编辑保存与冲突覆盖均保留 wizardScope（含 wizard_completed）。
8. **可编辑状态**：仅 DRAFT/REWORK；IN_REVIEW/APPROVED 的 PUT 必须 409（见 02.19）。

## When to Use

**用**：用户说「验收 02.17」「走查协同编辑」等。

## 前置

1. **epic 级前置**：见 epic skill。
2. **AI_REQUIRED=false**。
3. **02.15 已就绪**：编辑器行已建好；draft 处于 DRAFT。
4. **engineer + admin 两个会话**（两个浏览器 tab 或两个独立 token）。

## 账号 × 权限

| 账号 | 角色 | 用途 |
|---|---|---|
| engineer | quality_engineer (L2) | 用户 A（先保存） |
| admin | admin (L5) | 用户 B（后保存 → 触发冲突） |

也可 engineer A + engineer B（两个 engineer 账号）若种子有第二个 engineer。

## selector 表

| selector | 读取方式 | 用途 |
|---|---|---|
| 在线用户列表 | 编辑器顶部组件，无 data-e2e | 显示当前在线编辑者 |
| 行级编辑指示器 | 行高亮 class | 他人正在编辑的行 |
| 冲突对话框 | `FMEAEditorPage.tsx:2060` 区域 | 显示 conflictInfo + diff |
| 「用我的覆盖」/「放弃我的修改」 | 按钮文本 | 冲突对话框 |
| 三方 diff 视图 | 冲突对话框内 | A/B/基线对比 |

## 走查剧本

### A. 两会话同时打开同一 FMEA

1. **做**：engineer 在浏览器 tab1 登录并打开 `/fmea/{id}`；admin 在 tab2（或隐身窗口）登录并打开同一 `/fmea/{id}`。
   - **期望**：两边 lock_version 相同（= N）。
   - **断言**：`GET /api/fmea/{id}` 回读 `lock_version == N`；两 UI 顶部在线用户列表各显示对方。
   - **若在线用户列表不显示** → MISSING。
   - **落库**：无。

### B. 行级编辑指示器

2. **做**：tab1（engineer）开始编辑第 3 行某单元格。
   - **期望**：tab2（admin）视图内第 3 行高亮 / 显示「engineer 正在编辑」指示。
   - **若无指示器** → MISSING。

### C. A 先保存 → lock_version N+1

3. **做**：tab1 改一字段 → 点保存。
   - **期望**：保存成功；lock_version → N+1。
   - **断言**：`GET /api/fmea/{id}` 回读 `lock_version == N+1`。
   - **落库**：1 条 UPDATE 审计（engineer）。

### D. B 保存 → 409 + conflict（关键）

4. **做**：tab2（admin，仍持 lock_version=N）改另一字段 → 点保存。
   - **期望**：后端返回 **409 Conflict**，detail 含 `conflict: {saved_by, saved_at, latest_lock_version: N+1}`；UI 弹冲突对话框。
   - **断言（关键）**：
     - HTTP 409；
     - 响应 detail.conflict.latest_lock_version == N+1；
     - UI 冲突对话框可见，含「用我的覆盖」「放弃我的修改」两按钮 + 三方 diff 预览。
   - **若直接保存成功（盲覆盖）** → FAIL（乐观锁失效）。
   - **若无 diff 预览** → FAIL（盲覆盖）。

### E. 三方 diff 预览断言

5. **做**：在冲突对话框查看 diff。
   - **期望**：显示 A 版本（engineer 已保存）/ B 版本（admin 当前修改）/ 基线（两用户开始编辑时的版本）。
   - **断言**：diff 视图含三方对比；新增/删除/修改高亮区分。

### F. 「放弃我的修改」路径

6. **做**：tab2 点「放弃我的修改」。
   - **期望**：UI 重新加载最新 graph_data（A 的版本）；admin 的修改被丢弃。
   - **断言**：tab2 表格内容与 tab1 一致。
   - **落库**：无新审计。

### G. 「用我的覆盖」+ FORCE_SAVE_OVERRIDE 审计

7. **做**：再次构造冲突（tab1 改一字段保存 → tab2 改另一字段保存触发 409）→ tab2 点「用我的覆盖」→ 前端带 `confirmed_latest_lock_version=N+1` 重试。
   - **期望**：保存成功；lock_version → N+2；写 `action=FORCE_SAVE_OVERRIDE` AuditLog（reason: "User confirmed overwrite after conflict detection"）。
   - **断言（关键）**：
     - `GET /api/admin/logs/audit?table_name=fmea_documents&record_id=<id>` 含 1 条 `action=FORCE_SAVE_OVERRIDE`，`operated_by=admin`，`changed_fields.reason` 含 "User confirmed overwrite after conflict detection"；
     - `GET /api/fmea/{id}` 回读 `lock_version == N+2`；
     - `graph_data.wizardScope` 保留（含 wizard_completed）——**覆盖不丢向导元数据**。
   - **落库**：FORCE_SAVE_OVERRIDE + Outbox `fmea.updated`。

### H. 二次冲突（lock_version_changed_again）

8. **做**：构造三方竞态：tab1 保存（N+1）→ tab2 触发 409 → tab2 看 diff 时 tab1 又保存（N+2）→ tab2 点「用我的覆盖」带 `confirmed_latest_lock_version=N+1`。
   - **期望**：后端返回 409 + `lock_version_changed_again`；UI 提示「文档在评审期间又被修改，请刷新」。
   - **断言**：HTTP 409 + 响应 detail 含 lock_version_changed_again 标识。

### I. lock_version 无变更不递增

9. **做**：tab1 点保存但**未改任何字段**。
   - **期望**：lock_version 不递增。
   - **断言**：保存前后 `GET /api/fmea/{id}` 回读 lock_version 相同。

### J. wizardScope 保留（覆盖路径）

10. **做**：在 G 步覆盖保存后立即 `GET /api/fmea/{id}`。
    - **断言**：`graph_data.wizardScope.wizard_completed == true` 且 5T 字段非空（**未被覆盖**）。

### K. 收尾

11. **做**：两 tab 登出；admin 把 lock_version 与文档状态恢复。
    - **落库**：无。

## 判定汇总

| 检查点 | 通过条件 | 当前预期 |
|---|---|---|
| 在线用户列表 | 显示对方 | PASS（若不显示 → MISSING） |
| 行级编辑指示器 | 行高亮 | PASS（若不存在 → MISSING） |
| 409 + conflict.latest_lock_version | 乐观锁生效 | PASS |
| 三方 diff 预览 | A/B/基线对比 | PASS（若盲覆盖 → FAIL） |
| 放弃路径 | 重新加载 | PASS |
| 覆盖路径 + FORCE_SAVE_OVERRIDE | 审计落库 + reason 正确 | PASS |
| 二次冲突 lock_version_changed_again | 409 + 标识 | PASS |
| lock_version 无变更不递增 | 不递增 | PASS |
| wizardScope 保留 | 覆盖不丢 | PASS |
| 可编辑状态（IN_REVIEW/APPROVED 409） | 见 02.19 | 见 02.19 |

## 缺陷分类

| 标签 | 含义 |
|---|---|
| **PASS** | 全部通过 |
| **FAIL** | 冲突未检测；盲覆盖；在线状态不更新；覆盖未审计；保存/覆盖丢 wizardScope |
| **MISSING** | 在线列表不存在；行级指示器不存在；冲突对话框不存在 |
| **BLOCKED** | — |

## 报告片段

```markdown
### 02.17 协同编辑 + 冲突检测 — <PASS|PASS-NOTE|FAIL|MISSING>

- 在线用户列表：<OK|MISSING>
- 行级编辑指示器：<OK|MISSING>
- 409 + conflict.latest_lock_version：<OK|FAIL>
- 三方 diff 预览：<OK|FAIL>
- FORCE_SAVE_OVERRIDE 审计：<OK|FAIL>
- 二次冲突 lock_version_changed_again：<OK|FAIL>
- wizardScope 保留：<OK|FAIL>
- 截图：screenshots/02.17-*.png
```

## 维护（同步）

1. 读 skill 顶部「故事版本」（定稿 v2（2026-07-25））。
2. 读 `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.17-collaborative-editing.md` 顶部。
3. 一致 → 跑；不一致 → 停下同步。

引用校验：`bash .claude/skills/verify-fmea-lifecycle/scripts/verify-refs.sh`。
