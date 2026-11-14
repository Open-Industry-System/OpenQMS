# Agent 主线语义集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立本地分支集成 main 与 Agent runtime，保留双方授权、来源与租户保护，不接管 CI、不更新 main、不推送。

**Architecture:** 以 runtime 已提交版本为起点，合入 main，并联动适配调用方而非整文件选边。保留默认关闭及 baseline DENY；旧 AgentReadTask 与新 AgentTask/Run 不互换。通过显式合并迁移和独立租户 delta 维持升级路径。

**Tech Stack:** Python/FastAPI、SQLAlchemy、PostgreSQL、Alembic、pytest。

---

## 固定基线与边界

- runtime: `ef3e24e076d5ef313e415d768567809987da04bc`。
- fetch 后 main: `d8e2cef5f60aa0272c1d16481afcd4cc3aa1b17f`。
- 独立分支: `integration/agent-main-semantic-20261102`。
- 工作区: `.worktrees/agent-main-semantic-integration`。
- CI Agent 位于原 runtime 工作树；不复制其未提交改动，不编辑 workflow、Makefile、pytest.ini、现有 E2E 分类或 CI runner。
- 首次完整检出等待本地 `dataless` 对象，已中断；Git 自动清理未完成工作树但保留分支。重新以 sparse checkout 创建，排除无关 `backend/app/services/capa_ppt_service.py`，无新 clone、无云同步设置修改。
- 已对源工作树相关权限目录执行精确 tracked diff 核对并在禁止网络/不加载根 conftest 条件下测试：32 passed，0 network attempts。这不是集成后验收。
- 数据库验收必须使用本轮专属、明确归属的资源；不能运行指向未知数据库的 make check。不能将 skipped DB 测试称为通过。

## Task 1: 复现合并并保留双侧合同

**Files:**
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/agent/permissions/{access,catalog,types}.py`
- Modify: `backend/app/services/capa_agent_projection.py`
- Modify: `backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py`
- Modify: `PROGRESS.md`, `docs/architecture.md`

- [x] fetch、确认源版本与 CI dirty scope，`git merge-tree --write-tree` 复现 8 个冲突。
- [x] 创建独立 sparse worktree，并确认 `git status --short` 无输出。
- [x] 执行 `git merge --no-commit --no-ff origin/main`，预期退出 1 且仅已知 8 冲突；异常冲突另行调查。
- [x] 逐文件阅读冲突，先保留 runtime 作为可执行骨架，同时保留 main 新增测试和非冲突代码；模型 import 与 __all__ 取并集，保留 AgentReadTask 和所有 runtime/platform 模型。
- [x] projection 保留 runtime 的 TenantBinding、第一条 RR READ ONLY、严格 search_path、显式列和完整 digest。main 测试的读暂停 hook 应适配 Connection，不移除并发断言。
- [x] 两份进度/架构文档保留历史与新功能说明，不把旧分支完成记录当本次验收。

## Task 2: 权限交集与 runtime adapter（RED → GREEN）

**Files:**
- Modify: `backend/app/services/agent/permissions/{access,catalog,types}.py`
- Modify: `backend/app/services/agent_runtime/{runtime_access,task_service}.py`
- Test: `backend/tests/services/agent/permissions/test_access.py`
- Create: `backend/tests/services/agent/permissions/test_mainline_runtime_integration.py`

- [x] 新测试使用 canonical local profile，而不是未注册 spec，写出 None 工厂不能由 CAPA ADMIN 授权的断言：

```python
summary = get_capability('capa.d4.summary.masked.v1', profile='local_metadata_v1')
grant = Grant(summary.id, frozenset({factory}), frozenset({report}), frozenset({'LINE'}))
attempt = AccessAttempt(summary, {Module.CAPA: PermissionLevel.ADMIN}, None,
    frozenset({'LINE'}), grant, grant, factory, report, 'LINE', datetime.now(UTC),
    catalog_profile='local_metadata_v1')
