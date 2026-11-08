# PR #28 合并阻塞修复记录

日期：2026-11-08。基点：`f9d6f95c804ed3f84bb583fa21fe9b61300ca4e2`。

本次只处理当前 PR 的实际 CI 阻塞，不扩展业务功能、不调整授权策略，不使用管理员绕过或 force push。最终合并须等待新 head 的真实 GitHub 检查通过；本地记录不替代远端结果。

## 原始失败

- `pull_request` run `42050741115`：backend 为 3741 passed /1 failed，失败用例为 `test_disconnected_owner_cannot_reconnect_and_inherit_permission`。维护连接被终止后，asyncpg 可能先抛出未被 SQLAlchemy 包装的协议/接口错误，随后退出清理又尝试访问失效连接。
- 同 head 的 push run `42050724144`：backend 通过，但两个事件的 browser-protection 均在 `window` 场景失败：预期仍显示 `1..100`，实际已显示 `11..110`。
- 浏览器用例先提交新消息，再注册路由，允许真实后台轮询先完成。原应用 hook 仍在完整两页取回后发布；不能以降低窗口、固定 watermark 或退避断言修复该测试竞态。

## 修复边界

### 维护连接

- 在读取 owner info 前拒绝 closed/invalidated 连接，避免惰性恢复产生新的物理会话。
- 维护身份验证遇到 DBAPI 或 asyncpg 接口/协议错误时，丢弃该物理连接并报告 `TenantUnavailable`。
- 不重试身份验证，不重新建立连接或继承 session advisory lock，不放宽 attempt/generation/schema/backend PID/真实锁归属判断。
- 已失效连接不再进入正常解锁 SQL；健康 owner、异常退出、取消和池污染检查仍按原合同执行。

新增两类驱动错误的真实 PG owner 故障注入：验证失败后没有额外 SQL、没有新 checkout，原 PID 不变；离开上下文后锁已释放。保留实际 `pg_terminate_backend` 场景。

### 浏览器窗口

- 在页面发起任何活动轮询前安装路由，始终先取得实际认证响应，不构造或改写 DTO。
- 对真实 watermark 110 的最新页和相邻历史页设置持有边界，忽略较早合法的 100 水位轮询，不把它们误当本轮请求。
- 显式观察真实最新页响应，保证后台轮询与测试动作交错时仍实际检验“历史页未释放前不得发布半窗口”。
- 保留完整 100 条窗口、watermark、跨页实际提交、缺失区间、断线撤回和 5 秒退避断言；不加 sleep、不提高重试或超时、不修改应用 hook。

## 第二轮：真实中间提交的窗口基线

`d7c7ccba` 的 push browser 通过，但 PR run `42435568642` 的 browser 为 10 passed /1 failed：历史页 110 被持有时，界面是完整的 `10..109`，不是半窗口。夹具 `seed_to()` 每条消息均经真实 HTTP 独立提交；从 100 增至 110 时，109 是允许被完整轮询并发布的水位。不能要求界面忽略这些合法提交。

用例现在先观察初始 `1..100`，真实追加到 109 并确认完整的 `10..109`，再追加到 110。在 110 历史页尚未释放时，精确要求上一完整窗口 `10..109` 不变，释放后仍精确要求 `11..110`；跨页追加 111、51–60 连续性、失败撤回及退避检查全部保留。没有从实际输出反推预期，也没有更改应用 hook 或夹具的提交方式。

先仅加入明确 109 前置、保留旧的 `1..100` 持有期断言，实际 Chromium 确定性复现 1 failed（收到 `10..109`）。修正该错误基线后进行新回归。Hook 单元同时覆盖旧水位 100、109，持有历史页时比较完整 100 条旧窗口，而不只检查首条。

## 本地验证与远端门禁

- 两个新驱动错误用例先实际失败；修复后连同实际断线用例 3 passed。
- 维护模块及 CI 契约回归 214 passed /3 既有 Pydantic warnings。
- 窗口测试以事件屏障复现与远端相同的 `1..100` 对 `11..110` 断言失败；修正路由次序后实际 Chromium 1 passed /5 warnings。
- 首次编写该屏障时一次字符串字面值错误已修正并通过 E2E TypeScript 检查；这次编辑错误不算功能 RED。
- Activity hook 单元测试 16 passed；E2E TypeScript 检查通过。整层无模型浏览器保护实际 11 passed /3771 deselected /5 warnings，exit0，0 skipped/error/xfail/xpass；deselected 是其他验收层，不计作本层通过。新 head 的远端检查与合并结果以 PR #28 实际状态为准，不拿这些本地收据替代。

证据保留在本工作树私有 `.superpowers/pr28-mergecheck-20261108/`，不提交运行配置、口令或原始私有数据。未调用真实 provider/scanner，未在本机安装依赖或浏览器。

## 第二轮验证结果

- 明确 109 前置的 Chromium 回归：先 1 failed（错误旧基线），修正后 1 passed /5 warnings。
- 完整无模型 browser 层：11 passed /3771 deselected /5 warnings，0 failed/error/skipped/xfail/xpass，exit0。
- Activity hook：17 passed；E2E TypeScript 和前端类型/生产构建 exit0。工具有既有 Vite/Node 弃用提示，不宣称无 warnings。
- 独立限定复核：无发现；未修改生产 hook、后台追加流程或 CI 跳过规则。
- 本轮专属资源的清理准备操作被权限系统拦截，未执行清理、未换工具绕过；实例保留。远端新 head 的检查仍须实际通过后才合并。

## 用户改动与资源

本地原落后远端 27 个提交，未直接覆盖用户文档：先按用户授权备份并校验原字节，再 fast-forward；架构文档三方恢复，进度顶部两段追加历史与远端记录均保留。原未跟踪开发基线和 `.env.e2e.example` 删除不改、不混入修复提交。

仅使用本轮明确授权的新临时 PG15 容器、随机 `_test` 数据库及回环端口。fixture 自建 schema/子库按正常流程清理；专属容器/卷/网络在不再需要后按精确 owner/ID 处置，不动其他项目或保留的测试库，不关闭 Docker Desktop。

PR 从草稿转为正式、最终合并和资源处置仅在对应实际检查满足后执行。不得把本文的本地回归数字写成远端 CI 已通过。
