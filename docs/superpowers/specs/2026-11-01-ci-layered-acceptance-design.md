# CI 分层与真实验收适配设计

日期：2026-11-01

状态：用户已选择“分层＋手动真实验收”；书面规格待确认，尚未实施。

范围：GitHub Actions、测试选择/资源/浏览器适配及说明文档；不改生产业务、权限、状态机或默认能力。

依据：[当前 CI](../../../.github/workflows/test.yml)、[现有 Playwright 配置](../../../frontend/playwright.agent.config.ts)、[E2E 说明](../../e2e.md)。

## 1. 问题与目标

现有普通 CI 会收集本机专属验收用例，却没有相应的运行条件：

- CAPA outcome harness/runner 默认读取未入库的 `.superpowers/sdd/2026-10-23-capa-outcome-review/owned-resources.json` 和私有 runner。
- 多处 Python 控制器及 Playwright 配置含 `/Users/sam/.../chromium-1223/...` 路径，不能在干净 Ubuntu runner 上工作。
- 必跑真实 provider 用例与“无 provider”测试混在同一 pytest 进程；把真实配置注入整段测试已实测破坏默认关闭断言。
- 当前 workflow 只在 main push / 向 main 的 PR 触发；功能分支推送本身没有获得 CI 运行结果。

目标是让干净 checkout 能运行明确、可复现的分层检查：自动 CI 不拿模型密钥；真实 provider/scanner 验收必须显式执行，未运行不算通过。不能靠忽略整个 `tests/e2e/`、弱化安全断言、伪造门禁或新增 xfail 来得到绿灯。

## 2. 方案比较与选择

1. **分层＋手动真实验收（选择）**：普通 push/PR 自动跑确定性检查和无模型浏览器保护；维护者另行手动运行真实 provider / ClamAV。避免 PR 密钥暴露和无意 API 费用。
2. 主分支自动真实验收：合入后自动消耗 API/容器资源，外部服务稳定性进入每次主分支检查；本轮不采用。
3. 仅排除本地验收：能较快修复基础 CI，但远端继续没有真实门禁入口；本轮不采用。

## 3. 自动 CI：基础检查与浏览器保护

继续使用 `.github/workflows/test.yml`，自动事件覆盖所有分支的普通 push（不含 tag）及向 main 的 PR。保留后端、前端和文档检查，并新增独立的无模型浏览器保护 job。

- **backend-tests**：真实独立 PostgreSQL 测试库、公共/租户迁移、确定性单元/API/事务/权限测试、既有 schema/SPC/import/preflight 检查。
- **frontend-checks**：使用仓库 lockfile 安装、TypeScript 和生产构建；不得为适配 CI 擅自升级依赖。若 lockfile 失配，先定位并记录，而非静默换版本。
- **browser-protection**：单独的 PostgreSQL 测试服务、Node/项目 Playwright 和明确安装的 Linux Chromium，运行不需要真实模型的只读侧栏、本地试用、D4 预览及 CAPA 终态保护。
- **docs-check**：保留代码/文档同步检查；测试基础设施及 CI 变更须同步说明。

后端和浏览器 job 均显式保持 provider/embedding 凭据为空，不自动读取 `.env.e2e`、本机配置或生产配置。不能以全局注入真实 provider 的方式运行普通测试。普通 job 的 `E2E_MODE` 不设置，不写成字符串 `false`；本轮不混用共享 seed/reset E2E 环境。既有 Redis、独立 seed suite 等环境依赖的 skip 继续真实记账，不能替代本层必需用例。

自动检查使用 `contents: read`；checkout 不持久化仓库写凭据。不使用 `pull_request_target` 来执行 PR 代码或获得 Secrets。fork PR 的确定性检查无需任何模型密钥。

## 4. 显式测试分组

在 pytest 中注册三个严格 marker，按具体用例标记，不按整个 e2e 目录粗放排除：

| marker | 范围 | 执行位置 |
|---|---|---|
| 无上述 marker | 确定性单元、API、真实数据库/HTTP/进程测试，包括不启动浏览器的双模块来源撤权保护 | backend-tests |
| `ci_browser` | 启动 Playwright 的确定性浏览器保护 | browser-protection |
| `live_provider` | 实际 provider/HTTP/D8/浏览器/知识/横向正向用例 | 手动 live gate |
| `real_scanner` | 真实 clamd/附件过程与附件浏览器用例 | 手动 scanner gate |

分组优先级为 live_provider / real_scanner 高于 ci_browser：

