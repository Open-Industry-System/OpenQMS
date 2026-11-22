# Runtime 慢测试准备优化（2026-11-19）

原 165 个场景全部保留并通过，同机本组 runner 耗时 **959.32 → 481.29 秒**，一次 A / B 实测减少 49.83%。主要变化是复用冻结租户准备、逐项克隆独立数据库，以及减少服务夹具的重复 TCP listener。生产代码、原 E2E harness 和原测试函数体均未修改。

## 范围与隔离

- 原始源码：`origin/main` 的 `051d4b06`，冻结在本机私有 `baseline-source` 目录。正式 A 从该快照执行；首轮共享工作树样本已主动中断，保留为中断记录，不计作结果。
- `test_d5_commands.py` 原 50 项，其中 48 项需要数据库，2 项是输入模型和能力目录合同；其他三模块分别为恢复重启 39 项、文本交付 41 项、停止围栏 35 项。原 165 个逻辑场景全部保留。
- 按实际准备次数，162 项使用 runtime 数据库 fixture；另 3 项无需数据库，其中 2 项在本次迁出，原文本交付模块的纯 JSON 编码预算测试仍在原处。文件标记和实际准备次数分别计量。
- `test_d5_command_contracts.py` 承接两项原测试，可通过 `scripts/check-ci-pure.py` 在禁网络、禁数据库环境执行。普通后端测试仍执行这两项。
- 仅在服务测试中用正常迁移及 `provision_new()` 准备一个租户模板；关闭其新连接后，每项用 PostgreSQL `CREATE DATABASE ... TEMPLATE` 创建独立随机数据库。模板复用的是迁移与基础种子，用户、报告、插件、来源证明、授权和任务仍在各自数据库内准备。
- 每项仍调用原 `owned_local_trial` / D4 harness。准备阶段把建租户替换为读取该项数据库内的已准备租户，并把 schema 与 registry 同事务改为新随机 slug 对应的规范名称。测试开始前恢复真实 `provision_new()`；同 UUID、不同真实租户的隔离用例仍实际建第二租户。
- 服务夹具的员工 / 管理员客户端使用原有 ASGI transport，D5 的 API 合同用例也通过真实应用的 ASGI 路由执行；省去一个 TCP listener。专门的 runtime TCP listener、两个 worker 子进程链、访问日志和真实事务竞争仍保留；正式 E2E harness 不变。

## 断言保留

AST 对照确认原四模块的 66 个函数体逐字义保留，344 条 `assert` 全部保留，其中 5 条随两项纯合同测试迁移。这里只改变 fixture 的选择和层次，没有删减参数组合。

| 保护内容 | 保留的实际验证 |
| --- | --- |
| D5 重复保存、并发保存与替换 | `atomic_save_and_lost_response_retry`、`concurrent_replay_serializes_on_task`、`concurrent_independent_commands_have_unique_order`、替换与旧消息绑定场景 |
| D5 撤权竞争及锁后重验 | `revocation_while_waiting_installation_lock_is_current`、`replacement_grant_revoked_during_capa_lock_wait_is_rechecked` |
| D5 回滚及已交付依据 | `precommit_failure_rolls_back_proposal_command_and_audit`、receipt 关系及 HMAC 参数矩阵 |
| 重启、旧请求及消息围栏 | 两次重启后的旧控制重放、未确认 START 复用、并发 restart、损坏关联、写入故障回滚、最终权限重验全部原组合 |
| 文本交付与撤权竞争 | 来源 / 证明 / 最终权限变更矩阵、真实写者等待提交、锁序、租户维护 generation 与跨租户同报告 UUID |
| 真实进程及 HTTP | `restart_fixed_receiver_reads_new_fact_and_creates_fresh_receipt`、`real_worker_and_server_error_hide_synthetic_body_and_exception`；真实 TCP 状态、receipt、日志和旧 token 断言 |
| stop / replay 围栏 | 20 项最终撤权组合、5 项冲突重试、工厂新增锁、业务写者锁序、撤 FMEA / grant / plugin 后仍可停止 |

新增 `test_d4_fixture_isolation.py` 的 1 项回归单独计数：真实提交用户禁用与报告污染，向打开的 fixture 注入异常，再创建下一项 fixture 验证状态干净，最后查询控制库确认两项随机数据库均已删除。

## 计量口径

A / B 使用同一绝对路径 Python 3.11 venv、相同诊断口径和冻结主线 runner；B 只把 runner 的执行目录指向候选源码。两侧均新建同镜像 PostgreSQL 15 容器和独立卷，先完成登记及正常 public prepare，然后串行执行相同 165 个逻辑场景；迁出的 2 项纯测试包含在 B 的该组耗时中。新增隔离回归单独运行，不计入提速比较。

私有诊断记录 `provision_new`、tenant migration / seed / parity、fixture、TCP startup、worker startup 和数据库创建 / 克隆的次数与耗时；原 runner 保留逐模块 setup / call / teardown 和真实成功 / 失败收据。B 另增加模板 public 迁移的计数器；A 没有该入口，实际为 0。嵌套耗时不可相加当作总耗时。初次数据库准备单独记录，不混入 pytest 子进程耗时。

Python 物理行数口径为四个原测试文件、整个 runtime `conftest.py` 以及本次所有新增 / 迁入 Python 文件：**2902 → 3092（+190）**，其中新增隔离回归 52 行。既有未修改 harness 不计入两侧。该改动减少重复准备，Python 总行数增加。

