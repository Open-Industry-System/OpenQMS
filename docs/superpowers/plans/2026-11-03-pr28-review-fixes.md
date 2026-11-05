# PR 28 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 PR #28 四项已审查问题，不自动合入 main，不混入其他工作树改动。

**Architecture:** 保留现行 runtime 默认关闭、权限、租户隔离和 D8 版本绑定合同。仅补齐确定性依赖、现有已绑定门禁材料的只读交付、下载末尾授权以及发布命令配置，不新增迁移或审批流程。

**Tech Stack:** Python/FastAPI/Pydantic/SQLAlchemy/PostgreSQL 15；React/TypeScript/Ant Design；npm 10 / Node 20 CI。

## 基准与隔离

- 起点 `4a00636f2928d0a4d3ca2de56599ad1ae3b57fb6`。
- 原共享对象库有云占位对象，首次检出停顿并取消；保留未完成工作树。实际工作树 `pr28-review-fixes-ready` 由远端新鲜 bare 对象库提供，不修改原树。
- 测试仅用本次新建、owner label 可核对的 PostgreSQL；不使用业务库、其他会话库或 provider 凭据。

## Task 1: Dependency lock (Lead)

**Files:** `frontend/package-lock.json`；保留 `frontend/package.json` 的现有版本范围。

- [x] npm 10.8.2 干净安装复现缺 esbuild 的 RED；本机 Node 26。Linux Node 20.20.2/npm 10.8.2 容器先验证锁，随后另一次正常 `npm ci`（含安装脚本）与 `npm run build` 均 exit0，源码只读挂载。
- [x] 仅补 27 个 esbuild 0.28.2 缺失条目；原 567 个条目逐一相同，不升级顶层依赖。
- [x] npm 10.8.2 再次 `npm ci` exit0；前端类型、构建、E2E 类型与 88 文件/748 单测通过，保留既有 UI warnings。

## Task 2: Make secret preservation (Lead)

**Files:** `Makefile`；新增 `backend/tests/ci/test_release_secret.py`。

- [x] subprocess 执行真实 Make recipe，但将 Python 替换成仅输出测试环境值的本地 probe，不运行迁移；RED 6 failed/2 passed。
- [x] 条件 legacy fallback 保留非空调用方 SECRET_KEY，不引入默认生产密钥，无提供则不设置覆盖。
- [x] 环境值/未设置/legacy fallback/双变量优先级 GREEN 8 passed；含现有 CI 纯回归共 192 passed/3 既有 warnings。

## Task 3: D8 gate visibility (outcome-fix)

**Files:** `backend/app/schemas/capa_outcome_review.py`、`backend/app/services/capa_outcome_review.py`、`backend/tests/capa/`；`frontend/src/types/capaOutcomeReview.ts`、`frontend/src/components/capa/CapaOutcomeReviewPanel.tsx` 及测试、locales 与必要现有 fixtures。

- [x] 后端 RED 4 failed/1 control passed，前端 RED 7 failed/22 passed；字段缺失、显示和预算反例成立。
- [x] 已绑定 `material['doc_gate']` 明确白名单 DTO/TS 类型与只读安全文本显示，保留 HMAC/来源权限/响应预算；历史 null 不补造记录。
- [x] 后端聚焦六模块 125 passed/5 既有 warnings（含真实 HTTP），面板/详情 88 passed，类型通过；中间接口 exact-field 与缺资源登记错误已记录并修正测试适配/调用环境。

## Task 4: Download final authorization (attachment-fix)

**Files:** `backend/app/services/agent_runtime/task_attachments.py`、`backend/tests/services/agent_runtime/test_task_attachments.py`。

- [x] 真实双事务事件同步复现：RED 9 failed/1 unchanged control passed，涵盖撤权/停用/目标重绑/附件变化、自然过期、提交异常/取消。
- [x] 文件验证后重查身份/权限/原目标及附件 status/expiry/factory/namespace/generation/hash/size；失败关闭描述符，审计提交失败回滚保留原异常。
- [x] 初始附件生命周期 GREEN 27 passed/3 既有 warnings。首轮全量到61%时已发现并保留历史代际兼容失败，随后取消，不计完整验收。既有 generation increment 用例单跑 RED 1 failed；最小修正为检查当前tenant归属而非强制origin代际相同，仍比较完整原始存储坐标。新增三项真实双事务改绑拒绝后，附件lifecycle/recovery/storage/API四模块 64 passed/3 既有 warnings。不改旧断言，终态和合法旧代际下载保持兼容。

## Task 5: Integration verification and handoff (Lead)

- [x] 审阅全部diff并执行最终全新库完整后端：3648 passed/4 skipped/19 deselected/5 warnings，pytest与runner exit0（2231.10秒）。整条 `make check` 在后端/tsc成功后的macOS Vite/esbuild文件open停顿超过10分钟而取消，不能称make exit0；另497个输入逐文件一致的全新本地frontend export npm ci/build exit0（build6.22秒），Linux Node20/npm10正常安装构建亦exit0。最终1423源码manifest `02ff9c2667b6c7305ec1f6d4f04fea3930194f22c0ecccf677f58e48b51e447e` 前后无变化。
- [x] 初次分别复核 Make/lock/download 和 D8；全量暴露代际兼容问题后另一次限定复核确认修正，无具体重要遗留。均只读，不冒充动态验收。最终同源实际 Chromium 保护 11 passed/3660 deselected/5 warnings/exit0；真实 provider/scanner 未请求。
- [x] 操作文档和 `PROGRESS.md` 已同步；本地交接仅包含本轮修复。精确容器/owner/零客户端/匿名卷独占核验后，已删除本次测试容器与其唯一匿名卷，其他容器/镜像/用户工作树保留。源码、冻结manifest与日志保留；原共享对象库首次云占位检出取消保留，新鲜bare对象库已持久复制至项目隔离目录并repair工作树指针。未取得远端 CI，不宣称远端通过，不自动推送/main 合并/部署。

## 验收边界

本轮授权为上述四项修复和测试；main 的现有冲突、远端手动 live/scanner 与生产部署不在本轮自动执行范围。若发现远端分支推进，先核对新提交而非强推覆盖。