- backend：`not ci_browser and not live_provider and not real_scanner`。
- browser：`ci_browser and not live_provider and not real_scanner`。
- live：`live_provider`。
- scanner：原真实 Compose gate 的过程与浏览器链，不以普通 scanner stub 或跳过代替。

保留原两项 graph 排除，不额外隐藏失败。普通 job 的 deselection 数量明确记账，表示其他层未在此 job 执行，不写成通过。默认关闭、权限内核、迁移、消息、checkpoint 和非浏览器真实进程测试仍留在自动检查中。

`make check` 明确定义为确定性 backend＋frontend 类型/构建，与 backend-tests、frontend-checks 一致；`make check-browser` 对应独立的自动 browser-protection job。`make check-live` 对应显式真实 provider gate，`make agent-attachment-e2e` 保留为真实 scanner gate。自动 CI 的完整必需集合包含前三个无密钥 job，不把单次 `make check` 的退出 0 等同全部验收。完整验收由所需各层的真实结果组成，而不是单个绿色 job。

## 5. 手动真实验收 workflow

新增独立的 `.github/workflows/acceptance.yml`，仅 `workflow_dispatch`，输入为固定枚举 `live-capa`、`scanner`、`all`，不接受任意命令、URL、schema 或 checkout ref 文本。

- 手动验收仅接受默认分支 main 的代码。无密钥预检先核对事件/ref，其他 ref 明确失败，不把被拒绝运行当成成功。
- 真实 provider job 使用固定 GitHub Environment `ci-acceptance`；管理员配置所需 reviewer、允许分支与测试专用 Secrets。代码不自动创建/修改 Secrets、Environment 保护规则或分支保护。
- 测试模型配置只从该真实 job 的显式 Environment 配置读入：变量 `LLM_PROVIDER`、`LLM_MODEL`、可选 `LLM_TIMEOUT`；Secret `LLM_API_KEY`、需要自定义端点时的 `LLM_BASE_URL`。不从 workflow input 接收这些值，不上传/复制本地 `.env.e2e`。
- provider、model、必要凭据/端点、数据库和浏览器预检不通过时，先明确失败，不调用模型，不用 skip/fallback/模拟结果得到绿灯。timeout 保持既有 1–120 秒合法范围。
- live job 只选择 live_provider，用真实业务服务和模型；普通/保护用例在其他无密钥进程运行。若本地入口一次编排多个层，各层也须使用独立 pytest 子进程，只有 live 子进程获得配置；保留原 api/browser/live/acceptance 操作目的，不再要求私有精确-node plugin 或整段 pytest 全局修改 Settings。
- scanner job 运行原 `make agent-attachment-e2e` 的固定 ClamAV 镜像及随机专属 Compose project。现有固定 digest 为 amd64，适配 Ubuntu x64；不得直接复用本机 arm64 PostgreSQL digest。CI PostgreSQL 延续现有 pg15 多架构来源。
- scanner 验收记录实际 daemon/definitions、VERSIONCOMMANDS、EICAR FOUND、加密/展开限制及 clean 下载，并验证自己的容器/卷/网络清理。

显式请求的 gate 不允许以 skip、无测试被选中、continue-on-error 或空日志作为通过。输入未请求的另一 gate 在摘要中标记 NOT_REQUESTED，不称为通过。

GitHub 要求 workflow_dispatch 的 workflow 文件先存在于默认分支。故本功能分支可验证源码/选择策略及自动 CI；手动远端事件须由维护者将 workflow 正式引入 main 并配置 Environment 后再执行。本轮不为此自动创建 PR、合并 main 或操作仓库管理设置。

## 6. 可移植的测试资源与产物

将 CAPA harness/runner 的私有登记依赖改成受版本管理的测试支持接口：

- CI 使用当前 job 的 PostgreSQL service、显式 TEST_DATABASE_URL 与 PG15_CONTAINER；工作流给该 service 添加当前 run/attempt/job 的归属标签。
- 测试支持代码核验真实容器身份/标签、端口、明确的 `_test` 数据库及当前数据库/用户；数据库连接仅接受 loopback（127.0.0.1、::1 或 localhost），端口须匹配本 job 的真实 service/专属容器映射。不得只因 GITHUB_ACTIONS 字符串为 true 就信任资源，也不回落默认/种子/共享数据库。
- 本地显式验收使用新登记的自有测试资源文件或受控入口，校验精确容器/owner/镜像/端点/专属资源；不隐式复用已处置的旧工作树登记。
- 租户 ID、schema、scope 仍由真实平台迁移/认证/业务事务门禁产生，服务与权限判断不被 fixture 替换。独立 fixture 只清理自己记录的临时租户/进程，不负责停止 GitHub 管理的 PostgreSQL service。
- 产物写入 RUNNER_TEMP 或显式专用目录，不依赖固定日期的 `.superpowers` 文件。工作目录、运行日志和登记有明确生命周期，不把 TEST profile 或凭据复制到仓库/产物。
- 数据库/schema 只能是该 job 的隔离测试目标；不使用共享 E2E 的 reset/seed，更不使用六个 synthetic passed gate 作为正向完成证据。

