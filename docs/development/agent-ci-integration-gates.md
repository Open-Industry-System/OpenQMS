# CI 独立提交接入与分层门禁交接

日期：2026-11-03。状态：CI 接入、本地后端/浏览器/前端/pure 及独立 pinned ClamAV 层均已完成验证；实际收据和源码指纹已复核，测试资源已精确清理。结果仅保存本地集成分支，不代表远端 CI、真实模型或生产启用。

## 来源、隔离与权限边界

- 语义集成提交：`20570157755ec197d68431e5215811bca02fce7c`，保留 runtime `ef3e24e0` 与 main `d8e2cef5`。
- 本轮起点：`ce9dcc0936e902ada9744b5092c8af0d87555bc8`（只比语义集成多接入计划）。
- 外部 CI 独立提交：`4a00636f2928d0a4d3ca2de56599ad1ae3b57fb6`，已核对父节点及39文件范围。原工作树中用户删除的示例、原架构/开发基线及进度修改没有被复制或提交。
- 全部本轮修改、测试和暂存只在 `integration/agent-main-semantic-20261102`。没有更新 main、push、建 PR、触发远端 workflow、读取真实模型配置或生产开启。
- 本轮 PostgreSQL15 使用新的独占容器、随机 owner nonce、自有卷和 `127.0.0.1` 随机端口。资源登记0600、无凭据；实际URL只保存在本轮私有执行配置。不会借用 CI Agent 的数据库、容器或私有profile。
- 当前本机 Python3.11.15、Node26.13.0；不是 Linux/Python3.12/Node20 的远端验收结果。前端按锁文件从本机缓存离线安装491包，没有升级锁文件或下载浏览器。

## 固定源码

本轮动态测试使用未提交的 Git **tree** 快照 `601e71b1713651d789d5cb11e469c79a524decec`。它不是 main commit，也不是远端已提交/已批准 SHA；本地 receipt 的 `frozen_sha` 对应这个明确标注的本地源码树标识。

1444个实际执行相关文件的 SHA-256 manifest：

```text
e980a5d6c931a04b0dae594568b14b397a6634f18dce2623ded6b938d8128d05
```

每层执行前后逐文件验证该 manifest；完整后端与浏览器两层均已证明无执行源码变化。文档结果收尾可在之后更新，不将文档变更误称执行源码已经重新运行。应用/模型/public与tenant迁移及先前语义保护回归文件相对 `ce9dcc09` 没有行为修改。

## 集成中补齐的缺口与红绿证据

1. **pure collection / dotenv / Python children**：collection不再探库；误用数据库fixture明确报错，不被转换成skip。所有支持的Python pytest/preflight/Alembic子进程在导入应用前禁隐式dotenv，保留显式临时 `_env_file` 测试。pure模式拒绝Python连接、DNS、datagram、bind与项目psycopg入口；普通DB层不安装network guard。
2. **默认pure插件隔离**：首次清洁默认启动出现 `1 failed /222 passed`，原因是提前导入Pydantic后ambient logfire插件引入warnings计数变化。仅pure模式固定插件配置，显式加载项目asyncio；不屏蔽warnings，也不修改原nested receipt的warnings=0断言。修正后默认入口通过。
3. **显式Chromium末级传递**：source中的专用executable键规范化、验证并传到Node，source优先；空/非法路径拒绝，不静默回退。保持系统/运行参数白名单及凭据隔离。真实函数链先红，25项纯回归通过；最终11项真实浏览器均实际启动指定wrapper。
4. **libpq ambient路由**：在inspect/DB I/O前拒绝额外 `PGHOSTADDR/PGSERVICE/PGSERVICEFILE/PGSYSCONFDIR/PGOPTIONS`，实际连接再固定数字hostaddr。原反例13 failed /1 passed，修正后与原资源测试76通过。
5. **统一地址族**：新增闭环反例5 failed /2 passed，证明localhost可验证IPv6但实际写IPv4的问题。现localhost仅IPv4，显式::1支持IPv6；登记、Docker binding、libpq URI/hostaddr、asyncpg URL和PG15工具候选按同一有效数字地址处理。原错误正向矩阵移入负向，未删除覆盖。
6. **Make secret**：fake Python实际执行recipe先7 failed /1 passed。测试迁移前置与后续recipe共享测试fallback且保留显式值；运维前置/迁移要求真实显式 `SECRET_KEY`，不再被空的旧变量覆盖。不执行部署。

