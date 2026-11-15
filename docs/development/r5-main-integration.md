# R5 与当前主线集成及草稿 PR

2026-11-15。用户授权核对最新主线、推送 R5 功能分支并创建草稿 PR；不授权合并 PR、部署或生产启用。

## 合并基线与迁移

R5 原完成提交 `73ad865c`，共同前驱 `78b428d2`；本轮合并提交 `dcd9812ec5040bca86c7af82de28ecacf3848cc9` 已推送，草稿 [PR #33](https://github.com/Open-Industry-System/OpenQMS/pull/33) 指向 main，未合并。本轮实际 fetch 的 `origin/main` 为 `dae0892f3be6f15ea297bd0d2659308029cd4d23`，包含 R4b PR #30、Oracle PR #31、refresh-session 认证及同期部署保护。保留主线认证实现、生产/预览工作流与 Oracle 自动化检查，同时保留 R5 原生检查 job。

不改写已发布迁移。新增两个只合并历史的空 DDL revision：

| 链 | 单一新 head | 保留的两个父 revision |
|---|---|---|
| public | `20261115_r5_main_merge` | `20261114_r5_models`、`20261114_production_merge` |
| tenant | `tv013_r5_main_merge` | `tv012_r5_models`、`tv010_refresh_sessions` |

租户迁移器识别 R5 head 和 refresh-session head，升级前按对应已审查前驱做严格同构比较。只从 public 参考侧排除该前驱尚未拥有的表/函数，tenant 侧不隐藏任何多余或部分对象；R5 前驱已有的 immutable 函数继续参与比较。历史配对测试固定其历史 public/tenant revision；当前 head 断言更新到合并 revision，保留原分支身份和回滚断言。

逐文件比对：109 个主线独有文件中108个与主线字节一致，另一个仅调整 refresh-session 迁移测试的当前 head 断言，同时仍核对原 production merge 的两个父 revision。两侧已发布迁移文件逐项无变化。主线与 R5 的 PROGRESS 条目均保留。

## 当前验证与实际失败

- 新增合并纯测试初次 **4 failed**：两个链各有两个 head、两种分支前驱未获支持。新增合并节点及严格前驱处理后 **4 passed**。
- 登记 R5 独占数据库 prepare 成功升至新 public head；新合并路径、两种 tenant 前驱及原 read-task 回归共 **32 passed /4 warnings /35.80s**，`run-1794709262831049000.log`。包含真实非空 D5 建议/refresh-session 保留、重复 public upgrade、tenant 完整同构及部分结构拒绝。
- 纯 CI＋图合同＋read-task 纯合同 **297 passed /3 warnings /23.79s**。一次误将混合文件放入纯 lane 导致 **304 passed /9 setup errors**，均被 `pure_test_database_forbidden` 拒绝；随后正确分层，无数据库绕过。
- 前端初次全量 **882 passed /34 failed**：33项 CAPA 页面旧测试遗漏 D5 API 隔离，真实客户端按主线新规则同步了不一致的假身份；另1项 PFMEA 五秒超时。最小单项先复现失败，补齐页面套件 D5 API fixture 后，CAPA详情、真实认证组合、D5面板及 PFMEA **100 passed /5 files /9.84s**。未改应用认证逻辑或超时/权限断言。随后全量前端复跑 **916 passed /101 files /42.02s /exit0**（`main-integration-frontend-final.log`）；前端与E2E TypeScript及构建exit0（build7.43s）。
- 首次直接 pytest 因未指定测试库被种子库保护拒绝；一次纯入口参数误带 `backend/` 前缀导致未找到文件。均未执行数据库测试，不计为通过。
- 完整迁移、refresh-session、user-service 与 read-task DB回归 **307 passed /1 skipped /4 warnings /627.45s /exit0**（`run-1794709340449920000.log`）。唯一skip为本地没有指定PG15工具；随后显式指定同一登记容器，snapshot再生成 **1 passed /4 warnings /9.70s /exit0**（`run-1794710021807410000.log`），保留原skip，不改写整轮统计。
- 当前合并版本本地Darwin确定性原生API＋新检查点浏览器 **59 passed /0 skip /6 warnings /382.95s**（`run-1794710124877996000.log`）；对照固定目录发现原命令未选另一文件的侧栏两角色用例，随后独立 **1 passed /0 skip /6 warnings /20.19s**（`run-1794710574231835000.log`）。明确为59＋独立1两批证据，不称一次60项完整make门禁。
- 上述数据库命令沿用 `/private/tmp/openqms-r5-d5-20261114-r3iyx1ce/run.py`，先prepare，再 `test tests/migrations tests/test_multitenancy/test_agent_read_task_delta_db.py tests/test_refresh_sessions.py tests/test_user_service.py -q --tb=short -x`；snapshot和native均在前一数据库命令退出后串行执行，owner/容器/卷不变，未操作R4B-CLEANUP-01。native四文件为test_r5_d5_process/test_r5_model_agent/test_r5_model_binding/test_r5_d5_browser，按 `-m ci_r5_native -q --tb=short -rs -x`；独立UI为test_r5_d5_ui。前端为 `npm test -- --run`。原T9完整make/browser/850项前端是合并前证据，不冒充当前完整门禁。

## CI 与试用状态

仓库 runner 清单实际返回 `total_count=0`，当前没有满足 `[self-hosted, macOS, openqms-r5-sandbox]` 的执行器；原生 macOS R5 job 仍为必选配置，不用条件跳过制造绿灯。首次重核清单有 TLS 握手超时，重试得到明确0。[PR run 43668221844](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43668221844) 已实际执行：SDK 3.11/3.12/3.13、前端、Oracle自动化、文档均success；browser-protection实际 **11 passed /0 skipped /exit0**，receipt固定PR测试合并SHA `a2510b81781b10549dde4748fe4f0b972084d2de`，保留1228 warnings。该合并提交的文件树 `e84c3c06173bc219e117d71adff6deda090f299b` 与本地 `dcd9812e` 完全一致。backend-tests已进入真实deterministic acceptance但尚in_progress，不能宣称普通CI全通过。

原生 [r5-native job](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43668221844/job/132672262812) 实际queued、steps=null，没有分配runner。本地Darwin通过不替代远端job执行。上述是dcd9812e的实际快照；后续仅文档收尾会重新触发CI，最新状态以[PR检查页](https://github.com/Open-Industry-System/OpenQMS/pull/33/checks)为准，未提前签收后端或原生CI。GitHub连接器创建/更新PR均403，本地已授权gh身份成功完成草稿创建及状态更新，无权限设置变更。

本轮查询 Oracle 自动部署总开关为 true、预览开关为 false。草稿 PR 不改变这些开关、不合入 main，也不发起部署。R5 仍默认关闭。

真实 LOCAL/CLOUD 模型试用均继续 **PENDING**，环境没有专用 R5 凭据、没有已登记真实部署信息。已准备[两份独立合成 8D 及工程师评价流程](r5-real-model-trials.md)，待管理员提供批准部署/专用凭据引用及负责工程师；不查找或复用历史密钥，不把确定性对端、链路保存成功或 Agent 自评当成人工质量签收。
