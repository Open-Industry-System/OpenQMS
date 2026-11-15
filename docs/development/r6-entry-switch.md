# R6 入口切换实施与验收台账

2026-11-15。产品合同见 [R6 规格](../superpowers/specs/2026-11-15-r6-d4-d5-entry-switch-design.md)，执行步骤见 [R6 计划](../superpowers/plans/2026-11-15-r6-d4-d5-entry-switch.md)。用户已授权执行 Tasks 1–11；本文件只记录真实状态，不授权推送、合并或部署，不改 CI 优化。

## 当前状态

- 实施起点 `codex/r6-entry-switch-design@f03fc01b0ef9a30a85da1917c8fa8ed81fcaa9f9`，开工工作区干净。R5 PR #33 实读仍 open/draft、未合并，head `75fcc51765bd3b6b739695178a399bfa01806574`，main `d3c0ada8f57c9c8831709117c7c95cbf2d925d66`，未发生影响计划的基线变化。
- 解释器 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`，setuptools `79.0.1`。前端在本 worktree 和冻结基线各自按 lockfile `npm ci`，不复制依赖。离线 npm 因缺缓存失败，随后联网按锁安装成功；不改 package lock 或运行代码。
- Task 1 数据合同实现、223 项专项验证及独立 SPEC/QUALITY 复审已通过；完整冻结基线仍运行，浏览器基线待其结束后串行执行。Task 2 开始；尚未签收整体或切换资格。

## 独占测试资源

两套全新 PG15 实例均有 `openqms.owner` 标签与完整容器 ID 校验，回环随机端口；与用户业务库、原 R5/云端试用资源无关。登记/包装器/日志在 owner-only 私有目录，凭据不进入本文件或 Git。

| 用途 | Owner / 容器 | 卷 / 端口 / 私有目录 |
|---|---|---|
| 冻结 `f03fc01b` 的完整基线 | `2b9d0cabd361650034f2422b` / `807b2271b47a19d87f0092dd8245e5abe566b7bef3f4eaab891bb7da4a518b60` | `openqms-r6-2b9d0cabd361650034f2422b-data` / 57322 / `/private/tmp/openqms-r6-0251m41h` |
| 实施与逐批迁移/服务测试 | `607e0a5f9862952b7172c2d2` / `f120ec27258baaacedd460622f589eaaa2c512bca9994feb6ee834778dbee9ec` | `openqms-r6-607e0a5f9862952b7172c2d2-data` / 58064 / `/private/tmp/openqms-r6-ky7vrez_` |

各实例内的数据库验收串行；完整基线从冻结导出与独立本地 Git 元数据执行，防止在实施中动态收集到新测试。SDK 的实际源码身份检查仍保留，不通过修改门禁或伪造 SHA 适配导出。

## 基线证据

| 执行 | 真实结果 | 范围与限制 |
|---|---|---|
| 两套 `prepare_database` | exit0，public 迁移到 `20261115_r5_responses` | 仅新建的专属 `*_test` 数据库；不是业务数据迁移 |
| 初次冻结 `make check` | exit2，SDK 源码身份前置失败 | 导出缺少 Git 元数据，未执行业务测试；失败日志 `run-1794751390511832000.log` 保留 |
| 补独立本地 Git 元数据后冻结 `make check` | 运行中 | `run-1794751467174793000.log`；SDK unit/loopback/wheel 三层已 PASS，后端未完成 |
| 私有包装器首次直接脚本启动专项 | exit1，找不到 tests 模块 | 包装器改为 `-m tests.e2e.capa_outcome_runner` 后原样重跑；不是特性 RED，未改仓库 CI |
| 冻结源码专项：R5 d5/responses 迁移＋d5_staff_actions | **48 passed /0 failed /0 errors /0 skipped /4 warnings；exit0；143.53s** | `run-1794751501192097000.log`，receipt `api-20261115T140501751437-receipt.json`；只证明 Task 1 相关基线，不替代完整 make/browser |

## 后续签收规则

按任务记录 RED、GREEN、原始失败、精确源码与独立规格/质量复审。完整来源在候选/兼容双版本通过、正式更正可用、旧实例和已准入事务排空、C9/C10 与最终清单齐全之前，不签署可切换。演练输入仅适用于绑定的独占合成环境；正式放行仍需独立授权，不能用此台账或用户“执行全部 tasks”代替生产发布许可。

## Task 1 数据合同验证与复审

- 有效 RED：配对迁移/前驱缺失、严格请求 Schema 缺失；`run-1794751716478215000.log`、`run-1794751731643643000.log`。首次 FileNotFound 诊断不计作特性 RED。
- 首轮迁移 23 passed /1 failed：旧数据夹具漏填 status，准备阶段失败，未走到同构判断；修正夹具后继续，未放宽数据库约束。直接 fixture 测试会话绑定问题也单独保留失败记录，现已显式绑定普通/tenant 会话到 owner 测试目标。
- 根因前驱遗漏和完整正文 16KiB 上限曾以真实 RED 捕获，已增加完整根因超长往返与继承回归；不把投影/命令大小约束当完整正式历史存储上限。
- 第一轮新合同＋正常登录夹具 **46 passed /0 failed /0 skipped /4 warnings，136.34s**（`run-1794752841569649000.log`）。之后补强的用例不冒充已包含在这轮。
- 历史迁移/current-head/同构及补强用例 **202 passed /0 failed /0 skipped /4 warnings，495.76s**（`run-1794753017161681000.log`）。只调整当前 head 断言；历史 R5 协议和数据保持固定。
- 独立规格复审第一轮 **未通过**：晚插旧根因历史绕过后继来源集合；D2/D3 完整快照误限 16KiB。修正后增加独立提交的逆序历史、双连接真实锁等待及超长快照往返，独立 SPEC 复审通过，随后独立 QUALITY 复审通过。
- 用户已明确确认后续真实 OpenAI 验收复用 R5 专用部署及凭据；只核对其已登记的 owner-only 配置引用存在，不输出密钥，不把它复制到普通测试配置。

- 最终当前源码专项 **223 passed /0 failed /0 errors /0 skipped /4 既有 warnings；exit0；618.02s**，`run-1794754150890729000.log`：包含全部 54 个新 R6 合同/夹具用例、FK 实际列与目标比对，以及 R5 员工采纳/可见性/消费者/审核材料与 D4 历史回归。原始采纳文本不可覆写，旧审核材料失效用例仍走合法业务写入。`git diff --check` 通过。此前 202 项结果发生在复审修正前，不替代此最终结果。
- 配对 head 为 public `20261115_r6_entry_contracts`、tenant `tv015_r6_entry_contracts`，前驱分别为 `20261115_r5_responses`、`tv014_r5_responses`。新持久化表仍未接通候选生成等业务入口；后续任务继续按计划实施。
