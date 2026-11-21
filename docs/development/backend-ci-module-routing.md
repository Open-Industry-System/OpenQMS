# 后端 CI 按模块运行

本轮基线是远端 main 的 `48f87156b0362900913d7c1fba9071108487b6d5`。候选保存在独立 worktree 的 `codex/backend-ci-module-routing`，基线另有只读对照 worktree。历史 [Actions 44445156751](https://github.com/Open-Industry-System/OpenQMS/actions/runs/44445156751) 和 `/private/tmp/openqms-backend-ci-398-files.csv` 用来定位热点。四个最慢文件的准备优化已在 `943bec27` 做过，当前 main 尚无这批改动，本轮移植并重测。main 已包含 #37 的通用模板支持、#39 的测试精简和 #41 的 CAPA 文档门禁精简。

PR #52 接入从 `e98e9c8c` 开始。该基线已合入 #50 的四慢文件模板、完整后端双分片和展示快路径，因此集成保留这些既有行为。以下 11 月 21 日耗时及行数是上述旧基线的受控本地工程对照。集成请求另有聚焦验证，远端双分片等待与累计耗时仍需从当前 Actions 读取。

## 测试变更与覆盖

| 原测试或范围 | 本轮变更及继续保护的用例 |
| --- | --- |
| `test_context_var_default_is_none` | 删除。由 `test_context_var_set_and_reset` 验证初始和恢复后的值均为 `None`。`test_cross_tenant_jwt_rejection` 保留。 |
| checkpoint 的 `test_recovery_validation_is_locally_redacted` | 六个 POST 参数节点合为 `test_recovery_post_validation_is_locally_redacted`。`invalid-task`、`invalid-run`、`invalid-epoch`、`boolean-epoch`、`extra-field`、`invalid-body` 仍各发送真实 TCP 请求，各自断言 422、固定错误正文和脱敏，输出带输入标签。`invalid-checkpoint` 迁为独立的 `test_recovery_get_validation_is_locally_redacted`。真实日志和状态变化仍为独立节点。 |
| `test_d5_commands.py` 和 `test_d4_text_delivery.py` 中的纯合同 | 两个 D5 纯校验、一个 D4 JSON 编码后字节上限，按原名称分别移到 `test_d5_command_contracts.py` 和 `test_d4_text_delivery_contracts.py`。真实保存、交付及超限不写入留在原组。 |
| `test_output_dtos_bound_typed_content_and_forbid_asserted_identity` 与 `test_strict_checkpoint_history_restart_contracts` | 同名迁到 `test_readonly_contracts.py`，用禁用数据库和网络入口运行。原场景也未申请数据库 fixture，此项迁移的数据库准备节省为零。真实 API、写入、交付、权限、事务时序和回滚另测。 |
| 只读及 hybrid 重复断言 | 删除紧随访问前的 `hasattr`、已由真实 D5 扩展调用证明的非空检查。ActivityQuery 的实例化继续证明类存在，并校验有效值和非法输入。 |
| D4/D5 四慢文件及 checkpoint API | 一次真实建库、公共迁移和标准租户种子制成只读模板。每个需要租户的测试克隆独立数据库。仍启动实际 TCP 服务和真实进程的测试保留，包括停止控制 5 种操作 × 4 种撤权、锁等待、幂等重放、来源权限、跨租户和事务回滚。新增真实提交污染和异常回收隔离回归。 |
| `test_d4_recovery_delta.py` 和 `test_r5_d5_delta.py` | 共用准备与断言函数，D4、R5 各自 4 条空库或旧版本到目标的 public/tenant 路径分别建库和升级。R5 七项实时约束负例共用专用数据库、一次迁移和一次已提交的 seed，每项独立连接和 savepoint，各自回滚。延迟外键在 seed 提交时照常校验。 |
| 其余历史热点 | 审阅历史前 60 个模块的相同函数体与覆盖。不同入口、错误原因、权限或事务时序的测试保留。 |

## PR 和 main

保留工作流 `Test OpenQMS` 及 `backend-tests` 汇总。main push 始终通过两个独占 PostgreSQL 分片运行完整 API 套件，原 marker、ignore、手工检查、D8 预检、SDK、浏览器、前端、Oracle、文档和专用原生门禁继续走原入口。普通 PR 由可信 base 解析完整 Git diff，覆盖删除及重命名的两端。合入新可信分类器后，匹配的 PR 获得按组执行。任何公共基础文件、CI 规则、环境依赖或影响未知的路径都转入完整套件。

无预览的纯文档及受限展示 PR 继续走原有快路径。预览已开启时，这些 PR 只执行基础组来产生同 SHA 的实际 API 收据。Oracle 仍验证唯一的 API 收据、运行 SHA、非零通过数和完整结果计数。其现有产物名称和必需检查来源不变。

| 组 | 执行范围与触发路径 |
| --- | --- |
| 基础 | 每个代码 PR 都跑。登录成功及失败、数据库 schema 隔离、两个真实租户之间的 TCP 拒绝、CAPA HTTP 写入和真实回滚。 |
| 接收器与 SDK | SDK、启动器、协议、令牌、交付与恢复。跑真实 SDK/接收器进程和相关命令行测试。 |
| Agent 运行时 | 任务、消息、运行控制、授权、结果读取与共用事务。关联接收器及 CAPA 依赖。 |
| CAPA D4/D5 | CAPA/8D、FMEA 与 IQC/SCAR 来源、可见性、员工操作、投影与审计。保留相关 D4/D5 的真实锁和撤权矩阵。 |
| 租户与迁移 | public/tenant Alembic 路径和租户生命周期。已知领域模型与 D4/R5 迁移带上相应业务覆盖。共享模型或未知迁移、共用数据库会话、租户维护与准备脚本、PG 镜像触发全量。 |
| 业务模块 | 显式映射 IQC/SCAR、FMEA、MSA、SPC、APQP、PPAP、控制计划和 ERP/MES/PLM。FMEA 与 IQC/SCAR 来源带上 CAPA，FMEA 协作、特性及权限带上控制计划与集成，CAPA 文档门禁带上控制计划，MES 写入带上 CAPA 和 SPC。 |

`backend-tests` 校验路由成功、选定 worker 成功、所选组与实际完成组相同。组失败、取消、漏跑或缺少收据均不满足门禁。文档跳过需有明确的文档路由、实际 skipped 状态和空执行结果。

## 验证记录

独占 PostgreSQL 15.18 容器，各样本以随机端口和空测试库开始。 本地回执的 Git HEAD 均为上述基线，候选未提交。冻结的受检源码指纹分别为基线 `a9707a0f1dfecfd4bd6484716bfbad54db1b4538c2c5323b81ffd034977e9219` 和候选 `38b6b81e0c38cb80aeb12d7e3d24fbb64bc515e177367f1a1d4d1f7db4e01b94`。使用同一台 macOS arm64、同一 Python 3.11.15 venv 和相同本地镜像。依赖预装、正常运行每次重建 SDK wheel。操作系统和 Docker 缓存未清空。每个后端样本是一个 pytest 进程，部分独占数据库的样本在宿主上重叠。按实际样本记录墙钟，并列出 pytest setup、call、teardown 的累计秒数。墙钟不包含 GitHub runner 排队、依赖安装、前端、浏览器及预览。

代表性 diff 是 `M backend/app/services/grr_service.py`。两种策略都读同一个 NUL 分隔的 diff。基线路由与 main 全量运行相同命令，因此两行共用一份基线执行样本。变更路径用于验证 CI 选组，测试执行时使用相同的 GRR 业务源码。

```sh
make check-backend PYTHON_BIN=/path/to/venv/bin/python SDK_PYTHON_BIN=/path/to/venv/bin/python
BACKEND_GROUPS=basic,msa make check-backend PYTHON_BIN=/path/to/venv/bin/python SDK_PYTHON_BIN=/path/to/venv/bin/python
```

私有收据、计时、数据库统计、收集差异、环境与复跑脚本保存在 `/private/tmp/openqms-backend-ci-module-evidence/`。基线与候选本地数据见下表。GitHub Actions 候选未运行。


| 物理行计数范围 | 基线 | 候选 | 变化 |
| --- | ---: | ---: | ---: |
| `backend/tests/**/*.py` 业务测试、fixture 和 helper（排除下列 CI 辅助范围） | 103,554 | 103,801 | +247 |
| `backend/tests/ci/**/*.py` 和执行器 `backend/tests/e2e/capa_outcome_runner.py` | 5,274 | 5,716 | +442 |
| `scripts/ci/**/*.py` 分类脚本 | 94 | 209 | +115 |
| `.github/workflows/test.yml` | 501 | 532 | +31 |
| `Makefile` | 222 | 223 | +1 |

固定范围以 Git 跟踪及本次新增文件为准。主线 API 收集 5,709 项，候选 5,763 项，两侧都排除 89 项专用门禁用例。业务部分净减 5 项（POST 合并 −5、默认值重复 −1、隔离回归 +1，纯合同迁移净零）。CI 路由和门禁覆盖净增 59 项，原场景映射到新的组参数。全节点差异见 `collection-diff.json`，D4/D5 原函数体和断言迁移核对见 `runtime-assertion-audit.json`。

分类和 worker 门禁本地回归覆盖文档、单模块、跨模块、共享基础、未知路径、改名、删除、main push 及失败、取消、缺结果。最终路由联合收集 317 个文件和 4,442 个 API 节点，预期与实际身份逐项相同。独立数据库上的 D4/R5 迁移及克隆隔离专项 33 项通过。Oracle 现有兼容测试 92 项通过，另用 MSA 样本真实 API 收据验证发布消费函数。 快照再生用例使用两侧独占容器内的 PG15 工具补跑，各 1 项通过且无跳过。补跑另有收据，保留原全量的跳过与计时。

| 已完成本地样本 | 选中 / 通过 / 跳过 | 含前置墙钟（秒） | pytest（秒） | setup / call / teardown（秒） |
| --- | ---: | ---: | ---: | ---: |
| 同一慢场景组，基线 | 186 / 186 / 0 | 1,548.02 | 1,543.61 | 1,258.95 / 175.61 / 93.83 |
| 同一慢场景组，候选 | 181 / 181 / 0 | 777.07 | 769.04 | 505.09 / 180.56 / 68.96 |
| MSA PR 后端，基线（执行同一全量） | 5,709 / 5,704 / 5 | 5,450.07 | 5,443.33 | 3,649.92 / 1,457.24 / 295.31 |
| MSA PR 后端，候选 | 12 / 12 / 0 | 51.91 | 35.92 | 17.86 / 10.54 / 1.73 |
| 完整后端，基线 | 5,709 / 5,704 / 5 | 5,450.07 | 5,443.33 | 3,649.92 / 1,457.24 / 295.31 |
| 完整后端，候选 | 5,763 / 5,758 / 5 | 4,605.88 | 4,594.57 | 2,820.18 / 1,484.48 / 251.00 |

两侧全量均退出 0，手工 schema/SPC、D8、引擎导入通过，候选额外通过选组收据校验。独立收集和实际执行记录逐节点哈希一致，见 `full-run-selection-verification.json`。两侧全量各 5 项常规环境跳过，分别为本机未提供 PG15 工具的一项、Redis 未启用的一项、未开启 E2E_MODE 的三项。PG15 工具另补跑通过。

每个样本只有一个后端 worker，同一样本的后端 worker 累计秒数即该样本的墙钟。本地并行跑的是独占库的不同对照样本。上表不相加作为 PR 等待，也未测整个 GitHub Actions 工作流的并行 job 累计耗时或用户等待。工作流的其他必需 job 也可能决定远端等待。

| 已完成本地样本 | 新建空库 | 模板克隆 | 租户初始化 | 公共 / 租户真实迁移准备 | 标准租户 seed |
| --- | ---: | ---: | ---: | ---: | ---: |
| 同一慢场景组，基线 | 1 | 0 | 185 | 1 / 185 | 185 |
| 同一慢场景组，候选 | 2 | 178 | 3 | 2 / 3 | 3 |
| MSA PR 后端，候选 | 2 | 1 | 2 | 2 / 2 | 2 |
| R5 D5 迁移文件，基线 | 17 | 0 | 3 | 17 / 3 | 3 |
| R5 D5 迁移文件，候选 | 11 | 0 | 3 | 11 / 3 | 3 |

慢组墙钟纳入一次公共库准备，范围为四个慢文件、checkpoint API 及候选迁出的三个纯合同节点。共享模板是第二个空库，独立跨租户用例仍真实准备第二个租户。建库、克隆、租户 schema 和新建迁移版本表来自 PostgreSQL DDL 日志，标准租户 seed 以成功的租户准备路径计数，逐用例的业务数据准备仍保留。迁移专项中 R5 七项实时约束使用同一空库、同一真实公共迁移及同一 proposal seed。 R5 文件独立 A/B 两侧均 17 项通过，收集 SHA 相同。墙钟 43.79 → 33.81 秒。七个约束场景的建库、初次公共迁移和 proposal seed 各从 7 次降为 1 次，实际测试各自回滚。表中的 seed 列记标准租户 seed。 两个全量样本的 Docker local 日志均发生轮转，保留日志从运行中途开始，不能据此报告全量建库、迁移或 seed 总数。上表只列完整捕获的样本准备计数。两侧分别用相同的真实 SQL 约束检查。

专项复跑可用私有证据目录的 `bench.py`。脚本用一个新的样本名创建独占 PostgreSQL。慢组复用当前相同版本的 Python，按下列顺序选择基线目标，候选另加两个迁出的合同文件。

```sh
PYTHON=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
EVIDENCE=/private/tmp/openqms-backend-ci-module-evidence
BASE=/private/tmp/openqms-backend-ci-module-baseline
CANDIDATE=/private/tmp/openqms-backend-ci-module-routing
set -- tests/services/agent_runtime/test_d5_commands.py \
  tests/services/agent_runtime/test_d4_recovery_restart.py \
  tests/services/agent_runtime/test_d4_text_delivery.py \
  tests/services/agent_runtime/test_d4_stop_final_fence.py \
  tests/api/test_d4_recovery_checkpoint.py
"$PYTHON" "$EVIDENCE/bench.py" baseline-slow-repeat "$BASE" slow "$@"
"$PYTHON" "$EVIDENCE/bench.py" candidate-slow-repeat "$CANDIDATE" slow "$@" \
  tests/services/agent_runtime/test_d4_text_delivery_contracts.py \
  tests/services/agent_runtime/test_d5_command_contracts.py
"$PYTHON" "$EVIDENCE/bench.py" baseline-full-repeat "$BASE" full
"$PYTHON" "$EVIDENCE/bench.py" candidate-full-repeat "$CANDIDATE" full
"$PYTHON" "$EVIDENCE/bench.py" candidate-msa-repeat "$CANDIDATE" module basic,msa
```
