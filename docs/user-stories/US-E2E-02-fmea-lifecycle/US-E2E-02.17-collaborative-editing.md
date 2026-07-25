# 子故事 US-E2E-02.17：协同编辑 + 冲突检测

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-collaborative-editing`
**前置**: 02.15（编辑器行已就绪）
**AI_REQUIRED**: false

## 故事

**作为** 前期策划质量工程师 / 设计质量工程师，**我想** 与同事同时编辑同一 FMEA 文档时，看到在线用户列表 + 行级编辑指示器，当他人先保存导致 `lock_version` 不一致时收到 409 冲突提示，可选择"用我的覆盖"或"放弃我的修改"，覆盖前预览三方 diff，
**以便** 多人协同编辑不互相覆盖，冲突可感知、可决策、可安全解决。

## 背景 / 前置条件

- 编辑器已集成乐观锁（`lock_version`）+ 短轮询在线状态。
- 后端 `fmea_service.update_fmea` 支持 `lock_version` + `confirmed_latest_lock_version` 双路径。

## 主流程

1. 用户 A、B 同时打开同一 FMEA 编辑器（同 lock_version = N）。
2. 顶部显示在线用户列表（短轮询）+ 行级编辑指示器（A 正在编辑第 3 行）。
3. A 先保存 → lock_version = N+1。
4. B 保存 → 后端检测 `lock_version != N`，返回 409 + `{conflict: {latest_lock_version: N+1, ...}}`。
5. B 选择：
   - "用我的覆盖"：带 `confirmed_latest_lock_version=N+1` 重试 → 若期间 A 又保存（N+2）→ `lock_version_changed_again` 再次 409；否则覆盖成功。
   - "放弃我的修改"：重新加载最新 graph_data。
6. 覆盖前展示三方 diff 预览（A 的版本 / B 的版本 / 基线）。
7. 覆盖写 `conflict_overwrite` 审计。

## 业务规则 / 验收标准

### 冲突检测
- 乐观锁：`lock_version` 不匹配 → 409 + `conflict` 详情（`latest_lock_version`）。
- 二次冲突：`confirmed_latest_lock_version` 仍不匹配 → 409 + `lock_version_changed_again`。
- lock_version 仅在有实际变更时递增（无变更不递增）。

### 协同可见性
- 在线用户列表实时更新（短轮询）。
- 行级编辑指示器：他人正在编辑的行高亮。

### 安全覆盖
- 覆盖前必须预览 diff（不可盲覆盖）。
- 覆盖写 `conflict_overwrite` 审计（含 reason: "User confirmed overwrite after conflict detection"）。

## 验收契约（字段级）

| 项 | 定义（跨 PFMEA/DFMEA） |
|---|---|
| 落库实体 | `FMEADocument.lock_version`、`AuditLog`（conflict_overwrite） |
| 关键字段 | lock_version、confirmed_latest_lock_version |
| 边类型 | 无 |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated`、`conflict_overwrite`（含 reason） |
| E2E seed 前置 | 02.15 编辑器 + 两个用户会话 |
| 通过条件 | 409 冲突正确返回 + 双路径（覆盖/放弃）可用 + 二次冲突检测 + 三方 diff 预览 + 在线用户列表 + 行级指示器 + 覆盖审计 |
| 失败条件（FAILED） | 冲突未检测（lock_version 不生效）；盲覆盖（无 diff 预览）；在线状态不更新；覆盖未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- CAPA/APQP 的在线状态（仅 FMEA/CP 接入乐观锁，本子故事只验 FMEA）。
- WebSocket 实时推送（现有为短轮询，本子故事只验现状）。

## 后续

- 协同编辑为 02.18 版本快照提供安全保存基础。
