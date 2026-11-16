# 2026-11-16 安全扫描修复记录

扫描仓库：`Open-Industry-System/OpenQMS`；基线：`193746abb7c1eb9d196ef3997b6b91767490e3d1`。
Run：`wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7`。
Output：`wfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731`。
报告共17项（高6、中11）。本记录对应独立分支 `fix/security-scan-20261116`；本地修复与整合验证完成，不代表云端复扫、部署或 finding 状态已关闭。

## 逐项改动

| 编号 | 风险 | 原始发现 | 修复行为 |
|---|---|---|---|
| 1 | 高 | [Starting a single-tenant deployment creates a publicly known administrator password](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_145632d9e8f05d383a4d1a67) | 移除启动默认管理员；演示种子为特权账号生成不可知口令；私密终端初始化；普通认证与刷新统一拒绝遗留公开管理员口令。 |
| 2 | 高 | [Changing an MES base URL forwards the existing hidden credential to the new host](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_5e422ac6515515f9872f0ba8) | MES 密文绑定认证类型和规范化目标源；改变目标或认证类型不能沿用隐藏凭据。 |
| 3 | 高 | [Testing an AI provider sends a masked stored API key to an arbitrary base URL](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_8827f5d8a841e2c0f7c13321) | AI 非持久化探测只使用明确重输的密钥；保存配置时禁止遮罩密钥跟随变更目标。 |
| 4 | 高 | [Editing a supplier name executes script in supply-chain heatmap viewers](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_b5bb53f77b94cc3a8e988348) | 风险热图提示使用 DOM 文本节点，供应商名称不再拼入 HTML。 |
| 5 | 高 | [Supplying sibling product-line identifiers exposes and changes FMEAs and control plans](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_cbef6df1c6633228530c29c4) | FMEA/控制计划创建、按 ID 访问和修改校验工厂、产品线及模块权限；CSR 同步校验全部输入。 |
| 6 | 高 | [Updating a special characteristic commits cross-scope safety changes before authorization](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_f671eb6b44c8d0090d2e6487) | 特殊特性所有修改、MSA 与安全审批在服务层写入前完成范围检查。 |
| 7 | 中 | [Requesting supply-chain risk data bypasses factory and product-line scope](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_1e1564d1312efa0e56502c71) | 风险热图、趋势、对比、导出与快照生成使用请求工厂和产品线范围。 |
| 8 | 中 | [Reusing a rotated refresh token leaves the attacker's successor session active](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_3e127770535bc2fcff0b0731) | 刷新令牌前驱重放永久撤销会话家族；服务端退出；新旧令牌轮换均保留绝对截止时间。 |
| 9 | 中 | [Viewing an ERP connection reveals credentials stored in URL fields](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_47efa70c2069583e2c251639) | ERP URL 不接受 userinfo/query/fragment；响应使用可公开字段白名单，清理遗留不安全配置。 |
| 10 | 中 | [Holding one slow attachment upload blocks the scan pipeline for every tenant](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_4b08bebaef88cd2eb8bedb8a) | 先有界暂存客户端输入，再占用全局扫描槽；用户并发配额与元数据锁独立于远程网络节奏。 |
| 11 | 中 | [Uploading oversized or highly expanded workbooks can exhaust the API worker before limits apply](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_4b85c51e96ca5930a8b510b5) | 上传进入 multipart 解析前有请求预算；文件读取、ZIP 展开、工作表/行/列/单元格数量均有预算。 |
| 12 | 中 | [Guessing platform-admin passwords is not throttled at the public API edge](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_5be3aa2921fcbd9c1a36c8a9) | 平台管理员登录使用跨进程持久数据库限流，IP 和规范化账号分别记账，拒绝响应前提交计数。 |
| 13 | 中 | [Configuring an ERP connector sends backend requests to arbitrary HTTP destinations](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_6ffd368561d1bcc4208ac839) | ERP REST 仅访问部署声明的精确源与 CIDR；固定已验证解析地址、保留 TLS SNI/Host、禁用代理及重定向。 |
| 14 | 中 | [Running a mutable third-party Action can compromise Oracle deployment credentials](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_7545a44c4fae85991bd96353) | 部署与预览清理工作流 Action 固定官方核实的完整 SHA；引入部署凭据前恢复可信检出。 |
| 15 | 中 | [Editing supplier fields plants active formulas in exported XLSX and CSV files](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_839f080b2fc7acc592a64e52) | XLSX 字符串显式保存为文本；CSV 中公式前缀作为字面量导出。 |
| 16 | 中 | [Requesting a document version discloses full historical FMEA and control-plan snapshots](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_fe82d4f12fef67c700edf6f2) | 历史版本、比较、完整性检查、回滚继承当前父文档的模块/工厂/产品线范围。 |
| 17 | 中 | [Using ERP or PLM object IDs bypasses product-line restrictions on integrations](https://chatgpt.com/mcp-app/connector_openai_defense_factory/open_defense_factory#/findings/raw/rf_wfr_1c121908379474e1eaa22549134696d27410bca1ace8f4041d719d9dec760cc7%3Awfo_d18a8bf3c02b7a1b8b888d0f766629b780e77ef8164af5fb0e84e48190459731%3Aocc_ff1783d63f65ef3e550a31be) | ERP/PLM 按 ID、子对象及列表/计数使用父连接与有效产品线一致的权限规则。 |

## 回归入口

| 报告项 | 主要回归文件 |
|---|---|
| 1 | `backend/tests/test_security_admin_bootstrap.py` |
| 2、3、9、13 | `backend/tests/test_connector_security.py`、`test_ai_config_service.py`；生产配置与控制器回归另见 `test_production_config_contract.py`、`tests/test_oracle_production_orchestrator.py` |
| 4 | `frontend/src/pages/supplyChainRiskMap/components/RiskHeatmap.test.tsx` |
| 5、6、7、16、17 | `backend/tests/test_security_scope.py`、`test_security_scope_db.py`；授权审批与混合CSR输入包含真实数据库断言 |
| 8 | `backend/tests/test_refresh_sessions.py`、`frontend/src/store/authStore.test.ts` |
| 10 | `backend/tests/services/agent_runtime/test_task_attachments.py`、`test_task_attachment_staging_pure.py`，另有真实ClamAV过程与浏览器门禁 |
| 11、15 | `backend/tests/core/test_import_body_limit.py`、`backend/tests/test_excel_security.py` |
| 12 | `backend/tests/test_platform_login_security.py`、`test_platform_login_security_db.py`、`backend/tests/migrations/test_platform_login_limits_migration.py` |
| 14 | `backend/tests/test_security_workflow_pins.py` |

## 升级要求

FMEA/控制计划等通过范围约束查询的 UUID 不可见对象返回404，模块权限不足返回403。拒绝发生在 CAPA 技术锁及内容读取之前；对应既有准入测试保留了锁顺序、最小字段读取和授权正向断言。

1. 在受控部署流程执行数据库迁移，新增的 `public.platform_login_attempts` 仅为平台登录限流状态，不属于租户业务表。
2. 管理员不再有公开默认口令。首次安装按迁移和所需的显式种子流程完成后，使用私密交互终端运行 `python -m app.cli.bootstrap_admin --username admin`；已有账号加 `--replace-existing`。Docker 使用 `docker compose exec backend`，生产使用已有 `production-compose.sh exec backend` 包装器。密码不通过参数/日志/默认环境变量传递；至少14字符、最多72 UTF-8字节并满足现有复杂度规则。重置撤销全部 refresh 家族及遗留 refresh 字段。多租户沿用租户开通/迁移的私密管理员流程。
3. 已保存的 MES REST 密文没有目标绑定时必须在确认目标后重新输入凭据；不自动为旧密文背书。AI 测试需要重新输入 API Key。详见[连接器安全约定](security-connectors.md)。
4. ERP REST 默认拒绝外发；生产根安装的控制器必须先按既有安装流程更新以认可新配置，不能直接执行候选部署代码或只更新应用镜像；运维需在受控 dotenv 文件中明确配置 `ERP_ALLOWED_ORIGINS` 源/CIDR 策略，生产包装器不继承 ambient 覆盖。允许显式批准的制造内网，拒绝回环、链路本地和多播地址。URL 中的凭据改放认证配置；端点仅使用无查询参数的静态相对路径。
5. 登录拒绝已知公开管理员口令之外，旧 access JWT 在普通退出后仍遵循其既有截止时间；refresh 退出/重放撤销不宣称通用即时 access-token 吊销。使用公开口令的特权账号现有 access 认证也被拒绝。E2E 专用模式保留其显式测试账号语义，生产必须保持 `E2E_MODE=false`。

## 验证边界与证据

- 测试使用本轮新建、带 owner 标识和0600登记的独占 PG15 容器；未访问业务数据库、真实模型凭据或生产主机。
- 本地环境为Python3.11.15、Node26.13.0和独占PG15；不是远端CI或生产部署收据。旧 embedding 隔离夹具要求字面库名 `qms_test`，本轮最终门禁已在自有容器中使用这一名称，未放宽安全闸；原始193与修复代码在 `qms_test` 上均11 passed、随机库名下均11 setup errors，对照日志已保留。
- 基线认证/平台/环境/附件77项通过；原有演示管理员口令实际 API 登录得到200，新负向回归捕获该问题。当前迁移结构下旧启动分支会吞掉部分建号异常，不能仅凭静态报告把它表述为每个空库都能成功创建管理员；固定口令路径仍已完全删除。
- 令牌前驱重放、绝对期限、服务端退出、升级前管理员令牌及 legacy 家族均有实际 API 红绿回归。
- 权限相关新增数据库用例验证拒绝后持久状态不变；补充锁后最新对象检查与父连接列表一致性。未把仅 mock 的测试当真实租户隔离验收。
- Action SHA由GitHub官方 API核实：`tailscale/github-action@6cae46e2d796f265265cfcf628b72a32b4d7cade`（v3）、`actions/checkout@11d5960a326750d5838078e36cf38b85af677262`（v4）、`actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065`（v5）、`actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020`（v4）。没有执行远端部署工作流。
- 真实ClamAV：过程6 passed、浏览器1 passed，清理回执为PASSED且容器/卷/网络余量0。验收使用本轮局部源码tree `7eaa0dc0d84bea12edff26ce35a10f53a12d55f2`（非提交），只读挂载测试目录补足生产镜像默认不含测试的验收环境；未修改生产 Dockerfile，也未将测试打包进镜像。首次浏览器插件未加载的失败不记为业务验证，修正启动器后完整重跑通过。
- 前端100文件/891项单测及类型检查、生产构建通过，保留既有Node/localStorage等警告。
- 首次完整后端运行5398 passed /36 failed /5 skipped：13项普通夹具仍使用已禁用的公开管理员口令，23项PLM编排替身缺少新增的父连接身份读取。仅修正4个测试文件，保留原业务断言和生产保护；相关4文件与管理员安全回归合计96 passed。干净测试库上的完整 `make check` 重跑退出0，后端5434 passed /5 skipped /19 deselected，失败和错误均为0；运行日志保存在本轮私有临时产物目录，不包含真实凭据。

## 最终本地验收

- 完整 `make check`：退出0；后端5434 passed /5 skipped /19 deselected，6 warnings。源码冻结后未再修改生产代码；旧夹具修正经独立复核，原业务断言保留。
- SDK：562项单元、16项loopback、1项wheel安装验证，均无失败、错误或跳过。
- 前端：100文件/891项单元测试通过；完整检查中的类型检查和生产构建通过。
- 实际ClamAV：6项过程、1项浏览器验收通过；其独立项目已清理，容器、卷和网络余量0。
- 后端5项跳过：1项本机未配置PG15 dump/restore工具、1项Redis不可用、3项显式E2E_MODE未启用。19项按既有门禁标记排除；普通 `make check` 不包含浏览器、真实模型提供商和真实扫描器门禁，ClamAV结果来自单独实跑。未执行真实模型调用、远端CI、云端复扫或部署。
- 完整后端收据：`/private/tmp/openqms-security-20261116-w1xwf2od/artifacts-final-pass/api-20261116T063607549389-receipt.json`；完整检查日志：`/tmp/openqms-security-final-pass-check.log`。初次失败日志、源码哈希和对照记录均保留，未将失败运行计作通过。
- 本轮主验收PG容器和卷已按完整ID、owner标签及唯一消费者核对后删除；清理前客户端0、应用哨兵库public表0，删除后容器/卷余量0，临时测试凭据已删除。清理收据：`/private/tmp/openqms-security-20261116-w1xwf2od/cleanup-final.json`。源码、私有验证日志和独立工作树保留；上述验收结束时尚未提交、推送、合并或部署。用户随后授权提交并推送独立修复分支，发布结果以Git记录及交接回执为准；不自动合并或部署。

## PR远端CI跟进

PR #38首轮 `Test OpenQMS`（run `43827639514`）的 `oracle-automation-checks` 为122 passed /1 failed /16 subtests passed，失败为预览ERP配置测试导入 `yaml` 时缺少PyYAML；该作业此前只安装pytest。本次在该作业中显式声明 `PyYAML==6.0.3`，保留YAML语义校验和所有业务断言。前端、3个SDK版本、文档、浏览器保护首轮已通过；后端查询时仍在运行，不能提前记为远端全绿。

隔离本地Python3.11.15环境仅安装 `pytest==9.2.0` 与 `PyYAML==6.0.3`，运行 `python -m pytest -q tests -p no:cacheprovider`：123 passed /16 subtests passed，退出0。生产代码及测试断言均未改变；远端Python3.12的重跑结果需另行核实。

## 与最新main整合

用户授权检查无问题后合并PR #38。准备合并时main已前进21个提交至 `f8b8d988`（R5/D5/Responses整合），原PR出现9个文本冲突。模型注册与双方进度记录均保留；公有迁移新增无DDL合并节点 `20261116_security_main_merge`，父节点为 `20261115_r5_responses` 和 `20261116_platform_login_limits`，不重写任何已发布迁移。tenant仍为 `tv014_r5_responses`，平台限流表继续从租户业务投影中排除。

整合后独占PG15空库升级成功；164项迁移/权限/凭据回归通过，包含从主线、安全分支、两个旧head同时存在三种起点升级并保留历史与限流状态。前端102文件/919项单测、类型和生产构建通过。上述结果取代旧代码规模的整合判断，旧完整5434项收据仍只证明原安全修复基线；最终远端CI与本机R5原生结果以PR当前head的检查及交接回执为准。ClamAV已验收的3个附件运行时文件哈希未改变，没有将先前结果冒充新代码实跑。

## 整合候选的SDK兼容回归

整合提交 `ec762a2e` 的远端后端收据为5660 passed /4 failed /4 skipped /89 deselected（run `43834841282`，115分钟）。4项失败均在新增的真实SDK HTTP边界测试：CI解析到OpenAI3.51.0/httpx2 2.16.1，原测试给SDK默认httpx2客户端注入httpx 0.27.2响应，造成流类型断言失败；D5完整材料拒绝仅为日志中的预期保护输出，不是实际失败项。370692字节产物SHA256为 `21dbc461dc47fede7dd39f6480b423b853fb39f3aa9c70b63ee91fc65bb43b13`。

隔离环境精确复现4 failed /48 passed。测试现在沿用项目既有的SDK传输识别方式，为实际默认HTTP客户端匹配MockTransport与Response；生产代码、SDK依赖范围及所有密钥断言均保持不变。OpenAI2.41.1与3.51.0环境分别运行连接器安全和运行器合同，共116项均通过，启用纯测试网络禁止保护，未请求真实提供商。新提交仍须等待远端必需检查完成后才合并。

新版SDK的本机R5 API验收另得到67 passed /1 failed：重定向保护实际抛出 `PermissionError(Model deployment unavailable)`，SDK2会包装成APIConnectionError，而SDK3直接保留该异常。仅调整原生测试兼容这两种形式，并新增对根因类型和固定拒绝原因的断言；继续保留目标A请求恰好一次、目标B请求为零的原断言。SDK2/3分别2项通过；完整新版原生门禁将在新head重新执行，不将67项通过当作整轮成功。


## 最终 CI 的知识沉淀并发修复

同步主线 PR #39 后的运行 `43861209312` 完整后端结果为5652 passed /1 failed /4 skipped /89 deselected（5568.66秒）；7项其他必需检查通过，先前4项SDK密钥断言全部通过。唯一失败 `test_concurrent_first_sink_unique_race` 在本任务独占PG15上复现：同一CAPA首次并发沉淀同时受主键及来源唯一键约束，只对主键使用ON CONFLICT无法吸收来源索引的并发冲突。证据产物SHA256为 `d70f28baebc4bd3b05e7e477e4834acd76c835d29c11c297b518e858bee94d1b`。

知识沉淀现在在生成摘要后、写入前，按确定性知识条目UUID获取事务级advisory锁，提交或回滚自动释放。同源持久化串行，其他来源及摘要生成仍可并行；保留原子upsert、条目状态、outbox取消与重建、审计及外层关闭事务。无新增DDL或配置。

原并发测试扩展为2/4独立会话，覆盖全部提交及首写者回滚；同步摘要完成后竞争写入，保留唯一条目和无IntegrityError断言，并核验最终内容哈希、唯一pending outbox、取消数量及审计与已提交事务数量一致。知识沉淀及CAPA关闭决策相关实际48项通过，0失败/跳过。修复后仍需最终提交的完整必需CI通过才可合并。
