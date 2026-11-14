# Agent runtime 与主线语义集成交接

日期：2026-11-02。此文保留CI接入前的语义集成快照与历史命令，不作为当前门禁执行配置。2026-11-03已进一步接入CI独立提交并完成本地分层门禁；当前配置、真实结果及限制见[CI集成交接](agent-ci-integration-gates.md)。不代表远端验收或生产启用。

## 隔离与基线

- 分支：`integration/agent-main-semantic-20261102`。
- runtime 起点：`ef3e24e076d5ef313e415d768567809987da04bc`。
- 主线：`origin/main@d8e2cef5f60aa0272c1d16481afcd4cc3aa1b17f`（已实际 fetch）。
- 工作树：`.worktrees/agent-main-semantic-integration`。创建完整工作树时本地 Git 对象标为 `dataless`，检出等待；中止后 Git 自动清理未完成目录并保留集成分支。随后沿用该分支按需检出成功，无新 clone、无云设置修改。测试导入需要的唯一排除服务，从原 runtime 工作树按提交 blob 哈希核对一致后补入；没有复制 CI 的未提交内容。
- 原开发分支、main 和 CI Agent 工作树未作为写入目标。不 push、不直接更新 main、不生产启用。
- CI 分层由其他 Agent 独立实施；本次不编辑 workflow、Makefile、pytest.ini 或 CI runner。随 main 已提交历史进入的 issue forms 不属于接管 CI。

## 语义集成内容

1. **权限交集**：无界工厂必须 `GROUP ADMIN`；无界产品线必须显式行级 bypass；空集仍拒绝，bypass 不替代工厂、owner module 和插件/任务 grant。恢复 kind/projection 联合合同。
2. **规范目录**：CAPA 模块持有只读声明；baseline summary/command 均 DENY，summary target_required 保留。服务端 local profile 仅改变 summary floor，command/未知 profile 仍拒绝。
3. **调用方兼容**：AccessAttempt 保留主线 bypass 原位置，profile keyword-only；task/runtime 两 adapter 同时传入新鲜范围解析得到的 bypass 和服务端 profile，不读取缓存角色。
4. **审批**：保留主线 owner module 权限映射、专门 approval 标记、DENY 不可批准及申请人/执行人双排除。
5. **来源 lineage**：SourceLabel 使用六字段 keyword，授权使用 owner/object/capability/projection 四键。当前 source ACL 成功后才构造授权集合；receipt 的 task/run/target/generation/epoch 校验及历史输出序列化前后复核保留。
6. **投影**：保留 runtime 原实现，独立连接第一条语句设置 RR READ ONLY，再绑定租户；无多租户 public fallback；显式元数据字段和完整 digest。主线并发测试 hook 适配实际 AsyncConnection；写验证子项的测试补真实 CAPA 编辑者，不绕过新鲜写权限。
7. **模型/迁移**：AgentReadTask 与 AgentTask/Run 两表族并存。新增 public `20261102_agent_mainline_merge` 显式承接两已发布 head；tenant `tv006_agent_read_tasks` 补旧表，reviewed gate、前驱 parity/升级目标同步。tv001..tv005、冻结 snapshot/manifest、两已发布 public 父链不变。
8. **租户安全**：保留每事务 generation/status/schema 验证、业务共享锁、维护 owner/PID/attempt/排他锁、严格 tenant search_path、完整 parity 与 seed/isolation 成功后才激活。

## 红绿证据

- 集成前权限基线：32 passed，0 network attempts。
- 权限恢复回归 RED：9 failed /51 passed；target_required RED：1 failed /1 passed；adapter/source API RED：4 failed /14 passed；均 0 network attempts。
- 最终权限＋adapter 纯回归：128 passed，1 既有 OpenTelemetry 弃用警告，0 network attempts，exit 0。
- 迁移图 RED：3 failed；租户前驱合同 RED：12 failed /1 positive control passed；均 0 network attempts。
- 最终迁移/租户纯回归：28 passed，1 既有 OpenTelemetry 弃用警告，0 network attempts，exit 0。
- 主线旧 projection 测试最初缺失 Session hook 导入失败；已改为真实连接拦截。真实数据库首轮 6 passed /1 failed，失败原因为旧测试 `user_id=None` 被 runtime 新鲜写授权正确拒绝；补真实编辑者 fixture，不改生产写保护。

## 本轮 PostgreSQL 15 验收

环境为本轮新建的 `pgvector/pgvector:pg15` 本地镜像容器，精确 owner 标签 `agent-main-semantic-20261102`，仅绑定本机随机端口；未使用 Compose 服务、原开发库或用户私有 profile。主 runtime 和辅助多租户测试使用不同新库，迁移 fixture 再创建/销毁随机 `_test` 库。

