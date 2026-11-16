# PR CI 触发去重与后端耗时基线

日期：2026-11-15。集成目标：`main`，fetch 后 `origin/main=d3c0ada8f57c9c8831709117c7c95cbf2d925d66`。
实现保留单一后端 job、全部既有 marker/ignore、SDK wheel 版本校验、浏览器门禁和 preflight；不实施分片或按改动选测试。

## 第一优先级：PR 事件去重

诊断样本是 PR #33 的同一 head `75fcc51765bd3b6b739695178a399bfa01806574`：
[push run 43714113498](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43714113498) 与
[pull_request run 43714120965](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43714120965)。
两者均启动 backend-tests，并各有一个 r5-native 排队。
最新 main 与该 head 的 test.yml 均为 `push.branches: ['**']`，没有单独列出功能分支。旧 concurrency 按 github.ref 分组，功能分支 push 和 refs/pull/33/merge 是两个组，不能相互去重。

最小变更仅把 push 分支收敛为 `[main]`；未找到需要额外保留的活跃独立验证分支/标签约定。
`pull_request.branches: [main]`、workflow 名 `Test OpenQMS`、所有主线 job 名/矩阵、job 条件及失败处理不变。
继续保留 `ci-${{ github.workflow }}-${{ github.ref }}` / `cancel-in-progress: true`，同一 PR 追加提交仍取消旧 PR 运行。

| 事件/场景 | 修改前 Test OpenQMS | 修改后 |
|---|---|---|
| 新建指向 main 的 PR | PR 一套；同次先前功能分支 push 可能另有一套 | PR 一套 |
| 已开 PR 追加提交 | push + synchronize 两套 | 仅 synchronize 的完整 PR 一套 |
| 重新打开 main PR | PR 一套 | PR 一套 |
| 合并后 push main | push 一套 | push 一套 |
| 未开 PR 的功能分支 push | push 一套 | 不触发，需开 main PR 获取此套验证 |
| integration 等其他非 main 分支 push | push 一套 | 不触发；这是明确的行为变化 |
| tag push | 不触发（原仅定义 branches） | 不触发 |
| 非 main 目标 PR | PR 不触发；同仓分支 push 原可触发 | PR/push 均不触发 Test OpenQMS |

按[GitHub PR 事件语义](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)，未设置 types 时仍为 opened/synchronize/reopened；checkout 不设置 ref，继续使用该 PR 的合并候选。
样本 PR browser job 实际日志为 `refs/remotes/pull/33/merge`，SHA `1d3cadc756d8ce5125d06ac9f86885005286f42b`，不是直接 checkout 75fcc517。
本地契约覆盖事件矩阵、默认 checkout、无 job-level skip/continue-on-error、原 concurrency 和检查名；另将 trigger-only delta 应用到 PR #33 workflow 的内存副本，逐对象确认所有 jobs（含 r5-native）及其 PR/concurrency 配置完全相同。没有改动或提交该功能分支。

样本未来每次 PR 更新少派发的 push job 为 backend-tests、browser-protection、frontend-checks、3 个 sdk-checks、oracle-automation-checks，以及一个排队中的 r5-native，共8次 job 派发；push 的 docs-check 原为 skipped，不算 runner 工作。主线尚无 R5 实现，因此本分支未复制 native job 或 Responses 功能；后续把本 CI delta 集成到 PR #33 时必须保留其独有 native job，不能用主线整份 workflow 覆盖它。

### 保护规则与 runner 的实际核查

只读 REST API 核查结果：main `protected=false`，传统 protection 返回404“Branch not protected”；`rules/branches/main` 返回空列表。仓库 ruleset `17638580`（名称 main）为 active，但 include/exclude 均为空，规则仅 deletion / non_fast_forward，没有 required_status_checks。**当前未发现实际配置的 PR 必需状态检查，因此无法声称失败 PR 已被仓库设置强制阻止合并。** 本任务不修改管理设置；需维护者另行确认/配置真正的 required checks。

样本 check-runs 的来源为 GitHub Actions App `15368`（github-actions），名字保留 backend-tests / browser-protection / frontend-checks / sdk-checks (3.11/3.12/3.13) / docs-check / oracle-automation-checks，以及 PR #33 独有的 r5-native。原 check failure 仍保持 failure，不转成成功/跳过；合并阻断是否有效必须同时依赖管理员设置，这次未冒称已建立。