root/network guards是支持的Python测试入口隔离，**不是任意Node、shell、native低层libpq或自定义exec的OS网络沙箱**。不依此运行不可信测试程序。

上述修正完成独立静态复核；最后DNS与地址族闭环限定复核为Scoped Approve，未发现未闭合Important。静态复核与下列实际门禁分开记账。

## 本轮真实门禁

| 层 | 实际结果 | 边界 |
|---|---|---|
| CI支持＋runner pure | 238 passed，3既有Pydantic warnings，exit0 | clean env，无外部pytest插件配置，真实pure入口；不以stub当DB验收 |
| backend | 3827 passed /4 skipped /0 failed /0 errors /0 xfail /0 xpass，6 warnings，exit0 | selected3831；保留原graph两项排除；实际PG15及public/tenant迁移 |
| browser | 11 passed /0 skip /0 fail /0 error /0 xfail /0 xpass，6 warnings，exit0 | 真正Chromium，显式wrapper启动11次，非默认缓存假覆盖 |
| frontend | tsc、生产build、E2E类型均exit0；88文件/741单测通过 | 单worker，不改测试或超时；保留act/jsdom/Node localStorage等现有warning |
| pinned scanner | 真实process 6 passed＋host browser 1 passed，0 skip/fail/error/xfail/xpass，exit0 | 固定1.4.3镜像；收据同源，实际导出/down/inspect均0，project容器/卷/网络余量全0 |
| live provider | NOT_REQUESTED | 未读取profile、未调用真实模型，不借原分支历史通过数 |
| GitHub auto/manual | 本集成分支未执行 | 未push/dispatch，不冒称本地通过等于远端通过 |

重新collect得到总3850个用例：backend3831 / browser11 / live1 / scanner7。四层节点集合互不重叠；collection不是运行通过数。backend四项skip为未配置的Redis及三个共享seed E2E endpoint，不记passed。PG15冻结快照使用本轮登记容器工具真实执行，没有用宿主工具缺失skip代替。

本轮实际调用：

```bash
# 以下资源变量均来自本轮新建实例的0600登记；不使用业务库或默认URL。
python scripts/check-ci-pure.py tests/ci tests/e2e/test_capa_outcome_runner.py -q
make check-test-db PYTHON_BIN=/明确核验的解释器
make check-backend PYTHON_BIN=/明确核验的解释器
make check-browser PYTHON_BIN=/明确核验的解释器
make check-frontend-tsc
make check-frontend-build
npm --prefix frontend run test -- --run --maxWorkers=1
frontend/node_modules/.bin/tsc -p frontend/tsconfig.e2e.json
make agent-attachment-e2e PYTHON_BIN=/明确核验的解释器
```

测试前置特意没有ambient `SECRET_KEY`，实际Make迁移已通过；合并public head为 `20261102_agent_mainline_merge`，`AgentReadTask`与`AgentTask/Run`及平台表均存在。普通测试child无隐式dotenv/E2E/provider回填。raw JUnit由runner保持私有并删除，只有过滤日志及实际收据进入本轮artifact目录；资源登记、执行配置和产物不提交源码。

## 下一步

scanner实际收据、导出与自有project清理已核验；主PG容器也已按精确ID/owner/唯一自有卷及零其他客户端核验后删除，卷一并删除，本轮私有执行口令文件已移除。镜像、过滤产物、工作树与其他项目保留。结果保存为本地合并提交，提交标识以该分支 `git log -1` 为准；不推送或更新main。

用户已选择后续R4b优先“元数据只读SDK与协议兼容”。仍先完成独立SDK设计/评审，不开放正文/附件外发、模型调用或业务写入，不复活已撤回D4候选审批方案。只读SDK/检查点不等同R5业务补偿；现有D8集中结果审核不等同通用两阶段模型操作审核。