优先复用现有真实 tenant provisioning / TenantSession 与进程控制逻辑；只提取必要的测试资源/浏览器支持，不重写 Agent runtime 或引入通用测试平台。

## 7. 浏览器与子进程边界

统一测试浏览器定位：优先显式 `OPENQMS_AGENT_BROWSER_EXECUTABLE`，否则通过当前项目的 Playwright 查找已安装 Chromium。删除本机用户名、缓存版本及 macOS 专属路径。显式路径无效或验收未安装浏览器时明确失败，不偷偷下载或跳过。

GitHub 的 browser/live/scanner job 明确执行项目 Playwright 的浏览器与系统依赖安装；这不授权在用户本机自动安装浏览器。

Python 后端仅向 Node/Vite/Playwright 传 system 和已有 browser-runtime 白名单：分配的回环地址、nonce、一次性测试员工登录、租户/报告/场景 ID、产物目录和浏览器路径等。DB/provider key、任意环境变量、真实用户凭据不传给 Node。依赖检查不能为了 CI 放宽实际授权、版本绑定或终态保护。

## 8. 结果、日志与清理

- 每个 job 记录选择层、命令、实际测试数、失败/skip/xfail/xpass/deselection、warnings 与退出码。自动 CI 的成功不表示手动外部门禁已运行。
- 日志写入前脱敏实际 API key、敏感端点、数据库 URL/密码及认证头；不把 provider/model/timeout 普通字段作为宽泛替换词破坏测试计数。
- GitHub 的日志自动 masking 不覆盖 artifact 文件，故不上传原始 profile/env dump/凭据文件。只上传经过过滤的失败日志、测试输出及受控截图；trace 保持当前关闭策略。
- finally 与 always 清理仅针对本 job 创建的进程、租户、随机 Compose project、volume 和 network；不 shutdown Docker、不 prune 镜像、不清其他项目。GitHub 管理的 service 由 runner 收尾。
- 普通 CI 可取消同 ref 的过期运行；手动收费/真实门禁不自动取消在途执行。被取消或未完成不等于通过。

## 9. 验证和完成判据

实现阶段先验证测试选择/配置/资源/浏览器支持的失败路径，再跑实际对应层：

1. 干净 checkout 不依赖私有 `.superpowers` 或本机路径，显式 marker 分类仍保留全部应覆盖测试。
2. 普通 backend/browser 无 provider，原 no-LLM 和只读浏览器断言保留并通过；双模块撤权仍分别检查 FMEA 与 PLANNING 的真实 HTTP 整包拒绝。
3. 资源缺失、错误 owner/数据库/端点、无效浏览器路径、显式真实 gate 缺配置均失败且不触碰其他资源；无凭据/无实际执行不算通过。
4. Node 白名单保留必要 runtime 参数并拒绝 DB/provider 凭据；日志与 artifact 不含测试配置秘密。
5. 无数据库的选择/配置纯测试、受影响后端及前端检查先通过；获授权的本地隔离资源只用于相关实际回归，不自动安装本机依赖。
6. workflow 静态检查与真实 GitHub run 分开记账。尚未推送/触发的 workflow 不声称远端通过；手动门禁在 main/Environment 就绪后必须实际运行，不能用 YAML lint 或旧本地收据替代。
7. 更新 CI/E2E/开发说明与 PROGRESS，明确 make check、自动浏览器与手动真实验收各自的范围。业务故事/verify skill 契约未变则不升级其版本日期。

## 10. 明确不做

不改业务权限、本人审批、受控版本/历史摘要、默认 DENY 或 runtime/附件默认关闭；不新增产品状态、业务迁移、候选审批或 Agent 写入能力；不修改用户删除的 `.env.e2e.example`；不读取/上传本地密钥或配置 GitHub Secrets；不擅自提交实现、推送、创建 PR、合并、部署或变更仓库保护规则。

用户本轮只批准先形成本规格并本地提交。书面规格确认后再形成实施计划，实施/验证资源与后续提交推送范围在计划阶段明确。