| 检查 | 本轮结果 |
|---|---|
| 空库先升级 runtime 旧 head，再升级新 merge head | 两次 Alembic upgrade 均 exit 0 |
| public 空库 / main 旧 head / runtime 旧 head → merge head；两表族、复合 FK、checks/indexes | 3 passed，3 既有 Pydantic warnings，exit 0 |
| 迁移图、旧 read-task 迁移、历史 controls delta、parity、fresh/tv005 既有租户升级/回滚重放 | 48 passed /1 skipped，3 既有 Pydantic warnings，exit 0，108.47s |
| 冻结基线再生补验 | 使用本轮容器内 PG15 pg_dump/pg_restore 在单独快照测试库按 manifest 锚点再生，1131 objects 与冻结 DDL/object_keys 完全一致，exit 0 |
| 权限＋完整 services/agent_runtime＋main projection | 首轮 741 passed /17 setup errors，3 既有 Pydantic warnings，exit 1，1095.41s；17 项均在同一专用库名前缀守卫拒绝，未进入业务断言 |
| 旧单报告 task service＋全部 test_multitenancy＋SPC 匹配测试＋single public head | 193 passed，3 既有 Pydantic warnings，exit 0，460.46s |
| 三份 trial 模块按要求使用 openqms_r4a_ 前缀的专属新库重跑 | 17 passed，3 既有 Pydantic warnings，exit 0，70.32s；没有修改生产逻辑、fixture 安全守卫或 CI 分类 |

741 项通过与 17 项重跑通过覆盖原大套件全部 758 个用例，代码树相同；未将两次结果冒称一次全套 exit 0，也未将不同套件的重叠用例相加为独立总数。

48-case suite 的唯一 skip 是宿主机无 pg_dump。未修改该测试的工具选择和端口守卫；补验通过容器内工具执行同一再生/比较逻辑，5432 URL 仅交给 docker-exec pg_dump，真正 Alembic 连接仍为专属随机端口。不将原 pytest skip 改称 passed。

## 可复现测试入口

所有数据库测试必须先确认自己创建的临时容器 identity/owner/端口，再显式设置 `DATABASE_URL` 和 `TEST_DATABASE_URL` 为该容器的专用测试库，不能回退默认配置，不设置 `ALLOW_SEED_DB_TESTS`。禁用 provider/E2E 并清空 provider key 环境；本次没有真实 provider/scanner 请求。

```bash
# 工作目录 backend；QMS_TEST_URL 必须是已核验归属的独立测试库，不是业务库。
# runtime trial fixtures 还要求库名以 openqms_r4a_ 开头且以 _test 结尾。
export DATABASE_URL="${QMS_TEST_URL:?owned disposable DB URL required}"
export TEST_DATABASE_URL="$DATABASE_URL"
export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export SECRET_KEY=semantic-integration-test-only
export LLM_PROVIDER= EMBEDDING_PROVIDER= LLM_API_KEY= EMBEDDING_API_KEY= E2E_MODE=false
python3 -B -m alembic upgrade head
python3 -B -m pytest -p no:cacheprovider -p pytest_asyncio.plugin \
  tests/services/agent/permissions tests/services/agent_runtime \
  tests/services/test_capa_agent_projection.py -q
python3 -B -m pytest -p no:cacheprovider -p pytest_asyncio.plugin \
  tests/migrations/test_agent_mainline_merge_db.py \
  tests/migrations/test_agent_mainline_merge_graph.py \
  tests/migrations/test_20260929_agent_read_task.py \
  tests/migrations/test_agent_readonly_controls_delta.py \
  tests/migrations/test_tenant_schema_parity.py \
  tests/test_multitenancy/test_agent_read_task_delta_db.py -q -rs
```

纯测试不能裸跑 pytest 或只用 `-m` 声称不触库：根 conftest 会在 collection 探测数据库。本轮使用 `--noconftest` 内联 runner，导入 pytest 前阻断 socket connect/connect_ex/create_connection/getaddrinfo 并计数，使用专用不可连接端口 1 URL，禁写 pyc/pytest cache。不复制另一 Agent 尚未提交的 CI runner。

## 独立复核与限制

权限/adapter 和迁移分别完成独立规格复核 PASS，再分别完成独立质量复核 Approve；四份静态审查均无实质 Critical/Important/Minor 发现。审查的是当前未提交工作树（含新增文件），不是仅 HEAD；审查者未运行测试或访问 DB，不代替上表真实验收。

未执行完整 `make check`、前端类型/构建、浏览器、真实 provider、真实 ClamAV 或生产部署验收；不把历史3450通过数或本轮纯测试当成这些层的结果。前端未因本次合并改变，且当前工作树为按需检出。CI 后续需由协调者明确接入另一 Agent 的已提交变更，再跑其分层门禁。

## 收尾与下一步

- 8 个文本冲突均已解决并登记到集成索引；全部 36 个变更 Python 文件 AST 检查、暂存 diff 空白检查及无冲突标记检查通过。原 runtime 工作树相关应用/迁移代码对起点提交的精确 diff 为空。
- 本轮专属容器在全部测试进程结束、核验精确 ID/owner/唯一数据卷及零其他客户端后停止并删除，匿名数据卷一并删除；镜像、工作树及其他已有服务未动。
- 交接策略：仅将合并结果保存为本地集成分支上的提交，保留该工作树供继续开发；不更新 main、不 push、不建 PR、不部署。当前提交标识以该分支 `git log -1` 为准。
- 下一步由协调者接入 CI Agent 的独立已提交变更，再运行其分层门禁；需要生产/浏览器/provider/scanner验收时另行确认专属资源与授权。不要用本报告宣称全站 `make check` 通过。