runner API 返回仓库可见 self-hosted runner 总数0，匹配 `openqms-r5-sandbox` 的列表为空；PR r5-native 仍 queued、runner_name 为空。该 job 在 queued 时 API started_at 等于 created_at，不能据此误报等待0秒。未取消远端运行、未改 macOS labels、timeout 或验收内容。去重减少重复派发/潜在 runner 占用，**不保证缩短 PR 等待时间**：缺少匹配 runner 时仍会等待。

本轮未 push，当前已运行的 PR #33 两套 workflow 不会被本地改动追溯取消；功能分支必须包含此配置后，未来 push 才采用新过滤。下一次实际 PR 仍须核对只有 PR run、合并候选 SHA、同 PR 旧运行取消、完整检查来源/结论及 main 合并后的 push。事件本地匹配不是远端运行通过证据。

## Actions 历史基线

来源：[成功 PR run 43686875078](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43686875078)，`backend-tests` job `132729087393`。
PR head 为 `13d1ac1baa4e72d9ebef6d0b2386bb4a848abc50`，实际测试 merge SHA（receipt.frozen_sha）为 `3d95cb912b0da920dc2e1a77dacc3b999f66dcaa`。
这不是当前目标提交 `d3c0ada8` 的同提交对照，不能把后续本地运行差异归因为优化收益。

Runner：`ubuntu-latest`，实际 Ubuntu 26.04.1 / image `ubuntu-26.04` version `20261111.196.1`；Python 3.12.16，pytest 9.2.0；GitHub Actions hosted runner `1000000518`。

| 指标 | 历史实测 | 测量口径 |
|---|---:|---|
| backend job 排队 | 2秒 | created_at 06:45:21Z → started_at 06:45:23Z；workflow run 排队0秒 |
| backend-tests 总时长 | 6134秒（1:42:14） | job started_at 06:45:23Z → completed_at 08:27:37Z |
| PostgreSQL service 初始化 | 22秒 | step 时间戳，秒级精度 |
| 后端依赖安装 | 17秒 | Install dependencies，含 pip 升级 |
| SDK 构建工具安装 | 2秒 | setuptools==79.0.1 |
| 首次数据库准备 | 7秒 | 独立 prepare step，包含校验、连接、建库检查、迁移 |
| 重复数据库准备 | 约1.46秒 | acceptance step 命令开始06:46:17.096 → prepared06:46:18.560；包括启动/输出延迟 |
| 手工检查 | 1秒 | Pydantic Schema + SPC engine |
| 后端 acceptance step | 6074秒 | 包含重复准备、SDK wheel、provider preflight、pytest及收据 |
| pytest 子进程 | 6071.36秒 | 既有 receipt.elapsed_seconds；包含启动/收集/执行/报告 |
| pytest 收集 / 执行 / phase 分项 | 未测得 | 既有日志不能准确拆分 |
| pip 下载缓存 | 未配置 | 原 workflow 无 pip cache；日志显示下载，不能声称是热缓存对照 |

历史结果：5240 passed /4 skipped /19 deselected /0 failed /0 errors /0 xfail /0 xpass，10760 warnings。warning 数保留原收据事实，本轮未改依赖或抑制 warning。
所有时间均为本轮读取到的历史记录；没有触发 Actions 或上传本地产物。

## 数据库准备决策

原链路：`prepare_database → manual → make check-backend → check-test-db → prepare_database → SDK wheel → runner verify → pytest → D8 preflight`。
两次 prepare 都调用 `verify_owned_instance → ensure_test_database → verify_owned_database → run_migrations`。第二次即便无待应用迁移，仍启动 Alembic 并连接数据库，不是仅做廉价身份校验。

手工 `app/test_schema.py` 只构造 Pydantic 模型；`app/test_spc_engine.py` 只调用纯计算引擎。它们不读取数据库，因此可在唯一准备前执行。另以支持的 pure network/database guard 实际运行两脚本验证这一点。

现链路：`manual → make check-backend → check-test-db → prepare_database → SDK wheel → runner verify → pytest → D8 preflight`。
仅删除 workflow 的后端独立 prepare step；Makefile、准备实现、runner 的独立实例/数据库重验、provider preflight 及 D8 preflight 均保留。未增加“已准备”环境变量或 Make 绕过入口。
开发者直接运行 `make check-backend` 仍须提供独占实例登记及 TEST_DATABASE_URL，入口负责从空测试库创建并迁移。
浏览器 job 本轮只新增下载缓存，未改变其已有数据库准备次序。