assert not authorize(attempt).allowed
```

- [x] 在禁止网络的纯 lane 运行新测试，确认旧骨架错误地 allowed；再实现恢复 GROUP ADMIN guard。
- [x] 新测试覆盖 None 产品线默认拒绝、显式 bypass 正向、空集合仍拒绝、bypass 不能跨工厂、GROUP ADMIN 不自动豁免产品线。
- [x] types 同时保留 `identity_bypass_row_level_security: bool = False`、`catalog_profile: str = 'baseline'` 与 `CapabilitySpec.target_required`；bypass 保留 main 原位置，profile 用 keyword。
- [x] catalog 默认声明从业务模块只读导出；profile 仅覆盖 summary 的 floor，baseline 两能力 DENY、command DENY、未知 profile 拒绝。
- [x] 两 adapter 从 freshly resolved `lines.mode == 'ALL'` 明确传 bypass，同时保留服务端 profile；不读取旧 cached role，不发明 ProductLineScope 属性。
- [x] 恢复 context/command 与 projection 联合校验，修正现有测试中 command 误沿用 masked 的声明，并测 canonical 已注册但合同非法时拒绝。
- [x] 重跑权限目录与 adapter 纯测试，必须保留有效正向 control，不能让 unknown capability 掩盖负向断言。

## Task 3: 审批与来源 lineage（RED → GREEN）

**Files:**
- Modify: `backend/app/services/agent/permissions/review.py`
- Modify: `backend/app/services/agent_runtime/readonly_delivery.py`
- Test: `backend/tests/services/agent/permissions/{test_review,test_delivery}.py`
- Test: `backend/tests/services/agent_runtime/` 相关历史输出测试

- [x] 保留 main 审批回归：DENY 不可批准、owner module permission mapping、专门 approval 标记、active employee、对象 scope、申请人与执行人双排除；只有独立合规员工正向可过。
- [x] 先用当前 helper 创建 main 六字段 SourceLabel，复现 runtime 历史来源路径旧位置参数不兼容。
- [x] runtime label 改 keyword：owner/object_id/sensitivity/capability_id/projection/source_version；capability 来自已核验 receipt projection，projection 来自 canonical spec，version 保留完整 digest。
- [x] 授权集合使用 `(owner, object_id, capability_id, projection)`，且仅在当前来源 ACL 成功后加入；继续保留 _sources task/run/target/generation/epoch 绑定及交付前最终复核。
- [x] 跑纯 lineage/审批测试；DB 撤权/并发部分留到独立环境，不以 mock 替代真实提交证据。

## Task 4: 迁移图与租户升级

**Files:**
- Create: `backend/alembic/versions/20261102_agent_mainline_merge.py`
- Modify: `backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py`
- Create: `backend/tests/migrations/test_agent_mainline_merge_graph.py`
- Review/if required modify: `backend/alembic_tenant/`, `backend/app/services/tenant_migrator.py` 及相关 reviewed revision/parity 断言

- [x] 写无 DB fixture 的 ScriptDirectory head 测试，证明双 head 失败；不能复用带 mig_db_url 的“静态”用例。
- [x] 新 merge revision 的 `down_revision` 同时包含 `20260929_agent_read_task` 和 `20261009_agent_task_attachments`，upgrade/downgrade 为 no-op；不改任何已发布父链、不 stamp。
- [x] 更新单 head 断言为新 revision，并确认两旧 head 均为 ancestors。
- [x] 阅读独立 tenant reviewed chain 和 parity；如 AgentReadTask 纳入 tenant metadata，新建 reviewed tenant delta 创建该表并更新允许版本/目标，保留冻结 tv001 snapshot 和 checksum 不变。
- [x] 分别验证空库、main 旧 head、runtime 旧 head 升级，以及新租户和旧租户升级；需要先核验专属资源身份。

## Task 5: 验证与交接

**Files:**
- Modify: `PROGRESS.md`, `docs/architecture.md`
- Create: `docs/development/agent-main-semantic-integration.md`

- [x] `git diff --check`、无冲突标记扫描、模型 import、Alembic public/tenant 图检查。
- [x] 执行权限纯回归并记录完整命令、数量、退出码及网络尝试计数。
- [x] 在归属明确的独立数据库执行权限/运行时/投影/迁移/租户相关 DB 回归；前端如未检出，不能声称构建通过。
- [x] 独立 code review，处理阻塞项后重跑受影响测试。
- [x] 记录本次新鲜结果与未执行层（真实 provider、ClamAV、浏览器、完整 make check），不引用历史通过数充当本次结果。
- [x] 核对原工作树未被本任务写入、CI 改动未复制；记录 CI 后续接入提交的边界。
- [x] 不更新 main、不 push；本地 merge commit 在完整复核后再决定，不能把未验收 merge 自动提交。

## 安全纯测试入口（命令约束）

从工作树根使用 Python 内联 runner，在 import pytest 前设专用端口 1 URL，`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`、`PYTHONDONTWRITEBYTECODE=1`，阻断 socket connect/connect_ex/create_connection/getaddrinfo；调用 `pytest.main(['-c','backend/pytest.ini','--noconftest','-p','no:cacheprovider','-p','pytest_asyncio.plugin', ...])`。若任何网络尝试发生则非零退出。不修改或复制 CI Agent 的 runner，不设置 ALLOW_SEED_DB_TESTS。

## 自检

覆盖 main 的 factory/product-line/applicant/lineage 保护和 runtime profile/tenant snapshot/source receipt 合同；不包含 R5 写命令、业务结构重构、CI 实施或生产启用。新增迁移必须经过实际图审查后再写，不能只让字符串断言变绿。
