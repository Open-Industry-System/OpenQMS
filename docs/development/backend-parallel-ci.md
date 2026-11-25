# 后端双分片 CI

完整后端由两个独立的 PostgreSQL matrix job 执行：`backend-full (runtime)` 和
`backend-full (remainder)`。必需检查仍叫 `backend-tests`，只有两片的真实执行
收据都通过校验后才成功。前端、浏览器、main push 和整条 workflow 的取消策略保留。

## 分组与原入口

分组唯一入口是 `backend/tests/ci/backend_shards.py` 的 `module_shard()`：
`tests/services/agent_runtime/` 与下面两个整文件归 runtime，其余文件默认归 remainder：

- [test_d4_recovery_checkpoint.py](../../backend/tests/api/test_d4_recovery_checkpoint.py)
- [test_r4b_main_merge_guards.py](../../backend/tests/migrations/test_r4b_main_merge_guards.py)

两个额外模块集中列在 `RUNTIME_MODULES`。新增测试文件无需更新文件清单，必定落到一组。
整个文件只在一片执行，保留模块 fixture 的复用范围。

两片仍由 `make check-backend BACKEND_SHARD=0|1` 调用原
`capa_outcome_runner.py api --pytest-target tests`，先验证和准备各自的测试数据库。
每片完整收集一次，然后在原 marker 筛选之后按模块分组。原有普通后端 marker、两个
`--ignore`、JUnit、hook 统计、退出码和普通可选 skip 语义不变。省略 `BACKEND_SHARD`
继续串行运行原完整集合。

R5、SDK wheel 和 D4 真进程的固定节点检查保留在各自的 owning runner 内，汇总时再
核对固定节点的实际结果；必选节点少一个、被替换、重复或 skipped 均失败。
SDK 真进程在 remainder，因此只由 remainder 安装 SDK 构建工具、构建并核对 wheel
的路径与 SHA256。未分片入口也继续构建 wheel。手动 schema/SPC 脚本、D8 preflight、
engine import 检查均只在 remainder 执行。

## 集合证明与执行收据

可执行检查从同一次完整 pytest 收集取得真实 node IDs，包括参数化 ID；检查原集合
等于两组并集、交集为空、两组非空且包含全部固定必选节点，不读取手工节点清单代替
pytest 收集。它保留正式 runner 的 pytest 插件和数据库可用性探针，无需可用数据库；
只收集，不执行用例：

```sh
cd backend
TEST_DATABASE_URL=postgresql+asyncpg://qms:unused@127.0.0.1:1/qms_test \
SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. \
python -m tests.ci.backend_shards collect --output /tmp/backend-partition-private.json
```

`--output` 保存真实 ID，权限为 0600，属于本地私有证据，不上传 artifact。终端打印
原集合、两组、并集和交集的计数。默认 marker 和 ignore 与 Make 入口的契约测试同步。

正式执行另外记录每片的完整收集集合、按模块分组、实际选中节点，以及每个节点的
setup/call/teardown 和结果。公开收据只含节点 SHA256，不公开原始参数值；原始 JUnit
和 hook 文件仍在私有临时目录，runner 完成后删除。每片使用独立的 PG service、随机
宿主端口、owner/shard label、artifact 根目录和 `backend-shard-{runtime,remainder}-evidence`。

matrix 的真实 `GITHUB_JOB` 为 `backend-full`，与校验使用的 job label 一致；额外的
`openqms.ci.shard` 区分分片，不尝试改写 GitHub 的默认身份变量。

`backend-tests` 下载两个 artifact 后验证：

- 恰好两份 API 执行收据，分片身份不同，均来自当前提交且真实成功。
- 两片的完整收集 manifest 相同，选中集合互斥，其并集等于原完整集合。
- 模块不跨片，每个选中节点都留下完整执行阶段，结果计数与原 runner 收据相符。
- R5、SDK、D4 固定模块的节点集合完全相同，且必选节点全部实际 passed。

缺结果、空集合、收集失败、运行失败、cancelled、意外 skipped、重复收据、缺失执行
阶段或缺失必选节点均不能变绿。通过后输出原格式的合并 `api-receipt.json`，仍上传为
`backend-tests-evidence`，供现有预览发布收据校验使用。汇总校验仅使用 Python 标准库，
无需重新安装后端依赖。

## 路由与必需检查

路由继续从 PR 的可信 base 提交读取策略。输出包含 `docs_only`、`backend_required`
和 `route_reason`；`docs_only` 只表示纯文档，展示资源快路径用后两个字段表达。只有
路由 job 成功并明确给出允许的快路径原因，且 matrix 全部 skipped，`backend-tests`
才接受跳过。路由失败、缺字段、未知原因和非成功的必跑 matrix 均失败。

main push、公共基础变更、未知影响或缺少可信 base 策略时运行两片。可信 base 支持模块路由后，已知业务路径可选择基础与相关组，由单个 `backend-full (selected)` worker 执行。预览要求 API 收据时，原本可跳过的快路径运行基础组。汇总验证选组与收据来自同一 SHA，并继续发布 Oracle 所用的唯一 API 收据。兼容旧可信 base 的既有快路径和全量回退规则。

前端与浏览器检查继续正常运行。范围见[模块路由](backend-ci-module-routing.md)和[快路径说明](backend-docs-fast-path.md)。

## 测量口径

历史基线为 main `051d4b06` 的 Actions run `44445156751`：runtime 目录 948 项，
setup/call/teardown 累计 2650.794 秒；其余 4761 项累计 2573.976 秒。这是分组依据，
不是双 job 的实测结果。

四个慢模块的正式本地 A/B 均为 165 passed：runner wall 959.32 → 481.29 秒，
setup 769.1168 → 328.1819 秒，call 102.9027 → 97.1595 秒，teardown
76.096 → 46.6972 秒。按各模块成功 B/A 的 phase 比值加权同 SHA 的历史模块计时，
估算应从 remainder 转移 261.78 秒到 runtime。候选整文件中，上述两个模块共 48 个
节点、历史 phases 264.9086 秒，最接近这个目标；估算调平后 runtime/remainder
分别为 2315.32/2309.07 秒。计算依据保存在本轮私有证据
`partition-balance-estimate.json`。

这只是确定初始分组的估算：本地和 Actions 主机不同，fixture 的收益不能直接当作
远端 wall time 收益，两个 job 的安装、PG 准备、收集与调度成本也不在 phase 估算中。
完整两片的真实数据库运行及下一次同类 Actions 结果应单独记录，再按实际耗时评估平衡。

比较时分别报告两片 job wall time、`backend-route` 开始至 `backend-tests` 完成的等待
时间、route/两片/gate 的 runner 分钟，以及整条 workflow 的 runner 分钟。使用
`scripts/ci/backend_metrics.py` 读取 GitHub jobs/run JSON；等待缩短不意味着 runner
分钟减少。额外一套 PG、依赖安装及完整收集的成本也计入新运行，不从旧串行日志外推。
本地验证与远端同类 runner 结果分开记录。
