# R5 与当前主线集成及草稿 PR

2026-11-15。用户授权核对最新主线、推送 R5 功能分支并创建草稿 PR；不授权合并 PR、部署或生产启用。

## 合并基线与迁移

R5 原完成提交 `73ad865c`，共同前驱 `78b428d2`。本轮实际 fetch 的 `origin/main` 为 `dae0892f3be6f15ea297bd0d2659308029cd4d23`，包含 R4b PR #30、Oracle PR #31、refresh-session 认证及同期部署保护。保留主线认证实现、生产/预览工作流与 Oracle 自动化检查，同时保留 R5 原生检查 job。

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
- 前端初次全量 **882 passed /34 failed**：33项 CAPA 页面旧测试遗漏 D5 API 隔离，真实客户端按主线新规则同步了不一致的假身份；另1项 PFMEA 五秒超时。最小单项先复现失败，补齐页面套件 D5 API fixture 后，CAPA详情、真实认证组合、D5面板及 PFMEA **100 passed /5 files /9.84s**。未改应用认证逻辑或超时/权限断言。全量前端复跑待记录。
- 首次直接 pytest 因未指定测试库被种子库保护拒绝；一次纯入口参数误带 `backend/` 前缀导致未找到文件。均未执行数据库测试，不计为通过。
- 完整迁移、refresh-session 和 user-service 合并后回归正在登记资源上串行执行；结果将在 PR/PROGRESS 单列。原 T9 完整 `make check` 与850项前端结果是合并前证据，不冒充当前完整结果。

## CI 与试用状态

仓库 runner 清单实际返回 `total_count=0`，当前没有满足 `[self-hosted, macOS, openqms-r5-sandbox]` 的执行器；原生 macOS R5 job 仍为必选配置，不用条件跳过制造绿灯。首次重核清单有 TLS 握手超时，重试得到明确0。PR 创建后记录实际 job/run 链接与状态；普通 CI 实际执行和原生 job 排队/不可用分别报告。

本轮查询 Oracle 自动部署总开关为 true、预览开关为 false。草稿 PR 不改变这些开关、不合入 main，也不发起部署。R5 仍默认关闭。

真实 LOCAL/CLOUD 模型试用均继续 **PENDING**，环境没有专用 R5 凭据、没有已登记真实部署信息。已准备[两份独立合成 8D 及工程师评价流程](r5-real-model-trials.md)，待管理员提供批准部署/专用凭据引用及负责工程师；不查找或复用历史密钥，不把确定性对端、链路保存成功或 Agent 自评当成人工质量签收。