## 单次 pytest 计时

在既有 `tests.ci.gate_results` 插件的 sessionstart 中延迟注册 `GateTiming`，避免前端/summary/scanner 导出工具新增 pytest 运行依赖。

- collection hook wrapper 记录当前这一次收集的 wall time；runtestloop hook wrapper 记录当前这一次执行循环的 wall time。
- 既有 runtest_logreport 读取 pytest report.duration，合计 setup/call/teardown，并输出总 phase 时长排名前20的用例及三阶段分项。
- 参数值从公开 test identity 中移除，同名参数化用例仍保留独立条目（按排名辨识），不聚合或改变执行。
- `OPENQMS_GATE_TIMING {JSON}` 写入既有脱敏 `.log` 并输出控制台；沿用当前 artifact upload。原 receipt 的字段/状态/计数、JUnit 合并与退出处理均不变。私有 hooks 仍由 runner 删除。
- collection 不包含解释器启动和 sessionstart 前的插件/conftest 导入；execution 包含循环内 fixture、测试体、teardown 和钩子开销。phase 总和与 loop wall time口径不同，不能直接相减断言 fixture 空耗。
- 不执行 collect-only、不另起 pytest，不请求第二次全量收集/执行。

## pip 下载缓存

backend-tests 和 browser-protection 的 `actions/setup-python@v5` 使用 `cache: pip`，由 action 按 OS/架构/Python 版本和依赖内容建立键（已核对[官方 v5 pip-cache 实现](https://github.com/actions/setup-python/blob/v5/src/cache-distributions/pip-cache.ts)）。backend key 内容覆盖 `backend/requirements.txt`、SDK `pyproject.toml` 和 workflow（内联 setuptools==79.0.1 工具安装）；browser 覆盖实际安装的 `backend/requirements.txt`。
沿用 pip upgrade、requirements 安装、固定 setuptools 与 wheel 构建版本校验。只缓存 pip 下载目录，不缓存 venv、数据库、资源登记、凭据或测试产物。宽泛的 workflow 哈希会让无关 workflow 编辑也失效，代价是更保守的缓存复用。

## 验证与后续读取

本地使用 macOS / Python3.11 的既有解释器，专用 PG15 随机端口和私有登记；不是 GitHub Ubuntu/Python3.12 的同类 runner。依赖已安装，未把本地安装当 pip 冷/热缓存实验。

已验证：原 CI pure 基线321通过；新增计时测试先4失败（缺 timing）再通过；最终 pure350通过/3既有 Pydantic warnings；pytest成功/测试失败/收集失败退出0/1/2、单次模块收集、参数值隐藏、三个phase分项及日志发布；损坏计时、日志不可写保持原成功/失败门禁，私有文本/bool/负数/NaN/Inf不发布；无实例登记时正常 Make 入口 exit2；手工检查在 pure guard 下通过；actionlint1.7.7（禁用未安装的 shellcheck）和 git diff --check通过。

同一解释器、同一专用PG15、已迁移 head 的重复准备为1.358秒和0.916秒（进程 wall time）。它们只证明可移除的准备开销，不能转化成总 job 节省比例。
最终正常入口从空库执行 `make check-backend`：**5269 passed /4 skipped /19 deselected /6 warnings，0 failed/errors/xfail/xpass，exit0**。既有4项可选skip与19项其他层deselection保留，增加29项CI基础设施回归；测试覆盖未缩减。D8 preflight为CLEAN（0 breaks）/exit0，8个引擎import exit0。

| 本地最终运行指标 | 实测值 | 口径 |
|---|---:|---|
| Make 正常入口 | 4612.65秒 | 含唯一空库准备、wheel/provider预检与pytest |
| pytest 子进程 | 4608.58秒 | 同原receipt.elapsed_seconds口径 |
| collection | 5.63秒 | 当前这一轮collection hook |
| execution | 4574.43秒 | 当前这一轮runtestloop |
| setup累计 | 2927.02秒 | 全部用例report.duration累计 |
| call累计 | 1391.27秒 | 同上 |
| teardown累计 | 253.25秒 | 同上 |
| 独立数据库准备次数 | 1次 | 正常Make日志中prepared仅一次 |
| 本地依赖安装 / 单独空库准备 | 未测得 | 已有venv；未把Make前置混合耗时拆算为DB时间 |
| pip缓存冷/热效果 | 未测得 | 未执行修改后的Actions，不能由本地venv复用推断 |

本轮未实际重跑浏览器、SDK多Python矩阵、live/scanner层；这些工作流/门禁保留，不能把后端exit0等同全部PR检查已通过。

这是macOS27.2.1/arm64、Python3.11.15、pytest9.0.3的**本地未提交代码快照**，不是GitHub Ubuntu同提交前后对照。receipt.frozen_sha中的 `d3c0ada8+local-ci-optimization` 是明确的本地标识，不是实际Git commit。1073个执行相关文件（backend/sdk/scripts/workflows/Makefile）运行前后集合及SHA-256均一致；manifest SHA256为 `f1e7dfee23be245fe3815074ccd6d826e4625c95a8e1c637b995fcdf3a4645c7`。

| 本地慢用例（参数值已隐藏） | setup秒 | call秒 | teardown秒 |
|---|---:|---:|---:|
| test_text_budget_and_response_faults_fail_closed | 3.82 | 16.24 | 1.36 |
| test_interrupted_owner_persisted_state_requires_explicit_rebuild_retry（某参数项） | 10.67 | 9.55 | 0.14 |
| test_other_client_refuses_before_drop | 13.08 | 0.12 | 0.10 |

当前阶段建议：**先优化慢fixture**。setup累计2927.02秒、teardown253.25秒，对比call1391.27秒；tenant rebuild的可见慢用例甚至setup13.08秒而call仅0.12秒。先定位这类fixture中的重复迁移/建租户/seed开销，保持隔离、状态守卫和真实迁移验收，再用同一runner的新PR数据复核。尚无证据支持跳过fixture或直接提升共享scope；两个独立PostgreSQL job留待此后评估，本轮未实现。

成功日志同时包含CI烟测中嵌套子进程的计时文本；当前完整suite的权威记录是父runner控制台的一条 `OPENQMS_GATE_TIMING`，或过滤log最后追加的同一条，不能把嵌套样本计时当整套数据。

本轮专用PG15验收后仅剩postgres/qms_test、其他客户端0；容器ID/owner/image和匿名卷唯一消费者核对后，已精确删除该容器/卷并移除0600凭据文件。日志、manifest、脱敏收据保留在本机 `/tmp/openqms-ci-baseline-local/`；中断产物独立归档，不当作通过。未清理其他工作区或历史资源。源工作区与PR #33未修改，CI分支保持本地未提交，未push/merge。更多进度见 [PROGRESS.md](../../PROGRESS.md)。

下次 PR 同类 runner 需读取：commit及实际merge SHA、runner image/Python/pytest版本、job总时长、setup-python缓存命中和恢复/保存耗时（明确冷/热）、两项pip安装、唯一准备（以make日志边界）、wheel/provider preflight、receipt.elapsed_seconds、OPENQMS_GATE_TIMING收集/执行/phase总和/top20及D8 preflight；同时核对selected/passed/skip/deselected与退出码。冷/热运行必须在同一执行提交上比较，不能用不同测试数量或不同runner的变化算收益。

以上保护规则、runner状态和Actions基线均为本轮读取时的快照；本地事件匹配已验证，优化后的远端运行/缓存收益/强制合并阻断未冒称实测。


## 后续送审授权与调查边界

用户在本地验收结束后授权将本批提交、推送并单独开PR；前文“本轮未push/未提交”是初轮验收快照，发布状态以PROGRESS后续条目为准。送审前再次核对main仍为d3c0ada8，main生效rules为空，ruleset17638580没有required checks，可见self-hosted runner总数仍为0；未改管理设置。

setup占当前本地execution约64%，这是阶段分配而不是预计节省比例，也不能归因到某个具体fixture。下一批先按耗时测试组度量fixture调用次数、单次与累计成本，再选累计最高项做对照；验收既看整组耗时，也核验数据库状态隔离与顺序独立性。本批PR不包含这些实现，可与R6 Task1并行；R6只以开工时实际合入的CI入口/提交为依据。

发布记录：代码提交 `0998be8b` 已push并创建非草稿 [PR #36](https://github.com/Open-Industry-System/OpenQMS/pull/36)。创建PR的完整head查询只有 Test OpenQMS run43725914972（pull_request），无push运行；远端尚未完成，缓存/阶段耗时以实际日志后续核对，不使用本地数据代填。