## 实际结果

| 相同 165 个逻辑场景 | A：冻结主线 | B：最终候选 |
| --- | ---: | ---: |
| selected / passed | 165 / 165 | 165 / 165 |
| failed / error / skipped / deselected | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| runner 秒 | 959.320 | 481.290 |
| setup 秒 | 769.117 | 328.182 |
| call 秒 | 102.903 | 97.159 |
| teardown 秒 | 76.096 | 46.697 |
| 初始主库准备＋runner 秒 | 962.014 | 483.778 |

两侧均为 6 项既有 warnings。原逻辑集合按两项迁出路径归一化后完全一致，165 个参数化节点均唯一；集合摘要为 `49e3a37c06d5cbbc87a1f50d399e0ad6368167f7ea5b56778d2cc69592f49a96`。B 的源码身份由本地 8 文件 SHA256 manifest 记录，收据未绑定远端提交。

下表为 pytest 子进程内的实际调用次数 / 累计秒。初始主库 public Alembic 两侧各 1 次，耗时 2.471 / 2.298 秒，另外统计；B 的模板 public 迁移使全部 public 迁移进程次数从 1 增为 2。tenant 计数是迁移入口调用次数，不是 revision 数量。

| 准备或启动 | A：次数 / 秒 | B：次数 / 秒 |
| --- | ---: | ---: |
| 新建模板数据库 | 0 / 0 | 1 / 0.021 |
| 每项独立数据库克隆 | 0 / 0 | 162 / 10.450 |
| 模板 public 迁移 | 0 / 0 | 1 / 2.230 |
| tenant provision | 163 / 323.624 | 2 / 3.939 |
| tenant migration | 163 / 225.759 | 2 / 2.742 |
| tenant parity | 163 / 35.192 | 2 / 0.387 |
| tenant seed | 163 / 34.012 | 2 / 0.465 |
| 独立租户业务 fixture setup | 162 / 638.415 | 162 / 199.357 |
| D4 来源 / 授权 fixture setup | 161 / 103.225 | 161 / 98.257 |
| command fixture setup | 48 / 25.906 | 48 / 24.573 |
| TCP listener startup 方法 | 274 / 0.018 | 113 / 0.004 |
| worker subprocess 创建 | 2 / 0.022 | 2 / 0.025 |

B 的两次真实 tenant provision 是模板准备 1 次、同 UUID 跨租户测试建第二租户 1 次。B 的模板初始化整体耗时 4.376 秒，已计入本组 setup；上表各阶段存在嵌套，不能相加。TCP 方法计时不含等待启动和关闭 listener 的完整生命周期，worker 创建计时不含后续执行。

| 原模块（D5 含迁出两项） | A：setup / call / teardown 秒 | B：setup / call / teardown 秒 | 总 phase B / A |
| --- | --- | --- | ---: |
| D5 commands | 247.169 / 8.787 / 15.504 | 115.217 / 8.174 / 7.345 | 0.4816 |
| D4 recovery restart | 179.175 / 37.640 / 21.242 | 73.776 / 34.909 / 13.594 | 0.5137 |
| D4 text delivery | 183.122 / 30.327 / 21.280 | 73.915 / 29.687 / 13.478 | 0.4988 |
| D4 stop final fence | 159.650 / 26.148 / 18.070 | 65.274 / 24.389 / 12.280 | 0.5000 |

新增隔离回归另跑 **1 passed / 0 skipped / exit 0，runner 11.45 秒**，setup / call / teardown 为 4.331 / 3.822 / 0.028 秒，包含独立模板初始化。禁网络 / 禁数据库的两项纯合同为 **2 passed**。维护 generation、跨租户同 UUID 和新增隔离回归的聚焦组为 **3 passed**。

初轮 B 曾为 164 passed / 1 failed：只适配 slug 时违反维护入口要求的规范 schema 关系。修复采用真实 `ALTER SCHEMA` 与 registry 原子更新，保留原维护 guard；该失败样本未用于性能比较。新增隔离回归的首次聚焦运行因在读事务内触发清理而中断，调整为先关闭独立 session，再注入异常；中断样本保留。

这是同机、同镜像的一次完整 A / B，宿主负载未独占；仅代表本组实测，完整 CI 与双分片耗时另行验证。

## 复现

先使用项目登记的独占测试实例运行正常数据库准备，再通过 `backend/tests/e2e/capa_outcome_runner.py` 的 `api` 层重复指定以下目标。以下列出仓库路径；runner 的 `--pytest-target` 参数使用去掉 `backend/` 前缀的路径：

```text
backend/tests/services/agent_runtime/test_d5_commands.py
backend/tests/services/agent_runtime/test_d4_recovery_restart.py
backend/tests/services/agent_runtime/test_d4_text_delivery.py
backend/tests/services/agent_runtime/test_d4_stop_final_fence.py
backend/tests/services/agent_runtime/test_d5_command_contracts.py
```

新增隔离回归用相同 runner 单独选 `backend/tests/services/agent_runtime/test_d4_fixture_isolation.py`。纯合同从仓库根运行：

```sh
python scripts/check-ci-pure.py "$PWD/backend/tests/services/agent_runtime/test_d5_command_contracts.py" -q
```

本轮私有快照、源码指纹、AST 对照、环境登记、计时和收据位于 `/private/tmp/openqms-ci-three-step-evidence/`；不把凭据或原始环境文件纳入仓库。
