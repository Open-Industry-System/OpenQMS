# OpenQMS 开发进度

> **2026-11-14 R4b 集成草稿PR已发布**：已普通推送独立分支`integration/r4b-main-20261114`并创建[草稿PR #30](https://github.com/Open-Industry-System/OpenQMS/pull/30)，base仍为main `5b712d94`，GitHub报告mergeable且draft=true；未合并main。首轮自动Test OpenQMS已触发，逐轮CI状态与最终实际head以PR动态记录及最终交接为准，不在此预写通过。执行候选`78b428d2`的本地完整门禁与资源证据见下一条/集成交接；后续仅文档记录发布事实，1575执行文件指纹保持一致。GitHub连接器创建PR受403集成权限限制，已用本机现有gh授权完成同一草稿请求，未提升权限。旧R4B-CLEANUP-01继续延期，新专用验收实例保留用于PR迭代。

> **2026-11-14 R4b 主线集成发布前本地验收完成**：origin/main刷新仍为`5b712d94`，独立分支`integration/r4b-main-20261114`合入已签收`dcda1d55`，17处冲突逐段解决；集成merge `ebc502c2`、最终执行候选`78b428d2`。保留main权限/PR #29与R4b双层来源、默认拒绝、消息门禁、受限恢复、撤权后停止；public/tenant分别新增无DDL merge至20261114/tv009，真实发现并修复merge拆分多head降级问题，独立规格/质量复审通过。新独占实例内public三路径、tenant空建/双旧head有值升级/full parity/27 guards均通过。当前`make check`真实exit0：**backend4973通过/4可选skip/19未选/6警告**，SDK **562+16+1**，前端tsc/build通过；真实browser **11通过/0skip/6警告**，pure **321通过/3警告**，Vitest **95文件822通过**，E2E类型通过，清理器普通/-O各55隔离测试通过。1575执行文件前后指纹一致（manifest SHA256 `27bcbdf738c63787934a29877ea608c08997a8e54b10d715fcd931f1a87a70bd`）；具体收据、工具差异、skip和未运行层见[集成交接](docs/development/r4b-main-integration.md)。主库为本次独占实例`127.0.0.1:62563/qms_test`，原初始测试库仍保留；因main旧夹具精确库名要求而调整登记，未放宽守卫，PR #29事务27通过。验收后迁移临时库/其他客户端/tenant登记/schema均0，哨兵不变。旧 **R4B-CLEANUP-01**仍延期，全部旧资源未用于本轮；T11仍“功能验收完成，清理待办”。下一步普通push独立分支并创建草稿PR、跟踪实际CI，不写main/不合并/不部署或启模型。

> **2026-11-14 R4b 主线集成进行中**：已刷新 origin/main=`5b712d94ed08412a6c3d92e4dca2d9193b5959d3`，在应用创建的独立工作树 `/Users/sam/.codex/worktrees/0cd0/OpenQMS`、分支 `integration/r4b-main-20261114` 合入已签收 `dcda1d55`。实际17冲突逐段处理，保留main权限修复/PR #29与R4b消息门禁、双层来源、恢复及停止边界。新独占PG owner=`26a2159e6e037e8d9e421c06`，端点 `127.0.0.1:62563`；完整身份/私有登记、冲突决策和验证记录见[集成交接](docs/development/r4b-main-integration.md)。旧R4B-CLEANUP-01全部保留，不用于本轮。纯权限当前150通过，CI pure321通过/3警告；迁移首轮72通过/2失败揭示merge拆分多head回退缺口，新增DDL前全部父路径/提交前单版本守卫并补真实回归；旧版本配对RED2后5通过、迁移state矩阵RED9后17通过。迁移/tenant整组中间378通过/5旧head断言失败/1工具skip，5断言修正后单独5通过；PG15工具现绑定本次容器ID重跑快照，运行时/附件/PR29焦点正在执行，尚不声称完整候选、远端CI或可合并。

> **2026-11-14 收尾方式调整：T11 功能验收完成，清理待办**：依用户明确指示，功能交付单独签收，保留此前完整门禁、独立规格/质量复核及本地提交记录（T11修复 `d49d45c6`、诊断清理器 `486451e5`）；不以延期清理否定功能验收，也不将T11标为全部完成。资源清理另登记为 **R4B-CLEANUP-01（待办）**，由本任务后续维护者承接；清单、凭据文件名、阻塞原因及恢复清理条件见[交付指南](docs/development/capa-d4-local-text-delivery.md#保留资源与后续清理入口)。本轮仅调整文档，未运行Docker、未删除资源或修改执行代码；既有测试证据保持原日期和范围，未宣称重新验证功能。

> **2026-11-14 已批准的最小daemon诊断已执行，清理继续未完成**：固定daemon/context/目标卷身份复核一致。创建时CLI要求递归只读配rprivate；随后daemon拒绝缺失的`/host_mnt/private/tmp/.../discourse`源，且拒绝以rprivate bind其存储根。未猜路径或提高传播权限：省略不可用源、将同一目标卷改为只读named-volume且NoCopy，仍无网络/无capabilities/非privileged/不挂宿主根或Docker socket。诊断容器`6e92a22ca560eacd0db2c6238eca6e6ca3d47b2f1b9597751db3a743d6fe89a2`（owner/name `openqms-r4b-bind-audit-20261114-441c9e1513ed`）退出0并保留。三源kernel mountinfo为fakeowner设备0:46，而stat为43；目标为ext4 254:1/stat65025，无probe子树嵌套。只能证明当前挂载图分离，不能忽略代理身份差异而排除底层别名；缺失源也非排除证据。新增纯诊断parser与audit附注经测试先行、独立规格→质量复核，主执行者普通/-O各 **55 mock tests passed**；别名、可靠同FS确认无关、未知嵌套、代理/设备差异及绑定不一致均覆盖。绑定标签不认证也不自动验证时间，解析结果恒不具删除授权，不能将一致的旧标签当fresh证据。真实原7引用经该parser仍全部INDETERMINATE，并附入新audit副本，分类/计数不变。新dry-run `t11-owned-cleanup-failure-1794617088009033000.json` 实查32容器：2个related named引用（包含新诊断容器）、25个excluded named引用、10个indeterminate bind（原7+probe3）。全部资源保留，无删除、无其他容器启停或修改。真实输出、身份/hash收据与附注报告保留在私有目录；T11清理与最终签收仍未完成。

> **2026-11-14 daemon侧bind身份调查（只读，未清理）**：重新核对 context `desktop-linux`、固定socket `unix:///Users/sam/.docker/run/docker.sock`、daemon ID `aaa6bf3b-6bc0-468e-88c5-f6f60da83210`；目标卷local驱动、Options=null、owner正确，daemon挂载位置仍为 `/var/lib/docker/volumes/openqms-d4-t3-8f168c8a4637882929447e6c-data/_data`。fresh只读枚举仍为7条bind引用（4个唯一Source），全部引用容器为exited；不能以退出或路径字符串排除关联。现有Engine inspect/info未提供canonical inode/mount-ID证据；本机debug-shell.sock不存在，自带diagnose入口只提供诊断包能力，未收集或上传诊断包。已准备最小5根只读挂载、无网络/无capabilities/无privileged/无host-root或Docker socket的独立诊断容器创建命令，私有 `daemon-bind-probe-proposal.sh`；依用户要求，创建和运行须先确认，尚未执行。新挂载类型收据 `t11-mount-type-audit-1794612436796800000.json`。未改清理器、未接入未经验证证据、未停止或修改其他容器，T11清理仍未完成；待取得daemon内核挂载与目录身份后再新增别名/无关反例、复核并dry-run，实际删除前必须刷新证据。

> **2026-11-14 提交前清理器复验**：仓库副本保持已复核私有控制器的资源常量和守卫，仅更新说明；测试使用同目录控制器与独立系统临时目录。主执行者重新运行仓库副本，普通 Python 与 `-O` 各 **43 tests passed**（均无 Docker/数据库操作），`git diff --check` 通过。未将凭据、资源登记或私有诊断文件加入仓库；功能验收与资源清理状态继续分开。

> **2026-11-14 授权本地提交：功能验收通过，资源清理未完成**：按用户明确指示，将已复核的 T11 权限围栏修复、清理器及文档精确本地提交；不以此次提交代表 T11 全部签收。提交前再次核对 backend/frontend/SDK 的1516个执行文件与最终完整门禁清单一致，无代码变化；清理器收录于 `scripts/maintenance/r4b_20261113_cleanup.py`，对应隔离测试与源码一并版本化。容器、卷、私有登记/凭据/诊断收据保留，资源完整身份及后续入口见 `docs/development/capa-d4-local-text-delivery.md`。7个bind仍须在daemon所在环境核实，之前不执行清理、不修改或停止其他容器。既有功能门禁结果与清理器本次检查分开记录，远端CI/生产/模型/部署未开启。

> **2026-11-13 清理器挂载归属复审，清理仍未完成**：按用户要求重新区分 named volume 与 bind。只读枚举准确确认容器完整ID、目标卷准确名称及双方owner和唯一 named-volume 消费者；发现旧清理器将 daemon VM 的 Source 用 macOS `Path.resolve` 验证，成功或失败均不能证明 daemon 挂载身份。私有清理器已改为关联/可信排除/未确认三态：named volume 用准确名称、local无选项驱动和Docker返回身份核验；bind 缺 daemon canonical/mount-ID 证据时明确未确认，不凭路径差异排除，也不称已关联。新增3项namespace反例及审计状态反例先RED后GREEN；最终独立规格→质量复核通过，主执行者当前普通/-O各 **43 mock tests passed**。新只读dry-run（`t11-owned-cleanup-failure-1794583188095072000.json`）实查 **31容器：1相关named引用、25排除named引用、7未确认bind**，结果 INDETERMINATE，未执行apply、未修改或停止其他容器；本任务容器/卷/凭据保留。功能验收仍是下述已通过结果，未改应用代码，不能用旧清理器测试替代本次43项及新dry-run。T11资源清理、最终签收与提交仍未完成；不要求用户猜测Docker Desktop路径映射。

> **2026-11-13 T11 当前完整门禁通过，资源清理受阻**：修正过期 T1 路由断言后重新冻结1668文件（manifest SHA256 `2121f48164e401434111017143994ffa71ab7171c7f769d94cca7eb41943663e`，前后一致）。当前 `make check` exit0：后端 **4537 passed /4 skipped /19 deselected /6 warnings**（`t11-gate-4tid0cqp/api-20261113T135507265334-receipt.json`；skip 为未配置 Redis 与3个未启用 E2E_MODE，正文22/SDK14/旧CLI3节点实际通过），SDK unit **562**、loopback **16**、wheel **1** 无skip，前端类型与构建通过；browser **11 passed /0 skip**（`t11-gate-ocvooate/browser-20261113T145115915267-receipt.json`），pure **307 passed /3 warnings**，前端 **741 passed /88 files**，E2E TypeScript 通过。此前首轮全量1失败及测试修正记录见下。整片规格→质量复核通过；当前源码的恢复与停止权限围栏仍未本地提交。测试后专用实例无客户端、临时租户和迁移库；仅查询的清理 dry-run 因其他容器 **2 个 bind 源无法在宿主解析**，不能证明卷唯一消费者而 fail closed（`t11-owned-cleanup-failure-1794581863341896000.json`、私有诊断 `t11-mount-diagnostic-1794581996632589000.json`）。本任务容器、卷、凭据与全部证据保留；待可信路径映射/可验证挂载后重试，未执行删除。远端 CI NOT_RUN；不合并、推送、部署或启生产/模型。

> **2026-11-13 T11 首轮完整门禁失败并修正过期测试**：冻结1668文件首次 `make check` 的后端为 **4536 passed /1 failed /4 skipped /19 deselected**（`t11-gate-woaltgfr/check.log`），前端阶段未执行。失败的 T1 测试仍要求正文 handler 不存在，与 T9 已实现的路由冲突；独立纯模式复现后仅更新测试为唯一 GET 路由/handler 断言，默认关闭、早404零下游与 metadata 检查不变，生产代码未改。独立规格/质量复核通过，当前该文件 **100 passed /3 warnings**。首次冻结前后哈希一致；须重新冻结当前代码并重跑完整门禁，不以首次通过项代替。

> **2026-11-13 T11 整片双复核通过，准备冻结门禁**：停止控制末次撤权真实20 RED→20 GREEN，锁冲突/新成员8项、业务写锁序3项、旧 metadata 与撤正文/FMEA/插件后停止4项均实跑通过；独立规格与质量复审无未关闭 Critical/Important。恢复围栏、来源先授权及旧测试注入适配此前综合 **218 passed /6 warnings /0 skip**，该结果早于停止围栏，完整门禁必须以当前源码重跑。停止控制在所有 profile 遇并发权限维护可短暂返回固定503，不依赖正文/FMEA授权；恢复锁历史元数据的线性成本及缺大历史性能证据需交接。尚未完成冻结完整门禁、资源清理或本地提交。

> **2026-11-13 T11 停止控制末次权限围栏**：整片质量复核发现 pause/cancel、blocked cancel 与重放在最后控制权检查后可并发撤权，真实 **20 failed→20 passed**（`test-1794573785078409000.log` → `test-1794573995535319000.log`）。统一所有 profile 只锁控制目标标量和操作者 CAPA/GROUP/工厂/产线权限，不分类正文任务、不读取正文/FMEA/grant，锁后重新核原控制权；冲突回滚固定503。写者先锁及新成员插入 **8 passed**（`test-1794574181237904000.log`）、三类真实业务锁序 **3 passed**（`test-1794574275544115000.log`）、旧 metadata 与撤 FMEA/grant/plugin 后停止 **4 passed**（`test-1794574352140930000.log`）。独立规格复审通过，质量复审及当前冻结综合/完整门禁仍待；旧 metadata 正常语义不变，但并发权限维护时可能短暂503。

> **2026-11-13 T11 恢复围栏复核与回归**：先授权来源再读取的忙闲侧信道真实 **3 failed→3 passed**（`test-1794572437403034000.log` → `test-1794572515539574000.log`），旧锁注入及 FMEA/正文锁序 **11 passed**（`test-1794572737081361000.log`）；恢复、正文及旧控制冻结综合 **218 passed /6 warnings /0 skip**（`test-1794572833851594000.log`）。整片规格复审与恢复围栏专项质量复审通过，但整片质量复核另发现 pause/cancel 最终控制权撤销窗口的静态疑点，正准备真实双事务验证；整片未签收。恢复会对报告现有历史 proof/revision/verification 元数据逐行加锁，成本随历史增长，冲突可能暂时 503，尚无大历史性能证据。

> **2026-11-13 T11 恢复围栏修复及待关闭来源侧信道**：末次授权撤销真实 RED（restart 5 failed `test-1794570766819150000.log`；checkpoint 4 failed/1 passed `test-1794570816993001000.log`）；局部围栏后新并发 **14 passed**（`test-1794571274822553000.log`）及身份/FK插入 **3 passed**（`test-1794571424415019000.log`）。综合旧链回归因旧同步注入与新增行锁互等，在 24 passed 后失败并卡住，779s 后仅终止该 pytest（`test-1794571476601298000.log`），凭运行前零租户与完整 ID/slug/schema 精确清理该次唯一残留，复核客户端/临时租户/迁移库均0；旧测试须改成真实锁竞争，不得计作通过。质量审查提出换源前置侧信道，独立实跑 **3 failed**（`test-1794572437403034000.log`），确认未授权 B 和已撤权 A 仍被提前读取/锁定；正在修复。整片尚未复核通过、未冻结或签收。

> **2026-11-13 T11 整片规格复核发现待验证竞态**：受限 restart 及 checkpoint 的最终授权/控制权重验与 commit 之间，可能并发撤权或换源；这会影响新 run/checkpoint 与成功审计的零写合同，不等同于已证明正文泄漏。正在准备独立真实双事务反例，确认并关闭前不冻结 T11 完整门禁、不签收整片。

> **2026-11-13 T11 开始**：T10 已精确本地提交 `ea7d2814`；进入 T11 前工作树干净。正在进行整片独立规格→质量复核，之后冻结当前执行文件并按计划运行完整门禁；现有专用测试资源保持登记与隔离。远端 CI、生产、模型及部署均未执行。

> **2026-11-13 T10 双复核与当前门禁通过，待本地提交**：正常管理员/员工及固定接收器均经真实数字回环 TCP；13 个场景参数化为22个必选节点，与实际 wheel 的旧 SDK 14节点及旧 CLI 3节点在受控 runner 中 **39 passed /6 warnings /0 skip**（`t10-wheel-gate-qirhgx2p/gate.log`）。旧 CLI 另以 JUnit 核验三个精确节点 **3 passed /0 skip**（`test-1794570408427304000.log`）；当前 CI pure 分类 **307 passed /3 warnings**。独立规格→质量复核通过；初审发现并修正员工/admin ASGI 非真实 TCP、blocked 指纹与只读窗口证据缺口，代际快照 fixture 曾因 maintenance 状态两次失败，按正常恢复 active 后实跑通过。测试后专用库 head `20261113_d4_recovery`，无客户端/临时租户/迁移库。T11 整片冻结门禁、文档与精确资源清理仍待；不合并、推送、部署或启用生产/模型。

> **2026-11-13 T10 规格初审未通过，补证中**：固定接收器正常 TCP、来源范围、故障注入、blocked 竞争等阶段测试已执行；初审指出部分员工/admin 请求实际使用 ASGITransport，不能称全程 TCP，须改真实回环后重新验证。当前角色/工厂/产线/暂停/旧 epoch、blocked 指纹不变和竞争胜者零授权、各运行窗口只读快照亦需补齐。finish 已提交后的坏 JSON/超限/断连及父 grant 过期新组合 **3 passed /6 warnings**（`test-1794569406970310000.log`）；此前声明测试因员工缺 CAPA EDIT 在来源检查前被拒，补测试身份并先证明正常声明后 **2 passed /6 warnings**（`test-1794569070202922000.log`），不改生产校验。T10 未验收、未提交，所有早期结果只作阶段证据。

> **2026-11-13 T10 实施中**：正常策略固定接收器真实 TCP 主链 **1 passed /6 warnings**（`test-1794568572357833000.log`）；新增 CI 13 个精确必选节点的合成 JUnit 反例已 RED→GREEN，runner 纯测试当前 **64 passed /3 warnings**，保留旧 SDK 节点检查。其余 12 个真实场景、分类、独立规格和质量复核尚未完成，不以主链通过代替整项验收。

> **2026-11-13 T10 开始**：T9 已精确本地提交 `be232bfe`，进入 T10 前工作树干净。下一步按计划实施正常策略真实 HTTP、来源权限反例及 CI 必选节点分类；不以 T9 阶段测试代替 T10、T11 整片验收，不开启生产或模型。

> **2026-11-13 T9 双复核与冻结回归通过，待本地提交**：受限正文经正常授权、只读有界快照、最终来源与权限围栏后，以 no-store 响应交付；receipt 与 `release_committed` 审计提交后才返回。固定接收器真实 restart 重读当前事实并取得新 receipt，旧 token/receipt 不可复用。授权撤销与锁序问题均真实 RED 后修复，T9 局部授权锁冲突回滚并固定返回脱敏 503，不改通用业务权限服务；并发权限维护期间可能暂时无法交付。独立规格→质量复核通过；当前冻结 T9/T8 综合 **144 passed /6 warnings /0 skip**（`test-1794567063087446000.log`），旧 metadata 控制/消息/checkpoint/CLI **181 passed /6 warnings /0 skip**（`test-1794567632898362000.log`），JUnit 唯一节点分别为144/181。固定接收器 SHA256 不变（`3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21`），测试后专用库客户端、临时租户、迁移库均0。T10 正常策略完整 HTTP/CI 分类及 T11 冻结完整门禁仍待实施，不合并、推送、部署或启用生产/模型。

> **2026-11-13 T9 锁竞争修复双复核通过，综合回归中**：末次授权后撤销用户/FMEA 权限真实 RED **2 failed**（`test-1794566101986946000.log`）；新增围栏后又真实发现工厂关联替换、CAPA 审计及用户混合更新的锁顺序冲突，均保留失败日志。限定 T9 的授权行 `NOWAIT`，冲突时回滚并返回不含正文的固定 503，不改通用业务写服务；真实并发 **14 passed /6 warnings**（`test-1794566901866497000.log`），实际租户 9 个父子 FK 即时约束 **1 passed**（`test-1794567024817108000.log`）。规格复审和质量复核通过，修复后的冻结 T9/T8 综合回归尚在运行，T9 未签收、未提交。并发授权维护时可能短暂 503，成功后才能继续领取正文；正文/receipt 均不会在冲突时提交。

> **2026-11-13 T9 规格复审通过，质量问题待复现**：受限 restart 新事实/新 receipt、真实日志、跨租户、真实维护代际、编码后撤权和实际锁等待等经独立规格复审通过；最新 25 项组合及日志、维护、跨租户单项分别通过，冻结综合回归正在运行。独立质量复核提出员工权限在最终复核后、正文/receipt 提交前可能并发撤销，尚为静态推断，必须真实双事务复现并关闭后复审；T9 未签收、未提交。

> **2026-11-13 T9 候选与规格初审**：正常 API、固定接收器 restart 新事实/新 receipt 与撤权停止链等阶段组合 **17 passed /6 warnings**（`test-1794564866033992000.log`）。真实并发反例先发现末次节点检查后变更仍返回 200（9 passed /1 failed，`test-1794564422275431000.log`），已增加来源父行锁并复测；但规格初审指出先前测试只凭时间推断锁等待，仍须数据库层直接证明。初审未通过：编码后末次撤权/证明/坐标、成功 audit 零新增、真实日志脱敏、实际 256 KiB 膨胀、跨租户/代际/ACL 等证据仍在补；17 项不是最终验收，正文服务未提交。

> **2026-11-13 T9 开始**：T8 已本地提交 `9195c1f5`，工作树在进入 T9 前干净。专用实例核验 head 正确且无客户端、临时租户和迁移库；首个正常授权真实 API 测试因正文路由尚不存在返回预期 404，真实 RED **1 failed /6 warnings**（`test-1794563967976255000.log`）。候选的正常交付、快照后变更与撤权停止链阶段性 **4 passed /6 warnings**（`test-1794564181863725000.log`），随后实现有调整，该结果不代表当前最终代码通过。正文交付及受限重开后的事实重读和新 receipt 正在实施，尚未验收；后续仍须独立规格、质量复核与当前代码回归。

> **2026-11-13 T8 与受限恢复验收通过，待本地提交**：最终完整后端 **4398 passed /4 skipped /19 deselected /6 warnings**，exit 0；4 skip 分别为未配置 Redis 与 3 个未启用 E2E_MODE 的入口，14 个必选 SDK 节点全部通过（`backend-gate-tbjtyvpy/api-20261113T090552194752.log`）。专项节点集合精确核对 **102 passed /6 warnings**，旧 CLI 三个指定节点 **3 passed /6 warnings**，CI pure 分类 **289 passed /3 warnings**。首次完整后端的 7 项失败源于旧测试替身缺真实授权 UUID，先复现、修夹具并独立复核后重跑完整门禁；不将首次失败记为通过。T8 全体及受限恢复分阶段规格、质量复核通过；接收器 SHA256 仍为 `3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21`。末次专用库 head `20261113_d4_recovery`，客户端、临时租户与迁移库均 0。受限 checkpoint 只保留控制信息并绑定原父授权；正文真实重读、新 receipt 和旧 receipt 拒用必须在 T9 实测，尚未完成。不合并、推送、部署或启用生产/模型。

> **2026-11-13 T8 最终门禁进行中**：受限恢复增加 checkpoint、restart 和固定原任务父 grant 的绑定三表；新旧类型隔离、旧凭据失效、并发幂等及当前授权重验已完成独立规格和质量复核。当前候选精确收集并运行 **102 passed /6 warnings**（`t8-recovery-final-20261113-c.xml`），旧 CLI 实际进程 **3 passed /6 warnings**（`t8-cli-final.xml`）；CI pure 分类 **289 passed /3 warnings**（23.89s，前两次因工作目录错误未启动测试）。完整后端首次运行 **4391 passed /7 failed /4 skipped /19 deselected**（`backend-gate-_a373bvg/backend-gate.log`）；7 项为旧权限适配器模拟 grant 缺真实模型必有的 UUID，修正夹具后禁网络/数据库纯测试 **20 passed**，独立复核确认未改生产授权或削弱断言。现已核对专用库 head `20261113_d4_recovery`、客户端/临时租户/迁移库均 0，并重新运行完整后端门禁；结果未出，T8 未签收、未提交。正文恢复后真实重读和新 receipt 属 T9，不能以旧 receipt 作凭证；不启生产或模型。

> **2026-11-13 受限 restart 阶段双复核通过，进入整体验收**：实现原子停止旧 run/创建新 run、固定入口消息、独立关联和幂等重放；真实 API 覆盖 ACK 前后、旧 token/旧 batch、同异键并发、撤权/换源、五写点故障回滚与类型/关联篡改。规格审查发现并经真实 RED→GREEN 修正末次撤权、缺失/损坏关联、连续水位、多次 restart 历史重放及并发授权换源；最终 CAPA/FMEA 快照后撤权 **2 passed**，历史重放及水位 **2 passed**，两个并发换源窗口 **2 passed**。旧控制/消息/授权中间版本 **162 passed /6 warnings**（后续有末次撤权修正，不冒充最终版本）。规格及质量复审通过；阶段4仍须冻结最终代码完成真实正常 API、旧链/SDK、强制节点及 T8 全体双复核；未提交、未进入 T9，真实正文再读取与新 receipt 留待 T9。

> **2026-11-13 受限 checkpoint 阶段双复核通过**：实现控制位置创建/读取、有界消息 SQL、类型分派、活动与新端点固定脱敏 422。独立复核发现并修正写入末次撤权、损坏 pointer 重试、真实访问日志路径泄漏及正文身份缺失时旧类型回退，均有对应真实 RED→GREEN；大量历史、跨租户、blocked cancel、授权/策略失效、活动分页等有实际验证。最终新旧 checkpoint API/服务组合 **69 passed /6 warnings /214.87s**（`test-1794552178035062000.log`），独立规格和质量复审通过；日志测试确认正常 access log 保留且恢复路径/查询哨兵不输出。此阶段未提交，正文 restart、新运行及 T8 整体仍未完成；下一步实现原子 restart 和固定消息入口。

> **2026-11-13 受限恢复迁移阶段双复核通过**：新增独立 checkpoint/restart 模型与 public/tenant 双迁移，保留旧 FK 及 tv001–tv007；专用临时迁移库实际缺表 RED **2 failed**，新旧迁移/parity 组合 **66 passed /4 warnings**，逐表有证据回退拒绝 **4 passed /4 warnings**，其他历史前驱 **46 passed /4 warnings**。规格复核要求补 tv007 字节冻结，质量复核发现浅克隆不含历史 Git 对象；新旧两份冻结测试改用经独立核验的签收哈希清单，纯检查 **2 passed /3 warnings**，双复核通过。首次组合中六项历史夹具失败因 public 固定旧版本而 tenant 使用新默认 head，已固定旧 tenant 前驱后重跑；不把失败当通过。已对同一登记独占测试库执行 `prepare`，head 实测 `20261113_d4_recovery`，临时租户/客户端/迁移库均0；未改业务库或清理未知资源。下一步 checkpoint 有界服务/API/活动；T8 仍未签收或提交。

> **2026-11-13 受限恢复合同已复核，实施中**：用户选择为正文任务增加最小受限恢复 checkpoint，而非借用旧 summary checkpoint；[设计](docs/superpowers/specs/2026-11-13-agent-d4-restricted-restart-design.md)与[补充计划](docs/superpowers/plans/2026-11-13-agent-d4-restricted-restart.md)经独立规格/质量与计划复审，已闭合类型解析、活动/dispatch、幂等重放、blocked 取消、最终控制权重验、有界消息 SQL 和局部脱敏 422。此为合同/计划复核，不是实现或测试通过；开始模型及双迁移 RED，保留 T8 未提交候选，完整恢复和 T8 验收前不进入 T9、不提交可 claim 的不完整候选。T9 才能见证新运行重新读取正文并取得新 receipt，旧 receipt 不作凭证。

> **2026-11-13 T8 候选待 restart 合同决策**：已实现两层来源范围、blocked 请求指纹、当前证明重验、停止/恢复权限分离及正常策略真实 TCP 消息哨兵。独立规格审查发现并经真实 RED→GREEN 修正请求重放先诊断、P/T 会话缓存、grant 提交前撤权、旧修订/验证及并发换源、投递 kind 等缺口；当前焦点与真实 API **42 passed /6 warnings /84.36s**（`test-1794545366617413000.log`），旧链中间版本 **229 passed /4 warnings** 不冒充最终版本。规格复审确认所发现缺口已接线，但正文正向 restart 存在合同冲突：现有 checkpoint 必须旧 summary/internal 收据，正文 profile 不能借授 summary，计划禁止泛化旧 checkpoint。换源 restart 负向拒绝已测试，不代表新 epoch 正向成功；已询问用户选择暂不支持或设计新受限 checkpoint。用户决定前 T8 未签收、未提交、不进入 T9；质量复核与最终旧链回归仍待完成，正文 GET/生产/模型均未启用。

> **2026-11-13 T7 双复核通过**：新增独立正文策略槽和服务端精确 admission 选择，策略快照从 app state 进入 DB session；单独 peer gate、受信 profile 投递声明和 HMAC 绑定不扩展旧 metadata。为接入既有选择调用，最小修改计划清单外 `task_service.trial_for_target`；更新 T1 对新 profile 未知的过时断言，保留 baseline DENY。正文-only 仍不能通过旧 summary/grant ready 防线，未使正文可 claim。规格复核指出旧 metadata 的 restricted/raw 消息声明及正文 token 截期/重启绑定测试缺失，已补并复审通过；质量复核通过。最终纯组合 **213 passed /3 warnings**；修正声明之前专用库旧链 **97 passed /4 warnings**、策略路径修复后 admission **8 passed /4 warnings**，不称为最终完整 DB 运行。祖先 symlink 真实 RED 后改逐组件 no-follow；文本 token/绑定测试使用内部接缝而非真实 claim。T8 首次可 claim 的真实 HTTP 消息哨兵仍为强制提交门禁；不启生产或模型。

> **2026-11-13 T6 双复核通过**：新增服务端固定启动消息门禁，在最终身份/准入刷新后、消息 claim 标记或审计、history 输出及真实批次 ACK 水位变更之前检查全部相关消息；旧 profile 语义不变，未开放正文准入。独立规格和质量复核通过，无未关闭 Critical/Important。纯合同真实 RED **4 failed → 4 passed**；Lead 当前独立纯检查 **4 passed /3 warnings**，专用库消息与 checkpoint 回归 **89 passed /4 warnings /239.99s，exit0**（`test-1794541243132929000.log`），其中五个负向及固定字面量正向使用服务端身份 seam 注入未来 profile，不代表真实准入。首次可 claim 的真实 API 哨兵见证仍是 T8 必须条件；下一任务 T7，正文与生产默认关闭。

> **2026-11-13 T5 双复核通过**：接续已有固定 stdlib 接收器及受监督启动器草稿，独立规格与质量复核均通过，未发现未关闭 Critical/Important。Lead 在获准的自有数字回环环境独立运行两份 CLI 测试 **104 passed /7.89s**；先前误用 `check-ci-pure.py` 的 74 failed /30 passed 为框架主动禁止 socket，不作为行为证据；沙箱内绑定拒绝的 77 failed /27 passed 同属环境限制。接收器 SHA256 `3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21`，启动器 `3d4bff2ff2e633eb2da8d6e80a52f68c4d6adb1dd5cbb187b190f9a6a5b961da`；SDK 传输差异见[对照文档](docs/development/d4-text-receiver-wire.md)。此为本地 wire 验证，正常策略真实 API 闭环仍待 T10；下一任务 T6 消息门禁，必须先于准入，不启生产或模型。

> **2026-11-13 T4 双复核与当前回归通过**：独立规格复核发现最后来源重验与签发之间的撤权窗口；真实双事务先见 200 而非403，修复后通过。质量复核再发现修订冲突和文本不匹配诊断期间撤权分别返回409/200；两项真实 RED 后补诊断前重验，另覆盖已有 proof 冲突。最终规格复审及质量复审通过，无未关闭 Critical/Important。测试夹具一次 rollback 后访问过期 ORM 触发 `MissingGreenlet`，改为先保存 UUID 并在新事务计数后，三项撤权测试 **3 passed**，已有 proof 冲突 **1 passed**。当前代码独占库新鲜 `tests/capa` **1276 passed /6 warnings /388.58s，exit0**（日志 `test-1794540341431944000.log`），离线写站点及合同 **111 passed /3 warnings**；运行前专用库客户端、临时租户及迁移库均0。此前一次 34 项焦点与另一执行者测试重叠，不作隔离验收证据。未跑完整 make check/前端/远端 CI，不代表整片验收；下一任务 T5，保留其已有未提交草稿，消息门禁仍须先于准入。

> **2026-11-13 T4 实现候选，待独立 SPEC→QUALITY**：员工创建验证新增严格可选 `source_declaration`，仅 POST 响应增加 `source_proof_issued`。声明分支使用真实 Request、runtime/body flag、dev 业务绑定和数字回环（拒代理头）；先 FMEA 当前可见性后关联/坐标/节点诊断，固定 403 与无敏感回显的 422，基本来源格式 400、未记录字段修订冲突 409。显式合格声明同事务 bootstrap/签发/安全审计，绑定新验证 server 时间版本、最新修订和源节点 HMAC；新证明 supersede 旧 active，同验证 helper 重复调用幂等。成功 PATCH 永久 invalidated_at，含同时间戳/同事务 ABA；无声明、D4/D5/D8、原审计/outbox/证据 RESTRICT 沿用原语义。必要范围扩展仅为 FMEA 内部 helper 的已授权节点诊断选项（默认行为保留），避免 CAPA 复制节点 SQL；相关[开发文档](docs/development/capa-d4-local-text-delivery.md)已同步。未改计划 checkbox，未提交、未进入或修改 T5，其他 Agent 的接收器文件不纳入本候选。
>
> 本轮实际证据：原验证路径基线 **46 passed/4 warnings**；新夹具首轮误用运行 flag 名导致23个 setup error，不计行为 RED。修正后 **19 failed/4 passed** 的真实 RED，首轮 GREEN 加旧验证路径 **69 passed**。扩展并发撤权/范围/ABA 首跑 **76 passed/2 failed**，两失败为重复插入 provision 已创建的 UserProductLine；改为核验现有映射，定向 **3 passed**。自审补非法 UTF-8/控制节点标识，真实 **2 failed/4 passed → 6 passed**；非对象 source_ref 新分支400/旧分支422顺序真实 **4 failed → 4 passed**。修正前完整受影响组1328 passed单独保留，不替代最终证据。
>
> **最终冻结7个源码/测试文件**重跑 `tests/capa`＋CAPA投影/草稿/推荐/重复确认/lesson embedding相关回归：**1332 passed /6 warnings /380.11s，exit0**，无 skip/xfail/xpass；私有日志 `test-1794537261393083000.log`。离线写入站点/验证Schema/D4合同 **117 passed /3 warnings，exit0**；`git diff --check`通过。六警告仍为既有Pydantic3、logfire1、websockets2。`/private/tmp/openqms-d4-text-20261113-RUUaxY/t4-final-source-manifest.json` SHA256 `a8e50f0264fdee797c06c32ff2bc50b8979134b75bbcfd0d219e1390a7862629`，执行前后源码一致。测试始终使用同一授权 owned 实例/当前新鲜测试库，未 reset 旧失败库；最终 owner/loopback/status 核验通过，public head正确、临时租户0、当前/旧测试库及哨兵client0、UUID迁移库0，资源保留供后续验收。未跑完整make check/前端/远端CI，不声称整片或生产准入；默认正文关闭，下一步仅交Lead独立规格再质量复核。

> **2026-11-13 T3 已签收**：已完成独立规格复核及质量复核，写站点粒度守卫与节点 JSON 规范化两项发现均经限定复核关闭。实施者在新鲜独占库完成受影响回归 **1319 passed /6 warnings/287.41s，exit0**；Lead 独立新鲜运行两份 T3 数据库测试 **44 passed /4 warnings/15.24s，exit0**，私有回执 `test-1794535237212363000.log`。源码 manifest 与整套运行一致，未将历史或夹具错误算作通过。默认关闭与 T4 及后续边界不变；下一任务为显式验证声明签发，不合并、不推送、不部署。自有资源登记 `/private/tmp/openqms-d4-text-20261113-RUUaxY/resource.json` 保留供后续计划内验收，旧失败库保留诊断；无业务数据库操作。此为 T3 验收，不是 R4b 全片验收或当前完整 make check。

> **2026-11-13 T3 接续实现与新环境回归完成，待 Lead 最终签收**：用户明确授权替代独占测试资源。普通 Docker socket 查询被沙箱拒绝，正式权限查询确认 Desktop 29.9.2 可用；一次镜像检查自动审核超时，随后获准运行私有控制器，使用缓存 PG15 新建随机 owner 容器/专属卷/数字回环。资源登记 `/private/tmp/openqms-d4-text-20261113-RUUaxY/resource.json`，完整容器 ID `706d28957c45595e0c8b3e056558ed1c8bbc55b2453345354e8ea83d9d4058ad`，`127.0.0.1:60114`；凭据只存私有 0600 文件，不借其他实例。原失败库 `qms_d4_t3_test` 保留；当前新鲜验收库 `qms_d4_t3_ae3ae21953ed_test` 已从空迁移至 `20261109_d4_text_delivery`。最终只读核验临时 tenant=0、UUID 迁移库=0、当前/旧测试库及哨兵连接=0；容器、卷与证据保留供后续验收，不清理其他资源。
>
> 本轮真实复现审核发现建 CAPA 缺 `factory_id` 的 NOT NULL 失败，最小修复为从 finding 及同厂关联 audit plan 继承工厂/产品线，保留现有 AUDIT CREATE/工厂入口规则，不增加客户端坐标或绕过约束。来源夹具补真实产品线前置并使用唯一代码；旧 `outcome_review_support` teardown 按本 fixture report_id 清理新增修订，生产 `RESTRICT` 不变；旧 audit unit 更新异步 scalar/修订 helper 接缝并断言坐标。新增真实租户提交/回滚、双写序列化，以及节点预算与读取之间另一事务提交 oversized/duplicate/revoke 的验证。规格复核提出同文件新增 writer 漏检，新增反例真实 **2 failed** 后改为文件＋所属函数＋AST 写形态及数量白名单，离线最终 **11 passed /3 既有 Pydantic 警告**。质量复核提出 PG 高精度有限 numeric 解码成 infinity：真实 PG **1 failed** 后，节点规范化窄捕获 ValueError/TypeError/UnicodeError 并固定拒绝，finally 来源重验保留。独立复核是否最终签收由 Lead 另记；未勾 T3 checkbox、未提交、未进入 T4。
>
> 实际失败与最终证据：首轮 **16 passed /1 failed /20 setup errors**（业务 NOT NULL 与来源夹具缺产品线分别记录）；补齐后来源20项通过，T3＋旧 audit 一度71项通过。首次完整受影响集 **1298 passed /21 errors**，20项为固定产品线重复、1项为旧 teardown 未清新 RESTRICT 修订；修正后复用该失败库为 **1315 passed /3 failed**，只读证实唯一残留正是失败 teardown 的报告，其 current analysis/decision 使三条旧不按报告过滤的断言取错行。未重置该库或修改这些旧断言，保留证据并在同一自有实例新建空库。最终同一受影响集加 numeric 用例 **1319 passed /6 warnings /287.41s，exit0**，无 skip/xfail/xpass；包括 `tests/capa`、旧 audit、CAPA 投影/草稿/推荐等相关回归。日志 `test-1794534876615552000.log` 位于上述私有目录；11个源码/测试文件 manifest SHA256 `3f976509bb245d853f7ddb0e06bae5843a84483d2a5665ad7a0f57f66850b7a5` 前后不变，`git diff --check` 通过。六警告为既有 Pydantic 3、logfire 1、websockets 2。未运行全站 make check、前端或远端 CI，不把此受影响回归称整片验收；正文/模型/生产准入仍关闭。相关已实现边界见[开发文档](docs/development/capa-d4-local-text-delivery.md)。


> **2026-11-13 T3 接续中，数据库验收受阻**：HEAD `d4106c2a`；保留交接时两处 tracked 修改及四个未跟踪 T3 文件，继续补充 FMEA 先鉴权/标量范围/有界节点读取、审核发现建单修订接线和离线写站点检查。独立规格预审未通过：发现采纳 NULL→空串漏记、按旧 HMAC 去重可复用修订及静态扫描遗漏字典写入；实施者已修正并补离线回归，尚待复审。Lead 新鲜运行 `python -B scripts/check-ci-pure.py tests/ci/test_d4_root_write_sites.py -q --tb=short`：**9 passed / 3 个 Pydantic 弃用警告**；这是无数据库证据，不代表 T3 验收。原登记私有目录 `/private/tmp/openqms-d4-text-20261110-gnf1_jut` 不存在，当前 Docker socket 拒绝访问；未连接、创建或删除数据库及容器。需恢复已登记独占资源或明确提供本任务授权的替代资源后，验证节点 SQL 与并发、三条真实写路径、A→B→A、同值、事务回滚及旧业务/embedding 回归。审核发现建单原路径疑似缺非空工厂坐标，须先在授权数据库复现并核实，不绕过约束。T3 未签收、未提交；正式规格与质量复核及后续任务尚未完成，不使用历史测试结果替代当前证据。

> **2026-11-11 T3命名空间身份补充已获用户确认**：原T3执行者实际核single/public无tenant UUID，按要求在任何代码/测试/DB操作前停下，未产实现。用户明确选择“显式区分tenant与single_public”：field_hmac绑定服务端类型化命名空间（真实tenant UUID或single_public）、report UUID、null/空区分及原文，不伪造UUID、不加表、不跳过single旧业务修订。两类须域隔离，身份不可由HTTP提供；single/public仍不得进入正文profile，不增加来源权限或模型/生产准入。补充已写回[规格](docs/superpowers/specs/2026-11-08-agent-d4-root-cause-local-delivery-design.md)与[计划](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)T3示例。下一步新的T3执行子代理按此明确合同恢复RED→GREEN及旧业务回归，仍须独立双复核。T1/T2技术签收保留，不把命名空间补充当T3完成。

> **2026-11-11 T2技术签收，进入T3**：候选`ea300bb4`经独立SPEC→QUALITY依次通过，Critical/Important/Minor技术问题均0；Lead在提交后串行真实PG焦点 **35 passed/4 warnings/92.09s，exit0**，原候选窄回归101 passed及恢复35 passed另列为各自证据，不冒充Lead全量。19文件范围与8冻结资产保持，public/tenant新head、六metadata表、旧前驱/parity及非空回退拒绝已签收；未实现来源业务/授权/正文API。回退边界明确：tenant依旧受控维护排他advisory锁与shared业务事务锁保护；public普通Alembic无该锁，本片只验离线无writer，不认证在线生产并发回退。过程限制单独披露：Lead及部分子代理若干调用错误携带sandbox_permissions字段，违反最新“省略该参数”要求；无审批提示/实际权限拓宽不等于纪律合规，不能以技术review通过掩盖。后续必须省略该字段。下一步按[计划](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)T3先鉴权的FMEA标量/有界节点读取及三写路径修订TDD，正文flag/profile仍关闭，不main/push/模型/生产。下方候选/中断条目保留为历史。

> **2026-11-10 R4b R2 Task2 实现候选，待 Lead SPEC→QUALITY**：仅新增六张 `TenantBase` 元数据表、public `20261109_d4_text_delivery` / tenant `tv007_d4_text_delivery` 自含等价增量及前驱/parity接线，不改旧业务/grant/receipt列或trigger。proof到实际验证表采用RESTRICT；源FMEA/节点及superseded_by不加删除阻塞FK；六表任一有行时两条downgrade均在任何DROP前拒绝。新增tv006专用`delivery_predecessor`状态，保留tv005–tv001全部既有前驱常量/状态；snapshot regeneration仍用原冻结public_head。tv001–tv006与快照/manifest相对签收`286d8e9f`逐字节/hash不变，`git diff --check`通过。迁移说明见[开发文档](docs/development/capa-d4-local-text-delivery.md)。无正文/签proof/源授权/API/SDK/frontend/worker/policy变更，不进入T3、不main/push/模型/生产；本条不签双复核、不改计划checkbox。
>
> 实际TDD与回归：现成Python通过私有`task2_runner.py`、登记独占PG串行UUID临时迁移库运行。原169行草稿先read核对真实接口，未当已有RED；`t2-red-public-01`真实空public/两旧分支/原merge升级后缺六表断言 **4 failed/12 deselected/4 warnings，exit1**（无collection/setup错误）。最小实现后`t2-green-initial-01` **30 passed/4warnings**。补逐表非空回退/约束验收首次`t2-green-expanded-01` **28 passed/1 failed/4warnings**，唯一失败是测试generic DATETIME与PG TIMESTAMP显示名比较，改为PG dialect编译比较并核对timezone/default/PK/UQ；非生产缺陷或有效行为RED。精确旧迁移/graph/PG15快照再生/parity/多租户回归`t2-regression-narrow-01` **95 passed/4warnings**；补六项其余元数据约束/全部guard先于DROP断言后，最终同八文件`t2-final-01` **101 passed/4warnings/251.79s，exit0**，其中新焦点35项，无skip/xfail/xpass；warnings为3项既有Pydantic class-config弃用＋1项logfire assert-rewrite。未重跑Task2后的完整make check/前端/SDK，前述T1冻结全量基线不是本候选全量结果。
>
> **2026-11-11故障恢复收尾**：新接手者完整读取实际19文件staged diff、T2合同及实现/测试后，用同一私有runner新鲜运行`t2-recovery-focus-01`，实际 **35 passed/4warnings/96.27s，exit0**，无skip/xfail/xpass；warnings仍为3项既有Pydantic class-config弃用＋1项logfire assert-rewrite，无真实失败、未改实现逻辑。测试前后独立核验tv001–tv006、snapshot及manifest共8资产的实际SHA256/字节，与`286d8e9f5d99a0e831729f8984117b6e9a469a25`、HEAD和index一致；同owned实例完整ID/owner/端点健康核验通过，最终UUID迁移库残留0、主测试库/哨兵client0。仅精确收尾本T2候选，不代签独立SPEC→QUALITY、不改计划checkbox、不进入T3；未重跑101项或完整make check/前端/SDK，历史回执不冒充本次运行。
>
> 失败/中断透明记录：曾误选整个`tests/migrations tests/test_multitenancy`广义回归，发现其后段可能调用普通db fixture即取消（SIGTERM，无完整汇总，不计GREEN）。私有日志50个pass进度/0E/0F；只collect重建302节点顺序，完整核首27项均mig_db_url、第28–51项为mig/纯测试，取消仍在readonly-controls迁移用例，普通db fixture未执行。取消遗留唯一已枚举且0client的UUID迁移库经精确核端口/完整containerID/库名后删除；最终行政catalog核临时迁移库残留0、主库/哨兵client0。未增加或删除容器/卷，不连接保护主库/哨兵本身，不访问旧SDK/业务实例；所有原始日志仅私有保留，未打印DSN/密码。

> **2026-11-10 T2资源边界已澄清，恢复真实迁移TDD**：T1签收后的完整冻结`make check`基线exit0/source unchanged（2504.85s）：SDK562＋16＋1全通过，backend4001 selected/3997 passed/4可选skip/6 warnings、零fail/error/xfail/xpass，前端tsc/build通过。Owned资源根`/private/tmp/openqms-d4-text-20261110-gnf1_jut`仅登记本片nonce容器/唯一卷/数字回环；启动曾因Docker事件模板.Status字段不支持及过期事件历史断言失败，当前健康、pg_isready、owner/ID/卷与check-test-db均已复验成功。T2原执行者发现mig_db_url实际上创建UUID临时数据库而非schema，按要求停在DB RED前，仅留下未运行测试初稿。用户已明确批准：同一登记独占实例内串行创建/精确删除qms_migtest_<UUID>_test，不增加容器/卷，不碰哨兵/业务/其他实例；已核临时迁移库残留0，预算写回[计划](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)。T2生产代码及迁移尚未实现，不把测试初稿当RED/GREEN；后续新执行子代理接手，完工仍须SPEC→QUALITY双复核。正文默认关闭，不main/push/模型/生产。

> **2026-11-10 R4b R2 T1双复核签收，开始T2准备**：用户已明确批准R2并选择子代理驱动。T1实现`3e2100d3`经独立SPEC→QUALITY依次通过，均无Critical/Important/Minor；Lead独立复跑权限/DTO/无socket ASGI **224 passed/3既有Pydantic警告**，另CI pure **278 passed/同3警告**。SPEC reviewer用进程内base middleware＋base routes重放12条early-guard均行为RED，再复跑候选224通过；不把此重放当亲历开发TDD。新合同/DTO、body baselineDENY、旧metadata目录冻结、默认关闭早404已签收；新profile仍unknown、无正文handler/生产许可，不代表源授权或整片交付完成。T2前置只读预检已核本地Unix Docker context/缓存PG15及public=`20261102_agent_mainline_merge`、tenant=`tv006_agent_read_tasks`单head；首次离线检查因-I导入路径漏配失败，修正检查脚本后通过，无应用改动/DB连接。下一步按[计划](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)登记新独占PG/卷与测试/哨兵库，再做六表迁移RED→GREEN；不借旧SDK资源、不main/push、不启正文/模型/生产。下方候选与待审条目是历史。

> **2026-11-10 R4b R2 Task1 实现候选、待规格/质量复核**：仅新增派生来源精确交集纯类型、安全叶子异常、内部只读合同和严格D4正文DTO；CAPA body能力在baseline仍DENY，旧metadata目录显式冻结为既有summary/propose，新text profile仍unknown。统一输出名`D4RootCauseTextProjection`，正文属性`text`（repr隐藏），内部声明`CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT`；`SourceProjectionContract`只有声明类型，无FMEA实例/读取服务/全局注册。新默认flag=false、policy file=None，专用runtime路径（含尾斜杠）在tenant/auth/body/DB前早404，runtime关闭或非dev同样拒绝；登记路径但未实现handler，flag开启不交付正文。无授权函数/SDK/frontend/worker/hash/trust集合/迁移/表/grant变动，无网络/DB/安装/服务器/Docker操作，未跑全量`make check`（本任务明确限纯/无socket ASGI）。计划checkbox不变，不代表Task1或整片已验收。
>
> TDD真实记录（均从worktree根运行现成解释器）：`/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -B scripts/check-ci-pure.py tests/services/agent/permissions/test_d4_text_scopes.py tests/capa/test_d4_text_contracts.py -q --tb=short` 初次RED **113 failed/13 teardown errors/3既有warnings，exit1**（新模块/声明不存在；门禁测试缺flag导致Pydantic monkeypatch setup失败，该部分不作为行为RED）；修正测试注入后 **112 failed/1 passed/3warnings，exit1**（其中部分ASGI scope缺app，亦不作行为证据）。补齐有效scope后单跑 `... -B scripts/check-ci-pure.py tests/capa/test_d4_text_contracts.py -k early_guard -q --tb=line`，实际 **12 failed/85 deselected/3warnings，exit1**，失败为tenant/downstream故障哨兵触发或400非404，非collection/typo。实现后首次GREEN **221 passed/4warnings**（含一项新DTO protected namespace warning，已用精确保护名消除）；补HTTP UUID解析/严格digest边界、实际生产router无handler断言后最终 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -B scripts/check-ci-pure.py tests/services/agent/permissions tests/capa/test_d4_text_contracts.py -q --tb=short` **224 passed/3既有Pydantic class-config warnings，exit0**（旧permissions108＋新116，无skip/xfail）。默认关闭ASGI直接使用真实tenant middleware与故障计数，tenant/auth/DB/body/downstream均0，不以app依赖替换声称生产隔离；另以测试专用HTTP解析DTO及实际runtime router确认flag不创建handler。后续仅等待Lead独立规格复核再质量复核，不进入Task2。

> **2026-11-09 R4b计划R2按三项实施审阅修订，仍未执行**：用户要求修正P1消息门禁晚于准入、P2阻塞任务请求身份未保存、P2撤权后停止验收未具体化。[计划R2](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)将服务端消息门禁提前为T6，先于T7准入/T8正常claim/T9正文服务，并要求首次可claim提交同提交真实API哨兵验收（T8即创建早期harness，不等T10）；新增与grant无关的不可变请求指纹旁表`agent_task_source_requests`，blocked任务同事务存指纹但不产授权/run，同key同A返原任务、换B409，真实唯一键并发分支同样比较；停止与恢复分离，保留pause/cancel仅用户控制权，完整源重验只用于resume/restart，T9正文首次可用即实测“撤grant→正文GET拒绝→pause成功→resume拒绝→cancel成功”，停止0正文/源node读取，不能拿未实现路径404当撤权成功。自审11任务依赖/路径/链接，12个Python块AST通过；纯HMAC示例同A稳定/A与B不同（socket拒绝守卫），不等于数据库并发或权限实现验收。当前只改计划及本进度，不改规格业务边界、实现代码/迁移，不建资源，不启正文/模型/生产，不main/push；待计划复审和执行方式选择。

> **2026-11-09 R4b v6书面确认，实施计划已编写（尚未执行）**：用户明确选择“通过v6，进入实施计划”。[11任务TDD计划](docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md)按纯合同/默认关闭→五表双迁移→来源读取与字段修订→显式签发→固定接收器字节定稿→第二策略槽→两层来源授权→正文最终交付→服务端消息门禁→正常配置真实HTTP/CI必选→冻结门禁/交接清理排序；明确精确write scope、共享文件串行、逐任务规格/质量复核、A/B来源范围反例、无权者真实/虚构节点不可区分、旧metadata/SDK不扩权，以及新独占PG/卷/两库预算。自审覆盖v6条款、路径依赖和链接；10个Python代码块通过AST检查，纯DTO示例在socket审计拒绝下验证显式true/严格UUID，修正了JSON UUID严格模式示例及异常模块循环依赖风险。此为计划文本/示例校验，不是功能测试通过；当前仅计划、规格批准状态及本条进度三份文档，所有实现checkbox未开始，无代码/迁移变动、无资源创建、无正文/模型/生产启用，不main/push。计划审阅及执行方式选择后才开始T1，下方待审状态保留为历史。

> **2026-11-08 R4b 规格v6按用户来源权限复核修订，仍待审**：用户复核v5未通过，指出P1“证明换源可能扩大旧插件/任务授权”与P2“签发先查节点再补FMEA权限可形成存在性探测”。[v6规格](docs/superpowers/specs/2026-11-08-agent-d4-root-cause-local-delivery-design.md)补充：插件长期grant和任务grant分别显式保存精确派生来源范围（新增两张grant旁表，既有grant表不改），最终当前证明来源必须同时属于两层交集；新DTO只用于正文投影，不授FMEA查询工具，缺范围即拒，supersede/claim/resume/restart/新epoch不能刷新旧范围，换源须显式新授权/新任务；加入A/B同产品线、执行人都可读但任一授权仅A时B必须拒绝的验收。新声明签发结构校验后先查当前FMEA读取权及对象可见性，无权/不可见/不存在/不确定均固定403且不查节点、不写验证/证明；可见后才作关联/坐标/节点诊断，错误返回与成功前均复核，非声明旧流程不变。加入真实/虚构节点的状态码、正文完全一致和零写入/零节点读取验收。本轮仍仅规格与进度，无实现代码/迁移、无测试资源或正文启用，不main/push/部署；书面批准后才写实施计划。下方v5“技术闭合”仅当时局部自审叙述，不代表用户已批准或来源权限问题已获得最终签字。

> **2026-11-08 R4b 下一片规格v5，技术审阅闭合，待用户书面确认**：v4经两轮独立技术审阅与一次闭合复核，最终发现仅剩错误码与少量准确性/清单问题并能修——`source_ref`节点缺失/关联不符实际为400而非404/403，字段侧去空白须Python `.strip()`而非SQL `btrim`，创建专用响应不得改动列表/更新响应字段，迁移清单需钉head/revision精确行号。v5 accordingly：按实际异常映射拆分错误码（FMEA文档缺失404、节点缺失/关联不符400、跨工厂产品线403）；409仅新增创建端点专用映射；`source_proof_issued`仅创建专用子类；字段侧strip语义与D5闸口一致；补齐`test_agent_mainline_merge_db`/`test_agent_readonly_controls_delta`/`test_agent_read_task_delta`等精确断言行号。此前v4已修正验证版本仅绑标量字段、有界SQL谓词、可落地覆盖测试、来源投影/profile内部常量载体与节点canonical HMAC。复审确认C1/I2/I4/M6已闭合、I3/M5由v5闭合；本结论仅针对规格文本，不代表实现或用户批准。仅修订[规格](docs/superpowers/specs/2026-11-08-agent-d4-root-cause-local-delivery-design.md)与进度，未写代码/迁移、未建资源、未启用正文，不main/push/部署。仍待用户书面确认后才进入实施计划；下方SDK结果仍为已收口切片历史证据。

> **2026-11-08 SDK 本地整片验收收口**：SDK/真实normal-policy HTTP/Make与CI接线完成各任务规格→质量双复核，整片集成复核Approve；冻结 `9e54ad52` 的1612文件完整本地门禁通过（后端 **3881 passed /4可选skip**、browser **11 passed**、pure **278 passed**、SDK **562 unit＋16 loopback＋1实际wheel probe**、前端类型/build与 **741项/88文件**单测及E2E类型）。文档收口后的新wheel也重跑SDK三层与 **14SDK＋3旧CLI真实HTTP**通过，3.12.16/3.13.13独立安装API smoke通过，不冒称完整远端矩阵。清理脚本3项守卫经RED→GREEN16项、独立复核关闭；11-08实际dry-run/apply复验精确owner/完整ID/唯一卷/零其他DB client/临时租户/测试进程后，仅删除本轮SDK PG、专属卷及执行口令文件，成功枚举确认资源缺席，其他服务/镜像/venv/证据均保留。[最终交接](docs/development/agent-metadata-python-sdk.md)记录hash、计数、首次失败、限制及清理收据。仅本地分支提交，不main/push/发包/部署/模型调用或生产准入；下一片必须明确R4b正文/附件接收方、范围、是否本地无模型及分类责任，R5命令账本/补偿、R6正式替换、R7第二插件仍未完成。下方待验收状态均为历史过程。

> **2026-11-07 SDK 冻结完整本地门禁通过，资源清理收尾中**：CI接线本地提交 `9e54ad52` 后1612个tracked present文件冻结，完整 `make check` **exit0**（SDK **562 unit＋16 loopback＋1实际wheel probe**；后端 **3881 passed /4 skipped /19 deselected /6 warnings**；前端类型与生产build通过）；独立browser **11 passed /6 warnings**、pure **278 passed /3 warnings** 均exit0，执行前后源码指纹一致。4skip为未配置Redis与3个共享seed E2E入口，不计为passed；SDK14 mandatory HTTP用例在完整后端中实际通过，当前backend wheel SHA256 `5c13c06d79893ad3fd2193bab6a6da5bccff8f1c5858d8963ffdaa5bb2568695`，七runtime字节独立核验一致。前端先行 **741 passed /88文件**及E2E类型通过，其源码manifest与最终冻结一致。整片集成代码复核Approve、0 Critical/Important/Minor；仍不将本地结果当远端CI或生产准入。仅剩自有资源清理与文档收口；私有清理脚本的3项守卫发现正在先红后绿修正，未执行删除。当前正文附件/模型交付、可信生产部署、R5/R6/R7仍未开放；[SDK交接](docs/development/agent-metadata-python-sdk.md)记录阶段/最终证据与后续实质范围决策。下方接线待验收状态为历史过程。

> **2026-11-07 SDK 独立门禁与真实 HTTP 已验收，CI 接线收口中**：Task9 分层入口/私有收据/实际 wheel 隔离安装及 fixture-only 样例完成双复核并本地提交（`2bda2434`）；Lead 实测 **562 unit＋16 loopback＋1 wheel probe**，均 exit0、无 skip/xfail/xpass/warning。Task10 安装实际 wheel 的正常策略真实 HTTP **14 SDK＋3旧固定CLI passed /5既有warnings**，已双复核并本地提交（`bd8b694d`），runtime 七文件与实际 wheel 字节/hash 独立核验一致；覆盖十操作、撤权/epoch/来源与 finish 已提交后响应故障 unknown，未改应用授权或固定worker。Task11 已补精确两字段矩阵兼容、SDK mandatory 14节点定向不跳过检查，以及旧Make fixture对独立SDK解释器的适配；Lead全CI纯契约 **278 passed /3既有warnings**，当前实际SDK Make **562＋16＋1** 全通过，实际新wheel交付核七runtime一致，受控runner新wheel真实HTTP **14 SDK＋3旧CLI passed /6warnings**（比旧记录多1项logfire rewrite警告），源码指纹不变。首次Lead直接runner遗漏既有PYTHONPATH前置的import失败已保留，修正的是调用环境而非生产代码。七文件规格PASS、独立质量Approve（0 Critical/Important/Minor，另实跑85项纯契约通过），Task11本地接线验收完成。最终冻结后的完整 `make check`、browser/前端组合门禁与自有PG清理尚未完成；不以历史回执代替。本轮仍不 main/push/发包/部署/模型调用或生产准入；后续 R4b 正文附件交付/可信部署、R5 命令账本、R6 正式替换与 R7 模块扩展未因 SDK 通信成功而完成。

> **2026-11-04 SDK client与离线构建器已复核，整体验收待续**：客户端中断后保留原代码恢复，18项明确RED及新增响应预算/非2xx deadline顺序反例已修；十方法、凭据分域、单D与finish全链unknown完成双复核（`b2d8cc96`）。SDK相关480项在3.11/3.13均通过，旧自有回环16项通过。独立构建器修正“仅声明pin却未核actual setuptools”后双复核（`8f4132a2`），仅自建静态fixture真实离线构建，不代表当前SDK wheel已验收；Lead 3.11全unit最新 **521 passed**（含41 builder案例）。下一步Task9：实际SDK wheel快照/独立venv安装与API smoke、分层SDK检查入口，再Task10真实normal-policy HTTP与Task11 CI。当前业务/权限/profile/worker与hash未改，未新增模型/正文附件/业务写、未main/push/发布/部署；下方11-03数字均为各阶段历史证据。

> **2026-11-03 SDK基础、codec与transport阶段收口（SDK尚未整体验收）**：包/安全异常/DTO已TDD并独立Spec/Quality通过（`426c2d20`）；严格十操作codec修正report透出children后双复核通过（`12a50948`），foundation+codec在3.11/3.13各294项通过；整体deadline、有界DNS、partial send、buffer下raw read及IO refs传输修正TE尾OWS后双复核通过（`1b97f067`）。Lead最新独立实测全SDK纯单测 **371 passed**、单独自有回环 **16 passed**，0 warning；未用远端DNS/模型/业务数据库。下一步Task8封装client及finish全链unknown，再做wheel/真实normal-policy QMS HTTP/CI。当前无公开client或完整SDK可用性结论，应用/权限/profile/固定worker/hash不变；不main/push/发布/部署。

> **2026-11-03 SDK 规格审查通过，进入实施**：用户已书面通过[SDK规格](docs/superpowers/specs/2026-11-03-agent-metadata-python-sdk-design.md)并要求继续；[实施计划](docs/superpowers/plans/2026-11-03-agent-metadata-python-sdk.md)明确唯一单调deadline覆盖整次操作、每client有界DNS helper/底层raw IO预算，以及finish发送后超限/解码/schema/绑定错误统一unknown。按包与DTO→codec/transport→client→wheel/真实HTTP/CI→复核门禁推进；当前尚不能称SDK完成。应用权限/profile/固定worker及hash不改，模型/正文附件/业务写、main/push/部署仍不开放。

> **2026-11-03 CI 接入与本地分层门禁完成**：本地 `integration/agent-main-semantic-20261102` 已接入 CI 独立提交 `4a00636f`，未复制原工作树未提交内容；pure/隐式dotenv、DNS/已知Python子进程、显式Chromium末级传递、libpq路由及地址族闭环、Make secret缺口已先红后绿并独立复核收口。冻结执行源码1444文件：后端 **3827 passed /4 skipped**，浏览器 **11 passed** 且显式wrapper启动11次，pure **238 passed**；前端类型/build/E2E类型与 **741项单测**通过；同源固定ClamAV **6过程＋1浏览器**通过且导出/cleanup收据核验成功。执行源码前后不变，本轮主PG/卷、scanner随机project及私有执行口令均已精确清理。四项skip为未配置Redis及共享seed E2E，不当passed；未执行本集成分支远端CI或真实provider，不更新main、不push/部署/生产开启。[完整交接](docs/development/agent-ci-integration-gates.md)保留失败、修正、真实收据与源码身份。用户选择下一片先做元数据只读SDK与协议兼容，先规格设计/评审，不提前开放正文附件外发或R5业务写入。

## 先前语义集成记录
> **2026-11-02 主线语义集成本地完成**：独立分支 `integration/agent-main-semantic-20261102` 集成 runtime `ef3e24e0` 与 `origin/main@d8e2cef5`，不直接更新 main、不推送。双方权限、审批、来源和租户保护及调用方兼容已保留，新增 public merge revision 与独立 tenant `tv006_agent_read_tasks`；两部分规格复核 PASS、质量复核 Approve，无实质发现。权限/adapter纯测试128通过、迁移/租户纯测试28通过（均0网络）；专属PG15真实升级3通过、迁移/parity48通过1跳过、旧任务/多租户等193通过。runtime大套件首轮741通过/17库名守卫setup errors；换符合守卫的新库后17项全部通过，未改代码/守卫，不冒称一次全套exit0。跳过的冻结快照再生另用自有容器PG15工具补验1131对象一致。临时容器/匿名卷已核验清理；未跑完整make check、前端、浏览器、provider或scanner，不启用生产。CI由另一Agent实施且其未提交内容未复制；下一步接入其独立提交并跑分层门禁。[完整交接](docs/development/agent-main-semantic-integration.md)保留命令、首轮失败、复跑证据和限制；下方数字均为历史快照。

## CI 原分支交付记录

以下授权与验证属于原 CI 分支，不扩展为本集成分支的推送、部署或生产授权。

### 2026-11-09 — PR #29 main集成验证通过（待推送后远端CI）

- 六处冲突保留双方有效改动；增量public merge head与tenant tv007、当前/历史parity、CAPA命名空间及锁顺序、测试隔离和CP协作权限已完成独立复审。复审发现的旧current-head测试遗漏已关闭，无剩余阻塞发现。
- 最终冻结1536源码文件前后相同：注册55434完整make真实exit0，后端4067 passed/5 skipped/19 deselected/5 warnings，0 failed/error/xfail/xpass；tsc/build通过。全量bounded Vitest822/95、projection8/8；55433新tag真实browser3/3通过，17图LOOK，精确Agent默认关闭GET404归因，无CP协作404/其他意外HTTP失败。协调者核对原始回执和截图。
- 55432历史库、55433浏览器审批证据及55434完整测试库均保留；A/B受控记录在full前后逐字段相同。仅自有app/worker停止，无删除卷/重置证据/部署。
- 用户已授权解决冲突、验证通过后合并；下一步创建集成merge commit并推送功能分支，检查PR #29实际远端CI，满足条件后合并。上述本地验证不冒充远端CI成功；旧失败和wrapper日志保留于验收文档。

> **2026-11-08 PR #28 第二轮窗口基线修复**：真实逐条提交允许完整109窗口先发布，现显式验证1..100→10..109，再持有110历史页检查10..109不变及最终11..110。确定性复现旧错误断言后修正；完整无模型浏览器11通过/3771未选择/5warnings，hook单元17通过、E2E类型/前端构建通过，独立定向复核无发现。不改生产hook、真实提交或退避合同。下一步等待新head远端CI后按授权合并；旧head失败不掩盖。本轮清理准备被权限系统拦截，临时资源保留、未绕过。用户原未提交内容不混入提交；详见[修复记录](docs/development/pr28-merge-readiness.md)。

> **2026-11-08 PR #28 合并阻塞修复记录**：基于远端f9d6f95c修复维护连接断线错误未收敛及窗口验收先变更数据后装拦截的竞态。驱动故障先RED2/实际断线控制1通过，修复后3通过；维护/CI回归214通过，activity hook单元16通过，整层无模型浏览器11通过/3771未选择/5既有warnings、E2E类型检查通过。独立定向复核无阻塞发现，不放宽归属/代际/锁/窗口/退避断言，不改应用轮询hook或调用真实模型/scanner。远端新提交的检查与最终合并以PR当前事实为准，本地通过不替代；[修复记录](docs/development/pr28-merge-readiness.md)。原用户文档已备份并三方恢复，用户历史段落/架构改动/开发基线/示例删除不混入此修复提交；本段为本次独立新增记录。

### 2026-11-04 — Task8 main 冲突已本地解除，合并态验证通过（未提交/推送）

- 隔离分支 `integration/agent-runtime-main-20261103` 合并 feature `35dc36bb` 与 main `d8e2cef5`；8 个冲突均已在工作文件和索引解除，保留双方历史及权限保护。原功能分支/根工作区未提交改动未触碰。尚无合并提交，远端 PR #28 不会在推送前自动解除冲突。
- 最终同源可执行文件 manifest `1bcb8175e69fa0d36ff01069755a72ec3eaa4ddf6e73b6c10480d65279297927`：完整 `make check` exit0，后端 **3742 passed /4 skipped /19 deselected /5 warnings**、0 failed/error/xfail/xpass，前端类型/生产构建通过；串行无模型浏览器 **11 passed /3754 deselected /5 warnings**、0 skipped、exit0。合并态真实数据库定向 **182 passed**，公共双分支升级及租户 tv005→tv006 parity/回退/重升 **3 passed**，禁网纯矩阵 **270 passed /3 DB deselected /3 既有 warnings**。collection 只作导入证据，不算执行通过。
- T8-01 历史来源适配已按 main 六字段 SourceLabel 和四元授权键修正，当前来源/版本/整包拒绝与防降级不变；投影测试使用真实持久、有限工厂/产品线、非 bypass 的 CAPA EDIT 操作者，不放宽服务写保护。独立复核及修正复核通过，无未关闭 Important/Critical；旧失败与拒绝记录保留于下方历史。
- 公共迁移通过加法合并头 `20261103_merge_agent_foundations`，租户新增 `tv006_agent_read_tasks`；冻结 tv001–tv005 和 snapshot 未改，main 内部 single-only read-task 与绑定租户 runtime/projection 职责分清。feature 最新锁文件、SDK/浏览器 CI 兼容、假 ClamAV 连接关闭修复保留。实际合并态回归未发现需追加修改 CI workflow 的问题。
- 用户在 2026-11-04 明确授权此专属 PG15 定向/完整/无模型浏览器回归；专属实例和 volume 按授权范围保留，未删除，仅 fixture 自建数据/schema 按正常流程清理。旧权限拦截没有绕过，后续实际结果来自人工授权后的本会话进程与退出回执。
- feature 合并前真实 GitHub run `41639970275` 已成功，但**尚未运行合并态远端 CI**；本次没有调用真实 provider/scanner 或 main 手动 gate，没有提交、推送、创建 PR、合入 main、配置 Secrets/保护或部署。下一步需授权创建这个合并提交并仅推送功能分支更新既有 PR #28，再读取真实合并态 GitHub CI；不直接合并 main。

### 2026-11-03 — Task8 main 隔离集成实施过程（以下待执行/失败记录为历史）

- 在 `integration/agent-runtime-main-20261103` 隔离工作树协调 feature `35dc36bb` 与 main `d8e2cef5`；两侧历史保留。feature 的真实远端自动三层 run `41639970275` 成功属于**合并前**，不是本次集成通过证据。
- 权限结合受控 profile 与 GROUP ADMIN 无界工厂、明确产品线豁免和禁止申请人自批；默认 DENY、runtime OFF、当前租户/generation 与来源复核不放宽。CAPA 模块持有能力声明，投影保留显式元数据 allowlist 与独立只读租户快照。
- 两条既有 public 迁移通过新增 `20261103_merge_agent_foundations` 汇合；新增 `tv006_agent_read_tasks` 保持租户 parity，冻结 tv001–tv005 与 snapshot 不改。本次无网络纯回归实际 270 passed /3 DB tests deselected /3 既有 Pydantic warnings，受影响目录 collection 1996 项通过；这只是局部策略/契约证据。DB/迁移执行、前端、浏览器及完整 `make check` 仍待控制方运行；不继承任一侧绿灯。真实 provider/scanner 与 main 手动 gate 未运行，未提交/推送/PR/部署。
- Fix round1：独立复核 T8-01 指出历史读取仍用旧 SourceLabel/授权键。真实专属库先复现历史 TypeError 与伪造 actor 拒绝两项 RED；现按已验证 canonical receipt 构造六字段标签/四元键，9 项新历史正反例已实际通过，涵盖结果/事件/活动整包拒绝。投影夹具改为真实持久 CAPA EDIT、非 bypass 且显式产品线成员的 actor；一次额外无效 method 字面值导致 3 setup errors（非 GREEN），现已移除，但修订后的最终 DB 验证仍未运行。请求原 95 项加历史/任务更新共 182 项的精确专属库重跑被权限系统拒绝，未重试或委托绕过，等待直接人工授权；最终纯回归仍为 270 passed /3 DB deselected /3 既有 warnings。控制方另提供迁移 3/3 通过及修前 94 passed /1 fixture fail，不冒充修后完整结果。
- 下一步：控制方请求上述精确专属目标的直接人工授权，完成修后 182 项 DB 走查和独立复核，再标记冲突并验证全部迁移、权限/来源并发、后端/前端/浏览器。未经实际回执不签 Task8 自动整层通过。

### 功能分支集成前历史（以下结果不代表合并态验证）

### 2026-11-03 — PR #28 后端 CI 超时根因修复（待真实远端全量）

- 诊断提交 `888c6b98` 已推送原PR，新run `41638011344` 在运行；其前端已通过。随后native Python3.12/CI依赖整套诊断的最后START精确落在index1764 `test_scan_stream_sends_newline_instream_and_zero_terminator`；不是先前怀疑的lifespan/DDL业务等待。
- Linux/Python3.12单跑该旧例30秒无结束，exit124，8秒堆栈处于asyncio等待；原因是StrictClamd假服务器的VERSIONCOMMANDS和held-stream分支读到peer EOF即return，未关闭accepted writer。Python3.12 Server.wait_closed继续等这个服务端半连接；不依赖GC的两条新TCP关闭断言先RED2failed，明确证明泄漏。
- 仅将测试fake handler包在try/finally关闭/等待writer，生产扫描器及原协议/结果/恶意文件/错误/输入限额断言不变。完整扫描模块Linux3.12/native3.11均16passed/3既有warnings，限定独立复核无重要遗留。旧整套诊断已在确认根因后取消，不能记为完整通过；后续按新提交的实际远端CI结果验收。未合入main、未调用模型/真实scanner或部署。

### 2026-11-03 — PR #28 远端 CI 跟进（诊断轮，超时未签解决）

- `aeaf7fb2` 已推送原PR分支；实际run `41585162399`：frontend成功、browser因Ubuntu26.04/Playwright1.60不兼容在安装阶段失败；backend超过6小时取消。下载1920字节backend产物后发现39%已有4个失败，47%后无更多换行，不能把取消当成无失败。
- 4项SDK fixture失败已复现：CI Anthropic2.4改用httpx2，原测试注入httpx.AsyncClient导致TypeError；生产adapter未注入此对象。改用各SDK公开默认client与匹配MockTransport，保留精确官方URL/ambient清空/无请求断言，不改生产依赖版本。旧/新SDK各目标4、整模块20通过。
- Chromium自动/手动3个job固定Ubuntu24.04，新contract先RED3后GREEN13；不改其他job或验收门禁。新增逐用例start/finish与120秒线程dump（仅诊断、不跳过/通过/延长超时），参数ID不输出；独立复核指出前缀碰撞，真实子进程RED后以精确JSON、源标识和连续序列校验/重构修正，避免实时回放正文。两套依赖纯CI均198 passed/3既有warnings。
- Linux/Python3.12/provider+附件recovery/storage相邻37项通过，但未复现整套顺序超时；native Python3.12/CI依赖整套诊断运行中，实际远端仍待验证。源码/断言未为绿灯删减，不将诊断增强宣称为超时根因修复。详见[CI跟进计划](docs/superpowers/plans/2026-11-03-pr28-ci-followup.md)。本轮不合入main、不调用真实provider/scanner或部署。

### 2026-11-03 — PR #28 四项审查修复（本地验证完成，未推送）

- 基于 `4a00636f` 的独立 `fix/pr28-review-findings-20261103`：补齐 npm10 缺失的27个 esbuild 锁条目，原567条目不变；Make 发布入口保留操作者密钥；D8 响应/中英文面板补齐已绑定门禁、豁免与责任信息；附件文件校验后重查权限/目标/附件状态，失败关闭描述符并回滚失败成功审计。运行时和生产边界不开放。
- RED/GREEN：Make 6 failed/2 passed → 8 passed；D8 后端4 failed/1控制通过、前端7 failed/22 passed → 后端125、面板/详情88通过；附件初次9 failed/1控制通过 → 27通过。首轮全量在61%发现新增代际比较过严后取消，日志保留，不算全量验收；既有代际用例再现RED后改为保持原坐标且检查当前tenant，扩大四模块64通过，并再次独立复核，无重要遗留。
- **最终完整后端**：全新专属库，3648 passed /4 skipped /19 deselected /5 warnings，pytest与runner exit0（2231.10秒）；4skip为Redis与3个未启用seed E2E端点。实际Chromium保护11 passed /3660 deselected /5 warnings，exit0；纯CI192、全前端88文件/748测试、app/E2E类型通过。Linux Node20.20.2/npm10.8.2正常干净安装与生产构建通过，既有warnings保留。
- **整条 Make 的限制**：最终 `make check` 后端及tsc通过后，macOS Vite/esbuild在文件open处停顿超过10分钟，主动取消，不能报告整条make exit0。497个输入逐文件相同的全新本地前端export正常npm ci/build（6.22秒）通过；此前Linux同源构建也通过，未修改源码绕过。最初两次检查命令工作目录错误亦已纠正，不计成功验证。
- 最终1423源码指纹 `02ff9c2667b6c7305ec1f6d4f04fea3930194f22c0ecccf677f58e48b51e447e` 检查前后不变；收据中的SHA为基点，修复源码以此manifest区别，不冒充已推送提交。操作与验证见[修复计划](docs/superpowers/plans/2026-11-03-pr28-review-fixes.md)。本次容器精确ID/owner、零客户端、匿名卷独占核验后已单独清理；原工作区、其他容器、源码及日志保留。
- **下一步**：按授权推送修复并获取真正远端CI，再独立处理main既有冲突及整合验证。本轮未推送、合并、调用真实provider/scanner或部署。

> **2026-11-03 07:36 CI 限定提交/推送已获授权，远端结果待实际回执**：仅提交本轮CI代码、测试、使用文档/实施计划和CI进度记录并推送 `feature/agent-task-runtime-foundation`；原有架构/开发基线文档、开发基线进度条目与 `.env.e2e.example` 删除不混入提交。当前代码逐文件匹配最终完整本地验证源 manifest `d7a3a8bc…`；下一步读取该提交真实 GitHub 自动运行结果，不以本地记录代替。未授权创建PR、集成main、手动模型/scanner事件、配置仓库保护或部署。

> **2026-11-03 CI 分层实施与本地交接完成（未提交/未远端验收）**：最终同源冻结 manifest `d7a3a8bc…` 完整 `make check` exit0：后端 **3622 passed /4 skipped /19 deselected /5 warnings**，前端类型/生产build通过；串行浏览器 **11 passed /3634 deselected /5 warnings**，纯测试 **184 passed**。最终修正另实际复验API85、显式浏览器11、ClamAV过程6＋浏览器1；真实收据/日志与daemon/场景/cleanup观测在销毁前保留，frontend CI无backend依赖CLI实测通过，actionlint通过。整体复核与全部Important修正均关闭；SDK短密码JSON结构、可选timeout、显式浏览器路径、CI证据保留均有反例。4skip为Redis＋三个seed E2E endpoint，PG15快照已实测；scanner属性记录兼容warnings如实保留。仅本任务owned PG/container/volume在零其他client/消费者核验后处置，扫描随机project资源清零；源码/旧失败与取消证据/其他Docker项目保留。未触发GitHub自动/手动或应用真实provider、未提交/推送/PR/main集成/部署；下一步需授权仅提交CI相关改动并推送取得远端自动CI，再隔离处理main冲突。详见[实施计划](docs/superpowers/plans/2026-11-02-ci-layered-acceptance.md)、[E2E指南](docs/e2e.md#ci-分层验收task-7)、[开发指南](docs/development.md#42-分层验收资源与边界)。下方失败/待复核条目均保留为历史。

> **2026-11-03 CI 最终复核修正波（新源码动态验收待执行）**：修正三项 Important：自动/手动 job 使用专用安全目录并在成功/失败时保留实际收据与过滤日志；scanner 过程证据在卷 teardown 前导出、host browser 与实际清理观察一并保留，summary 校验冻结 main SHA/完整计数/退出码而非 PASSED wrapper；显式 Chromium 路径规范化后保留到 pytest；可选 live timeout 缺省/空值为 30 秒，仍严格限制 1–120。已对配置、真实本地子进程收据、文件系统导出/删除保留、workflow wiring 和 summary 失败场景进行 RED/GREEN；本波网络禁止纯检查 182 passed /3 既有 warnings；真实 DB/browser/scanner 尚待 controller 验证。下方 manifest `79859d6b…` 的完整检查为历史源码 D，不代表本波修改后的完整验证；保留早先失败/中断记录。下一步由 controller 执行新源码 focused Make/browser/scanner 与 workflow lint；GITHUB_AUTO 为 BLOCKED（无 push/trigger 授权），GITHUB_MANUAL/真实 provider 为 NOT_REQUESTED（main/Environment/显式 dispatch 尚未就绪）。未提交、推送、PR、合并、配置 Secrets/Environment 或调用模型。

> **2026-11-03 CI 最终本地回归通过（整体复核待收尾）**：修正 SDK 端点空值、CI 通配绑定/随机端口与 PG15 工具登记后，新冻结干净源码（manifest `79859d6b…`）完整 `make check` exit0：后端 3577 passed /4 skipped /19 deselected /5 warnings，前端类型/生产构建通过；串行浏览器 11 passed /3589 deselected /5 warnings，exit0；纯 CI 139 passed。同源 ClamAV 过程 6/6＋浏览器 1/1、随机 project 清理通过，actionlint 两 workflow 通过。PG15 快照已实际执行，剩余 skip 为 Redis 与三个共享 seed E2E endpoint。旧中断/失败收据均保留，未以历史结果拼接。尚未触发远端 GitHub 自动/手动、调用真实 provider、提交、推送、建 PR、合并或部署；进入最终整体复核和交接。

> **2026-11-03 干净源码完整回归首轮失败（未签通过）**：已在新登记专属测试库完成未中断的完整后端检查，结果 3536 passed / 2 failed / 5 skipped / 19 deselected / 5 warnings，pytest exit1、make check exit2；两项失败为默认 OpenAI/embedding SDK 端点被测试隔离环境空值覆盖。串行 make check-browser 实际 11 passed / 3551 deselected / 5 warnings，exit0；纯 CI 101 passed、npm ci 成功。正在修正 SDK 环境移除语义及进一步核查发现的 CI 发布端口匹配/PG15 工具随机端口衔接问题；前端类型/构建单独补跑中。此前中断运行及这次失败均保留记录；尚无全套通过、远端 GitHub 验收、真实 provider、提交、推送、PR、合并或部署。

> **2026-11-02 CI Task 1–5 已复核，实施 workflow 中**：分组、资源归属、Chromium/Node 白名单、隔离验收 runner 与分层 Make 入口已完成任务复核。最新 Task 5 纯测试 66 passed（3 既有 warnings）；真实固定 ClamAV 过程 6/6＋浏览器 1/1，通过随机专属 project 且容器/卷/网络清理已核查。现有 backend CI 已先切到资源核验和确定性 Make 路径，Task 6 正在扩展所有分支 push、独立浏览器及 main-only 手动验收。完整冻结回归、干净 checkout 和远端 GitHub run 尚未完成；未读取模型密钥、调用真实 provider、提交、推送、建 PR、合并或部署。

> **2026-11-02 CI 分层实施中（Task 1–4 已复核）**：已实现纯测试引导入口与严格逐用例 marker，分类回归经一次补充 local-trial 保护后独立复核通过；纯 runner 基线 5 passed、分类回归 3 passed（3 项既有 Pydantic warnings），前端类型/构建均 exit0。收集核账为 backend 3450/browser 11/live 1/scanner 7，不是各层实际运行通过。Task 2 已实现并经修正复核通过：所有权纯测试 28 passed，专属有标签 PG15 经核验后建库/迁移，provider-disabled 双来源真实 HTTP 1 passed；额外拒绝全部 URL 查询参数以防 hostaddr/service 重定向。Task 3 已完成并独立复核 Chromium 解析与 Node 白名单实现：纯支持层与 legacy runner 18 passed（3 项既有 Pydantic warnings）、前端 tsc exit 0，项目 Playwright Chromium 已实际解析；更正首次将临时口令误作数据库名的本地调用，使用正确已迁移 `qms_ci_layered_test` 后以 Task 2 的 `verify_owned_instance`/`verify_owned_database` 替代 legacy `openqms_r4a_*` 前缀守卫（更强 ownership/loopback/_test 验证），并修正实际浏览器 RED 暴露的 readonly `frontend` 初始化顺序；provider-disabled deterministic browser 层 11 passed（另 2 项既有 websockets warnings），未弱化业务/来源/终态安全断言或回落其他数据库。Task 4 已完成纯测试复核：live 配置改为显式环境或显式 `--test-profile`，不再隐式读取 `.env.e2e`；api/browser/live 独立子进程，普通子进程显式清空 provider/embedding 凭据且移除 `E2E_MODE`，并以隔离 Settings 预检确认无 provider 回补；JUnit+pytest hook 生成含 deselected/warnings/xfail/xpass 的收据，原始 XML 保持私有并在公开收据前删除，日志过滤密钥、URL 编码密码和 Authorization header。纯套件 `36 passed`（3 项既有 Pydantic warnings）；未运行真实 provider/scanner/browser/数据库 gate，Task 5 可通过 runner 的 `--pytest-target`/`--pytest-arg` 接口执行全量 backend/browser 选择。额外前端全量单测默认并行基线 739 passed/2 timeout；不改测试/超时，限制 maxWorkers=1 后完整 88 文件/741 测试通过，原并行超时仍保留记录。当前未提交/推送/建 PR/集成 main/部署，尚未调用真实 provider；下方“未实施”条目为此前计划阶段历史。

> **2026-11-02 CI 计划复核修订（未实施）**：已对照 Makefile 与 conftest 核实并修订两项问题：数据库建库/迁移/pytest 从同一已核验目标派生，补充显式 PG 变量冲突零写入与缺库先验实例核验；纯测试统一使用导入前设置专用不可连接测试 URL、禁止网络连接的计划入口，不绕过种子库守卫。详见 [实施计划](docs/superpowers/plans/2026-11-02-ci-layered-acceptance.md) 第 0 节及 Task 2/5/6。仅文档修订与静态检查，脚本尚未实现，未运行测试/操作数据库或提交推送。

> **2026-11-02 CI 分层实施计划已落文（未实施）**：已复核分层设计、当前 workflow/Makefile、CAPA 私有资源及浏览器控制器，计划见 [CI 分层验收实施计划](docs/superpowers/plans/2026-11-02-ci-layered-acceptance.md)。按逐用例分类、资源归属验证、Chromium/Node 环境隔离、独立 live 配置与结果收据、Make 入口、自动/手动 workflow、干净环境验证分步推进；主分支 8 冲突集成为后续独立检查点。手动远端验收需 workflow 进入 main 且 Environment 就绪，不能用静态检查或旧本地收据替代。本轮仅新增计划及本条进度，未修改 CI/测试代码、运行项目测试、读取本地密钥、提交、推送、建 PR、合并或部署；原有未提交改动和示例删除保留。

## 更早的分支历史
> **2026-11-01 CI 适配：方案已选，书面规格待确认**。用户选择“普通自动CI无模型密钥＋独立确定性浏览器保护＋维护者手动真实provider/ClamAV验收”。规格见 `docs/superpowers/specs/2026-11-01-ci-layered-acceptance-design.md`，本阶段只落文并按授权本地提交供复核，尚未修改workflow/pytest/Makefile或测试harness，也未触发新CI、上传本地profile、配置Secrets/Environment/分支保护或推送。新手动workflow需进入默认分支后才可触发，设计限定main；不为此自动合并。确认书面规格后再写实施计划与明确验证资源/后续提交推送范围。

> **2026-11-01 推送前只读Agent设计核对**：已完整阅读用户指定的2026-09-29基础设计，并按用户确认的现行后续合同核对，不把旧表/旧函数/固定24小时服务接口原样套回当前架构。当前AgentTask/AgentTaskGrant持久化、当前身份/权限/工厂/产品线与租户代际检查、逐事务严格绑定、只读RR元数据白名单及完整digest、baseline DENY和runtime默认关闭均有对应实现；受限local_metadata试用沿后续独立合同，不放开命令或生产交付。新补跑设计契约 **16 passed /3既有warnings**；与已验收3450全量快照对比，唯一变化的冻结源码是本轮已独立复核并33项通过的MES测试。未声称当前工作树重跑过全站make check。用户已授权将MES整改独立提交并仅推当前功能分支到origin，不建PR、不合并、不部署；用户删除示例、TEST profile和全部私有证据不纳入提交。远端CI尚未适配本地live条件，功能分支推送不等于远端CI通过；Git执行结果另以实际远端ref回执为准。下方早先未提交状态为当时交接历史。

> **2026-11-01 MES 预期失败测试整改（独立后续任务，仅改测试）**：原3条XFAIL/2条XPASS实际对应4个用例，现已重写无效覆盖、移除4处旧xfail并修复rollback后的fixture主键清理。4项目标测试通过；整份MES并发模块正常运行及`--runxfail`均 **33 passed /3既有Pydantic warnings /exit0**，无skip/xfail/xpass/teardown error。四个私有故障变体均被关键业务断言捕获，独立代码复核无阻塞发现；本轮专属临时容器/卷/网络已清理。生产逻辑未改、未调用真实MES/provider，用户删除示例保留；本轮测试改动现已获独立提交及功能分支推送授权。本次按授权只跑MES相关回归，未重跑全站make check；下方CAPA3450全量记录对应当时快照，不覆盖这次新增测试改动。

> **2026-11-01 CAPA 实施结果集中审核：8/8 任务、44/44 步骤已完成验收**。最终交接、私有配置隔离、原始收据和源码冻结已独立复核通过，无阻塞发现；完整 `make check` **3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，exit0**。补充后端1203、前端232、类型/构建、真实主链与两条保护链、真实ClamAV7过程＋1浏览器均有通过证据。父级随后重新核验精确容器/owner/镜像/回环端点/专属卷/两库归属及零连接、零登记worker，已删除本轮核心测试容器与专属卷，两测试库随卷处置；Docker Desktop、镜像缓存、其他服务、工作树、用户profile和全部SDD证据均保留。用户删除.env.e2e.example仍为唯一未提交改动，不恢复或提交。不push、合并、部署或开启生产/Agent/R5权限；下方待复核/保留核心资源条目是历史，以本条为最新结论。

> **2026-11-01 Task 8 最终验证交接（UTC 收据 2026-10-31，待父级复核/核心清理）**：私有 runner 的 provider 全局污染已限制到唯一真实 live node 的 setup/call/teardown；纯配置 **8 passed**，混合真实 **14 passed /5 warnings /exit0**。新1390文件冻结后的唯一新鲜完整 `make check` 实际 **3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit0**（总2201.64秒），并在真实主链后证明 provider 不再存在。后续受影响后端 **1203 passed /5 warnings**，前端 **232 passed /24 files**、app/E2E类型与生产build、真实Chromium终态及双来源保护 **2 passed /5 warnings** 均exit0。Task7真实一条主链＋两条保护链及真实ClamAV7过程＋1浏览器已通过，不混称三条AI正向链；旧失败与历史阻塞保留。1390指纹不变、实际public/tenant heads与无新候选表、无临时租户/进程/事务已核对。无tracked应用/测试/配置改动；用户删除.env.e2e.example保留且不提交。核心PG/卷/DB/SDD/worktree/证据保留，清理仅DRY_RUN；独立交接DONE_WITH_CONCERNS，不签Task8/整片完成、不push/合并/部署。完整证据见文末“Task 8 FINAL CLOSURE”。

> **2026-10-31 Task 7 真实分层验收与独立复核通过，scanner 专项通过**：用户批准将真实AI正向闭环与双模块撤权保护分层；代码00b8bd5d及D3证据前置修正82c7985e经独立规格/质量复核通过，无阻塞发现。完整受控验收 **3 passed /5 warnings /exit0**：真实provider/HTTP/D8浏览器批准/知识/横向主链、终态保护、确定性双模块撤权保护；后者不冒充AI影响选择。真实ClamAV专项 **7过程测试＋1浏览器控制测试通过**，ClamAV1.4.3/定义28170，随机专项容器/卷/网络均清理，核心CAPA测试环境保留。现在进入最终受控全量检查与新冻结；旧3447/2failed是改动前历史，不是当前源码绿灯。用户删除.env.e2e.example保留且不纳入本轮提交；仍未签Task 8/整片完成，不push/合并/部署。

> **2026-10-30 最终代码复核收口，整体验收仍 BLOCKED**：整片复核提出的唯一 Important I1 已由 `b375f26d` 修正，并经唯一一次最终限定复核确认 ADDRESSED，限定规格 PASS、质量 Approved，无新增 Critical/Important/Minor。来源锁等待后重新核验 verification create/update 及 run_audit 当前权限；真实并发32 passed，受影响后端1113 passed，前端232 passed及类型/构建/真实终态保护通过。当前1391文件指纹 `87fb0a10615affa1d3ef3c3c4bee3db9273fc3896a23ccdea8146f07858a5b33`，最后完整检查 **3447 passed /2 failed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit2**，两项强制live缺opt-in，不能称全绿或Ready to Merge。代码发现已关闭，不再自动派发修正；授权测试profile、真实正向provider/浏览器/知识/横向、精确授权scanner专项及依赖安全的最终清理仍待完成。保留分支、worktree、自有核心PG与全部证据，不push/合并/部署。下方各“待复核”条目是历史过程，以本条为最新状态。

> **2026-10-29 FINAL REVIEW FIX（I1，自检完成，待 ONE scoped 独立复核）**：验证 create/update 与 run_audit 在来源锁后复核当前 actor/CAPA EDIT/命名空间/目标范围；update 复核前不改脏子记录。真实 PG source-wait 功能 RED24 failed /8 valid passed → GREEN32 passed。新1391文件指纹 `87fb0a10615affa1d3ef3c3c4bee3db9273fc3896a23ccdea8146f07858a5b33`；唯一 fresh full 实际2 failed /3447 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit2，仅两项强制 live 缺 opt-in，不是全量绿灯。完整受影响回归1113 passed、前端232 passed/24files、类型/构建及真实 provider-free 终态保护通过；资源/DBheads/指纹未变。Ready to Merge NO，外部门禁/最终清理仍 BLOCKED；详见文末 FINAL REVIEW FIX，不签 Task8/整片完成。

> **2026-10-29 Task8 review-fix R1（I1已局部验证，待SCOPED独立复核）**：仅SCAR denial测试补齐source ProductLine前置四行，保留non-bypass actor及403/不变断言。空迁移库真实FK RED1 failed后，同库cold GREEN1 passed、D3controls12 passed，168表行数及product_lines0前后全恢复，无预载/重复reset。新1391文件freeze `a8acea805fd51fba5b4c1494b3909e5dfb6a40ca8eba43b6c8d9b9c182077e07`，完整make实际2 failed /3415 passed /12 skipped /3 xfailed /2 xpassed /5 warnings、make exit2，仅两项强制live缺opt-in；不是全量绿灯。补充/前端/真实终态保护/DBheads/资源/链接均有当前收据；真实Task7/scanner/最终清理仍BLOCKED，控制方将仅对b16..新HEAD复核，不签Task8/整片完成。

> **2026-10-29 Task8 独立交接 DONE_WITH_CONCERNS（非Task8/整片签收）**：最终真实完整检查 **2 failed /3415 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit2**，仅缺live opt-in的两项强制用例失败，不能称全量绿灯。修正后的普通回归无失败/错误；额外API/并发与R4保护 **344 passed /5 warnings**，真实Chromium终态保护 **1 passed /2 deselected /5 warnings**（不代表真实关闭），最终前端232 passed及类型/构建通过。1391文件指纹未变，实际public/tenant heads及无新候选表、临时租户/进程/事务清理已证明；登记核心PG/卷/工作树/证据保留。正向provider/浏览器/知识/横向、精确授权scanner及最终破坏性清理仍BLOCKED；待控制方整体独立复核，不push/合并/部署。详见文末Task8最终独立交接。

> **2026-10-27 Task 7 实现复核通过，真实验收仍 BLOCKED**：代码 `665511e3` 独立实现符合性/质量复核无 Critical/Important；API/并发35 passed、额外后端104 passed、前端221 passed及类型/构建通过。完整真实验收 **2 failed /1 passed，exit1**：一项 Chromium 保护通过，两项正向用例因缺少本工作树授权测试 `.env.e2e` 在真实D3阻断，D4及后续审批/知识/横向扩散未验证。不能标Task 7完成，Task 8最终冻结及整体收口未完成。另已披露自有测试DB配置误输出工具记录，未涉及生产/provider密钥、未静默轮换；临时租户/进程/端口清理，登记PG资源保留。独立复核的拒绝审计缺席断言、缺少provider错误类别及噪声归因建议保留在最终复核台账，不push/合并/部署。

> **2026-10-27 CAPA 结果审核 Task 1–6 已验收，进入 Task 7**：Task 6 `99f108ff` 通过独立规格及质量复核，无 Critical/Important。受影响后端 **821 passed /3 warnings**，前端 **121 passed /5 files**，类型与构建通过。归档后仅补充 d8_closure 的既有冻结仍为400，依据实施计划第52行明确保留原规则；已审核心及混合PUT继续固定409，不是新增豁免。诊断噪声保留供最终复核，不扩展整改。下一步真实员工HTTP/provider/浏览器验收及最后完整冻结，整片尚未完成；不push/合并/部署。

> **2026-10-27 CAPA 结果审核 Task 1–5 已验收，进入 Task 6**：Task 5 第二轮修正 `fa5f4332` 已通过独立规格及质量复核，原 I1/I2/I3 和新增 F1 均已解决，无 Critical/Important 遗留。最终受影响前端 **245 passed /27 files**，前端 tsc、生产 build、E2E tsc 均有 **SHELL_EXIT=0**。下面各轮待审条目保留历史过程，以本条最新验收为准。下一任务为未审补充的知识/经验派生边界；真实 provider/浏览器和最终完整冻结尚未完成，不 push/合并/部署。

> **2026-10-27 Task 5 fix round 2/5：F1 本地修复待独立重审**：FIX_BASE `e79be478`；owned refresh 取消/失效时现有无关订阅者以各自原始 401 reject 并结束，不再无限等待，旧 CAPA 不重放。最终覆盖 **107 passed**，完整原目标集 **27 files /245 passed**（保留原 241）；前端 tsc、生产 build、E2E tsc 均有持久 **SHELL_EXIT=0**。I1/I2/I3 已由控制方确认 addressed，本轮不重开；Task 5 不宣告完成，仍待 scoped re-review。详见文末 round 2 报告。

> **2026-10-26 Task 5 fix round 1/5 本地修复批次完成，待重审**：BASE `16dff517` 的 I1 前置/子操作归属、I2 Axios 认证副作用及 I3 无关知识操作 loading 已按复核修正。最终完整前端 **27 files /241 passed**（保留原 210），前端 tsc、生产 build、完整 E2E tsc 均有持久日志 **SHELL_EXIT=0**。下方初次 Task 5 自检结论已被复核问题取代，以文末同名 fix round 1 报告为当前状态；不冒称独立门禁已通过，不 push/合并/部署。

> **2026-10-26 CAPA 结果审核 Task 5 本地实现完成**：生产 D8 集中审核面板、当前 revision/round 唯一决定入口、身份/范围请求隔离与终态核心只读已实现；最终受影响前端 **25 files /210 passed**、前端 tsc、生产 build、完整 E2E tsc 均 exit 0。尚待控制方独立复核；真实浏览器/provider 仍属 Task 7。本次完整报告见文末同名 Task 5 章节，不将单元 mock 当作真实验收，不 push/合并/部署。

> **2026-10-25 CAPA 结果审核 Task 1–4 已验收，准备 Task 5**：Task 4 实际 D8 批准/驳回版本绑定、当前权限/来源/事务锁与完整五键生产回执已通过独立规格及质量复核（代码 `2c3d212b`）。最终受影响聚焦回归 **662 passed /3 既有 warnings /exit 0**；两个升级的 E2E API 调用方类型检查通过。下一任务为生产界面，真实 provider/浏览器与最终完整冻结尚未完成。六个固定种子报告的 synthetic passed gate 仅是测试前置，不能作为真实门禁成功证据。非阻塞的驳回来源等待覆盖建议已进入最终复核台账；不 push/合并/部署。下方 Task 3/4 记录为历史实现与验证过程，以本条当前状态为准。

> **2026-10-25 CAPA 结果审核 Task 1–3 已验收，准备 Task 4**：Task 3 受控读取、来源/快照/完整性预算和审核版本已通过独立规格/质量复核（最终代码 `894349fa`，用户批准的规则修订 `cbd4ee3a`）。I1–I4 首轮修正全部解决，最终完整受影响聚焦回归 **242 passed /3 既有 warnings /exit 0**。旧待审批兼容轮次不含 updated_at，正常重提使用新入审计 ID；GET 不写数据。下一任务为实际 D8 决定绑定及完整五键生产回执，不能把消费测试当作审批写入已实现。下列验证/修正条目保留历史过程，以本条当前验收状态为准；不 push/合并/部署。

> **Task 3 独立复核及用户决策**：本次读取实现尚未验收。复核要求修正必填原因节点为空、DTO 组装后的材料/补充一致性、历史回执严格结构及来源完整性三项缺口；计划原旧轮次公式含 updated_at 与维护稳定性冲突。用户已明确选择固定租户＋报告兼容轮次，不含 updated_at；按此已批准修订进入同一批修正，不新增 GET 写入、迁移或后续任务。

> **Task 3 fix round 1/5（2026-10-25）**：I1–I4 修正及自检完成；基于 fix-review BASE `0adf2f17`，保留 `cbd4ee3a` 中用户批准的轮次契约修订。最后一次代码/测试支持修改后的完整受影响聚焦回归 **242 passed / 3 既有 Pydantic warnings，exit 0，213.27 秒**，无 skip/xfail/xpass。包含全部原 217-case Task 3＋R4b-1/R4a 当前读取兼容与 25 项本轮新增用例。下方保留初次 217-case 历史记录，并追加本轮逐项证据；独立规格/质量门禁仍待重审，不启动 Task 4。

### Task 3 本次验证记录（2026-10-25）

- [x] 完整 D4–D7/子集合字段与版本、稳定排序、证据和 source_ref、门禁 decision/revision/version_snapshot；100 条 UUID keyset 批次，超过 200 行仍完整。状态、D8 DTO/补充、report updated_at 和 generation 不进入核心 HMAC。
- [x] 当前 CAPA/FMEA/PLANNING 权限、身份/角色停用、产品线成员撤销、目标/来源工厂和产品线迁移；RR 内真实外部提交不混版，快照后及最终 DTO 组装后的撤权拒绝旧正文。
- [x] 真实提交 ReviewCase、两完整租户同 UUID/public sentinel、伪造/缺 TenantBinding 拒绝、维护 generation 后持久版本不变；真实员工 HTTP 成功，refresh/runtime/plugin 凭据拒绝。
- [x] 源版本 object/factory/hash、历史节点/CAUSE_OF；FMEA/CP 正常新版本不影响旧审批。必要来源缺绑定/未知形状/不可读整次失败；legacy pending 精确 UUID5，legacy closed 不造审批；密钥轮换/坏 HMAC 标记 unverifiable，不改历史记录。补充文本与编辑人/时间来自实际 UPDATE 审计。
- [x] 真实 8 MiB text/JSON/source-validator 字段预检、JSON 编码膨胀、独立 response 预算、固定 409；SQL 观察证明超限正文未加载，GET 不写业务/audit/embedding/outbox。
- **RED→GREEN**（所有日志均在私有 `.superpowers/sdd/2026-10-23-capa-outcome-review/`，不含环境凭据）：`focused-20261025T054328902104.log` 为初始 23 failed（缺 reader）；`054507232745` 为 23 passed。`054629911389` 为 source/API 5 failed /16 passed（gate 排序、GET 缺失）；`054703807915` 为 44 passed。`055036674047` 为 D7 历史 CAUSE_OF 1 failed /16 passed；`055355943962` 为证据排序 1 failed。`055658931110` 为畸形 source module/Unicode HMAC 3 failed /6 passed；`055737784934` 为现有版本 validator 的大 change_summary 未预检 1 failed /1 passed。自检追加 `060434299360` 为最终 DTO 后撤权 3 failed；均在最终 217-case GREEN 中通过。中间两次测试自身问题（response 长度 null→string 的 2-byte 差值、非空 PL fixture、refresh helper tuple）已更正，不算产品缺陷 RED。
- **最终命令**（工作目录为本独立 worktree；wrapper 每次静态读取已登记 owned env、清空 provider keys/E2E_MODE、脱敏输出）：

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_d7.py tests/capa/test_d4_text_preview.py tests/capa/test_d4_text_preview_schemas.py tests/api/test_d4_text_preview.py tests/services/agent_runtime/test_readonly_delivery.py tests/capa/test_capa_by_fmea_node_sources.py tests/capa/test_capa_by_fmea_node_api.py tests/capa/test_capa_review_guard.py -q
```

- **最终输出**：`217 passed, 3 warnings in 197.99s (0:03:17)`；完整脱敏日志 `focused-20261025T060513145952.log`，exit 0。没有重跑完整基线/Task 8 freeze，也没有把历史 2999/424 当作本次结果。前端未修改，未运行前端 build；未安装依赖或浏览器、重建基础设施、触碰主 checkout、push/merge/deploy。
- **自检与交接**：复用原 current-access 和 source integrity validators，保留 reader 旧接口；parent/source 写锁协议未改。新增 collector 不是授权入口；Task 4 仍须在实际写事务重查 actor/source 权限并持有既定锁。Task 4 必须实际生产并核对嵌套 `{contract, round_id, revision, doc_decision_id, source_versions}` 回执（首次 helper 少了 doc_decision_id，已在本轮 I3 修正）；本次仅通过真实提交的测试回执验证消费端。API/services README 已同步；等待独立复核后再推进 Task 4。

#### Task 3 fix round 1/5：I1–I4 完整修正证据

- **范围/基准**：只修 `task-3-review.json` 的 I1–I4。fix-review BASE 为 `0adf2f17`；起始 HEAD `cbd4ee3a` 仅含用户批准的 I4 修订，本轮保留该提交及协调方进度文字。沿用既有随机 owned application/test 库、Python 3.11 和私有 wrapper；不读取凭据正文、不调用 provider、不重跑完整基线/Task 8、不重建基础设施、不改依赖/迁移/策略/主 checkout，不 push/merge/deploy。此 PROGRESS 节按协调方许可充当本轮完整报告，不新建独立 report Markdown。
- [x] **I1，必填原因节点**：在精确形状 `{fmea_id,cause_node_id}` 通过后、调用可选 report-node 引用逻辑之前，明确拒绝 cause_node_id 的 null、非字符串、空字符串。非空字符串继续走真实不可变版本的 FailureCause 节点类型/存在性检查。`test_i1_exact_verification_source_requires_nonempty_string_cause` 使用真实提交且已绑定的 FMEA/验证；覆盖 null/空串/0/False/列表/字典，拒绝不写任何业务/audit/outbox。初次 RED 的 null 用例真实复现原先绕过，其他五项作为已有拒绝控制；可选 report node 为 None 仍由原完整回归证明可读。
- [x] **I2，DTO 后完整一致性 fence**：保留原专用 RR/READ ONLY 快照及当前 `db.bind`/TenantBinding。请求 session 在已有 DTO 组装/比较之后，先以 `FOR SHARE` 锁 CAPA 父行，锁后重查当前 admission，再按既有 `version_service` 写锁顺序（control_plan → fmea、同类按 UUID）对源父行加共享锁；不在已启动事务里修改 isolation，不写数据。共享锁持有至请求事务结束，串行化 Task 2 父锁材料/补充/gate 写入及真实来源版本/范围写入。锁定后重新收集完整材料并检查核心 HMAC，再组装完整 DTO 比较；补充文本/补充 UPDATE 编辑元数据/决定元数据的变化通过完整 DTO 检测，不移入核心 HMAC；之后仍独立重查身份、权限、scope、round、来源。
  - `test_i2_commit_after_request_dto_before_last_gate_cannot_return_old_response` 用 Events 精确暂停首次 request-session `_dto` **组装完成后、取最终锁前**，另一真实 session 提交验证 result、d8_closure、仅补充审计、仅决定审计时间，及实际 source-version helper 创建的新版本。前四项均功能性 RED，补充及两类 audit-only 更新保持核心 revision 不变但必须 409，验证/显式源版本变化改变 revision；GET 不回写业务/审计。新增源版本分支也在最终完整运行通过。
  - `test_i2_read_fence_serializes_actual_parent_and_source_writer_protocols` 四项正向竞争：调用实际 `lock_current_material_write` 的验证/补充 writer、实际 `create_fmea_version`/`create_cp_version`。`pg_blocking_pids` 证明 writer 确实等待 reader，SQL 观察证明锁顺序是 CAPA → CP → FMEA；reader 结束后 writer 正常提交。下一读看到验证/补充/显式 FMEA 版本变化；gate-bound CP 正常出新版不改绑旧版本。没有时间睡眠或假锁替代。
- [x] **I3，严格五键回执**：核对更新 context 中已批准的 Task 4 producer，消费端严格匹配嵌套 `{contract, round_id, revision, doc_decision_id, source_versions}`，要求正确 contract/UUID/小写 HMAC 格式、实际 gate decision ID 及完整唯一来源集合；不能因为 gate 能补齐来源就把损坏回执标为 verified。gate 的 doc_type=control_plan 历史别名仍可读，receipt.module 严格仅 fmea/planning，source entry 精确四键。未知必要源 shape 整次拒绝；有效历史 revision 不被重签，历史显式来源仍只使用原绑定版本而非 latest。
  - 原 `approved_receipt` 测试 helper 及正常驳回测试回执已补齐真实 doc_decision_id；它们仅在测试中创建回执，不是 Task 4 producer 集成证据。修正前先使 fixture 符合已批准契约，避免把 fixture 不完整误计为产品 RED。
  - 九项 `test_i3_valid_hmac_is_not_enough_for_noncontract_or_incomplete_receipt` 每项先确认完整回执 verified，然后保留原真实 HMAC，仅破坏 receipt 的 planning→control_plan discriminator、去掉 FMEA/CP 来源、重复来源、额外 envelope 键、缺失/错误 doc_decision_id、source 额外键、错误 contract。前七项功能性 RED（损坏回执原先仍 verified），后两项是已有拒绝/无法验证控制；最终均不再错误 verified，业务/审计不被 GET 改写。原 FMEA/CP 正常新版本与历史节点回归仍通过。
- [x] **I4，用户批准的稳定 legacy 轮次**：精确实施 `uuid5(NAMESPACE_URL, 'capa.outcome-review.legacy:' + str(tenant_identity) + ':' + str(report_id))`，没有 updated_at、其他维护元数据、稳定性例外、GET 写入或迁移。已更新既有 UUID5 断言。新增 composed regression 无 entry audit：标题＋updated_at 维护不改变 round/revision；实际 core、子验证、源图内容＋受控版本逐一改变 HMAC 而 legacy round 固定；正常审计重提改用新 TRANSITION.log_id 并使 revision 改变。API/service README 已同步该明确批准修订及 I2/I3 协议。

**本轮命令/输出（均从本独立 worktree 运行，每次 wrapper 静态加载 owned env、清空 provider/E2E_MODE、脱敏输出）**：

```bash
# Functional RED: 13 failed, 7 passed, 3 existing warnings in 8.17s; exit 1
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py -q
# I1/I3/I4 GREEN: 45 passed, 4 deselected, 3 existing warnings in 14.58s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py -k 'not test_i2' -q
# I2 + existing RR/budget/current-authority GREEN: 50 passed, 3 warnings in 21.26s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_boundaries.py -q
# Including actual PostgreSQL writer waits: 24 passed, 3 warnings in 11.92s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review_fixes.py -q
# LAST implementation/test-support tree: COMPLETE affected suite, 242 passed, 3 warnings in 213.27s; exit 0
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_d4_text_preview.py tests/capa/test_d4_text_preview_schemas.py tests/api/test_d4_text_preview.py tests/services/agent_runtime/test_readonly_delivery.py tests/capa/test_capa_by_fmea_node_sources.py tests/capa/test_capa_by_fmea_node_api.py tests/capa/test_capa_review_guard.py -q
```

- **日志与 RED 真实性**：日志均位于私有 `.superpowers/sdd/2026-10-23-capa-outcome-review/`；依次为 `focused-20261025T140523453110.log`（RED）、`140639729856`、`140843615768`、`141147468030`、`focused-20261025T141924330442.log`（最终完整 GREEN）。本轮 13 个 RED 全是已登记真实提交 case 的功能性断言失败，无 fixture/导入/环境失败冒充 RED；其中 I1=1、I2=4、I3=7、I4=1。后续补足四项真实锁等待及一项 post-DTO 源版本提交，最终新增 25 项全部通过。最终 242 项无 skip/xfail/xpass；三个 warnings 均为原有 Pydantic class-based config 弃用提示，未屏蔽或改写既有 warning。
- **自检/交接**：逐项重读 structured findings 和更新 context；核查源锁顺序、真实 writer 阻塞/释放、只读快照与 request fence 分离、核心与完整 DTO 的不同失效边界、五键回执/来源完整性及历史版本不改绑。原 current-access 接口、Task 2 写保护/锁 helper、collector/DTO 公共签名、8 MiB/100-row 完整性预算和默认关闭的旧候选/Agent 边界未变。没有已知未处理的 I1–I4 技术缺口；规格/质量重审仍由协调方执行，未宣称门禁已通过。Task 4 仍未启动，必须验证其实际 producer 生成的完整五键回执与实际写时权限/版本绑定，不把本次消费测试当作 producer 证据。

> **2026-10-25 CAPA 结果审核 Task 1–2 已验收，准备 Task 3**：[八任务计划](docs/superpowers/plans/2026-10-23-capa-outcome-review.md)持续按用户授权执行。Task 1 共享基础复核通过；Task 2 已接通终态写保护、当前权限重查、来源删除与 JSON 引用锁协议，两轮修正后规格/质量复核均通过（最终代码 `acc54804`）。完整聚焦回归 **424 passed /3 既有 warnings**，包含真实 HTTP、源权限与目标范围撤销、FMEA/CP 删除及 PostgreSQL 实际锁等待/回滚竞争。以下 fix round 条目为历史实施记录，以本条最终验收状态为准。下一任务为受控读取和版本 DTO，整片结果审核/界面/最终验收尚未完成；不 push/合并/部署。

> **2026-10-25 Task 2 fix round 1 takeover**：补齐真实 HTTP 终态/撤权/目标迁移、FMEA/CP 实际删除、来源变体/畸形 JSON、正常版本演进及 PostgreSQL 真提交竞争验收。追加修正 PUT fresh admission 前重复取锁、waiver 锁后 APPROVE 门槛与历史 planning 来源别名；沿用同一自有测试库，不执行完整 `make check`、迁移或后续任务。最终同树聚焦回归 **411 passed / 3 既有 warnings**；证据及 I1–I8 对照见 `.superpowers/sdd/2026-10-23-capa-outcome-review/task-2-report.md` takeover 节；本轮仍待控制方独立复核，不声明已通过审核。

> **2026-10-25 Task 2 fix round 2/5**：复核仅余 I1（D7 来源权限锁等待重查）与新增 B1（采纳回滚后 User 过期）。本轮仅补 D7 当前 FMEA VIEW/EDIT 在父锁/来源锁后的校验，以及回滚前保留可信 actor UUID；新增 13 项真实提交/锁等待/实际唯一冲突回滚用例，完整 Task 2 聚焦回归 **424 passed / 3 既有 warnings**。增量复核 BASE 为 `5665228f`；等待控制方独立复核，不重开 I2–I8 或后续任务。

> **2026-10-19 R4b-2 已完成**：默认关闭的任务私有附件、真实扫描门禁、受权下载/删除与可恢复保留期清理已验收。最终冻结 `make check` **2999 passed / 12 skipped / 3 xfailed / 2 xpassed，exit 0**；前端 **95 项**及类型/构建、实际 ClamAV **7 项**和 Chromium **1 项**通过；1371 个源码/配置指纹未变，自有验收资源已清理。完整证据见[实施计划](docs/superpowers/plans/2026-10-09-agent-task-controlled-attachments.md)，运行边界见[操作指南](docs/development/agent-task-attachments.md)。没有 push/合并/部署；插件/模型附件投递与生产部署仍未开放。

**更新日期**: 2026-11-03
**当前分支**: `integration/agent-main-semantic-20261102`
**集成基线**: runtime `ef3e24e0` ＋ main `d8e2cef5` ＋ CI `4a00636f` 与本地安全收口
**当前阶段**: CI接入及本地分层门禁完成，进入元数据只读SDK/协议兼容设计；无 main 更新、远端推送或生产启用。

**被集成分支的历史状态**：runtime 的 R1–R4b-2、CAPA 集中审核及其多轮验证记录保留在上方和文末；main 的 PR #24/#26 权限内核、单报告只读基础与自批修复记录保留在下方。旧运行状态、资源登记和验证数字均限于对应历史快照，不作为本次结果。

**更新日期**: 2026-10-29
**当前分支**: `feature/agent-task-runtime-foundation`
**基线**: `7503e9e5`（独立工作树，未合入主工作区）
**当前阶段**: R1–R4b-2 已完整验收，原候选审批方案撤回；CAPA结果审核Task1–6已独立复核，Task7代码已复核但真实正向provider/浏览器/知识/横向仍BLOCKED（无本工作树授权.env.e2e）。Task8独立文档/契约/冻结普通回归已执行并交接，完整make仍因两项强制live测试exit2，不能签署Task8/整片完成；精确授权scanner、控制方整体复核和最终破坏性清理仍待条件。核心PG/卷/工作树/证据保留，仅授权本地提交，不push/合并/部署，Agent新能力默认关闭。

### main 集成前历史

**更新日期**: 2026-11-01
**当前分支**: `feature/agent-permission-kernel-pr`
**基线**: `main@63d06571`（#24 已合并）
**最近实现提交**: Agent 权限内核、单租户只读 8D 内部基础及测试库夹具隔离
**当前阶段**: PR #26 自批回归修复与 `main` 整合已完成本地验证，提交推送后检查远端 CI 与复审

> **历史背景（2026-07-08）**：US-E2E-01 已从单文件 v7 升级为 **epic 合集 v8.1 定稿**（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事，经 3 轮评审修订）。配套 gap analysis 已完成（`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`）。该实现工作及 US-E2E-02 FMEA 生命周期工作均已合入，以下保留的故事细节仅供历史追溯，不是当前开发分支的待办。

详细路线图见 `docs/ROADMAP.md`，本文件为当前阶段的快速看板。

### 2026-11-09 — PR29 latest-main整合本地验证完成，待parent最终集成

- 首次真实集成浏览器A业务主体验证完成但严格console门禁3失败；未改称PASS。定位main CP presence不支持已有control_plan consumer与默认off Agent capability404。
- 经确认的窄修复保留FMEA/unknown保护，CP用Planning VIEW-before-ID +effective/accessible factory及PL求交集；33真实API cases绿色；probe仅exact网络GET404+URL归因+隐藏入口，其他404/500仍失败；7文件独立复审APPROVED/0新增项。
- 新授权full-only55434与browser55433物理分离，旧55432不动，三PG/volume均保留。后修复code freeze1536路径；57focused、42前端focused、822/95完整bounded Vitest及tsc/build通过。
- fresh tag pr29-main-b **3 passed/46.5s/exit0**；17图contact与5原图LOOK，0 pageerrors，23个明确defaultoff probe404，唯一其他HTTP失败为预期stale409，CP404为0；4正常approvals/8 live-valid hashes/4completed outbox/4guardsO。仅停已核对的own app jobs，端口释放，所有controlled数据/历史失败证据保留。
- 最后full make在注册full-only55434真实exit0：4072selected/4067passed/5skip/19deselected/0fail/0error/5warnings，tsc/build通过；code1536路径before/after一致，显式projection8通过。A/B只读retention逐字段一致，55434临时schema/migrationDB均0，三PG/volume全部保留。六冲突内容无marker、index留parent stage；等待parent最终审查/提交/推送/合并，本agent未commit。

### 2026-11-08 — PR29 latest-main 本地整合（验证进行中，未提交）

- 在活动 no-commit merge 内保留功能批准来源/逐行baseline/保守保护，同时整合 main tenant、当前权限、reviewed-material及来源删除锁。六处冲突未整文件覆盖；main与功能进度均保留。
- public additive merge head `20261108_merge_characteristics`；tenant新增 `tv007_characteristic_refs`，旧revision/frozen snapshot不改。真实provision、strict namespace与audit完整CP输入锁的RED/GREEN见[既有验收文档本轮节](docs/development/characteristic-correction-acceptance.md)。
- 旧55432与证据不动；经用户新授权建立真实owner注册的独立55433/新volume，所有新运行使用该资源。bounded Vitest806/95通过，projection注册runner8通过；完整最终make和新专用browser待完成，不复用旧通过数字。
- 独立复审指出的CURRENT-head漏改已真实RED6/14→GREEN20；全部504个baseline失败/错误逐项归因。夹具保留隔离与生产guards：embedding用正式mig_db_url独立public测试库，tenant业务/后台用实际binding；最终affected226/226与完整collection4049通过，精确6文件跟进包已冻结供复审。第二轮full观察自然结束后才执行真正最终make-verified；未用混合源码跑次冒充最终结果。
- 停止预修复pytest的SIGINT被拒绝后未重试，等待自然结束，再顺序跑最终full gate。parent负责独立审查与最终提交/推送/合并；本轮不commit、不改settings/其他worktrees。

### 2026-11-08 — 特性纠偏专项验收与独立复审通过，提交前完整检查通过

- 本次运行获执行权限，严格owned55432、匹配worktree story/skill v6、新tag `mode-exit-a/b/c`。正常state/approval/hash guards开启，真实不同actor审批、5行CP/单位/手工字段、409/partial/fresh、lateworker、已消费事件后新CP部分导入刷新、可应用删除及tree确认/save/reload、DFMEA product均实际运行；最终c **3 passed/45.8s exit0**，不再仅静态/UNRUN。
- a为2pass/1fail（两个PFMEA共用fixture编号，真实400）；仅测试helper增加TREE label并新增RED/GREEN。b为3pass/54.8s，但LOOK发现最终删除截图在loader；仅增四行visible后截图及覆盖回归，c全量重跑3pass。无生产修改、无timeout/guard放宽，精确两test文件delta留`mechanics-only.patch`待独立复审。
- 新鲜bounded Vitest **602 passed/77 files**、tsc exit0；前轮完整make2302/5skip/5xfail为未改生产代码的最后baseline，不冒称重跑。c17图contact sheet全部LOOK，partial/delete/tree五张另原尺寸LOOK；无空白/loader成功证据。三页pageerror0，console12/2/5为既有弃用warning＋预期409，保留原始JSON。
- 本次新日志`.superpowers/browser-mode-exit-logs/`，完整命令/失败/截图/APIvsUI/只读审计及保留UUID见[既有验收文档最新节](docs/development/characteristic-correction-acceptance.md)。三run共12真实approve/hash proofs与12completed outbox，四guards全O、临时schemas/迁移DB0。最终新partial CP四行pending=false；原CP因后续v4删除且有manual execution保留五行pending=true，未冒称全部CP已清洁。
- 仅停核对身份/cwd后的自有worker69553/backend69889/frontend70177；PG/volume与三组受控records保留，无私密env/AI/shared reset。最终两文件test-mechanics独立scoped复审APPROVE，无新增Critical/Important/Minor；协调者核对原始退出码并实际查看17图contact sheet及删除后四行原图。原CP pending仅证明未接受工作和内容保留，不单独证明运行时曾发起并被拒绝的保护删除；该拒绝由定向回归覆盖。提交前parent完整make check已通过（exit0，2302 passed/5 skipped/5 xfailed/3 warnings，280.36s；tsc及build通过）；按用户明确授权提交推送当前分支，不创建PR/合并/部署，不清理worktree/证据/PG。

### 2026-11-08 — 新用户明确授权专用环境后，runtime仍被执行权限拒绝

- Coordinator收到用户“授权专用环境验收”后，本worker先核对owned PG/端口与worktree story/skill v6；工具解析原checkout旧v4未采用，不改原checkout。
- 第一个CPsyncworker启动在执行前再次被权限系统拒绝：requires direct user authorization; coordinator relay does not establish it。立即停止，未等价重试/peer代跑/改权限，未启动backend/frontend/browser/bootstrap，无新业务写入、PID、截图或LOOK；专用gate仍BLOCKED。
- 新只读状态`.superpowers/browser-authorized-logs/resource-final.log`：PG healthy/卷保留，58111/58112无监听；无worker执行log/exit，因为命令未执行。精确拒绝和条件限制已追加[既有验收文档](docs/development/characteristic-correction-acceptance.md)。代码/测试未变，make2302/frontend600仅为前轮实际结果；不重标新通过。
- 下一步仅由coordinator向用户说明执行权限仍阻塞；不让parent重跑同一拒绝动作。用户提交/推送条件未达成，本worker不暂存/提交/推送/部署/清理；所有代码/证据/资源保留。

### 2026-11-08 — 用户继续：bounded residual F1/F2（独立代码复审通过，browser仍BLOCKED）

- 仅修复F1/F2，不重做八项已关闭发现。F1新增最高同源/同工厂真实批准完成检查，复用hash/归属/逐行accepted覆盖与既有parent锁；历史来源仍可选，但不能抹掉新批准义务。直接耦合sync/no-op分支同修，实际完成当前目标后可清pending。真实隔离事务RED3项→聚焦六文件146 passed/3 warnings，保留partial/late/localoverride/protection。
- F2修正专用脚本候选表定位、partial剩余notice显式关闭、无失效行wf通过实际向导编辑、草稿先合法完成wizard再进主树删除。静态基线复现2失败后，mock/static/editor聚焦14 passed。来源检查/语法transpile不冒充浏览器执行。
- 先前worker及draft-browser-write拒绝仍生效；本轮无app/worker/browser/bootstrap启动、无等价/peer/API/test绕过、无guard/privateconfig变更，无新UI证据或截图LOOK。新证据仅`.superpowers/residual-fix-logs/`；新冻结residual-fix-base.zip及既有日志保留，scoped diff/checksum对新基线生成。
- 新鲜完整make exit0：2302 passed/5 skipped/5 xfailed/0 xpassed/3 warnings＋tsc/build通过；最终bounded全量Vitest600 passed/77 files，timeouts/assertions不变；默认collection42 tests/16 files。四guards全O、临时schemas/迁移DB0，自有PG保留、无新服务或资源清理。命令/限制见[既有验收文档residual节](docs/development/characteristic-correction-acceptance.md)。独立scoped复审已通过：F1 ADDRESSED、F2 source/static级ADDRESSED，八文件delta无新增Critical/Important/Minor。下一步仅为待权限系统合法授权后以新tag补跑专用真实浏览器gate及截图LOOK；overall验收仍BLOCKED，不将静态复审当作运行验收。不暂存/提交/推送/发布/删除资源。

### 2026-11-07 — 特性纠偏 final coordinated fix wave（复审未通过；代码与真实浏览器验收均阻塞）

- 核实并最小修复 I1–I7/M1–M2：初次部分导入同事务持久 pending、可应用删除显式勾选、功能/结构删除关联影响确认与dangling UUID清理、demo工序来源、独立CC/SC呈现、pytest/浏览器隔离guard分离、默认Playwright opt-in排除、受审SC规范单位复核、drawer重开busy重置。保留共享节点/审批/hash/逐行基线/手工安全API边界。
- 实际RED后backend聚焦169 passed；最终完整make exit0：2299 passed/5 skipped/3 xfailed/2 xpassed/3 warnings＋tsc/build通过；最终bounded Vitest597 passed/77 files，maxWorkers2、timeouts不变；projection8 passed。第一次make因新测试Array.at不兼容TS target exit2（非wrapper0即通过），改兼容索引后完整重跑。默认collection42 tests/16 files通过。
- CP worker启动被权限系统拒绝；专用collection因无owned worker PID fail-closed exit1。独立draft浏览器写入也被拒绝，均未改入口重试/peer代跑/绕guard。本轮没有新UI验收或截图LOOK，不复用旧r2-a作为新通过；已扩展但未运行的partial reload/applicable deletion/tree delete专用spec待合法授权重跑。
- 完整九项处置、命令/日志/失败/资源见[既有验收文档 final wave节](docs/development/characteristic-correction-acceptance.md)，新证据`.superpowers/final-fix-logs/`，冻结feature-review-head.zip未覆盖。仅新bootstrap工厂/PL/2actors/roles残留，实际FMEA/CP为0；四guards全O、临时schema/迁移库0。只停自有backend8755/frontend9022，PG/卷保留；无提交/暂存/发布。
- 独立 scoped 复审：Request changes。其余八项原问题代码层面关闭，I1 仍未完整解决：完整导入历史 v1 会把已由 v2 事件置真的 pending 清掉；扩展浏览器脚本另有候选表定位、部分导入弹窗预期、工作要素编辑入口及 wizard 未完成前置条件错误。两项均为 load-bearing，不能以现有绿色测试或权限授权代替修正。
- 下一步：按单次最终修复波次规则停止自动修复，向用户交回上述 F1/F2 与权限阻塞，等待明确后续处置；未批准合并/交付。不自动开启第二轮，不重试被拒运行，不清理未提交 worktree/证据。手工SC/默认并发/MES/外部标准等既有限制不扩大修复范围。

### 2026-11-03 — 特性纠偏 Task11 fix round 2（剩余 I2 已确认覆盖语义修正，待 scoped 复审）

- 从冻结 round1 archive 验证 scoped baseline；已关闭 I1/M3 及 version_service.py 字节不变，不重做。仅完成谓词移除 CURRENT local 值必须等于源值的额外条件，继续要求可信逐行 accepted SOURCE 投影等于完成 DOC SOURCE 投影、owner/hash/作用域/完整覆盖有效；不盲信指针，不放宽 partial/unknown/legacy/changed-source conflicts，不改 normal local-override policy。
- 实际事务 RED **2 failed/9 passed**（same/older 已真实 preview+ACK 却被重开 pending）；最小修复后聚焦 **67 passed**（包含同一 late 文件 **11 passed**，不相加）。真实 CP 普通编辑与后台 validation 在自身临时 schema 完成；另证明 changed-source 冲突拒绝 ACK，后来事件仍保守 pending。
- 新 `r2-a` 实际浏览器 **2 passed/27.0s**：普通 UI criterion edit→真实授权 API 零候选/非阻塞 warning/explicit ACK（clean CP 无 drawer，不发明入口或标志）→释放自有 worker 后值/UUID/ref/marker 保持、pending=false；经过其他特性 v2/v3 完成后再 ACK/late 交付仍不重开。Older-after-later marker 为独立真实事务例，不冒称浏览器旧事件重插。
- 新鲜完整 make check exit0：**2289 passed/5 skipped/4 xfailed/1 xpassed/3 warnings**，tsc/build 通过；完整 bounded Vitest **587/77 passed**（CLI maxWorkers2，超时不变；默认失败仍为历史、非绿色）；显式 projection **8 passed/3 warnings**。新日志 `.superpowers/task11-r2-logs/`，12 张全新截图已实际 LOOK，旧 r1/404b462f 证据不覆盖。
- 现有 [验收文档 R2 节](docs/development/characteristic-correction-acceptance.md) 已追加命令/失败分类/实际 UI/API 区分/资源与只读通知审计；仅真正 worker-first v2 一条通知，两次 late 不重 pending。guards 均 O、临时 schema/迁移库0；本轮记录保留，自有服务已停，PG/卷保留。无 report.md/提交/推送，手工 SC 遗留与外部认证限制不扩展。下一步仅 coordinator scoped I2 re-review，之后 whole-feature final review。

### 2026-11-03 — 特性纠偏 Task11 fix round 1（I1/I2 已修复并验证，待复审，未提交）

- I1：共享 criteria_with_unit 让 CP 现有准则列与新自动 SC spec_requirement 保留单位恰好一次；单位不能补成空白准则、不换算数量，unit-only 变更/明确清空沿同源 import/sync/stale 协议。SC 受审材料只提示复核，手工 API 未改。
- I2：CP worker 沿 scope→CP parent 有序互斥、等待后 fresh-row 重读，验证实际批准/hash/来源/逐行基线及完整覆盖；已完整处理的 same/older 晚到事件不重开 pending。真正更新、部分/未知仍保守；不改 source pointer 或业务字段，仅真实 false→true 记原两个字段审计。
- RED：单位参数 5 failed，SC 单位 1 failed；独立事务 late-worker 4 failed（含真实 stale-reader 死锁）后聚焦绿色，最终强持有 ORM 实例断言重读通过。实际浏览器 r1-a/r1-b 均 2 passed：真实 CP API/UI 准则有单位、unit-only 修改、worker-first；暂停自有 worker 后批准→新 CP/UI 导入，和真实 partial→再批准→UI 完成同步，恢复 worker 后仍不 pending。三轮实际批准/hash、行 UUID/逐行接受版本/手工方法保持；11 张新 tag 截图已 LOOK，旧 404b462f 数据/图片/JSON 保留。
- 新全套发现旧 embedding 测试 claim 64 个公共事件导致 6 failed；获协调者窄范围授权，仅三文件 opt-in 使用必要表/FK闭包的临时 schema，保留实际 claim/fetch/upsert、commit/rollback、batch64 和所有断言；新 regression 证明提交/回滚/重连不落 public，三文件 22 passed。未 drain/伪嵌入/删除保留队列；r1 两浏览器工厂各 12 pending embedding tasks、0 stored embeddings。
- 最终 make check exit0：**2286 passed、5 skipped、4 xfailed、1 xpassed、3 warnings**，tsc/build 通过；full Vitest **587/77 全覆盖通过（CLI maxWorkers=2，超时不变）**，默认命令两轮均有 3 个 5s timeout，不称默认绿色；显式纯 projection **8 passed/3 warnings**，最终真实浏览器 **2 passed/28.2s**。新证据路径 `.superpowers/task11-r1-logs/`；完整结果/命令/失败/LOOK/资源见 [既有验收文档 r1 节](docs/development/characteristic-correction-acceptance.md)。旧 2258/587/2pass 只作首轮历史。
- 02.18 故事/scoped verify 剧本同步 v6（2026-11-03）；epic/planning 的 M3 历史/当前矛盾已澄清。仅 owned qms_test，正常 UI guards 开启；新临时 schema/迁移库已清理，自有 app/worker 已停，PG 容器/卷和批准证据保留。手工 SC 遗留缺陷、外部服务/标准认证限制未扩展修复。下一步由 coordinator 独立复审 I1/I2 与 Task11，再作 whole-feature final review；无提交/推送。

### 2026-11-03 — 产品／过程特性纠偏 Task 11（首轮历史；随后 I1/I2 缺口与修复见上节）

- 同步 planning／types／utils／graph 文档、四个故事与派生 verify 剧本（02.3/02.10/02.15 v3、02.18 v5，2026-11-03）、epic README v4；[验收基线](docs/development/characteristic-correction-acceptance.md) 已追加 A01–A21 证据、全部验证日志、真实 UI/API 前置区分与限制，保留历史结论。
- TDD 收尾真实 HAS_FUNCTION owner＋FMEA type 判定、既有空名必填反馈、metadata-only Alembic head 断言（20261101_char_refs）。真实浏览器进一步发现并以失败回归修复 CP create MissingGreenlet、CP response pending/source 字段遗漏、确认缺 step_ids 及 409 后 busy 锁死；未放宽任何业务／批准保护。
- 实际浏览器：合法 draft 的同工序 2 产品＋3 过程录入／单位／关系、保存刷新、既有向导完成、不同授权人真实批准、选择批准快照生成 5 CP 行；合法返工改名再批准，实际 409→重预览→部分 pending→显式新预览完成，稳定行 UUID／逐行接受版本／手工执行字段保持。DFMEA product smoke、历史快照只读及普通 SC 精确 trace API＋无 MSA/SPC 证据提示通过；九张截图已实际 LOOK。
- 最终 **make check exit 0**：后端 **2258 passed、5 skipped、3 xfailed、2 xpassed、3 warnings**，tsc/build 成功；full Vitest **587 passed / 77 files**；显式纯 projection **8 passed、3 warnings**；最终真实浏览器 **2 passed（18.3s）**。未排除 head/backfill。保留 E2E 历史后，全库 outbox/audit 断言曾失败；现改为本 fixture IDs 精确断言，无删除历史或约束放宽。worker 等待按确切版本的只读 completed metadata，而非旧 pending 标志或固定延时。
- 仅任务 PG 127.0.0.1:55432/qms_test；完整旧负面 fixtures 的临时库／schema／trigger fault 数据按授权使用并恢复，正常 UI guards 全开。14 个明确无版本 draft 已经合法 API 清理，保留审批／版本／审计及最终 smoke 证据；自有 app/worker PIDs 已停止，PG 容器／卷保留。无私密 env 复制、外发 AI、共享 reset、原 checkout 修改或提交。
- 限制：手工 SC 安全更新／删除与通用 create 审计缺陷仍 UNFIXED；未做全 AI、PPAP、CSR、scanner 或 live Neo4j 认证。下一步只交 coordinator 做 Task11 独立评审，再做 whole-feature final review；不把本轮自动／专项结果当成整功能获批。

### 2026-11-03 — 产品／过程特性纠偏 Task 10（演示数据与版本基线，未提交）

- `seed.py` 将 DC-DC 100W SMT 主示例收敛为固定 UUID 的产品“元器件贴装偏移量（≤0.05 mm）”和过程“贴装力（3.0±0.5 N）”两项，分别形成 AOI 位置／每次动作力监控行；均为模拟草案、无特殊分类、无接受版本来源。PFMEA、最小 DC-DC DFMEA、CP 与 APQP 使用同一 DC-DC 设计来源；BMS DFMEA 明确为独立示例并有同工厂有效 BMS-DEMO 产品线范围。
- 旧主示例中的空载转速、RPM、压力／扭矩、伪 CC/SC 和悬挂失效引用已移除；原不完整 PFMEA/CP 新环境构造改为 draft 且审批字段为空。SPC/MSA 演示不再以主特性作为已验证证据。
- Doc-gate E2E canonical 行将“定位销磨损量”作为对象、把检测活动放入方法、保留未知限值，并将显式空来源写入版本快照构造以保持 diff/hash 输入一致。
- 验证：首轮 RED `test_characteristic_demo_data.py` 为 5 failed（构造函数不存在）后，聚焦回归为 **41 passed**；评审修复再做 RED（3 failed：DC-DC 选择／BMS scope／APQP 参数未实现）后，demo＋Task 3 mapping＋CP provenance 为 **27 passed**，CAPA doc-gate preflight（排除 `hash_backfill`）为 **16 passed、1 deselected**。仅使用独立 `qms_test`；未执行 `app.seed`／`seed_e2e`、迁移、全后端、E2E 或容器操作。
- 下一步：Task 10 独立评审；如需验证实际新环境 seed，先取得独立 E2E 环境执行授权，不能将本轮纯构造通过视为已发布、MSA、PPAP 或顾客批准。

### 2026-11-03 — 产品／过程特性纠偏 Task 9（自动消费者完成，未提交）

- 用户已明确仅约束本次自动同步，解除下方历史阻塞：SC 按文档＋特性 UUID 提取，类型／分类／规范独立，空数组及未分类项不因功能分类／严重度升级；改名保持 SC 身份。submitted／approved 安全材料和来源绑定不自动改写／删除，源变化仅返回复核提示。旧手工 SC 保护和通用 create 审计缺陷仍未修复。
- 新来源 CP 追溯按完整 source_ref、实际 RequestScope 和工厂／产品线派生全部控制行，不写最后一个 `cp_item_id`；SC 自动入口不改写新来源 CP 字段或已批准 CP，差异指引进入正式版本同步。SPC／量具依实际 FK，MSA 依实际同范围研究／结果，缺证据不显示缓存 PASS。
- 新增 R005／R006 warning，finding 按来源＋持久行 UUID 分隔；改名／排序不换身份，同源多控制行不共用决定，不增加审批门禁。Task 2 延后的两工厂同名写入级回归已通过：两份 FMEA 均实际 PUT 成功，第二份引用第一份产品 UUID 后由特性验证拒绝，图／锁／审计保持。
- 验证：聚焦后端 **161 passed、1 deselected**（主动排除 backfill 风格用例），含真实独立连接／临时 schema 竞态和 API 中途失败回滚；追溯组件 **4 passed**，`npx tsc --noEmit` 通过。仅用 `127.0.0.1:55432/qms_test`；未运行全后端／全 CAPA、迁移、容器操作或真实浏览器验收。
- 下一步：独立评审 Task 9，随后按授权做 Task 11 真实服务验收；不把聚焦通过当作 PPAP／CSR 或全部标准验收。详细范围、RED／GREEN、手工入口遗留风险见 `.superpowers/sdd/2026-11-01-product-process-characteristics-correction/task-9-report.md`。未提交／推送。

### 2026-11-02 — 产品／过程特性纠偏 Task 9（历史安全前置阻塞，已由用户限定自动范围解除）

- 按 Task 9 Step 5 先验证受审对象保护：真实 SC 安全提交 API 成功后，通用 PUT 仍可改变名称／规范且保持 `submitted`；DELETE 返回 200 并实际删除该受审对象。仅在 `127.0.0.1:55432/qms_test` 的回滚事务内验证，新增两项 API／DB 测试真实 RED（2 failed，3 项既有 Pydantic 警告）。
- 未擅自增加审批／删除策略或修改安全工作流；按 brief 的阻塞条件停止，Task 9 提取／追溯／校验与 Task 2 延后写入级隔离验收尚未完成，无 GREEN 或完整验收结论。
- 下一步：确认受审保护是否涵盖 SC 主数据；若涵盖，先明确授权窄范围的安全状态／字段修改删除规则与合法变更路径，再恢复 Task 9。详细场景与命令见 `.superpowers/sdd/2026-11-01-product-process-characteristics-correction/task-9-report.md`。本轮未提交。

### 2026-11-02 — 产品／过程特性纠偏 Task 8（CP 前端，未提交）

- CP 的 PFMEA 导入改为仅使用用户选择的已批准 FMEA 版本快照：版本列表只提供 `change_type=approve` 的 v1.0+ 快照，工序来自所选快照，而非当前 rework 图；预览和确认分别携带来源版本、CP 锁、摘要与 `candidate_key`。
- 同步抽屉显示后端候选与安全限制，受保护／冲突／不适用候选不能选择，删除默认不选；空候选允许显式 no-op 确认。导入／同步的 409 都会失效旧预览，不自动重试；CP、来源、选择、关闭及卸载时忽略陈旧异步结果。
- CP 写入明确白名单化，只保留现有 `item_id` 与允许字段，绝不回写服务端来源元数据；控制计划标准列、分组和中英文主题未重排。`controlPlanDiff` 改为来源元数据内容比较，避免对象引用导致永久冲突。
- 验证：Task 8 三个新组件／模板测试与 `CPVersionSnapshot` 共 11 passed；前端 `npm run build` 通过。Vitest/Vite 仍输出既有 Node localStorage、getComputedStyle 和 esbuild/oxc 弃用警告；未运行浏览器 E2E、后端、数据库或容器操作。
- 下一步：按授权做 Task 8 独立审查与 Task 11 浏览器验收；不把本轮组件测试当作端到端验证。

### 2026-11-02 — 产品／过程特性纠偏 Task 6（后端，未提交）

- 已按用户确认的[同步保守保护补充](docs/superpowers/specs/2026-11-02-cp-sync-conservative-protection-design.md)恢复并实现逐特性同步、稳定候选选择、逐行批准快照三方基线及统一 stale-check；之前缺少既有 guard 的阻塞已由正式补充解决，不再沿用旧假设。
- 保留实际行 UUID、人工方法及执行关联；源清空和工序编号变化显式呈现；部分接受、受保护行及旧混合行待办保留 pending。仅全量覆盖处理完才推进文档来源跟踪；真实 no-op 不偷偷重置逐行接受版本。
- 自动同步保护活动 CAPA 当前有效材料，执行／特殊特性关联禁止自动删除；CAPA 目标发布、审核及决定参与 CP 父锁／输入新鲜度协议。通用手工更新、草稿回退及 CAPA 审核／豁免业务含义未改变。
- 验证：特性／导入／真实事务／实际权限替换写入器／worker 及完整 CAPA 聚焦回归 724 passed。全后端首次执行 2143 passed，唯一失败是原有迁移测试硬编码旧 head（实际授权 head 为 `20261101_char_refs`），相关测试与迁移均与 Task 6 基线归档一致，未越界修改。 最终后端复跑排除该旧断言：2154 passed、5 skipped、1 deselected、3 xfailed、2 xpassed；Task 6 四文件最终 43 passed。
- 验证范围偏差：全量套件既有 `mig_db_url` 夹具通过任务实例的管理连接创建／清理 `qms_migtest_*` 临时库，超出了本次仅 qms_test／临时 schema 的限制；已如实交接，未再执行此类验证。Task 6 新事务测试自身仅使用 qms_test 临时 schema，未操作其它容器或业务库。
- 下一步：Task 6 独立评审，随后按授权处理 Task 7/8 前端选择契约与后续验收；本次不自动开展。仍未补 Task 2 延后的跨工厂同名写入级测试，也未新增已批准 CP 的合法返工流程。详细后端语义见[验收基线新增节](docs/development/characteristic-correction-acceptance.md)。
### 2026-11-01 — PR #26 提交推送与远端复核

- 按本次授权提交自批回归修复及 `main@63d06571` 的冲突整合，更新原 #26 分支；提交前重新执行权限策略测试，39 passed（3 项既有 Pydantic 弃用警告）。完整本地验证证据见 2026-10-31 条目。
- 本次推送后核对远端提交、冲突状态、CI 与代码复审结果；以对应提交的 GitHub 检查为准。当前授权不包含直接合并 PR。

### 2026-10-31 — PR #26 自批回归修复与 main 整合

- 恢复 `can_employee_approve()` 的请求发起人检查；员工发起、服务执行及其他用户代执行均不得由发起员工自批，独立审批员工仍可按原资格规则审批。新增回归先复现失败，再验证修复。
- 与 `main@63d06571`（#24）逐项整合 13 个冲突文件：保留 CAPA 模块持有声明、模块专用审批/范围/来源投影检查，同时保留不可原位修改的目录、无时区时间戳拒绝、来源版本、非空交付目标及派生交付敏感等级绑定。能力仍为 `DENY`，未新增运行入口。
- 验证：聚焦策略测试 39 passed；在自有临时 PostgreSQL/全新 `qms_test_pr26_merge_20261031` 上执行 `make check-backend`，2048 passed、5 skipped、3 xfailed、2 xpassed（3 项既有 Pydantic 弃用警告）；前端 `check-frontend`（TypeScript + Vite 构建）通过。临时测试容器已清理，未连接业务库。文档相对链接与差异空白检查通过。当前为本地未提交的合并结果，尚未推送或合并 PR。
- 限制：`npm ci` 报告锁定依赖有 30 项审计告警（1 low、18 moderate、11 high），本次未修改依赖或自动升级；既有 MES 的 2 个 XPASS 不视为本次修复。
- 下一步：经授权提交本地合并结果并推送以更新 #26，确认远端 CI 后再决定合并 PR；当前远端 PR 尚未变化。

### 2026-09-29 — Agent 模块权限内核（独立切片）

- 对照 [权限设计](docs/superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md) 核对并修订 [实施计划](docs/superpowers/plans/2026-09-26-agent-module-permission-kernel.md)：CAPA 持有声明；派生数据按来源能力及投影校验，脱敏权限不能复用为原文权限。
- 已实现纯策略目录（调用前核对服务端规范声明）、身份×插件×任务交集（全域范围须验证 GROUP ADMIN / 行级豁免）、审批下限/模块专用员工资格、来源投影限制与显式交付守卫；CAPA 试点能力仍为 `DENY`，**未接入生产入口**。业务锚点和边界见 [能力盘点](docs/development/agent-module-capability-inventory.md)。
- 验证：新内核与旧 Agent/工厂作用域聚焦回归通过；完整 `make check-backend` 未通过（1909 passed、34 failed、2 errors，另有 skipped/xfail/xpass），独立复现 `qms_test` 缺少 FMEA 版本 trigger；旧 PPT review seed、嵌入表列等另有失败，未在本切片修改。
- 下一步：先确认设计 §6 的租户绑定、插件身份/可信部署、任务授权持久化、CAPA 脱敏投影及外发矩阵，再另行规划只读 8D 试点；不要把内核测试通过当成实际授权上线。

### 2026-09-29 — 独立测试库基线恢复

- 旧 `qms_test` 的 Alembic 版本虽为 `20260727_warranty_factory_id`，但缺少 FMEA/控制计划版本 trigger 和 `document_embeddings.embedding` 列；在该库运行 `make check-backend` 得到 34 failed、2 errors。新建 `qms_test_baseline` 并从空库迁移到 head 后，上次失败的 36 项全部通过，完整后端套件为 1974 passed、5 skipped、3 xfailed、2 xpassed。
- 已把旧库改名保留为 `qms_test_drifted_20260929`，重新创建默认 `qms_test` 并从迁移构建。默认 `make check` 通过：后端同上，前端 TypeScript 检查与构建通过。此项为本地测试库修复，没有改动业务数据库或生产代码。
- 下一步：确定只读 8D 试点的首个开发切片，再补齐对应实施规格；身份/租户绑定、任务授权持久化及 CAPA 脱敏投影是当前建议的起点。

### 2026-09-29 — 只读 8D 首切片设计与计划

- 设计阶段选定单报告任务授权持久化与 CAPA D4 元数据投影作为首切片；[设计规格](docs/superpowers/specs/2026-09-29-agent-readonly-8d-foundation-design.md)按审查意见增加多租户逐事务隔离前置条件及完整投影摘要。单租户内部基础现已实施，见下节。
- [实施计划](docs/superpowers/plans/2026-09-29-agent-readonly-8d-foundation.md)按测试先行顺序执行了单租户任务表、服务和投影；多租户路径在逐事务绑定和无 `public` 回退的测试验收前关闭；能力仍为 `DENY`，不提供插件或 HTTP 读取入口。
- 后续依赖：多租户隔离改造及验收独立安排；外部交付尚未开放。

### 2026-09-29 — 只读 8D 内部基础

- `agent_read_tasks` 表及迁移、单报告任务生命周期服务已实现。服务仅在 `TENANT_MODE=single` 运行；创建时按服务端 CAPA 记录确定工厂与产品线，检查时重验操作者权限、范围、有效期及撤销状态，并记录安全审计。
- CAPA D4 元数据投影使用明确字段白名单，在同一只读 `REPEATABLE READ` 快照中读取报告和验证子记录，对完整投影计算 SHA-256 摘要。新增验证记录、修改结论会改变摘要；投影不包含 D4 自由文本。
- 集成测试覆盖真实持久化任务生成 `Grant` 后，规范能力 `capa.d4.summary.masked.v1` 的 `DENY` 仍使 `authorize()` 拒绝交付；非单租户模式在任务服务查询和投影开启会话前拒绝。未新增 HTTP、插件或模型读取入口。
- 验证：任务及投影聚焦测试 30 passed；新建隔离库从空库迁移后，新任务表的升级/约束/降级 3 项测试通过。首次新库 `make check` 通过：后端 1969 passed、43 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过。原默认 `qms_test` 虽标记为新 head，仍缺少控制计划版本 trigger 和基础角色，导致全量测试失败；已保留为 `qms_test_drifted_task4_20260929`，并将经全量验证的新库改名为默认 `qms_test`。默认 `make check` 复跑通过：后端 2007 passed、5 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过。
- 后续连续复跑定位到 `tests/test_spc_fmea_match.py` 的夹具会对共享 `qms_test` 执行 `drop_all/create_all`，抹掉迁移 trigger 和角色种子，造成下一轮全量失败。该夹具现使用独立临时库；回归测试先复现 trigger 丢失、修复后 11 passed。恢复默认测试库后，连续两次 `make check` 均通过：后端各 2008 passed、5 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查和构建通过；首轮后确认 trigger 与基础角色仍存在。漂移库保留为 `qms_test_drifted_fixture_20260929`。
- 2026-09-30 PR 整合：在独立工作树的 `feature/agent-permission-kernel-pr` 分支合入 `main@dbd58690`，保留 main 的 SPC 临时库夹具及本切片的 trigger 保留回归；进度文档保留两侧记录。新建 `qms_test_agent_pr_20260930` 后运行 `make check` 通过：后端 2026 passed、5 skipped、3 xfailed、2 xpassed，前端 TypeScript 检查及构建通过。
- 下一步：先独立完成逐事务租户绑定、无 `public` 回退及提交/回滚/连接复用/租户缺表等隔离验收；插件身份与外发控制再单独设计、评审。当前单租户内部基础不代表能力批准或多租户可用。


---

## 独立租户迁移与 Agent 接入（2026-10-01）

- **已实现**：逐事务租户/generation 绑定、全局功能失败关闭、独立静态迁移链与对象级 parity、固定物理连接维护锁、原子 seed 和同租户恢复；插件安装与长期授权表默认禁用。规格及实施记录见[租户设计](docs/superpowers/specs/2026-09-27-independent-tenant-migration-design.md)、[租户计划](docs/superpowers/plans/2026-09-27-independent-tenant-migration.md)。
- **本轮改动**：精确测试清单、观察 Compose/数据库排空、同一锁所有者重建、跨 schema 依赖拒绝、失败恢复与完整空租户插件表验收。独立规格复核发现并修复了 owner claim 清除未完成重建标记的问题；规格与代码质量复核均通过，无未解决的重要问题。
- **验证**：独立一次性数据库完整后端 `2109 passed / 4 skipped / 3 xfailed / 2 xpassed`；skip 为 Redis 未启动和 E2E 未启用。前端 `tsc --noEmit` 与 production build 通过。最终崩溃标记修复后的重建/维护/parity 聚焦运行 `90 passed / 0 skipped`，其中 36 项重建覆盖四个持久化中断阶段；PG15 快照导出已验证。
- **Agent R1 Task2**：已实现持久任务、运行、只读授权与受限消息模型，public `20260926_agent_task_core` 接在平台 attempt 之后；独立租户 `tv002_agent_task_core` 接在冻结 tv001 之后。已知完整 tv001 可在原维护锁/generation 流程下前向升级，未知或部分 schema 仍拒绝；尚无任务服务或 API。新增约束及两链升级/回滚、旧租户升级和最新 parity 聚焦验证 `20 passed`；任务/迁移/租户恢复/测试重建回归原批次 `120 passed / 1 failed`（旧基线夹具缺平台 owner 列），仅修正该 bootstrap 夹具后的独立复验 `1 passed`，冻结快照导出已通过。独立规格与质量复核均通过；`compileall` 与 `git diff --check` 通过。
- **Agent R1 Task3**：安装凭据仅持久化 bcrypt 哈希、默认禁用、轮换递增 epoch；独立短期运行 JWT 每次验证回查租户 generation、插件、任务与执行人。单租户显式绑定 public，多租户要求真实 TenantSession；无新 API 或业务数据交付。凭据与既有模型矩阵 `108 passed`；复核小修正 `6 passed`，规格与代码质量复核均通过。
- **Agent R1 Task4**：目标绑定任务服务每次重读用户、角色权限及工厂/产品线范围，列表和数量使用相同可见性过滤；只读授权固定目标且经过规范内核。默认 DENY 生成阻塞任务，无运行；测试声明授权完整时生成待运行记录。幂等与真实双事务插入竞争验收通过，凭据/任务/内核矩阵 `161 passed`，两阶段复核均通过。
- **Agent R1 Task5**：发起者消息在任务行锁内分配序号、处理幂等并提交受限正文与安全审计；锁后重新检查当前权限、范围和任务状态。真实事务覆盖不同键/相同键/冲突内容、持久化、缓存状态及锁等待中停用；运行时/内核矩阵 `191 passed`（含 30 项消息测试），规格与代码质量复核均通过。
- **Agent R1 Task6**：用户任务/消息和管理员插件/长期 grant API 已实现，默认关闭、两阶段复核通过；聚焦矩阵 `230 passed`，单独锁等待归属测试 `1 passed`。完整后端首次运行发现解析器旧连接池跨测试事件循环及旧版本断言，仅修正测试夹具/协调/断言后受影响组 `234 passed`。最终全新一次性库复验 **`2320 passed / 4 skipped / 3 xfailed / 2 xpassed`（528.71 秒，exit 0）**，前端类型检查与构建通过；测试修正经规格、质量复核确认，R1 完整验收通过。
- **Agent R2 Task1**：运行领取、租约、完整权限刷新、插件专用 HTTP 身份与 public v3／tenant tv003 已实现，规格与代码质量复核均通过，无未解决的重要问题。较大回归 `370 passed / 0 skipped`（445.60 秒，包含 PG15 导出），锁归属/关闭路径修正后的相关组 `39 passed`，补充持久化与撤权组 `40 passed`；能力发现规范修正后最新运行时/内核/相关 API `274 passed`（133.71 秒，exit 0）。
- **Agent R2 Task2**：按序消息领取、连续幂等确认、当前 run/租约绑定、读后最终权限检查与安全审计已实现，规格与代码质量复核均通过，无未解决的重要问题。较大相关组 `316 passed`（251.68 秒），跨运行批次修正后完整相关服务/API `43 passed`（117.48 秒，exit 0）；不修改历史迁移。
- **Agent R2 Task3**：完整 D4 元数据白名单、租户绑定 RR/只读快照、两个 view 的完整 digest、读后最终授权及服务端 receipt 已实现。规格与质量复核发现并修复两种产品线迁移竞态；最终交付核对权限检查当次获授权的产品线。修正前相关回归 `354 passed`（319.48 秒）；最终受影响服务/API/身份组 **`176 passed`（172.94 秒，exit 0）**，真实双事务证明撤权和两种产品线迁移拒绝旧快照且不生成 receipt/审计。规格、质量及最终身份字段专项规格复核通过。
- **Agent R2 Task4**：有界结构化事件/受限结果、当前运行/租约/generation 的复数 receipt 校验、串行幂等和原子审计已实现。普通用户结果读取重查任务及全部来源权限，保留停用插件、结束运行或租户维护后的授权历史；最终再校验来源与任务目标，拒绝读取中的目标变更。规格与质量复核通过；相关运行时/API/内核 **`381 passed`（415.34 秒，exit 0）**，最终输出服务/实际中间件 API **`42 passed`（103.72 秒，exit 0）**，编译与差异检查通过。
- **Agent R2 Task5**：独立 stdlib 插件进程已通过实际 HTTP、完整租户和真实凭据贯通两轮依赖查询、按序消息确认、复数 receipt 及事件/受限结果。最终进程矩阵 **`22 passed`（64.15 秒，exit 0）**，包含轮间停用/撤权、同 UUID 跨租户拒绝、默认关闭/DENY、禁止重定向及真实 TCP 畸形响应拒绝；两种异常输出泄漏已红绿复现修复。规格与质量复核通过。CLI 修正前相关组 `418 passed`（495.46 秒）；最终前端类型检查与构建通过。
- **R2 最终门禁通过**：冻结代码在新一次性库完整后端 **`2526 passed / 4 skipped / 3 xfailed / 2 xpassed`（948.18 秒，exit 0）**；独立进程 22 项包含在该运行内，前端类型检查与构建 exit 0。4 项 skip 为 Redis 未启动和 E2E_MODE 未启用，既有 xfail/xpass 保留。整体实现复核通过，无未解决的重要问题；[只读元数据链路](docs/superpowers/plans/2026-09-30-agent-readonly-metadata-integration.md)完整验收结束。CAPA 能力目录仍为 DENY、运行时默认关闭；未执行用户环境重建、push 或 merge。
- **R3 完整验收通过**：固定目标统一侧栏、同运行暂停/继续、服务端只读检查点与新运行重开已实现。Tasks1–7 及显示/取消两项整片修正均通过规格、质量及最终复核，无未解决的重要问题；完成/追加双向竞争、连续两页刷新与失败重取、历史重新授权、旧凭据/receipt拒绝、当前事实重读及8个真实浏览器场景已贯通。最终冻结后端 **2731 passed / 4 skipped / 3 xfailed / 2 xpassed（1729.61秒，exit0）**，前端 **78项/7文件**、类型/构建及专用E2E类型检查通过；61个最终源码哈希不变，一次性测试库已清理。4项skip为Redis1与旧E2E_MODE端点3，既有xfail/xpass保留。恢复不保存插件内部记忆，不回滚业务数据。默认关闭、CAPA DENY、可信目录为空；改动保留独立工作树，未合并或部署。详见[实施计划与验收证据](docs/superpowers/plans/2026-10-01-agent-sidebar-readonly-controls.md)。

- **R4a 范围已确认（2026-10-02）**：用户采用“仅 D4 元数据、本地受控试用”。已编写[设计提案](docs/superpowers/specs/2026-10-02-agent-metadata-local-trial-design.md)和[六任务实施草案](docs/superpowers/plans/2026-10-02-agent-metadata-local-trial.md)：服务端精确策略与规范能力 profile、正常 grant/任务配置链、令牌/到期绑定、永久撤销、固定启动器、正常策略下真实进程/浏览器验收。仅完成文档，未改变 R3 代码、启用运行时或执行迁移；书面方案尚待用户审阅。
- **R4a 实施中（2026-10-05）**：用户已确认书面方案，另行明确授权自有随机 `_test` 库的创建/迁移/清理。保留 R1–R3 原有改动基线；相关后端基线 `526 passed`，前端类型/构建通过。Task1 严格启动策略与请求会话快照接入红绿验证 `53 passed`；Task2 规范 profile/精确绑定与默认拒绝回归 `85 passed`，正常 grant→目录→建任务及绑定变更 `8 passed`。广回归 `606 passed`、运行 API 回归 `26 passed`、撤销/真实事务与凭据回归 `61 passed`，最终 R4a 新契约/规范权限/正常 CLI/Chromium 聚焦 `147 passed`。冻结前端类型/构建、74项单测及 E2E 类型检查通过，独立复核未发现具体重要缺陷；1197个源码/配置文件已冻结且未变化，相关47个文档链接及差异检查通过。完整全新隔离库冻结后端 **2859 passed / 4 skipped / 3 xfailed / 2 xpassed（1977.86秒，exit0）** 通过；4项skip为Redis1与旧E2E_MODE端点3，既有MES非严格预期失败/通过标记保留，沿用Makefile两项graph测试排除。R4a整片验收结束，自有主测试库与插件/Vite/浏览器进程已清理；另4个目录创建于2026-09-27/28的存量随机临时库未删除。默认关闭，不启用用户或生产环境。详见[六任务计划与执行台账](docs/superpowers/plans/2026-10-02-agent-metadata-local-trial.md)。
- **R4b-1 设计中（2026-10-05）**：用户已选择“D4正文脱敏底座”与“规则＋显式替换词”。首片只覆盖 d4_root_cause 及验证 root_cause_text/result，生成平台内部只读候选，全部仍为restricted，不扩到附件/模型/插件正文或业务写入。[书面设计](docs/superpowers/specs/2026-10-05-capa-d4-text-redaction-foundation-design.md)已写入，包含当前CAPA/FMEA来源权限、默认关闭、预算、内容安全422、源版本/短期失效和审计；尚待书面审阅，未实现新接口或运行新片测试。
- **R4b-1 实施中（2026-10-06）**：用户确认书面设计并按[六任务计划](docs/superpowers/plans/2026-10-06-capa-d4-text-redaction-foundation.md)执行。相关新基线186项及前端类型/构建通过；纯规则/DTO42项、受权快照17项、普通用户API4项红绿验证通过，共享当前访问抽取及旧运行时回归643项。本片与R4a/R3实际进程/浏览器聚焦119项通过，前端相关40项及类型/构建/E2E类型检查通过。独立复核两项收口已红绿修正：服务端失权/不确定性同时清空显式词；成功快照仅查询批准正文/来源元数据。修正后服务/API/实际Chromium25项与前端40项通过；1214个源码/配置已冻结；2026-10-06完整新库后端 **2926 passed /4 skipped /3 xfailed /2 xpassed（2067.61秒，exit0）**，前端 **87项/8文件**及类型/构建/E2E类型检查通过。2026-10-07恢复会话实际 `make check` 在另一个自有新库复验，同样 **2926 passed /4 skipped /3 xfailed /2 xpassed（2174.36秒，exit0）**，前端构建通过。冻结源码未变、60个文档链接有效、自有库和子进程清理；既有Redis1/旧E2E_MODE3跳过、MES非严格xfail/xpass及Makefile两项graph排除保留。整片验收结束，剩余附件/原文例外/降敏发布/SDK/部署与正文外发门禁不因此开放。始终restricted/外发关闭，不改业务原文、结论或R4a目录；[操作指南](docs/development/capa-d4-text-preview.md)已同步。
- **当前下一步（2026-10-25）**：按[CAPA 措施实施后的集中结果审核实施计划](docs/superpowers/plans/2026-10-23-capa-outcome-review.md)子代理驱动执行；本片资源与本地提交已获明确授权，独占环境与完整基线已通过；Task 1–2 已验收，Task 3 完整结果读取、来源约束与版本 DTO 的 I1–I4 fix round 1/5 已修正，最终完整受影响聚焦 242 passed；Task 3–4 独立复核已通过，按授权推进 Task 5 生产集中审核界面；Task 7 真 provider/浏览器与 Task 8 完整冻结仍须完成。设计及 P1 已通过书面复核。原 D4 候选申请/发布审批及 7 天审核正文清理不再实施，不重复启动已验收的 R4b-2。D8 保留既有状态机/门禁并已接入版本条件，前端仍待 Task 5 配套升级；插件/模型正文附件投递、Agent 业务写入、原文例外与可信部署不因此开放。保留独立工作树，提交、push/merge/部署仍按各自授权边界处理。

---

## 模块级 Agent 权限内核（2026-09-26，第一切片）

> 以下为第一切片当日状态；后续单租户任务持久化和内部投影进展见上文，不能据此判定生产授权已接线。

- **已完成**：CAPA D4 样板能力目录（条目均为 `DENY`，未开放；授权时回查不可原位修改的服务端目录）；纯策略内核覆盖执行身份×插件×任务授权范围、最低审批与员工资格、明确外发许可、跨模块派生来源和敏感等级继承。服务身份发起操作不一律人工审批；由员工发起的后台任务禁止该员工自批。
- **边界**：尚未接入现有 Agent gateway、任务/插件持久授权、业务查询和写入、审批 API、模型调用、索引或外部插件。此内核的单测通过不代表生产入口已受新策略保护；现有 Agent 功能保持不变。
- **下一步**：按[权限规格](docs/superpowers/specs/2026-09-26-qms-agent-module-permissions-design.md)逐片确认插件身份/协议、8D 数据分类和审批矩阵、任务授权与可信外发部署；随后编写持久化与只读 8D 样板的独立计划，再规划正式命令和模块推广。

---

## 公开项目首页（2026-09-13）

- **状态**：公开 `/` 首页已完成，无需登录；AI-first 内容、中文/英文切换和 Viewer 演示门控已完成。
- **自动化证据**：页脚链接 TDD RED `1 failed / 8 passed`（语义页脚内缺少 `View GitHub`），最小实现后 GREEN `9/9 passed`；公开首页 focused tests `5 files / 30 tests passed`；`PublicHomePage.tsx` 与其测试文件级 ESLint exit 0；前端 production build exit 0（Vite `6835 modules transformed`）。最终 `make check TEST_DB=qms_test_public_home_fix_round1` 在新建专用库上 exit 0：backend `1957 passed / 5 skipped / 3 xfailed / 2 xpassed`（25 warnings），frontend `tsc --noEmit` 与 production build 均通过。
- **2026-09-21 范围收缩**：多轮评审持续发现 authStore、Axios 401 队列与跨标签 refresh 轮换的新增竞态；按产品决策，已从本 PR 撤回认证状态机、刷新协调器及其并发测试，`authStore.ts`、`api/client.ts` 和 `ProtectedRoute` 恢复到已合入 `main` 的行为。公开首页“进入系统”只在 token 且 user 已加载时进入 `/dashboard`，否则进入 `/login`，避免仅凭持久化 token 进入受保护页。TDD RED：仅有持久化 token、user 未加载时错误跳往 `/dashboard`；GREEN：公开首页/演示/路由聚焦 `5 files / 26 tests passed`，文件级 ESLint 与 production build 通过。`make check` 首次运行时现有共享 PostgreSQL 容器中途停止；改用仅绑定 `127.0.0.1:55422` 的隔离临时数据库后，`make check TEST_DB=qms_test_pr22_homeonly_20260921b` exit 0：backend `1975 passed / 5 skipped / 3 xfailed / 2 xpassed`，frontend `tsc --noEmit` 与 production build 均通过。隔离容器已停止。认证基础设施的既有问题留待独立任务处理，本 PR 不宣称修复它们。
- **浏览器验收**：真实 Playwright 在 `1440×900`、`390×844`、`320×844` 通过；三档均 `scrollWidth == clientWidth`（分别 `1432/1432`、`382/382`、`312/312`），Hero、AI、能力、架构、开源区均可读。桌面锚点导航可见，移动端隐藏；语言和系统入口始终可见，320px 头部两行均在视口内。新增页脚链接后复验 390/320px：两链接均可见，320px 页脚宽 `284px` 且完整位于 `312px` clientWidth 内。
- **路由与可访问性**：公开 `/` 无 `/api/` 请求即可渲染；未登录访问 `/dashboard` 跳转 `/login`；中英文原地切换不 reload；实际交互链接均可由 Tab 到达且有 `3px` 可见焦点。语义页脚内新增 GitHub 与项目文档链接，复用本地化文案和既有 URL，均带 `_blank` 与 `noreferrer noopener`；真实浏览器中分别为 Tab stop 15/16。
- **演示门控**：关闭配置时 `/login?demo=viewer` 不显示演示卡或凭据；仅用进程环境临时启用的假值可显示 Viewer 卡并填充表单，未提交、未发出 `/api/auth/login` 请求，未写入跟踪文件。启用态真实键盘验收中，首页演示 CTA 为 Tab stop 9、登录页“使用 Viewer 账号”为 Tab stop 1，两者均在视口内且有 `3px` 实线可见焦点。
- **验证例外**：仓库级 `npm run lint` 有 1 个与本功能无关的既存错误（`frontend/e2e/global.setup.ts:33`，`preserve-caught-error`；总计 `1 error / 49 warnings`）。按 Task 6 裁定不修改该文件；公开首页相关源文件的文件级 lint 已通过。
- **下一步**：启用多角色公开演示前，先设计隔离租户、自动重置、写入限流和危险操作控制的可重置基础设施。

---

## Release Stabilization（2026-09-06）

- **范围与分支**：仅稳定化，不新增功能；工作位于 `chore/release-stabilization-20260905`，基线为 `main@98bca381`。
- **协同编辑隔离**：heartbeat、active-users、leave 在访问 session 前校验文档 factory scope；跨工厂统一 404 且无读写副作用。回归选择 23 passed，FMEA 相关选择 193 passed。
- **最终全量 `make check`**：backend `1975 passed / 5 skipped / 5 xfailed / 0 failed`（181.95s）；frontend TypeScript 与 Vite build 通过（7.61s）。
- **最终 fresh E2E 数据库**：已授权的 `qms_e2e` reset、迁移与 seed 通过；唯一 Alembic head 仍为 `20260727_warranty_factory_id`。此前初始 seed 与两次额外 reseed 均为 `5 accounts / 21 CAPAs / 5 PFMEAs`。
- **最终 Playwright（zero retry）**：44 total，`42 passed / 0 failed`；仅两项 allowed skip：`no creds: advice endpoint 422 blocked + import still 200 blocked` 与 `no-LLM: D8 close is blocked (422 outcome=blocked)`。
- **最终 CAPA PPT**：export `f3f5753b-cbd6-45ba-818b-c51df70a9d83` 在 round 1 `passed`，11 张幻灯片，source/carrier/DB/audit 验证通过；`issues=[]`，非空 `suggestions` 为 advisory。
- **最终系统集成菜单**：权限切片 `2/2 passed`；viewer 可见集成组而不见 admin-only 管理项，admin 可见三组及 MES 子页。

## 历史：系统级 E2E 测试套件（M0+M1，2026-07 基线）

> 本节记录 2026-07 的初始套件范围与验证基线；其 M1 3/4、dashboard follow-up 和 `9 passed / 1 skipped` 结果均已由上方 **Release Stabilization（2026-09-06）** 证据取代，不能作为当前 RC 门禁结论。

- **M0 基建**：`docker-compose.e2e.yml`（独立库 qms_e2e + 卷 pgdata_e2e + 端口 5433/8001/5174，redis 不暴露，AI 服务 `profiles:["ai-infra"]`，`!override` 端口）；`E2E_MODE` config + 生产门控条件路由；确定性幂等 `seed_e2e`（2 工厂/产品线含 DC-DC-100 默认/5 账号 + UserProductLine/已知 PFMEA-E2E-001 + 8D-E2E-001）；`/api/e2e/seed-state` 只读（账号密码单一来源）+ `/api/e2e/cleanup` 白名单 FK 逆序单事务删（禁用 version 触发器）；`make e2e*` 目标（先 db/redis→migrate→backend/frontend）；`tsconfig.e2e.json` + `@types/node`；helpers/fixtures/global.setup（5 角色 UI 登录→storageState）+ guards。
- **M1 流程（2026-07 历史基线，3/4）**：①登录+RBAC+工厂隔离 ②FMEA 生命周期 ③CAPA 8D 生命周期。④看板下钻当时仅实现一半（`KPICard` onClick + 列表页 query param 已有；widget→navigate 接线 + `dashboardDrilldown.ts` 缺失），后续已补齐；此处的 E2E Task 13 follow-up 不是当前 RC 待办。
- **生产代码**：仅 `data-e2e` testid（`CAPAListPage` 的 `product_line_code` 为已批准的 bug 修复例外）。
- **验证（2026-07 历史基线）**：M1 套件 9 passed / 1 skipped（无 LLM 凭证时 AI spec skip-with-warning）；backend e2e 端点测试 2 passed；`make check` + e2e tsc 干净；生产门控 `[]`（TENANT_MODE=production 时 `/api/e2e/*` 不载入）。
- **已知摩擦**：backend 登录限流（`auth.py` 10 次/5min 内存）在反复跑 Playwright 时可能让 `global.setup` 超时——重启 e2e backend 即恢复（未改生产代码）。
- spec: `docs/superpowers/specs/2026-07-01-system-e2e-test-suite-design.md`；plan: `docs/superpowers/plans/2026-07-01-system-e2e-test-suite.md`；指南: `docs/e2e.md`。

---

## 测试库隔离 + Schema 漂移修复（2026-07-27，US-E2E-02 后续）

- **Schema 漂移已修**：qms dev 库此前 alembic stamp 滞后 + 列被带外手加 + 31 个未跟踪 ` 2.py` Finder 副本导致假多头。已重建 qms 到 head `20260727_warranty_factory_id` 并重 seed（备份 `/tmp/qms_backup_20260727_122825.sql`）；`stage_runs`/`shipment.factory_id` 迁移改为幂等；新增 `warranty_records.factory_id` 迁移；`audit_plans.factory_id` 补进模型（反向漂移）。
- **测试库隔离（对齐 CI + 守卫）**：`make check-backend` 现默认 `TEST_DATABASE_URL=qms_test`（与 CI 一致），新增 `check-test-db` 目标用 psycopg 自动建库 + `alembic upgrade head`（不依赖本机 psql/createdb）。`conftest.py` 加 `_assert_not_seed_db` 守卫：未显式设 `TEST_DATABASE_URL` 而回落到种子库 `qms` 时直接 `RuntimeError`（`ALLOW_SEED_DB_TESTS=1` 可显式绕过）。
- **验证**：脏 qms_test（旧 create_all schema + 无 stamp）经用户确认后 drop 重建到 head（151 表，users 有 role_id/legacy_role/factory_id，warranty.factory_id NOT NULL）；backend 全绿 `1906 passed / 4 skipped / 3 xfailed / 2 xpassed / 0 failed`；守卫三路径（拒绝种子库 / 显式 qms_test 通过 / ALLOW_SEED_DB_TESTS 绕过）均正确；`make check-frontend` tsc+build 绿。
- **后续**：126 个 ` 2.` Finder 副本已删（0 git-tracked）；残留的 `__pycache__` ` 2.cpython-*.pyc` 无害，可后续清理。

---

## 历史：US-E2E-01 8D 全程闭环特性缺口审计（2026-07-03，已完成）

以下为当时对 `docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`（v6，定稿）的代码路径审计记录；当时结论是需补齐产品实现并新增故事级 spec。所列 11 项现均已完成，保留本段仅作实现演进追溯。

**进度**：11 项全部完成（P0-1~P0-4 / P1-5~P1-10 / P2-11 全部落地）

### 已完成 ✅（约 50%）

- [x] **CAPA 8D 状态机 D1→D2→…→D8_CLOSURE 严格顺序** —— `backend/app/state_machines/eightd_state.py`
- [x] **权限模型**：D1-D6 需编辑权限、D7→D8 需 `canApprove('capa')` —— `backend/app/api/capa.py:189 advance_capa`
- [x] **建单 + D 步字段 + 状态转换审计** —— `CAPAEightD` 模型 `models/capa.py:11-40`；服务层每次 advance 写 `AuditLog`
- [x] **D2 AI 草拟按钮** —— `AIDraftButton.tsx` + `useAIDraft.ts`
- [x] **D4/D5/D7 推荐 API + 面板骨架** —— `api/capa.py:276-461`；`D4RecPanel.tsx` / `D5RecPanel.tsx` / `D7RecPanel.tsx`（⚠️ 有骨架但缺阶段/来源丰富度，见"待补 P0-2/P0-3"）
- [x] **3 类推荐源实现** —— `FMEAGraphSource`、`SemanticSearchSource`（pgvector + FTS RRF）、`HistoricalCAPASource`（已关闭 8D D2→D2 语义匹配）、`RuleEngineSource` + LLM 融合（`match_source: "llm"`）

### 历史缺口（已完成）

1. [x] **P0-1 D4 现场根因验证子流程** — 故事验收：「根因必须经现场验证才可确认；验证记录（方法/结果/证据）落库且可追溯；未验证的根因不能推进 D4→D5」
   - 当前 `d4_root_cause` 只是单个 `Text` 列，**无** 方法/结果/证据字段，**无** 附件表关联，**无** D4→D5 阻断校验
   - **交付物**：新表 `capa_root_cause_verification`（`capa_id, root_cause_text, method, result, evidence_attachments(JSONB), verified_by, verified_at, is_verified`）+ API（create/list/update） + `D4RecPanel` 增加「候选根因 → 验证卡」子面板（method 输入 / result 选择 / 证据附件上传）+ `advance_capa` 在 `D4_ROOT_CAUSE → D5_CORRECTION` 时校验至少 1 条 `is_verified=true` 记录 (Spec A 已落地，commit 见 git log)
2. [x] **P0-2 AI 推荐 12 阶段可视化 DAG 面板** — 故事验收：「触发 D4/D5 推荐后，流程编排面板出现，展示 12 阶段（名称/来源/状态 pending·running·done·skipped·error/命中数·摘要）」
   - 当前 `D4RecPanel.tsx` 仅按 `match_source` 分组（5 组），无 stage/status 概念；后端也无 stage 事件流
   - **交付物**：新服务 `RecommendationOrchestrator` 把现有 sources 组织成 12 阶段执行图，返回 `{stages: [{name, source, status, hit_count, summary, error?}], items: [...]}`；`D4/D5RecPanel` 增加 `<RecommendationDAG>` 组件（12 节点 + 状态色 + 命中数徽标）；无 LLM 凭证时相关阶段 `status="skipped"` 且带 reason (Spec B 已落地，commit 见 git log)
3. [x] **P0-3 AI 推荐来源 provenance 落地到 UI + testid** — 故事验收：「最终推荐列表非空、**每条带来源标签**」
   - 后端已有 `match_source`（linked/keyword/rule/llm/historical_capa/semantic_search/fmea_graph）但 UI 层无 `data-e2e` 钩子
   - **交付物**：`<RecItem>` 渲染 `<Tag data-e2e="rec-source-{source}">` + 阶段命中位置徽标；每条推荐 payload 增加 `stage_index` 便于 UI 关联到 DAG 节点 (Spec B 已落地，commit 见 git log)
4. [x] **P0-4 AI 采纳审计留痕** — 故事验收：「AI 推荐采纳 + 根因验证记录留痕（含来源）」
   - `grep "adopt_recommendation|recommendation_audit"` = 0 命中；当前采纳只把文本追加到 `d4_root_cause`/`d5_correction`，未记录 which item / from which source / at what stage
   - **交付物**：新表 `capa_ai_adoption`（`capa_id, d_step, adopted_text, source, stage_index, item_ref, adopted_by, adopted_at`）；D4/D5/D7 采纳按钮点击时 insert 记录并写 `AuditLog(action='ADOPT_RECOMMENDATION', metadata={source, stage})` (Spec A 已落地，commit 见 git log)

### 历史缺口（已完成）

5. [x] **P1-5 SPC 异常关联推荐源**（故事阶段 6）— 已有 SPC 判异算法（`spc_service.py`），需新增 `SPCAnomalySource` 类：查询该产品线近 30 天判异记录 → 关联到候选失效模式 → 输出到 D4 推荐；无 SPC 数据时 `status="skipped"` reason="产品线暂无 SPC 图" (Spec B 已落地，commit 见 git log)
6. [x] **P1-6 IQC 来料检验推荐源**（故事阶段 8）— 已有 IQC 模型（`iqc_materials`），新增 `IQCSource`：本批 + 历史来料不良趋势 → D4 推荐；这两个（5、6）由于底层数据已在系统内，接入成本最低，建议先做 (Spec B 已落地，commit 见 git log)
7. [x] **P1-7 供货历史推荐源**（故事阶段 9）— 已有 `supplier_quality_service`，新增 `SupplierHistorySource`：供应商评级/历史 PPM/SCAR 状态 → D4 推荐 (Spec B 已落地，commit 见 git log)
8. [x] **P1-8 MES 设备/过程数据推荐源**（故事阶段 7）— `mes_connector.py` 存在但仅为连接骨架；需评估：先做 mock 数据源接入 vs 等真实 MES 集成 (Spec B 已落地，commit 见 git log)
9. [x] **P1-9 同类型产品 KB 检索**（故事阶段 4）— 需按 `product_types` 主数据聚合跨工厂共享 KB，扩展 `SemanticSearchSource` 增加 `product_type` 过滤维度或新增 `SameTypeProductKBSource` (Spec B 已落地，commit 见 git log)
10. [x] **P1-10 经验教训库结构化**（故事阶段 5）— 当前 `HistoricalCAPASource` 只做 D2 语义匹配；建议新增 `capa_lessons_learned` 表（`capa_id, lesson_text, category, tags`）或从 D7/D8 抽取字段，让 lessons 检索更精准 (Spec B 已落地，commit 见 git log)

### 历史缺口（已完成）

11. [x] **P2-11 `capa-story-closed-loop.spec.ts`** — 用 `E2E-STORY-CAPA-001` 前缀（故事主角单号），覆盖 10 步主流程 + 12 阶段 DAG 结构断言（`data-e2e="rec-stage-{n}"` 状态属性）+ 7 条 TRANSITION 审计断言（`GET /api/audit-logs?target_id=...` 断 1 CREATE + 7 TRANSITION，D1-D7 operator=engineer、D7-D8 operator=manager）+ AI 采纳留痕断言（`capa_ai_adoption` 表通过 seed-state 端点回读）+ viewer 只读断言（`/capa` 列表看到关闭 8D、详情打开、`capa-create`/`capa-advance` 隐藏）
    - LLM 无凭证时 AI 断言 `test.skip` + 核心闭环照跑（沿用 `_guards/ai-credentials.guard.spec.ts` 模式）
    - 前置：现有 `capa.spec.ts` / `capa-ai-draft.spec.ts` 保持不变（M1 冒烟），故事 spec 与之并行
    - 落地（`frontend/e2e/specs/m1-core/capa-story-closed-loop.spec.ts`）：单测覆盖 10 步闭环（engineer D1..D7 → manager D7→D8 → viewer 只读）。**实现取舍**：审计回读走 `GET /api/admin/logs/audit?table_name=capa_eightd`（admin token）按 `record_id` + 时间窗客户端过滤（原 PROGRESS 写的 `/api/audit-logs?target_id` 端点不存在，`admin/logs/audit` 无 `record_id` 过滤参数，客户端过滤等价且无需新增后端端点）；AI 采纳留痕同样从审计日志回读（`ADOPT_RECOMMENDATION` 的 `changed_fields` 含 `source` + `stage_index`），不另建 seed-state adoptions 端点。DAG 断言用实际 testid `rec-dag-stage-{n}` + `data-status`（非 `rec-stage-{n}`）。viewer 只读：D4 推荐恒非空（`RuleEngineSource` 默认候选兜底），无需关联 FMEA 即可断言 provenance + 采纳；`CAPAListPage` 新增 `canEdit('capa')` 门控隐藏 `capa-create`（viewer 真正只读）

### 补齐建议顺序

`[x] P0-1 (D4 验证) → [x] P0-4 (采纳审计) → [x] P0-2 (DAG 面板) → [x] P0-3 (provenance UI) → [x] P1-5/6 (SPC/IQC 源) → [x] P2-11 (故事 spec) → [x] P1-7~10 (MES/供货/同类型/lessons，视实际 ROI 决定)`

理由：D4 验证 + 采纳审计是**数据模型缺口**，先落表结构；DAG + provenance 是**观测层缺口**，依赖 orchestrator；4 类源里 SPC/IQC 数据已在库最优先；MES/供货/同类型/lessons 优先级由业务实际数据密度决定。

### 参考

- 故事：`docs/user-stories/US-E2E-01-capa-8d-closed-loop.md`
- 现有 E2E 覆盖度：`frontend/e2e/specs/m1-core/capa.spec.ts`（~10%，仅 D1→D2）+ `capa-ai-draft.spec.ts`（~5%，仅按钮可见性）
- 相关既有代码：`backend/app/services/{capa_service,capa_recommendation_service,recommendation_sources}.py`、`frontend/src/components/capa/{D4,D5,D7}RecPanel.tsx`

---

## 一、已经开发完成

### Phase 1 — 基础平台 + 核心模块 ✅
- MVP 闭环：JWT + 7 角色 RBAC、产品线 JSONB 图、PFMEA/DFMEA 编辑器、8D/CAPA 工作流、仪表盘、审计日志
- 控制计划编辑器（与 FMEA 双向联动）
- SPC 控制图（X-bar R / I-MR / 直方图 / P/NP/C/U + 8 大判异规则 + Cp/Cpk）
- MSA 测量系统分析（GR&R、偏倚、线性、稳定性、计数型 Kappa）
- 特殊特性（CC/SC）贯穿管理、产品安全特性管理、质量目标、内部审核、管理评审、FMEA/CP 版本管理

### Phase 2 — 供应商 / 客户质量 ✅
- 供应商档案 + 准入审批 + A/B/C/D 评级
- IQC（AQL/ISO 2859-1 抽样引擎，含克隆重检）
- 供货质量看板（PPM / 批次合格率 / 准时率 / 排名）
- SCAR 5 态生命周期 + 8D 闭环
- 客诉、RMA、客户质量看板（含 0 公里 PPM、保修费用、满意度、客户审核摘要）
- 客户审核、APQP（5 阶段门）、PPAP（AIAG 18 要素 + 5 态）
- 产品线选择器、CSR/VOC → 控制计划同步、Excel 导入导出

### Phase 3 — AI + 知识图谱 ✅
- Neo4j 基础设施 + JSONB 双 Repository
- G6 v5 图谱可视化（FMEA 嵌入 tab + `/knowledge-graph` 全局页）
- 全局知识库（跨 FMEA 统计 + 相似节点搜索 + 响应白名单脱敏）
- LLM RAG 语义搜索（pgvector + 全文 + RRF 融合，6 实体）
- FMEA 编辑智能推荐（混合规则 + 图相似 + LLM，多 Provider）
- 8D D4/D5 全混合推荐管道（4 D4 源 + 3 D5 源 + FusionEngine + LLMFusionLayer）
- 变更影响分析（BFS + AP 预测 + 影响评分）
- SPC-FMEA 异常关联推荐、D7 预防复发提示
- 多人协同编辑（乐观锁 + 短轮询在线状态 + 三方 diff）

### Phase 4 — 高级分析 + 生态集成 ✅
- MES / PLM / ERP 三大连接器（Mock + REST，Outbox 可靠推送，凭证 Fernet 加密）
- 8D 报告 AI 草拟、质量趋势 AI 解读
- 经验教训智能推送（5 源融合）
- 控制计划智能校验（4 规则引擎）
- IQC 抽样方案智能优化（10 规则 + 多级审批）
- 供应商风险智能预警（10 规则 + 4 级 + 邮件/Webhook + SCAR/CAPA 闭环）
- 管理评审报告自动生成、供应链风险地图（热力图 + 时间线 + 对比）
- 自定义拖拽看板（react-grid-layout + 18 widget）
- 多工厂部署（factory_id 行级隔离 + 三层 Scope）
- SaaS 多租户（schema-per-tenant + JWT 域隔离）

### Phase 4+ — FMEA 体验优化（已合并到 main） ✅
- PFMEA 七步法生成向导（Step 0 范围 → Step 6 确认）
- DFMEA 向导增强（5T 工具/趋势 AI 推荐 + PC/DC AI 推荐 + 工具结构引导）
- FMEA 版本快照只读查看器、安全删除（draft/rework）
- 产品类型主数据（`product_types` 表，跨工厂共享）
- 图谱布局清晰度（边色/方向切换/PNG 导出背景合成）
- 结构树拖拽迁移 `@dnd-kit`、推荐缓存与作用域修复

### 历史：`fix/dashboard-admin-pages` 已完成并已合入
1. **管理后台增强**（2026-06-26 起）
   - 用户管理页（创建 + 列表 + 启停 + 删除 + 工厂访问/角色/密码编辑）
   - 日志管理页（audit / login / system 三 tab 分页）
   - `system_logs` 表 + DBLogHandler（异步队列 + 每租户 drain）
   - `login_audit_logs` 表 + 登录成功/失败捕获
2. **仪表盘下钻**（设计 2026-06-26；**2026-07-03 补齐实现**）
   - 注：此前 PROGRESS 误记为已落地（`b82967c` 实为 customer-quality 的 searchParams 修复，非下钻），实际仅 `KPICard` onClick + 列表页 query param 就绪，widget→navigate 接线 + `dashboardDrilldown.ts` 缺失；本轮补齐。
   - KPI 卡片 → 过滤列表/详情页、Alert 行可点击、Pending 聚合 → 类别菜单
   - 后端：`pending_breakdown` 分项计数 / FMEA `pending` 过滤 / SPC `abnormal` 过滤（近 7 天 open 告警的 IC 子查询）
   - 前端：`dashboardDrilldown.ts` 权限映射 + `useDashboardDrilldown` hook、`KpiPendingWidget` 受控 Dropdown、IQC/SPC/MSA/MES drilldown、`AlertRow` a11y（hover/键盘/灰显）、无目标模块权限时灰显禁用
3. **P0 Agent Base — AI-driven QMS 基座**（2026-06-29 ~ 06-30，合并 `178487b`）
   - 6 张 `agent_*` 表 + `audit_logs` 扩 `factory_id/tenant_schema/correlation_id`
   - `@agent_tool` 注册表 + 三级权限网关（readonly / draft / commit）
   - 5 元组白名单（user × tool × module × min_level × max_scope）+ HITL 待办审批 + 状态机（approve/reject/modify）
   - 三层记忆（Redis 短期 + `task_state` JSONB + `agent_memory` 入队）
   - Guardrails（输入注入启发式 + 输出脱敏/清洗）
   - 自研 tool-calling 主循环（基于 openai/anthropic SDK，**未引入 pydantic-ai** — 与 pinned pydantic 2.9.2 冲突）
   - API 路由：sessions / messages / actions / whitelist（含 factory_id + `check_factory_access`）
   - 82 个测试（含 4 个 P0 验收用例：readonly 隔离 / draft 不落库 / commit 三态 / guardrails）
4. **P1-B：质量趋势解读迁移到 Agent 基座**（2026-06-30，合并 `4102de5`）
   - `quality_trend_service` LLM 调用切到 `provider_adapter.complete_json` + `audit.write_audit_raw`
   - config-check 前置于 cache（修回归）、严格 provider 白名单、每调用本地 httpx、路由测试 assert kwargs
   - 5 个 TDD 任务，全分支回归绿
5. **P1-C：FMEA 智能推荐迁移到 Agent 基座**（2026-07-01，6 任务 TDD 已落地）
   - `RecommendationService.recommend()` 的 LLM 调用从旧 `LLMProvider.complete()` 迁到 `provider_adapter.complete_json`
   - 新增两态审计 `_write_recommend_audit`（`success` / `llm_failed`），仅覆盖 `need_llm=True` 路径
   - 抽 `_tenant_schema` 到共享 `core/tenant.py`（dashboard + fmea 路由共用）；`build_client` 前置于 cache 检查
   - 丢 `llm_provider` ctor 参数 + `self.llm`；`llm_available` 穿透 `_get_cached`/`_cache_result`
   - 混合 rule-fallback UX、缓存行为、5 态 `source` 状态机**不变**；未配置 LLM 静默 rule 降级（200，不审计，不 503）
   - 经 4 轮 spec/plan 对抗评审（17+ 修复合并入计划），零中间红 commit；41 推荐测试绿
6. **P1-D：剩余 4 个 LLM 消费者迁移到 Agent 基座**（2026-07-01，5 任务 TDD 全部落地）
   - **8D D4/D5 混合推荐**：`LLMFusionLayer.enrich()` 返回 `LLMOutcome`（attempted/succeeded/failed 两阶段计数）；`HybridRecommendationPipeline` 迁到 `(db, pc, embedding_provider)`，写入 3 态审计 `llm_recommend`（`success`/`partial`/`llm_failed`）；D4/D5 路由 `build_client` 解析 `pc` + 透传 audit ctx + `await db.commit()`；LLM 未配置静默降级，不 503
   - **RAG 语义搜索问答**：`SearchService.ask()` 顶部解析 `pc`（no-results 早返回 `llm_available=pc is not None`），`complete_json` + 2 态审计 `llm_rag_qa`（哨兵 `record_id=uuid5` + `table_name="rag_qa"` + sort/dedup `correlation_id`）；路由改 503 守卫为 embedding-only + commit；hybrid 200 sources-only 保留
   - **管理评审报告**：`_enrich_with_llm`/`_generate_executive_summary` 改返回 outcome（`section_attempted`/`section_failed_keys`/`summary_failed`）；`generate_report` 重算 `llm_enriched` + `pc.model` 空值保护 + 2 态审计（与 CRUD 审计并存，骑乘 service L264 commit，路由无 commit）
   - **CAPA draft D2-D8**：仅换 `complete_json`（`llm_model_name` 空值保护，503 保留），**保留现有 `AI_DRAFT` 审计**不引入 `write_audit_raw`；`capa_capabilities`（`:112`）改 `build_client` 探测，`draft_capabilities`（`:480`）不动
   - 全消费者 timeout 来源不变（D4/D5 2s / mgmt `REPORT_LLM_TIMEOUT` / RAG httpx 30s / CAPA draft `CAPA_DRAFT_LLM_TIMEOUT`）；`LLMProvider` 类保留给 `ai_config_service` 自检
   - 经 3 轮 spec + 3 轮 plan 评审（11+7 findings 全闭合）+ 4 任务子代理逐任务评审 + opus 全分支评审；948 backend 测试绿 + frontend build 绿
7. 杂项：`a178b5d` 清理 5 个 Finder 复制的 ' 2.*' 文档文件；`e91b1ad`/`97cf6d3` Makefile 用 venv 绝对路径跑 pytest；`f80c27a` SCAR 测试改 `SCAR-TEST-*` 避免种子碰撞

---

## 二、Post-RC backlog（非当前 RC 阻塞）

### 已完成的历史交付与后续选项
- **P1 LLM 迁移收尾**（P1-D 后剩余项）
  - P1-B + P1-C + P1-D 全部落地：4 个 LLM 消费者（8D D4/D5 / RAG 搜索 / 管理评审报告 / CAPA draft）已迁到 `provider_adapter.complete_json` + `write_audit_raw`
  - 经核实 **SPC-FMEA 异常关联 / D7 预防复发 / 经验教训推送均无 LLM 调用**（纯规则/图匹配），早先 PROGRESS 列入"剩余 LLM 调用点"有误
  - 仅剩 `ai_config_service` 自检仍用旧 `LLMProvider`（诊断用途，单独处理，不迁）
  - 后续可选：旧 `LLMProvider` 类在 `ai_config` 自检也切基座后删除；P0 follow-up（embedding worker / 多工具 LLM 循环 / Anthropic shaping）排期
- **系统级端到端（E2E）测试套件**（2026-06-30 新增需求）
  - 目标：对所有代码更改进行系统级端到端测试，覆盖每次合并/发版前的回归
  - 已落地（TDD 计划 14 任务）：
    - Task 3 `seed_e2e` / `seed-state` endpoint / `backend/tests/test_e2e_endpoints.py`：确定性 E2E 种子（2 工厂 / 1 产品线 / 5 账号 / 1 PFMEA / 1 CAPA）+ `GET /api/e2e/seed-state`
  - 待 brainstorm 的范围：模块覆盖（FMEA / CAPA / IQC / SPC / MSA / 客户质量 / 供应商质量 / Admin / Agent Base）、层次（API 契约 + 浏览器 UI 流 + RBAC 角色矩阵 + 多工厂 `factory_id` 隔离）、运行方式（docker-compose 整栈 vs in-process）
  - 候选工具：后端 pytest + httpx；前端 Playwright（仓库已有 `mcp__plugin_playwright`）；位置建议 `backend/tests/e2e/` + `frontend/e2e/`，或新增顶层 `e2e/`
  - 与现有 `make check`（单元层）分离为独立 target，避免 CI 时长爆炸
  - 历史 E2E 建设与本轮 Task 10 最终 reset + 全套发布门禁均已完成。

### P2 — Copilot（对话式助手）
- 前端 UI 侧栏（`ProtectedRoute` 接入待做）
- Readonly tools 扩展：查 FMEA / SPC / 客诉 / 8D / 供应商
- Draft tools 扩展：8D 草稿生成 + PFMEA 行建议
- 验收：工程师可用自然语言查数 + 生成草稿落入编辑器

### P3 — 流程自动化（客诉 → 8D 端到端）
- 任务队列 / worker
- Agent 拆解 D1–D8 起草 → 待办审批 → 落库
- 一条客诉全流程 agent 产出草稿、人审批后入库、全程可审计

### 从 P0 拆出的独立后续任务
1. **embedding worker 支持 `agent_memory`**
   - 当前 worker 用固定 `table_field_map`，**不认识 `agent_memory`**
   - P0 仅验收 queued 入队 + 非向量 fallback 检索；向量检索待 worker 增强
   - 需把 `agent_memory` 加入 worker，upsert `document_embeddings` 后置 `ready/failed`
2. **既有随机 `record_id` 写审计调用点的兼容修复**
   - 如 `quality_trend_service` 等
   - P0 只保证新增 agent 审计使用可追溯主键 + `factory_id/correlation_id`，**未触碰旧调用点**
3. **真正的多工具 LLM 循环**
   - P0 harness 主循环目前是骨架，需补完多轮 tool-call 调度
4. **Anthropic tool_result 完整 shaping**
   - 当前 provider_adapter 偏 OpenAI 形态，Anthropic 侧的 tool_result 结构需补齐
5. `fix/dashboard-admin-pages` 的内容已合入当前稳定化历史；不再作为 `main` 合并前的独立阻塞项。

### ROADMAP 之外的已知缺口（来自 CLAUDE.md）
- 测试套件仍在补齐，部分历史模块缺 `factory_id` fixture 回填
- 登录限流为每进程内存 `10 次/5min`，未在多副本间分布式共享；跨副本部署时限流不具全局一致性。
- Redis 已配置但**未实现缓存逻辑**
- 前端 bundle 5.5MB，需代码分割
- 部分 Alembic 迁移号重叠，需规整

---

## 三、当前阻塞 / 风险点

### Release stabilization 门禁：已通过
- 最终 fresh `qms_e2e` reset/migration/seed、全量 `make check`、zero-retry Playwright、CAPA PPT 与系统集成菜单切片均通过；两项 E2E skip 均为允许的 inverse 场景。

### 待办：分支评审与集成
- 稳定化证据已齐备；仍需完成分支评审并决定是否集成至 `main`。这不是测试、迁移或 E2E 门禁失败。

### Post-RC 风险（不阻塞本轮）
- Agent Base：embedding worker、随机 `record_id` 兼容、多工具循环及 Anthropic `tool_result` shaping 尚待产品化排期。
- 性能与维护：前端 bundle 代码分割、Redis 通用缓存、历史 `factory_id` fixture 回填与 Alembic 编号规整均待后续评估；本轮 fresh migration 已验证唯一 head。

---

## 四、当前在做

| 项目 | 状态 | 证据 / 下一步 |
|---|---|---|
| Release stabilization | ✅ Task 1–10 门禁通过 | final fresh reset/migration/seed、回归、E2E、PPT、菜单权限均通过；待分支评审与集成决定 |
| `make check` | ✅ 最终通过 | backend `1975 passed / 5 skipped / 5 xfailed / 0 failed`（181.95s）；frontend tsc/Vite build 通过（7.61s） |
| Playwright | ✅ 最终 zero-retry 通过 | `42 passed / 0 failed / 2 allowed skips`，共 44 项 |
| US-E2E-01 / US-E2E-02 实现 | ✅ 已合并，当前为历史 | 保留归档与 story/skill 契约资料，不是 RC 功能开发 |
| Agent / 性能后续 | ⚪ Post-RC backlog | 不作为当前 release blocker |

---

## US-E2E-01 v8.1 实现历史（已完成并已合入）

US-E2E-01 已升级为 epic 合集 v8.1 定稿（`docs/user-stories/US-E2E-01-capa-8d-closed-loop/`，README + 10 子故事）。配套 gap analysis：`docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`。以下为按 gap 分析结论排定的实现任务，按优先级 + 交付顺序。

### P0 — 收尾（编排器已就绪，补硬 gap）

- [x] **01.2 12 源推荐收尾** — LLM 未配置严格 `BLOCKED`（orchestrator 顶部 pc=None→`RecommendationResult(blocked=True)` + D4/D5 endpoint 422+`detail.blocked` + 前端 `rec-blocked-banner`）；`RecommendationCache.stage_runs` JSONB 列 + 新增 CAPA 专属 `_cache_capa_result` write-only 写入路径（report_id 键 + uq_cache_capa upsert）+ `_serialize_capa_suggestions`（D5 单次遍历互斥）；e2e 拆 `capa-story-ai-recommend.spec.ts`（AI，无凭证 skip 整测）+ `capa-story-closed-loop.spec.ts`（非 AI 始终照跑）。切片 A（A1-A7）全部 review-clean。
  → **A3 已完成**：`RecommendationCache.stage_runs` JSONB 列 + Alembic 迁移 `20260709_capa_cache_stage_runs` + `backend/tests/migrations/` PG 迁移测试基础设施（`mig_db_url` fixture + `_cfg` helper），B1 可复用。
- [x] **01.3 D4 验证 + D7 + 审批壳状态机细化切片** — 新增 `D7_COMPLETED`/`D8_GATE_PENDING`/`D8_APPROVAL_PENDING` 3 状态 + 驳回回退边 + `capa_d7_node_action.status=pending` + edge 权限 + `update_capa` 冻结守卫；9 任务已落地，backend 测试绿
- [x] **01.3 D4 验证 method 枚举 + 回退计数器切片** — `CapaRootCauseVerification.method` 自由文本→枚举（measurement/observation/reproduction）+ CHECK 约束 + 迁移测试；`conclusion`（pending/passed/failed）+ `d4_retry_count` 回退计数器 + 双行锁递增 + 审计 `D4_VERIFICATION_PASSED`/`D4_VERIFICATION_FAILED`；服务层 `create_verification`/`update_verification` 结论驱动，`is_verified` 派生；同记录并发仅 +1，跨记录并发 +2（commit `8ccb29c5`）
### P1 — 新建/收尾

- [x] **01.1 D3 遏制全链路新建** — 4 类数据导入（在途/库存、发货/物流、IQC、SPC 判异）+ 受影响范围分析报告（5 项）+ AI 遏制建议（带 provenance）；ERP 数据模型（`ERPInventoryBalance`/`ERPShipment`）+ `capa_draft` 的 containment_actions 可复用；补 D3→D4 闸口（`advance_capa` 当前不检查 d3_interim 非空）。**实现态 v4（2026-07-12）**
  - **Task 12 E2E seed 扩展** ✅：D3 源数据 7 表 upsert + 7 独立 CAPA + 幂等 + E2E_MODE 守卫测试（`backend/app/seed_e2e.py` / `seed_e2e_constants.py` / `tests/e2e/test_seed_e2e_d3.py`）；附 `shipment_records.factory_id` 迁移补齐 schema drift
- [x] **01.4 8D↔FMEA 双向收尾** — 三源反查（header / D4 `source_ref` / D7 confirmed|auto_filled，含 Prevention）+ 同厂同 PL 写不变量 + factory/effective 过滤 + FMEA 可见性 404 + D4 Cause 选择器 + D7 Prevention 持久化/fingerprint + `FMEA_LINKAGE_CREATED` + deep-link/`activeRelatedNodeId` + reverse-lookup indexes + E2E `capa-story-fmea-linkage`（4/4）。spec: `docs/superpowers/specs/2026-07-14-us-e2e-01.4-fmea-linkage-design.md`；plan: `docs/superpowers/plans/2026-07-15-us-e2e-01.4-fmea-linkage.md`
  - **Deploy note 01.4**: D7 `recommendation_hash` now includes prevention fields; in-flight D7 CAPAs with pre-change hashes may need re-confirm/skip before D7 completion gate passes.
- [x] **01.5 8D→SCAR 触发新建** — 1:1 CAPA↔SCAR（`capa.scar_ref_id` + `scar.capa_ref_id` 双边 partial unique）+ `POST /capa/{id}/trigger-scar`（body `supplier_id` 必填，D3+ 非 ARCHIVED，同厂同 PL，FOR UPDATE + IntegrityError→400）+ GET `linked_scar`/`d3_affected_lots` 投影 + `SCAR_STATUS_SYNCED` 审计（CAPA 行不写状态）+ link-capa 硬化（SCAR CREATE + CAPA EDIT）+ FE CAPADetail 触发 Modal + seed `8D-E2E-SCAR-001` + E2E `capa-story-scar-trigger`。spec: `docs/superpowers/specs/2026-07-15-us-e2e-01.5-scar-trigger-design.md`；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.5-scar-trigger.md`（worktree commits `98f7e539`..`c5f4e970`）
- [x] **01.6 8D→供应商风险新建** — D7_COMPLETED 写 `supplier_risk_capa_inputs` outbox（severity/disposition/repeat 检测）+ 30s worker `evaluate_supplier_risk_in_tx` + `SUPPLIER_RISK_INPUT_SENT`；`POST /capa/{id}/confirm-repeat`（CAPA EDIT ∧ SUPPLIER_RISK EDIT）+ `SUPPLIER_RISK_CHANGED`；GET 投影 `supplier_risk_input`；FE `SupplierRiskInputCard`；E2E seed `8D-E2E-RISK-001`/`8D-E2E-RISK-HIST-001` + `capa-story-supplier-risk-input`。
  - **Deploy note 01.6**: (1) R11 须经 `seed_supplier_risk_configs`（e2e seed 已调；生产/新厂 seed 后确认 R11 存在）；(2) backend lifespan 启动 risk input worker loop（30s）— 进程不跑 loop 则 outbox 永挂 pending；(3) `capa.supplier_id` 生命周期：D7+ 锁定更换；create API 可带 `supplier_id` 但历史 create 路径未必设置，须在 D7 前通过 update/ORM 写入，否则 advance 不写 outbox。

### P2 — 新建/收尾

- [x] **01.7 D8 文档更新门禁新建** — 3 表 `capa_docg_*` + `generate_impact_analysis` 三阶段（BLOCKED/stale/CAS/C9）+ `run_audit`（diff_engine 版本间 diff + 关键点覆盖 + 空清单守卫）+ `record_defer`/`confirm_no_affected` + `_d8_doc_gate_gate`（C8/C9，defer 仍阻断）+ 7 路由 + `DocGatePanel`（全局推进排除 D8_GATE_PENDING）+ E2E seed `8D-E2E-DOCGATE-001` + `capa-story-doc-gate.spec.ts`；窄范围只审 CP/FMEA（C1）。plan: `docs/superpowers/plans/2026-07-13-us-e2e-01.7-doc-update-gate.md`。**终审第七轮修复**（3 P0 + 5 P1）：drop full UQ 允许重试、field 级覆盖判定、None baseline 不崩、CP item_id+完整 snapshot、空清单→done→confirm、phase3 refresh+rebuild candidates、defer owner 工厂校验、审计事件链补全；+10 回归测试 + advance-flow/TOCTOU gate 接入修复。**终审第 20–24 轮**：历史 hash 双算法 + backfill 全量 demote C9；preflight 可执行处置 + `make deploy-check` 强制入口；**structured waiver**（`waiver_items` 绑定 analysis/audit_run/doc_id/target_key/field + latest_version_id/hash；仅 server-confirmed blocked_modify；C8 仍核验非豁免文档；preflight 仅 latest decision 精确匹配；TOCTOU FOR UPDATE）；CHECK `chk_docg_waiver_items`；fixture `capa_with_cp_blocked_modify`。**第 24 轮**：residual completeness（同批次全部未覆盖 keypoint 须被 items 覆盖；不可豁免 FMEA/pending_update/incomplete 拒整单）；C8 version_snapshot 保留全部文档并绑定 latest_version_id/sha256，gate 重比版本+target_key 仍缺；preflight waived_keys 绑定版本，CP 漂移即复报；`20260715_waiver_items` 迁移先 UPDATE 失效遗留 reason-only waiver 再加 CHECK；`make deploy-release` 强制 migrate->check+preflight->再放行 app；+5 回归测试（partial/FMEA residual/version bump/stale waiver/legacy migration）。444 capa 绿。
- [x] **01.8 知识库沉淀收尾** — `knowledge_entries`（结构化 fields + document_no 50 + embedding_*）+ outbox `content_hash` + worker stale/dead_letter；`sink_capa_on_close` 挂 D8 close fail-closed（blocked/failed）+ 手动 resink；list/detail factory 403/404；stage-5 `KnowledgeEntrySource` + `KNOWLEDGE_SUNK`/`KNOWLEDGE_RETRIEVED`；FE CAPA knowledge card + outcome UX；E2E seed `8D-E2E-KNOW-001` + `capa-story-knowledge-sink.spec.ts`。spec: `docs/superpowers/specs/2026-07-16-us-e2e-01.8-knowledge-sink-design.md` v5；plan: `docs/superpowers/plans/2026-07-16-us-e2e-01.8-knowledge-sink.md`（worktree commits `5493d331`..本 task）
  - 与 `capa_lessons_learned` 写路径共存（未改 lessons）。
  - E2E：无 LLM → close 422 `outcome=blocked`；有 LLM → close + list/card + audit SUNK；embedding ready / recommend 命中依赖 embedding worker（可选，软断言）。

### P3 — 新建

- [x] **01.9 横向扩散预警新建** — 4 依据并集类似产品检查（同 product_type/共享 FMEA 模式/共享控制计划/同供应商+物料）+ 通知提示 + 状态追踪；D8 关闭 fail-closed 钩子；decide/rerun；FE Modal/Card；E2E seed+spec
- [x] **01.10 PPT 输出新建** — D8 关闭后一键生成 8D 报告 PPT（D1-D8 + 封面 + 联动附录）；前端 `generatePpt` API + 生成按钮（`canCreate('capa')` L2 门控，D8_CLOSURE/ARCHIVED 可见）+ 审核报告 Modal + admin ReviewSkillsPage 已落地（commit `c78d774d`）

### 配套（非子故事）

- [ ] **verify skill 同步** — 编排器 + 10 子 skill 已建。**契约修复第四轮**（针对第四轮 review 5 个 finding）：(1) 新增 `_seed_d4_audit` 到 `seed_e2e.py`，产出 `8D-E2E-D4-001`（D4_ROOT_CAUSE，01.3 pre-gate 专用）和 `8D-E2E-APPROVAL-001`（D8_APPROVAL_PENDING，01.3 post-gate 驳回专用），避免破坏 01.4 的 seed 状态；(2) 01.3 post-gate 审批/驳回拆到两个不同 CAPA；（3）01.3 D7 auto-fill 判定改为无 LLM→BLOCKED / 有 LLM 但缺失→FAIL；（4）编排器/01.3 更新种子引用。（第四轮）01.4 移除 rule 兜底项断言 + 修正 LLM 要求；编排器强制 reseed；_seed_d4_audit 审计清理；01.3 A 节闸口顺序；编排器图拆 01.3 pre/post。（第五轮）01.4 假 PASS 防护 + keyword/rule API 区分 + skip 审计名 + DOCGATE 审计清理 + provider 感知 LLM。（第六轮）审计 API 用法 + 01.4 解绑/skip-reason + LLM DB 源 + DOCGATE version 清理。（第七轮）trigger disable/enable + 01.7 空清单 FAIL + passed 路径前置 + 01.4 t0/skip 澄清。（第八轮）**发现 US-E2E-01.7 产品缺口**：实现 allowlist 只查询 ControlPlan+FMEA（`capa_doc_gate_service.py:265`），prompt 也只允许 CP/FMEA（`:422`），**SOP 无实现路径**——故事要求 ≥3 类（CP/FMEA/SOP）无法满足。skill 改为：走查若仅拿到 CP/FMEA 两类 → 记 FAIL（功能缺口：SOP 未覆盖），非 skill 问题；修复 SOP 接入后才能 PASS。reseed 时间漂移修复：`_seed_doc_gate_capa` else 分支新增 `capa.created_at = NOW()-1day`（原来仅 insert 时设，reseed 不重置 → 几天后 baseline NOW()-2d 漂移过 capa.created_at，`_get_baseline_version` 的 `version.created_at <= capa.created_at` 查询失败）。impact 字段名修正：断言改为 `baseline_version_id`/`baseline_version`（非 `version_before`，后者是 audit 结果字段）。（第九轮）review 发现 4 项并修复：(1) **seed 补同产品线 CP**——`_seed_doc_gate_capa` 新增 `CP-E2E-DOCGATE-001`（`E2E_PRODUCT_LINE` + baseline version，trigger disable/enable 包裹），使 01.7 impact 能产出 CP+FMEA 两类（此前只有 FMEA，唯一 CP 属 01.9 的 LATERAL 产品线不可见）；(2) **记录 FMEA 不可写字段产品 bug**——FMEA `allowed_fields` 含 `prevention_control`/`detection_control`，但 `GraphNodeSchema` 无此二字段，`PUT /api/fmea` 经 Pydantic 丢弃 → 版本 diff 无法覆盖，FMEA `passed` 仅当 LLM 恰好选 `name` 才可能，否则必 incomplete；CP 的 allowed_fields 均可写故 CP passed 稳定；skill C 节如实记录此限制；(3) **freshness 断言修正**——`analysis_input_hash`（C9）明确不含 latest version，分析后 bump 版本是 passed 必要步骤且不触发 freshness 阻断，E 节改为正确语义；(4) **FAIL 传播规则**——编排器 `跳过/传播策略` 与 01.7 skill 新增「FAIL/BLOCKED 后 01.3 衔接」节：01.7 因 SOP 缺口必然 FAIL 时不为给 01.3 留状态而强造 passed decision，01.3 审批路径标 BLOCKED（前置未通过）、驳回路径（不依赖 01.7）照常验收。验证：seed_e2e.py 语法 OK、verify-refs exit 0、doc-gate 123 测试全绿。（第十轮）review 再发现 3 项并修复：(1) **reseed 不重置 CP item**——existing 分支只在 item 缺失时插入，上轮走查改过 `control_method` 等字段不会被重置，但 baseline 又恢复 canonical → live CP ≠ baseline → 后续 diff 混入幻影旧变更。修复：else 分支补全 canonical 字段重置（step_no/process_name/characteristic_no/product_characteristic/process_characteristic/special_class/sample_*/control_method/reaction_plan/source_fmea_node_id/sort_order），保证 live item 与 baseline 逐字段一致；(2) **FMEA passed API 行为写错**——skill 原写「`PUT /api/fmea/{id}` 触发版本」，实际 `update_fmea` 只更新提交不建版本（`fmea_service.py:279`），版本须显式 `POST /api/fmea/{fmea_id}/versions`（`version.py:97`）。修正 C 节步骤：先 PUT 改 `name`，再 POST versions，漏掉则 latest 不变 → audit 仍 pending_update；(3) **seed-state 测试过期**——`E2E_KNOWN_DOCS` 已扩 PFMEA/CAPA 并新增 `control_plan` 键，测试仍精确断言旧单元素列表（`test_e2e_endpoints.py:38`），E2E_MODE 下必败。修复：改为 `from app.seed_e2e_constants import E2E_KNOWN_DOCS` + `assert data["known_docs"] == E2E_KNOWN_DOCS`，由常量驱动（端点本就声明镜像该常量）。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过、**doc-gate 123 passed / 2 skipped**。（第十一轮）review 再发现 3 项并修复：(1) **CP passed 路径不可执行**——seed 将 CP 设为 `approved`，但 `update_control_plan` 明确禁止更新 approved CP（返回 400，无 reopen 端点），故「改 item→建版本」走不通。修复：seed 改 `status="draft"`（allowlist/baseline 不筛 status，draft 仍是有效受控文档且可更新），skill C 节注明 CP 为 draft；(2) **CP reseed 未完全恢复 canonical**——item 漏重置 `equipment`（baseline 固定 None）、CP header 的 `phase`/`fmea_ref_id`/`part_no` 等未同步、额外 item 未清除 → 重复走查后 live CP 仍≠baseline。修复：抽出 `CP_CANON`/`ITEM_CANON` 字典，reseed 时 `setattr` 全量恢复 header+item 字段（含 equipment），删除 `item_id != DOCGATE_CP_ITEM_ID` 的多余 item；baseline `header_snapshot` 改为从 live cp 字段派生并补 `fmea_ref_id`+`phase`（对齐 `version_service.create_cp_version` 形状，避免 header diff 幻影变更）；(3) **seed-state 测试同源循环**——测试与端点共用 `E2E_KNOWN_DOCS`，常量漏项时双方同步通过，无法证明文档真已 seed。修复：新增 `test_seed_docs_actually_exist_in_db`，直查 `FMEADocument`/`ControlPlan`/`CAPAEightD` 表，硬编码关键 doc_no 断言真实存在（独立于常量），打破循环。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过、**doc-gate 123 passed / 3 skipped**（新增 DB 实查测试为第 3 个 skip，收集无误）。（第十二轮）review 再发现 4 项并修复：(1) **engineer 无权更新 CP**——`PUT /api/control-plans` 要求 `Module.PLANNING >= CREATE=2`，seed 角色 engineer=`field_qe` 的 planning=1（VIEW）→ 403；manager planning=4 可过。skill C 步改为切换 manager 改 CP、engineer 改 FMEA；(2) **PUT items 全量替换 + 必须保留 item_id**——省略 items 不改项；提交 items 缺/换 item_id 会删旧建新 → doc-gate `target_key` 匹配失败。skill 给完整示例 body（固定 `DOCGATE_E2E_CP_ITEM_ID`）；(3) **reseed 审批残留**——status 回 draft 后 `approved_by`/`approved_at` 仍可能非空；item `factory_id` 未钉回。修复：else 分支 `approved_by=approved_at=None`、`item.factory_id=factory_id`；(4) **seed DB 测试过浅**——只验 doc_no 存在，未验 draft/单 item/baseline 对齐。`test_seed_docs_actually_exist_in_db` 扩：`status==draft`、`approved_*=None`、恰好 1 item 且 id=CANON、item.factory_id==cp.factory_id、`control_method` 回 ITEM_CANON、baseline version 存在且 `items_snapshot` 钉住固定 item_id。验证：seed/test 语法 OK、verify-refs exit 0、git diff --check 通过。（第十三轮）review 再发现 3 项并修复：(1) **passed 路径不得硬编码只改 control_method**——audit 经 `_match_key_point` 严格匹配 action+target_key+field；skill C 改为：先读 impact 全部 key_points，再按每条落库（CP modify 用 manager+完整 items/原 item_id；FMEA 仍受 schema 限制）；漏改 → incomplete；(2) **POST .../versions 必须 JSON body**——`ManualVersionCreate` 必填 req，裸 POST 422；skill 明确发 `{}` 或 `{"change_summary":"01.7 doc-gate update"}`；(3) **reseed 幂等 + baseline/hash 真测**——新增 `tests/e2e/test_seed_e2e_docgate.py`：seed → 污染 status/approved_*/title/control_method/extra item/baseline snapshot → 再 seed → 断言 draft、approved_*=None、单 CANON item、header/items 全字段对齐、`sha256_hash == compute_pg_jsonb_hash`，且两次 hash 稳定。**不依赖 E2E_MODE 环境**（monkeypatch + 直接调 `_seed_doc_gate_capa`），`make check` 可 GREEN。验证：`test_seed_e2e_docgate` **1 passed**、verify-refs exit 0、compile OK。（第十四轮）review 再发现 4 项并修复：(1) **`target_kind=document` + `expected_action=add`**——baseline=NULL 文档（seed `PFMEA-E2E-001`）只需 `POST .../versions` 建首版，audit 对 document 直接 covered；skill C 表补此行；(2) **CP/FMEA add 精确匹配**——CP add：`source_fmea_node_id=parent_node_id` 且 product/process characteristic == business_key 且 field 非空；FMEA add：parent→new edge + type 匹配 + name==business_key + field 非空；delete 只比 id；skill 用表写清，避免 incomplete；(3) **FMEA 产品限制按 action 区分**——prevention/detection_control 主要卡 modify 与对应 field 的 add；delete 忽略 field 可过；不再写「选 prevention 就永远无法覆盖」；(4) **seed 测试全量 header 契约**——断言 part_no/part_name/contact_info/drawing_rev/org_factory/core_group/phase/fmea_ref_id；hash 用 CANON 派生 payload 与 stored 双比；污染步骤覆盖全部可选 header 字段。验证：docgate seed **1 passed**、verify-refs 0。（第十五轮）review 再发现 3 项并修复：(1) **FMEA PUT 整图替换**——`fmea_service` 写整个 `graph_data` 非 patch；skill 明确 modify/delete/add 均须 `GET` 全图 → 改 → PUT 带回全部 nodes/edges，只交目标节点会丢图；(2) **FMEA add 边必填 type**——`GraphEdgeSchema` 要求 `source`/`target`/`type`，缺 type → 422；skill 给完整边对象与建议 type（FailureMode→HAS_FAILURE_MODE、FailureEffect→EFFECT_OF、FailureCause→CAUSE_OF），方向 parent→new；(3) **seed 测试钉 product_line + factory CANON**——断言 `cp.product_line_code == E2E_PRODUCT_LINE["code"]`、`cp/item/ver.factory_id == FACT_DC100_ID`（非仅 item==cp 自洽）；header `product_line_code` 用常量；污染同时改 `product_line_code` 与 `factory_id` 到 SH。验证：docgate seed **1 passed**、verify-refs 0。（第十六轮）review 再发现 2 项并修复：(1) **FailureCause add 不得写反向 CAUSE_OF**——标准图 `CAUSE_OF` 是 Cause→FM（`seed.py`），matcher 却要求 parent→new；skill 不再建议 parent→new + CAUSE_OF，记为 **产品缺陷**（matcher/add-anchor），走查对该 key_point incomplete/PASS-NOTE，禁止假 PASS；(2) **baseline version factory_id reseed**——`_seed_doc_gate_capa` CP/FMEA version UPDATE 补 `factory_id = :fact`；测试污染阶段改 version.factory_id 到 SH 再断言 reseed 回 `FACT_DC100_ID`。验证：docgate seed **1 passed**、verify-refs 0。（第十七轮）review 再发现 1 项并修复：**add_anchor 非法组合不限 CAUSE_OF**——实现是每个已有 node × {FM,FE,FC} 笛卡尔积，matcher 不验 parent type / edge type；docgate seed baseline 仅 ProcessStep，全部 anchor 均非 canonical。skill 补 canonical 父子表 + 规则：凡 parent type 不匹配 / CAUSE_OF 方向冲突 / 其它非 canonical 组合 → incomplete/产品缺陷，**不得落库**（禁止为 gate 写语义错误边）。验证：verify-refs 0。（第十八轮）review 再发现 1 项并修复：**非法 add_anchor 不得 PASS-NOTE**——与「一律 incomplete」及编排器总体结论仅 PASS/FAIL/BLOCKED 对齐；走查规则改为 key_point incomplete → 无法 decision=passed → **passed 路径 FAIL（产品缺陷）**，删除「或 PASS-NOTE」软化；缺陷分类节同步。验证：verify-refs 0。（第十九轮）review 再发现 2 项并修复：(1) **01.7 FAIL→01.3 传播**——`verify-capa-8d-d4-d7-audit` C 节补表：权限/驳回在 `8D-E2E-APPROVAL-001` 上 01.7 FAIL 仍可跑；仅审批 (c) BLOCKED；禁止整段 post-gate 因 01.7 FAIL 跳过；01.7 skill 衔接节同步；(2) **PASS-NOTE 统一**——编排器子报告契约写明步骤四态 + 备注列、总体三态；全部子 skill 缺陷分类/步骤结果去掉 PASS-NOTE 作结果枚举（说明进备注；PPT 无 LLM 审查→BLOCKED）。验证：verify-refs 0。**状态：契约层 GREEN，仍 🟡——未做 RED/GREEN 行为测试；产品 bug 仍在。**
- [ ] **gap analysis 维护** — 实现推进中若发现新 gap，回写 `docs/superpowers/specs/2026-07-08-us-e2e-01-gap-analysis.md`

### 关键约束

- **交付顺序**：01.1→01.2→01.3→01.7→01.4→01.5→01.6→01.8→01.9→01.10（D 步业务流程；01.4/01.5/01.6 可并行）
- **状态机**：实现时须先把 `eightd_state.py` 细化为 D7_PREVENTION→D7_COMPLETED→D8_GATE_PENDING→D8_APPROVAL_PENDING→D8_CLOSURE（含驳回回退），01.3/01.7 依赖此细化
- **AI_REQUIRED**：01.1/01.2/01.3/01.7/01.8/01.9 为 true（无 LLM 凭证→BLOCKED）；01.4/01.5/01.6/01.10 为 false

---

## 参考资料

- 详细路线图：`docs/ROADMAP.md`
- AI-QMS 总体设计：`docs/superpowers/specs/2026-06-29-ai-driven-qms-overview-design.md`
- P0 Agent Base 设计：`docs/superpowers/specs/2026-06-29-ai-qms-p0-agent-base-design.md`
- P0 Agent Base 实施计划：`docs/superpowers/plans/2026-06-29-ai-qms-p0-agent-base-plan.md`（13 任务 / 4 验收）
- P1-B 质量趋势迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1b-quality-trend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1b-quality-trend-migration.md`（5 TDD 任务）
- P1-C FMEA 推荐迁移：`docs/superpowers/specs/2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md` + `docs/superpowers/plans/2026-06-30-ai-qms-p1c-fmea-recommend-migration.md`（6 TDD 任务，4 轮评审）
- P1-D 剩余 LLM 消费者迁移：`docs/superpowers/specs/2026-07-01-ai-qms-p1d-remaining-llm-migration-design.md` + `docs/superpowers/plans/2026-07-01-ai-qms-p1d-remaining-llm-migration.md`（5 TDD 任务，3 轮 spec + 3 轮 plan 评审）
- 权限矩阵：`docs/permissions.md`
- 各模块详细文档：`docs/modules/`


---

## Task 4 — CAPA outcome-review production decision binding (2026-10-25)

### Scope, assumptions and result

- **DONE: Task 4 only**, based on `a1721b3c`, reviewed dependencies Task 3 `894349fa` and Task 2 `acc54804`.
  Read only the Task 4 brief/context, not the eight-task implementation plan. The approved existing D8 approve/reject
  edges, current APPROVE/source authority and existing self-approval policy remain authoritative.
- Implemented the actual production D8 producer in `backend/app/services/capa_service.py`, not a fixture receipt or UI.
  No new state/table/feature switch/migration, no client-selected receipt, no version-skip flag, no new policy.
- Worked solely in this worktree. Used the already registered owned application/test resources via private `run-owned.py`;
  no environment/profile/credential dump, global installs, infrastructure recreation, shared/seed/production data writes,
  migration CLI, full `make check`, push/merge/deploy or main-checkout edits. Existing reviewed owned tenant fixture
  provisioning was reused for real tenant/JWT tests. `app.seed_e2e.main()` was **not** run.
- CodeGraph focused context was queried first; its stale index was not repaired. Actual reviewed helper interfaces were
  inspected directly in the known files. No unrelated audit or agent delegation.

### Production contract and transaction review

1. `AdvanceRequest` adds exactly `expected_outcome_revision: str | None` (64 lowercase hex) and
   `expected_review_round_id: UUID | None`. Only valid D8 decision edges require both. Authorized missing/partial
   expectations return 409 `CAPA_OUTCOME_REVIEW_REQUIRED`; stale material/round returns 409
   `CAPA_OUTCOME_REVIEW_CHANGED`; malformed DTO fields remain 422. Arbitrary client `outcome_review` metadata does
   not satisfy the expectation. Invalid state edges remain invalid. A three-argument service call at pending cannot
   infer a D8 decision; it retains the explicit-target error, not a bypass. Early three-argument EDIT progression and
   archival without tokens remain supported.
2. API dependency and direct service entry use current actor identity/role/factory/product-line admission. CAPA parent is
   locked and refreshed; actual EDIT/APPROVE edge authority is determined again after waiting. Server UUID scalars are
   captured before any closure rollback could expire ORM identities. Neither a cached role nor a GET receipt grants access.
3. `require_outcome_expectation(db, scope, capa, req)` reuses the complete reviewed collector, round resolver and HMAC
   plus **fresh** CAPA/target/source/tenant authorization. It does not call the RR/GET wrapper. The temporary collector
   access context is restored on success/failure. It returns only the server-owned five-key metadata envelope.
4. `apply_outcome_expectation(db, capa, req, actor_id)` resolves a current server-UUID scope. Approval calls the existing
   `_d8_doc_gate_gate()` with the complete additional source-parent set, preserving C8/C9, waiver and version checks.
   The retained order is CAPA → analysis → ProductLine → sorted CP/FMEA parents; explicit references outside the gate
   snapshot join that **same** sorted set, never a late reverse-order lock. Full material/version/access checks repeat
   after all actual waits. Approval also requires a current-root-cause matching passed record and nonblank D5/D6;
   text alone does not establish effectiveness. Rejection locks the same source/gate hierarchy and binds the same tokens,
   still needs a nonblank reason, and returns only to D7; it need not turn a failed gate into a passing one to reject.
5. Knowledge sink, lateral diffusion, transition, audit and MES outbox stay in one transaction with the parent and all
   source/gate locks retained. Revalidation occurs after sink and after lateral long awaits, then again after actual
   state/audit/MES flush and immediately before final commit. Failed closure effects roll back. No helper commits early.
   This does **not** claim to retract information already sent in a previously authorized external call.
6. Existing `D8_APPROVED` / `D8_REJECTED.changed_fields['outcome_review']` gains exactly
   `contract`, `round_id`, `revision`, `doc_decision_id`, `source_versions`. Existing reason remains a normal rejection
   field; no free-text body/verification snapshot is copied into the receipt and no second D8 decision audit is emitted.
   Decision and TRANSITION audits carry the target factory so the reviewed round/reader can locate actual production logs.
7. New production receipt tests check actual emitted approve/reject envelopes. Actual approval is consumed as `verified`
   by the reviewed RR reader, survives archive and later normal source evolution, and its nested source refs are found by
   the reviewed source-reference collector. A rolled-back test transaction removes nonreceipt FMEA refs to prove the
   **actual** receipt alone still identifies the CAPA; no manually fabricated D8 receipt is used for this acceptance.
   Legacy round remains tenant+report only; no updated_at binding, GET write or historical re-signing was added.

### Test evidence and limits

The exact command prefix for all backend runs below, from this worktree root, was:

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest
```

The runner re-parses the private owned exports, removes provider keys/E2E_MODE and redacts sensitive connection data.
No real provider was called. Strict unit provider responses isolate only external responses; authorization, collectors,
state transitions, source locks, real sessions and commits run normally. The old flush-only helper is used only in old
unit cases; those are **not** represented as committed HTTP/RR or concurrency evidence.

#### Actual RED → GREEN

Initial RED exact command:

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_decision.py -q
```

`focused-20261025T145705208875.log` ended with:

```text
7 failed, 2 passed, 3 warnings, 1 error in 2.32s
```

Failures were absent expectations on approve/reject, stale D6/verification material, missing expectation on direct service,
missing real approval receipt and missing real rejection receipt. The old-round branch initially stopped earlier at the
missing receipt assertion; it was not claimed as independently reached RED. The error was teardown of the newly real sink:
the old fixture did not remove KnowledgeEntry before deleting its factory. Fixture cleanup was extended for actual
knowledge/lateral rows; the exact single owned RED fixture residue was subsequently removed with a guarded, exact-UUID
cleanup test (no database recreation). The initial simple decision GREEN using the identical command was
`9 passed, 3 warnings in 2.73s` (`focused-20261025T150054775690.log`).

Iteration ledger (all logs are in the private ignored plan workspace, not a new report artifact):

| Log suffix (20261025T…) | Actual summary | Reason / resolution |
|---|---|---|
| 150117697305 | 10 failed, 54 passed, 3 warnings in 2.98s | Old closure callers lacked expectations/prerequisites; overbroad failure rollback also broke an early D7 flush-only case. Closure rollback was scoped to the D8 decision execution path; old callers/fixtures upgraded, not assertions weakened. |
| 150452642041 | 5 failed, 67 passed, 3 warnings in 6.69s | Test prerequisite helper tried the gate writer while already pending; corrected explicit fixture rows; fixed a provider fixture import. |
| 150608779259 | 4 failed, 43 passed, 3 warnings in 4.77s | New MES assertion named the wrong model and old flow created its first source version after analysis in one flush-only transaction; corrected the model and created the controlled version before analysis. |
| 150853618342 | 1 failed, 37 passed, 3 warnings in 12.04s | Negative verification fixture violated the existing conclusion/is_verified DB constraint; kept the constraint and made the negative row valid. |
| 151349392516 | 37 passed, 3 warnings in 18.20s | Expanded decision + real-wait acceptance green. |
| 151642614486 | 80 passed, 3 warnings in 27.03s | Decision/concurrency + upgraded closure caller suites green. |
| 151821820365 | 40 passed, 3 warnings in 24.42s | Added seed prerequisite/real JWT HTTP acceptance green. |
| 152044538564 | 46 passed, 3 warnings in 25.25s | Added actual PostgreSQL commit-boundary failure/retry + C9 approval coverage green (includes old flow file). |
| 152324581179 | 5 failed, 656 passed, 3 warnings in 129.08s | First complete affected run: three unscoped old gate assertions saw the single initial RED residue; two old direct gate race fixtures lacked current actor role/scope rows. Cleaned only the exact owned residue and backfilled those two real fixture actors. No gate assertion was relaxed. |
| 152841755867 | 1 passed, 3 warnings in 1.86s | Exact initial RED-fixture cleanup only, guarded to the registered owned random test DB. |
| 152858430310 | 661 passed, 3 warnings in 125.75s | First green complete rerun. Final diff self-review then caught an accidentally removed, unrelated synchronous lateral suggestion test; restored it unchanged, removed newly unused imports and retained the original explicit blocked-flag assertions. |
| 153709552672 | **662 passed, 3 warnings in 125.20s** | Complete affected rerun after the LAST source/support change, including the restored original lateral test. |

The first 64-case caller regression used exactly these pytest arguments:

```text
tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_knowledge_sink.py tests/capa/test_lateral_diffusion_concurrency.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_lateral_diffusion_api.py tests/capa/test_capa_post_review_fixes.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/recommendation/test_lessons_extraction.py -q
```

The next 72-case iteration prepended `tests/capa/test_capa_outcome_decision.py` to that list. The 47-case iteration used
`tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_knowledge_sink.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_lateral_diffusion_api.py -q`.
Decision/concurrency-only iterations used those two exact files with `-q`; the 38/46-case iterations also appended
`tests/capa/test_capa_advance_flow.py`. The 80-case command was decision/concurrency/advance_flow/advance_permission/
knowledge_sink/lateral_diffusion_service/lateral_diffusion_api (the seven named files above), with `-q`.
The cleanup-only command appended
`-c pytest.ini /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task4_owned_cleanup.py -q` to the same runner prefix.

#### Final complete affected command and output

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_review_guard.py tests/capa/test_capa_review_source_guard.py tests/capa/test_capa_reviewed_writes.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_post_review_fixes.py tests/capa/test_capa_doc_gate_api.py tests/capa/test_capa_doc_gate_concurrency.py tests/capa/test_capa_doc_gate_coverage.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_capa_doc_gate_preflight.py tests/capa/test_capa_doc_gate_regression.py tests/capa/test_capa_doc_gate_service.py tests/capa/test_knowledge_sink.py tests/capa/test_knowledge_api.py tests/capa/test_lateral_diffusion_api.py tests/capa/test_lateral_diffusion_concurrency.py tests/capa/test_lateral_diffusion_match.py tests/capa/test_lateral_diffusion_service.py tests/capa/test_capa_d4_gate.py tests/capa/test_capa_d7_action_service.py tests/capa/test_capa_verification_api.py tests/capa/test_capa_verification_conclusion.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_source_ref.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/recommendation/test_lessons_extraction.py --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py -q
```

```text
CHECK_COMPLETE: mode=pytest; exit_code=0
log=.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261025T153709552672.log
662 passed, 3 warnings in 125.20s (0:02:05)
```

The three warnings are the existing Pydantic class-based Config deprecations. The selected run has **0 failures,
0 skips, 0 xfails, 0 xpasses**. Both Makefile graph exclusions were retained explicitly. Migration/release-entrypoint
suites were not invoked. No historical 242/2999/full-suite baseline was counted as this result.

The two changed E2E API callers were statically checked without starting the app or contacting providers:

```bash
node frontend/node_modules/typescript/bin/tsc --noEmit --skipLibCheck --moduleResolution bundler --module esnext --target es2020 --esModuleInterop --typeRoots frontend/node_modules/@types frontend/e2e/specs/m1-core/capa-story-knowledge-sink.spec.ts frontend/e2e/specs/m1-core/capa-story-lateral-diffusion.spec.ts
```

Actual result: exit 0, no output. `git diff --check` also exited 0 with no output.
A final AST comparison against BASE confirmed every original test name in all changed existing backend test files was
preserved (`task4-check-old-tests.py`: `Original test-name preservation: PASS`). The accidental intermediate test removal
is recorded above, not counted as a skip or silently omitted from final acceptance.

### Source, transaction, receipt and caller coverage

- **True race, approval first:** session A retains a cached pending ORM object, then reaches real CAPA FOR UPDATE.
  SQLAlchemy execute witness sets an Event and `pg_blocking_pids` proves A is blocked by B. B executes real approval
  and commit; A refreshes and receives ReviewedContentLocked. No simulated authorization/commit/source lock.
- **True race, material first:** real D6 update and real verification service update each commit ahead of a waiting
  approval with old tokens. Both directions have Events + PostgreSQL blocker evidence. Approval conflicts and remains
  pending with no D8_APPROVED, knowledge, lateral or MES success rows.
- Both approve/reject orderings emit exactly one first actual decision; the second sees the fresh invalid edge.
  CAPA authority revoked during parent wait is refused. Planning-source permission and product-line assignment revoked
  while waiting for explicit FMEA (after gate CP was locked) are rechecked. A real source-version commit during that
  wait invalidates the token. A CP version change with unchanged bound revision still fails the original C8 gate;
  a freshly read token cannot replace a stale C9 gate.
- Complete CP→FMEA union order is witnessed. An actual source-version writer is blocked while knowledge provider
  response is paused; only the real decision commit releases it. Reader then still verifies the accepted old version.
- Current CAPA role, source-module permission, active actor and product-line scope revocation during a provider wait all
  roll back the transaction. Separate owned tenant status/generation changes exercise real registry admission, not fake
  authorization. The post-MES test stages a **real** outbox row, revokes authority, observes complete rollback, restores
  authority and retries to exactly one decision/knowledge/MES event. A real PostgreSQL `SELECT 1/0` at the actual commit
  event aborts the database transaction; retry produces only one final D8 audit. Commit itself is not mocked.
- Real employee JWT login, tenant middleware, production scope dependencies, real committed sessions and RR/RO GET are
  exercised for both approve and reject. Approved output becomes verified; rejected output returns the existing early-state
  404. The `review_http_client` cases separately use committed production handlers with explicit scope fixtures; they are
  not mislabeled as JWT authentication evidence.
- Missing/partial/malformed expectations, client receipt injection, stale D6/verification, resubmitted old round,
  current-source access, current-root validation, D5/D6 content, blank rejection reason, valid state edges, self-approval,
  early EDIT and archive compatibility are asserted without softening old permission assertions.

Updated old callers/fixtures:

| Location | Exact treatment |
|---|---|
| `backend/tests/capa/test_capa_advance_flow.py` | Actual D8 approval/rejection requests use same-transaction real collector expectations; source version exists before analysis; passed current-root prerequisite added. Blank-reason negative also has valid version fields. |
| `backend/tests/capa/test_capa_advance_permission.py` | Manager approval gets explicit verified-root/gate prerequisites and real collector token. EDIT denial remains exact 403 with no unnecessary source grants. |
| `backend/tests/capa/test_knowledge_sink.py` | Success/50-character cases use real collector tokens and prerequisites; provider failure cases moved to actual committed cases so production rollback is observable. |
| `backend/tests/capa/test_lateral_diffusion_service.py`, `test_lateral_diffusion_api.py` | Real own case + real current role/scope + real sink/advance/rollback; only external responses isolated. Removed old fake sink/authorization setup from the affected closure cases. |
| `backend/tests/capa/test_capa_doc_gate_regression.py` | Two existing gate-lock direct-service actor fixtures now have real EDIT permission and factory/product-line assignments plus scoped cleanup; existing gate/race assertions retained. |
| `backend/tests/capa/outcome_review_support.py` | Explicit legacy unit prerequisites and actual knowledge/lateral teardown; existing `review_expectation` is same-transaction collection, never a production bypass or independent RR claim. |
| `backend/tests/capa/test_capa_post_review_fixes.py` | Inspected and rerun; only D8-looking calls are invalid stale-state / exact permission-denial tests, not successful decisions needing a token. No weakening or source grants. |
| `backend/tests/recommendation/test_capa_lesson_embedding_chain.py`, `test_lessons_extraction.py` | Inspected actual calls: D7_COMPLETED / manual extraction, not D8 decisions. Unchanged and rerun. |
| `frontend/e2e/specs/m1-core/capa-story-knowledge-sink.spec.ts`, `capa-story-lateral-diffusion.spec.ts` | Existing direct closing API requests now GET the review revision/round and send those fields; no Task 5 UI added. Static TS check passed. |
| `backend/app/seed_e2e.py` | Backfill only the six affected pending knowledge/lateral/rejection fixture reports with root/gate/source-version prerequisites and a new submission audit. No D8 decision receipt, no early helper commit. Representative helper case is tested inside owned rollback; main seed was not executed. |

### Self-review, documentation and next steps

- Self-reviewed the complete source/fixture/caller diff for exact five-key producer/consumer compatibility, state-edge
  authority, complete lock union/order, post-wait/current access, late rollback identity expiry, helper commits, HMAC
  exclusions and frozen legacy round. Existing C8/C9/waiver/current-source and Task 2 write/source-deletion guards were
  rerun in the final covering command. No unresolved Task 4 correctness finding remains.
- Synced `docs/permissions.md` with DTO/error/authority/transaction/receipt contracts. This named PROGRESS section is the
  requested full Task 4 report, using the brief's explicit fallback because this session prohibits standalone report Markdown.
- Remaining **planned** work only: Task 5 production frontend review UI/interaction and Task 7 real-provider/browser
  acceptance. Existing production frontend closes must fail closed until upgraded in Task 5; no missing-version legacy
  escape was added. This run is not presented as real LLM, Chromium or release acceptance. Full check belongs to Task 8.
- Local commit subject: `feat(capa): bind D8 decisions to reviewed outcome versions`. No push/merge/deploy.


## Task 5 — Production D8 outcome review panel: implementation and verification report (2026-10-26)

### Scope, authority and completion

- **DONE locally.** Implemented Task 5 only on BASE `f89b6806`, using reviewed writer `2c3d212b`,
  reader `894349fa` and source/material guard `acc54804`. Local task commit was explicitly authorized.
  Prior backend acceptance is not presented as new frontend evidence; independent Task 5 review remains the controller's gate.
- Read only the exact Task 5 brief/context, current PROGRESS/decisions and focused production/test files, not the whole plan.
  CodeGraph context was queried first; its narrow/stale results lacked current outcome symbols, so precise known-file reads followed.
  No index repair, other task implementation, backend DB/provider/infrastructure/migration work, full `make check`, package
  installation, main-checkout edit, push, merge or deployment was performed.
- Loaded frontend-design guidance within the existing UI scope: Chinese/English locale keys, Ant Design, PageShell/DataCard,
  theme variables and responsive existing columns; no font, dependency or visual redesign. Report uses this existing file because
  this session prohibits standalone report Markdown, as explicitly permitted by the Task 5 context.

### Actual reviewed contract and implementation

- Inspected `backend/app/schemas/capa_outcome_review.py`, `backend/app/schemas/capa_verification.py`, production
  `backend/app/api/capa.py`, and the reader/source tests. TS mirrors `capa.outcome-review.v1`, full core/Verification/D7 action
  collections, exact `{module, object_id, version_id, sha256}` references, exact decision fields and the separate supplement.
  The existing reused D7 type now includes the actual response `status`. The reviewed verification source dictionary is
  **`{fmea_id, cause_node_id}`**, not an invented object/version reference; immutable versions are in `documents`.
- Added `getCapaOutcomeReview(id, signal?)`; advance forwards the current seen revision/round, rejection reason and optional
  signal. No backend compatibility bypass, new policy, candidate approval or per-step D4/D5/D6 approval was introduced.
- The panel renders only pending approval/closed/archived. It shows implemented D5 measures, D6 result text, verification
  method/conclusion and complete escaped evidence/source metadata, D7 actual action/status and before/after controls, both
  FMEA and PLANNING controlled source versions/hashes, decision history and explicit legacy/unverifiable labels.
  D7 pending is never relabelled verified; nonempty D6 never becomes an effectiveness badge.
- Read completeness checks reject malformed/partial DTOs, unknown verification source shapes, mismatched report/status and
  missing required referenced documents. Empty documents remain valid for genuinely unreferenced materials. Authorization,
  source-version integrity and current authority still belong independently to the backend.
- Evidence is text/JSON metadata only: no extraction, external URL preview/link execution, HTML/Markdown execution or new
  download. Formal materials have no preview TTL and are not persisted to Zustand/localStorage/sessionStorage/IndexedDB.
  Existing private D4 preview TTL and attachment behavior were not weakened.
- Only the successful current panel callback supplies the sole page approval/rejection path. It checks pending status,
  APPROVE, matching report/current identity, nonnull round, pending binding and no decision. Both decisions consume the token
  once; rejection uses the existing trimmed nonempty reason. Duplicate clicks are locked synchronously and disabled visually.
- Before reload the old material/token/reason is cleared. 409 requires explicit reload/review, never silently reading a new
  revision and approving it. Network uncertainty queries actual report state without replaying the POST. 401/403/404 withdraw
  the decision/report. Exact outcome-read and advance-POST 401/403 failures reject before Axios refresh/replay; refresh
  coordination and other private-route guards were left intact.
- Page/panel local epoch/controller registries cover their concurrent reads and actions. User/permissions, store and actual
  stored credential, tenant, report/route selection, factory and product-line changes unmount/withdraw the view, abort requests
  and clear reasons/tokens. Every page/panel awaited result is checked before publication; late success **and** late denial
  cannot update the new view. Existing draft generation also aborts on replacement/clear/unmount; no private result is cached.
- Terminal core handlers guard update/replace/append/undo/link before API calls; terminal UI unmounts draft controls immediately
  (including retained modal content), removes association/core/verification edits even for admin, and keeps closed `d8_closure`
  editable only with EDIT under the explicit unreviewed label. Archived supplement is frozen. Early D4/D5/D6 editing and D4
  verification permissions remain writable under their existing rules. Supplier-risk/lateral/knowledge behavior was not given
  new review policy; page-owned requests were only cancelled/fenced for identity safety.

### RED/GREEN evidence and self-review corrections

All commands below ran from this workspace's `frontend/` using existing node_modules. Logs are retained in
`.superpowers/sdd/2026-10-23-capa-outcome-review/` and are private local verification evidence, not task source files.
The first attempted combined sourcing of `owned-env.sh` was refused by the worktree command verifier before execution;
frontend-only commands therefore used the identical explicit workspace path and did not need backend environment variables.
Node **v26.4.0**, npm **12.0.2**, Vitest **4.1.7**, production Vite **5.4.21** were the installed tools.

| Actual command / log | Actual result and interpretation |
|---|---|
| `npx vitest run src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx -t 'outcome review contract\|Task 5 reviewed'` → `task5-red.log` | **5 failed, 33 skipped** (selection only). Missing getter, missing forwarded signal and missing actual outcome materials. Initial D7 fixture error was corrected before this retained meaningful RED. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx` → `task5-panel-red.log` | 1 suite failed / no tests because the component did not yet exist. Scaffolding RED only, not a behavioral acceptance claim. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx` → `task5-green1.log` | 50 passed, 2 failed: old assertions/caller fixture still omitted the newly required signal/current review. Separate tsc also exposed `.at` vs project lib and nullable narrowing; corrected without changing target configuration. |
| `npx vitest run src/pages/capa/CAPADetailPage.test.tsx -t 'Task 5 reviewed'` → `task5-races-red.log` | 18 passed, 3 failed, 24 selected-out. One actual failure: a withdrawn 409 token still left an approval control visible (disabled). Two invalid early recommendation fixtures caused 2 unhandled errors; fixed to actual D4/D5 contracts, not counted as product RED. |
| Primary four-file run → `task5-green2.log`, then `task5-green3.log` | An intermediate duplicate test variable caused panel transform failure and four legacy assertions needed new cancellation arguments; corrected. Subsequent actual four-file run: **79 passed**, frontend tsc exit 0. No backend fallback or permission assertion relaxation. |
| `npx vitest run src/components/capa/useAIDraft.test.ts` → `task5-draft-red.log` | **1 failed, 8 passed**: in-flight draft signal was absent on replacement/unmount. Added narrowly scoped cancellation and after-await checks; covered in final GREEN. |
| Expanded complete affected run → `task5-expanded.log` | 25 files / 195 passed before the final added regressions. This is an intermediate run, not the final count. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/pages/capa/CAPADetailPage.test.tsx` → `task5-extra.log` / `task5-extra-green.log` | **2 failed, 68 passed**: real retained Append/Replace modal controls remained during terminal transition. Unmounted the actual draft component immediately; **70 passed** afterward. |
| `npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx` → `task5-source-red.log` / `task5-source-green.log` | Self-review corrected the initial source fixture to the actual reviewed `{fmea_id,cause_node_id}` shape and added negative cases. **2 failed, 16 passed** showed missing required refs/unknown source shape were accepted; runtime completeness checks fixed both. **18 passed** afterward. |
| Panel + detail + locale run → `task5-self-review.log` | **3 files / 76 passed**, tsc exit 0, after final terminal, successful verified-decision and bilingual parity assertions. |

The primary four-file command above is exactly:

```bash
npx vitest run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx src/api/client.agentTasks.test.ts
```

Self-review covered the actual Python-to-TS field contract, exact source shape, no-source legitimate case, revision/round
provenance, single decision route, rejection reason lifecycle, duplicate click lock, post-await checks, every page-owned
request/controller, stale success/denial, terminal state controls and modal retention, unchanged preview guards, escaped
metadata, no private persistence, locales and documentation. No unresolved Task 5 defect was identified by that self-review.
No external review or real browser/provider success is inferred from these mocked transport unit tests.

### Final verification after the LAST code/test/support change

```bash
cd /Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

Actual final output:

```text
Test Files  25 passed (25)
     Tests  210 passed (210)
Start at 22:55:31
Duration 11.78s
VITEST_EXIT=0

npm notice run 'tsc' --noEmit
TSC_EXIT=0                         # no compiler diagnostics

npm notice run tsc -b && vite build
vite v5.4.21 building for production...
6847 modules transformed.
CAPADetailPage chunk: 98.55 kB (gzip 29.63 kB)
built in 6.52s
BUILD_EXIT=0

npm notice run 'tsc' --noEmit -p tsconfig.e2e.json
E2E_TSC_EXIT=0                     # no compiler diagnostics
```

Final logs: `task5-final-vitest.log`, `task5-final-tsc.log`, `task5-final-build.log`, `task5-final-e2e-tsc.log` in the
private verification directory above. Final selection has **0 failures, 0 skips, 0 xfails, 0 xpasses and no unhandled errors**.
Existing diagnostics remain visible: Vitest's Vite/react-babel esbuild→oxc deprecation notices, Node experimental localStorage
notice and jsdom pseudo-element getComputedStyle messages; build reports the existing mixed static/dynamic `api/version.ts`
import chunk warning. None was hidden, converted to a skip or fixed by unrelated configuration changes. `git diff --check`
also passed. No historical backend/full-suite baseline is counted here.

Coverage includes complete real DTO values, D7 pending vs verified, both source modules/version/hash, escaped malicious-looking
metadata and no arbitrary URL elements, no-reference reports, legacy/unverifiable labels, incomplete/mismatched/source-missing
reads, current approve/reject expectation parameters, 401/403/404/409, explicit new-version review after conflict, timeout actual
state lookup without POST replay, same-document identity/credential transitions, every concurrent initial view controller,
panel/decision close and aborts, stale success/denial, terminal/admin replacement/append/undo/link/verification controls,
closed supplement preserving the core binding, archived freeze, successful verified decision display and still-writable D4/5/6.
The formal-material test advances beyond 30 seconds and checks no storage writes. Existing D4 preview tests are included.

### Exact changed files

All task files, including this report and existing README/permission documentation sync:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capaDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.agentTasks.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/fmea.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/knowledge.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useCapaViewRequests.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/capa-ppt.i18n.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/en-US/capa.json
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/locales/zh-CN/capa.json
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/types/capaOutcomeReview.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/types/index.ts
```

### Remaining limits and next steps

- These are frontend unit/component/transport tests and static/build checks. No actual browser, backend HTTP transaction,
  database, provider, LLM, production report or live permissions acceptance is claimed. **Task 7** remains the real browser/
  provider acceptance; the final full-system freeze/check remains its separately authorized task. No infrastructure was touched.
- Ordinary formal material reads do not inherit candidate retention/expiry. Local abort does not roll back a POST already accepted
  by the backend; uncertainty deliberately queries actual state and requires explicit material review before another decision.
- Existing toolchain/build warnings above are retained, not new unresolved Task 5 functionality blockers.
- Next: controller's independent Task 5 review, then only the separately authorized next task. No Task 6/7/8 implementation,
  candidate workflow, global auth/state-machine redesign or new self-approval policy was started.
- Authorized local commit subject: `feat(capa): add consolidated D8 outcome review panel`. No push/merge/deploy.


## Task 5 fix round 1/5 — complete action ownership, auth effects and independent reloads (2026-10-26)

### Status and scope

**DONE locally against fix BASE `16dff517`; ready for the coordinator's independent re-review.** Both initial gates
returned Needs fixes (no Critical, three Important). The earlier Task 5 "no unresolved defect" self-review statement
was incomplete and is superseded by the findings and evidence below; this report does not claim the external gates passed.
Local fix commit is authorized. This batch changes only the exact frontend actions/helpers/tests/docs needed to address
I1–I3, including the explicitly authorized same-pattern D3/D7/doc-gate/draft child continuations. No backend, DB, provider,
infrastructure, dependencies, business/self-approval policy, global auth state-machine redesign, later task, push/merge/deploy
or main-checkout work was performed. CodeGraph focused context was consulted first; current known files were read afterward.

### Received findings (verbatim)

> I1: A cancelled prerequisite resolves successfully, allowing an old child action to write under the new credential. CAPADetailPage.tsx:496-519,1080-1085 and D4RecPanel.tsx:130-149: A's beforeAdopt awaits handleUpdate(...,true); switch credential/report to B aborts A; handleUpdate returns normally when !request.current even in catch/throwOnError path; old child resumes adoptRecommendation(A) without signal/identity check and Axios supplies B. It can write to A if B is authorized, then toast/refresh from old continuation. Verification requests also lack cancellation/post-await ownership at D4VerificationCard.tsx:38-43,77-100,125-130. Cancellation must not resolve a prerequisite as permission to continue; fence the complete child action, subsequent writes, notifications and reloads under its originating lifecycle.

> I2: Page guards run too late to prevent stale Axios denial/refresh side effects altering new session. client.ts:69-71,101-115,129-136; authStore.ts:85-97; CAPADetailPage.tsx:274-287. A-owned initial/related getCAPA request 403 can start unsignalled /auth/me; switch to B while it waits; A's response setUser mutates B before request.current checks. Likewise A's in-progress tryRefreshToken can later install A tokens or log out B. Exact outcome-read/advance exclusions are correct, but generic page-related paths are unfenced. Carry originating request/session ownership through Task 5 path and check BEFORE auth side effects, preserving other routes' existing refresh policy. Add real Axios transport-level races during /auth/me and refresh, not mocked page API rejection only.

> I3: Reload review aborts unrelated page work and leaves permanent loading. CAPADetailPage.tsx:218-225,380-424,431-480; CapaOutcomeReviewPanel.tsx:29-33: every load first publishes null; parent invalidates ALL page requests. Knowledge lookup/resink pending gets aborted, finally refuses to clear loading because not current; same identity/report/status means effect doesn't restart and retry control can remain inaccessible. Separate token withdrawal from whole-view invalidation, or explicitly reconcile cancelled operations/busy state. Same-identity material reload must not silently strand unrelated business work.

### Implemented fixes and self-review

- **I1 — entire child action lifetime:** `handleUpdate(..., true)` now rejects with `CanceledError` on stale success and
  stale failure instead of granting successful prerequisite completion. The actual parent callback is tested directly as well
  as through recommendation children. `refreshCapa` also refuses to start under an old credential.
- D4, both D5 adoption paths and verification list/source/create/conclusion/source-PATCH operations own their prerequisite,
  POST/PATCH, callbacks, notifications and subsequent reads. Every await is followed by an origin check; each transport receives
  the original owned signal. `useCapaChildRequests` binds report/credential/tenant/factory-line/selection to the existing local
  controller registry. Invalid `begin()` calls produce an already-aborted signal. Late success and late denial do not toast,
  reset a new form or reload under B. D4 verification's source read and record read are both cancelled on close.
- The same actual chain pattern in D7 confirm/auto-fill, doc-gate sequential reads/actions/defer/advance and D3 import/advice/
  execution/read paths is fenced, not deferred as another task. D3 selection cancels child work and clears busy/modal/private
  edit tokens without refetching the visible run list. Separate run-list and selected-run lifetimes avoid a newly introduced
  selection spinner regression. Draft generation now uses registered ownership as well as cancellation/request IDs and resets
  private draft/undo state on lifecycle changes. Early workflows and their payload/provenance remain unchanged.
- **I2 — before auth side effects:** a WeakMap of explicitly owned signal → current-origin guard contains lifetimes only,
  never result content. Axios checks ownership before injecting credentials or entering auth mutation/redirect/retry work.
  Related `/auth/me` and refresh calls carry the same signal. `setUser` is fenced after `/auth/me`; the optional CAPA owner and
  original refresh credential are rechecked inside `tryRefreshToken` before installing tokens or logging out.
- The existing exact outcome-read/advance/D4-preview/Agent private-route exclusions are unchanged. An invalidated owned CAPA
  request settles without being replayed or stranded in another session's refresh queue. Successful still-installed refreshes
  can release existing unrelated queued reads. **Unowned routes retain their existing refresh/queue policy**; the shared queue,
  rotation protocol and global auth state machine were not rewritten. Tests exercise the real interceptor, real auth wrapper
  and real store helper through an Axios adapter, including a stale POST blocked before B's Authorization reaches transport.
  Stored access, refresh and tenant changes are checked even without a storage event or React rerender.
- **I3 — independent panel reload:** null panel callbacks now withdraw only the review token and rejection reason; they do
  not invalidate the whole page request registry. Same-identity material reload lets pending knowledge lookup/resink finish,
  settle loading and retain accessible controls. Whole identity/selection teardown and explicit decision-denial withdrawal
  still cancel the appropriate originating lifetimes. The panel's own failed/new reads still clear all old actionable tokens.
- Self-reviewed all touched await chains and auth side-effect entry points, source versus selected-run scope, settled busy
  state, signal forwarding, exact private exclusions, backend authority and unchanged single decision/terminal/DTO guarantees.
  Original test payload/provenance assertions were retained and only extended with `expect.any(AbortSignal)` where signatures
  gained cancellation. No test/assertion was dropped or warning suppression added. An AST comparison against BASE found
  **25 original test files /171 original declarations /0 removed tests**, with no per-file assertion-count decrease; those
  declarations expand to the original 210 runtime cases, all retained in final 241-case coverage.
- Synced the existing API/components/store READMEs and `docs/permissions.md`. No new user-facing copy was needed, so locale
  files and the approved outcome DTO were unchanged; their original locale/DTO/terminal tests were rerun.

### Actual RED commands, outputs and recorded exit codes

All commands ran in `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend` with
existing node_modules/Node/npm. Every final evidence log below ends with its actual `SHELL_EXIT` marker. Logs live under
`.superpowers/sdd/2026-10-23-capa-outcome-review/` in this workspace and are not committed source files.

New regressions first failed against the live unfixed implementation. To preserve explicit exit-code evidence after writing
all regression cases, a second deterministic mutation RED restored **only** the ten implicated production files from fix
BASE `16dff517` (not the whole worktree, no stash/reset); current tests, API-compatible optional signatures and the ownership
registry stayed in place. Each RED ran in a fresh process. A `finally` block restored every fixed source byte and verified
`FIXED_SOURCE_BYTE_RESTORE=PASS` before any final GREEN. This is failure-proof regression evidence, not production execution.

```bash
npx vitest run src/components/capa/CapaChildOwnership.test.tsx src/pages/capa/CAPADetailPage.test.tsx -t 'same-identity material reload|cancels the entire|pending D4 adoption|pending verification|aborts both|D7 confirmation|DocGate load|D3 import|cancelled actual beforeAdopt'
```

`task5-fix-r1-i1-i3-red.log`: **2 files failed /15 failed /60 selected-out /SHELL_EXIT=1**. The actual prerequisite resolved
`{resolved:true}` instead of rejecting for both late success and denial; children sent old adoption POSTs or reloaded/toasted,
verification/source signals were absent, doc-gate/D3/D7 continued, and both knowledge operations were aborted by review reload.

The isolated real-transport commands were:

```bash
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual /auth/me late success'
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual refresh late success'
npx vitest run src/api/client.capaOwnership.test.ts -t 'actual refresh late failure'
npx vitest run src/api/client.capaOwnership.test.ts -t 'an old child signal'
npx vitest run src/components/capa/useAIDraft.test.ts -t 'registers the complete draft lifecycle'
```

| RED log | Actual failure and output |
|---|---|
| `task5-fix-r1-auth-me-red.log` | A's user/permissions replaced B after pending real `/auth/me`; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-refresh-success-red.log` | Store token became `A-new` instead of `B-access`; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-refresh-failure-red.log` | B's user became null on A refresh failure; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-stale-post-red.log` | Old child POST reached B transport instead of rejecting; **1 failed /9 selected-out /SHELL_EXIT=1**. |
| `task5-fix-r1-draft-red.log` | Draft's signal had no registered owner (`undefined` rather than current=true); **1 failed /9 selected-out /SHELL_EXIT=1**. |

GREEN used the identical I1/I3 selection command: `task5-fix-r1-i1-i3-green.log` → **2 files /15 passed /60 selected-out /
SHELL_EXIT=0**. I2 plus existing exact private-route controls used:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts
```

`task5-fix-r1-i2-green.log` → **2 files /18 passed /SHELL_EXIT=0**. No selection skip is counted as acceptance in the complete
final run. The actual Axios adapter tests are transport-level unit evidence, **not** browser, backend/provider or live JWT evidence.

### Intermediate attempts retained, not silently counted as success

- `task5-fix-i1-i3-red.log`: initial 13-case behavioral RED after correcting a test-only D7 locator (`d7-confirm`, not
  `d7-confirm-0`). `task5-fix-i1-i3-green1.log`: the corresponding 13 passed with 55 selected-out after child/I3 fixes.
- `task5-fix-i2-red.log`: first combined unfixed interceptor run had 5 failures, including a timeout/global-refresh-flag cascade
  after the late auth denial. Those dependent failures are **not** counted as five independent defects. Subsequent isolated
  `task5-fix-i2-refresh-success-red.log` and `task5-fix-i2-refresh-failure-red.log` showed actual token overwrite/logout, then
  `task5-fix-i2-green1.log` had 13 passed including old private-route guards. Final marker-bearing isolated REDs above are authoritative.
- `task5-fix-expanded1.log`: **18 failed /210 passed**. Seventeen were old exact-call assertions needing the new signal while
  preserving payload/provenance; the other was a real new D3 selection spinner caused by unnecessary run-list refetch. Fixed
  both, without dropping cases: `task5-fix-expanded2.log` → **27 files /228 passed**.
- `task5-fix-draft-red.log`: **1 failed /9 passed** for missing transport ownership. `task5-fix-prerequisite-red.log`: BASE-only
  method mutation gave **2 failed /57 selected-out /RED_EXIT=1** for wrongly successful cancelled prerequisites.
  `task5-fix-prerequisite-green.log`: page + draft **69 passed** after actual method and registered draft fixes.
- `task5-fix-extra-green.log`: **35 passed** for additional source/conclusion PATCH, D5 late denial, report switch, D7 auto-fill,
  stored-credential transitions and normal unrelated queued refresh behavior. `task5-fix-last-focus.log`: **20 passed** after
  final stale pre-transport POST and draft reset checks. These are intermediate counts, not replacements for the final suite.
- Earlier no-diagnostic tsc attempts (`task5-fix-ts1.log` and tool output) are not relied on for shell success; the final
  explicit marker-bearing compiler/build logs below are the authoritative results. Tool-verifier refusals of compound shell
  forms did not execute tests; a zsh runner executed the exact commands and persisted their real shell statuses instead.

### Final complete verification AFTER the last production/test change

```bash
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

| Exact final evidence log | Actual output |
|---|---|
| `task5-fix-r1-final-vitest.log` | **27 files passed /241 passed /0 failed /0 skipped /no unhandled errors**, start 23:54:27, duration 13.82s, **SHELL_EXIT=0**. Original 210 cases +31 new regressions. |
| `task5-fix-r1-final-tsc.log` | `npx tsc --noEmit`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r1-final-build.log` | `tsc -b && vite build`; production Vite 5.4.21 built in **6.43s**, CAPADetailPage 103.87kB /30.48kB gzip; **SHELL_EXIT=0**. |
| `task5-fix-r1-final-e2e-tsc.log` | `npx tsc --noEmit -p tsconfig.e2e.json`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r1-preservation.log` | `BASE_TEST_FILES=25; ORIGINAL_TEST_DECLARATIONS=171; REMOVED_TESTS=0; ASSERTION_COUNTS_NOT_DECREASED=PASS; PROCESS_EXIT=0`. |
| `task5-fix-r1-diff-check.log` | `git diff --check`; no whitespace errors; **PROCESS_EXIT=0**. |

The installed Node/npm and dependencies were reused; no packages or test configuration changed. Existing Vite/react-babel
esbuild→oxc notices, Node experimental localStorage notices, jsdom pseudo-element getComputedStyle diagnostics and the mixed
static/dynamic `api/version.ts` production chunk warning remain visible. They were not suppressed or converted to skips.
Final full selection has no xfail/xpass or omitted original assertions; this is not a historical backend/full-system baseline.

### Exact fix files (relative to BASE `16dff517`)

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/auth.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capa.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/capaRequestOwnership.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.capaOwnership.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/fmea.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaChildOwnership.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D3ContainmentPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D3ContainmentPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4VerificationCard.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D4VerificationCard.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D5RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D5RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D7RecPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/D7RecPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/DocGatePanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/__tests__/D4VerificationCard.cause.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useAIDraft.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/useCapaViewRequests.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/store/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/store/authStore.ts
```

### Remaining limits and next steps

- No unresolved I1/I2/I3 blocker was identified in this batch's self-review. Independent coordinator gates remain pending;
  this report does not self-approve the fixes. Review only `16dff517..` the final local fix head.
- The optional owner is deliberately limited to explicitly owned Task 5 CAPA requests. Unowned routes' existing global
  refresh/queue behavior is retained, not claimed fixed or redesigned. Exact private-route controls and backend authority remain.
- Cancellation cannot undo a POST already accepted by the server. It prevents old continuation/publication and prohibits
  replay under B; the existing D8 uncertainty path still queries actual state without auto replay. DTO/revision/round binding,
  terminal/admin core freeze, unreviewed closed supplement, archive freeze, escaped metadata and no private result persistence
  remain unchanged and covered by the original tests.
- No real browser, provider, database or production acceptance was run or claimed. Those remain separately authorized Task 7
  and final-system gates. No later task or business approval/self policy was started.
- Authorized local commit subject: `fix(capa): fence child actions and auth side effects`. No push/merge/deploy.


## Task 5 fix round 2/5 — F1 owned-refresh subscriber settlement (2026-10-27)

### Status, received finding and root cause

**F1 fix batch implemented and verified locally against FIX_BASE `e79be478`; independent scoped re-review remains
required. Task 5 is NOT declared complete or accepted.** The coordinator independently marked prior I1/I2/I3 addressed;
this batch does not reopen them or change their ownership/session fences. No plan-mandated conflict arose.

Reviewer finding (substantive text preserved): **Cancelling the owned refresh initiator strands unrelated refresh
subscribers.** An owned CAPA 401 starts the shared refresh; unrelated unowned 401s subscribe; navigation or selection
disposes the CAPA lifetime and aborts its refresh signal; the scoped store returns null; the interceptor clears
`isRefreshing` and rejects only the initiating CAPA request. A null token never calls the success-only subscriber callbacks,
and the interceptor waiting Promise has no rejection path, so unrelated requests can remain pending indefinitely.
Adapter timeout does not bound that interceptor Promise. This was a fix-induced same-session cancellation regression,
not authorization to audit or redesign unrelated failed-refresh policy.

Systematic debugging/TDD steps were followed: focused CodeGraph context first (no useful current frontend symbols),
precise reads of actual `client.ts`, `authStore.ts`, ownership adapter tests, comparison with the working valid-refresh
queue test, deterministic deferred-adapter RED, then a single small correction and covering/final verification. No
production change preceded the new failing regression. No mutation RED or guessed backend response was needed this round.

### Minimal correction and self-review

- The existing subscriber callback now accepts a token **or null**. The helper is named `settleRefreshSubscribers` to reflect
  both outcomes; it still drains the same existing subscriber list. A real token retains the existing success/replay behavior.
- An owned refresh that returns null or no longer matches installed credentials explicitly settles that list with null,
  including the owned initiator exception path. Each queued request then rejects with **its own original 401 error**, without
  replay or a new automatic refresh. No null path is added to unrelated unowned-initiated refresh behavior.
- The obsolete initiating CAPA action still rejects and never replays. Existing owner checks before auth effects, signal
  propagation, store token-install/logout fences, private-route exclusions and backend authority are unchanged. `authStore.ts`,
  child/page hooks and all decision/DTO/terminal code were not modified in this round.
- Tests queue unrelated requests **before** cancelling the initiating view. Two same-session cases cover navigation/unmount
  and selection invalidation, multiple subscribers, retained A credentials, explicit new-request recovery and proof that drained
  subscribers/obsolete CAPA do not replay on a later successful refresh. Two replacement-session cases cover late refresh success
  and failure, waiter rejection, unchanged B credentials/user and no old A replay.
- Self-review traced null, obsolete-token, exception and valid-token branches and queue drain ordering; checked each waiter
  uses its own error; checked no automatic CAPA replay or stale auth mutation was introduced. The previous successful-refresh
  queue test and all prior actual adapter/session/privacy tests remain intact. This is not a blanket auth/refresh redesign.
- Synced existing API README and permissions documentation. No new UI text/policy was added, so no locale changes were needed.
  All 241 prior tests and their payload/provenance assertions remain unchanged; the adapter regression file was append-only.
  AST preservation against `e79be478` reports **27 original files /191 declarations /0 removed tests**, and no per-file
  assertion-count decrease. Those original declarations expand to the prior 241 runtime cases.

### Actual RED / GREEN evidence

Commands ran from `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend` using
existing Node/npm/node_modules. Full logs below are retained under
`.superpowers/sdd/2026-10-23-capa-outcome-review/`; every test/compiler/build log has its real persisted shell exit marker.

RED, before production changes:

```bash
npx vitest run src/api/client.capaOwnership.test.ts -t 'owned refresh cancellation|owned refresh replacement'
```

`task5-fix-r2-red.log` actual result: **1 file failed /4 failed /10 selected-out /SHELL_EXIT=1**. Navigation and selection
left both subscriber states `pending` instead of `rejected`; replacement success/failure left `settled=false`. The bounded
`waitFor` assertions expose non-settlement, not a hidden five-second test-runner timeout or an adapter/network fixture error.
The real interceptor, real refresh wrapper/store and deliberately deferred adapter were used; no mocked page API rejection
was substituted for the queue race.

First GREEN:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts
```

`task5-fix-r2-adapter-green.log`: **2 files /22 passed /SHELL_EXIT=0**, including all four new regressions, previous real
session-corruption cases and exact private-route controls. No global queue state reset or diagnostic suppression was added.

### Final checks after the LAST source/test change

Covering adapter/store/child/page/hook command:

```bash
npx vitest run src/api/client.capaOwnership.test.ts src/api/client.agentTasks.test.ts src/components/capa/CapaChildOwnership.test.tsx src/components/capa/useAIDraft.test.ts src/pages/capa/CAPADetailPage.test.tsx
```

`task5-fix-r2-covering-green.log`: **5 files /107 passed**, start 00:32:35, duration 6.98s, **SHELL_EXIT=0**.
The store helper is exercised through the actual Axios transport/real store path, not a fake store implementation.

Complete prior targeted set and all required final compiler/build commands:

```bash
npx vitest run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api src/locales/capa-ppt.i18n.test.ts
npx tsc --noEmit
npm run build
npx tsc --noEmit -p tsconfig.e2e.json
```

| Final evidence log | Actual output / exit |
|---|---|
| `task5-fix-r2-final-vitest.log` | **27 files passed /245 passed** (all prior 241 +4 new); start 00:32:42; duration 12.57s; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-tsc.log` | `npx tsc --noEmit`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-build.log` | `tsc -b && vite build`; production build **6.43s**; CAPADetailPage 103.87kB /30.49kB gzip; **SHELL_EXIT=0**. |
| `task5-fix-r2-final-e2e-tsc.log` | `npx tsc --noEmit -p tsconfig.e2e.json`; no compiler diagnostics; **SHELL_EXIT=0**. |
| `task5-fix-r2-preservation.log` | `BASE_TEST_FILES=27; ORIGINAL_TEST_DECLARATIONS=191; REMOVED_TESTS=0; ASSERTION_COUNTS_NOT_DECREASED=PASS; PROCESS_EXIT=0`. |
| `task5-fix-r2-diff-check.log` | `git diff --check`; no whitespace diagnostics; **PROCESS_EXIT=0**. |

The complete final run has **0 failures, 0 skips and no unhandled errors**. The RED selection's ten selected-out cases were
not omitted from final acceptance. Existing Vite/react-babel esbuild→oxc, experimental localStorage and jsdom pseudo-element
getComputedStyle diagnostics and the production mixed static/dynamic `api/version.ts` chunk warning remain visible. No
assertion was removed, warning silenced, dependency installed or configuration changed. No historical suite count is used.

### Exact round-2 changed files

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/client.capaOwnership.test.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/api/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
```

### Limits, concerns and next step

- No unresolved F1 blocker was identified in this batch's self-review. **Independent scoped re-review follows**; this is not
  a claim that both gates passed or Task 5 is complete. Prior I1/I2/I3 fences and decision/terminal/metadata guarantees remain.
- Abandoned-refresh waiters now reject; they do not transparently retry. Recovery is an explicit new request subject to current
  session/server authorization. This does not promise recovery from every real server-side refresh rotation or fix pre-existing
  unowned failed-refresh policy; neither is part of this scoped F1 correction.
- These are adapter/component/static/build checks, not real browser/provider/DB evidence. Task 7 remains separately authorized.
  No backend, provider, DB, infrastructure, browser, full baseline, later-task, global auth redesign or business/self policy work
  was performed. No push/merge/deploy.
- Authorized local commit subject: `fix(capa): settle waiters when owned refresh is cancelled`.

## Task 6 implementation report — unreviewed closure supplements (independent review pending)

### Scope, assumptions and implementation

- Worktree: `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel`.
  Starting HEAD: `8187f6a9`. Requirements read in order: task-6-brief.md, then task-6-context.md.
  Only Task 6 is implemented; this report does not change the controller ledger or grant acceptance.
- Used focused CodeGraph context/explore before editing and precise source/test reads. Read only the
  relevant status/decision tails, not the full plan/history/PROGRESS. Used TDD, systematic debugging
  and verification-before-completion. No child agents or independent-review claims.
- Exact provenance literals: KnowledgeEntry `fields.closure_review_scope=unreviewed_supplement`;
  D8 lesson tag `review_scope:unreviewed_supplement`, generated once on insert/upsert and returned
  lesson objects. D7 extraction does not receive this tag or any approved classification.
- Existing summary prompt explicitly calls closure an unreviewed supplement, not an approved root
  cause or verified outcome, without expanding business source fields or adding a provider call.
  Knowledge embedding text labels closure and warns about mixed summaries; original stored closure
  and lesson_summary values remain intact, preserving all original assertions and consumer contracts.
- Knowledge list/detail projections expose nullable closure_review_scope; detail copies fields before
  adding the marker for CAPA closure, including legacy rows. No ORM/database read-side backfill.
  Existing source type, classification, tags, authorization and factory/product-line predicates remain.
- Lesson retrieval selects source_d_step, adds D8 review_scope metadata and a Chinese unreviewed
  warning to content. Knowledge retrieval selects source_type and adds closure_review_scope plus an
  explicit warning for CAPA closure, including legacy summary/embedding/chunk text fallbacks.
  Text-only D4/D5 serialization retains the warning. The existing 500-character bound is retained.
- Supplement metadata selects ONLY operated_by and operated_at from the report/factory's latest
  UPDATE containing d8_closure, ordered by operated_at then log_id. It does not load private audit
  bodies or infer responsibility from CAPA.updated_at/created_by. Missing audit/actor stays null.
  Real update_capa UPDATE audits now stamp capa.factory_id: previously the scoped reader could not
  see those production audits. Historical null-factory audit rows are not inferred or backfilled.
- Existing Task 5 panel source is unchanged. Added rendered tests for actual actor/time values, null
  fallback (`— · —`), unreviewed label and separation from reviewed core.
- Real supplement test uses Task 4 production HTTP approval producer and production reader with real
  source snapshots; only external provider responses are deterministic test fixtures. It compares the
  receipt audit, revision, round, decision, core, source versions and D7 lessons before/after editing.
  Legacy is explicitly legacy_unversioned, never a fabricated verified receipt. Mixed PUT rejection,
  archive freeze, relevant-only metadata, unknown actor, private audit-body isolation and failed
  delete/rebuild restoring tags/outbox/audits are covered. Existing assertions/declarations remain.
- No terminal/auth/core/HMAC or source-version policy changes, migrations/model columns, new
  dependencies, live provider calls, browser run, UI redesign, install, full make-check, DB reset,
  reseed/recreation, infrastructure recovery, settings/permissions changes, push/merge/deploy.
  All pytest runs used the existing registered run-owned.py pytest mode. No private profile, URL,
  secret or credential output. Shell complexity refusals made no changes; edits used absolute-path
  file tools where the shell could not verify the operation. No denied operation was forced.

### RED, setup distinction, focused GREEN and self-review correction

Commands below ran from the worktree root. Backend command prefix (verbatim):

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest
```

1. Initial RED: prefix + `tests/capa/test_capa_outcome_supplement.py tests/capa/test_knowledge_api.py tests/recommendation/test_capa_lesson_embedding_chain.py tests/services/test_knowledge_entry_source.py tests/capa/test_knowledge_sink.py -q`.
   Result: **10 failed, 38 passed, 3 warnings**, exit **1**, 4.80 s. Log:
   `.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261026T164527480658.log`.
   Expected defects, NOT setup failures: missing audit responsibility for actual supplement saves;
   metadata unnecessarily subject to private changed_fields body-size limit; missing knowledge scope
   marker; missing D8 tag; legacy recommendation metadata/text provenance absent. Real approval was
   produced and read as verified before the expected missing-responsibility assertion failed.
2. Before implementation, revised only new tests to preserve existing raw closure/summary contracts
   (rather than prefixing stored source fields); provenance belongs to projections/derived text.
   RED: prefix + `tests/capa/test_knowledge_api.py tests/capa/test_knowledge_sink.py -k 'legacy_closure_projection or marks_closure' -q`.
   Result: **2 failed, 2 passed, 18 deselected, 3 warnings**, exit **1**, 0.37 s; both failures are the
   missing closure_review_scope. Log `focused-20261026T164656696324.log` in the same SDD directory.
3. Focused GREEN: same command as initial RED after implementation.
   Result: **48 passed, 3 warnings**, exit **0**, 4.75 s.
   Log `focused-20261026T164906190689.log` in the same SDD directory.
4. Self-review caught prefix growth beyond the existing recommendation 500-character cap. Extended
   new summary/embedding/chunk fallback cases with long text and the existing bound assertion.
   RED: prefix + `tests/services/test_knowledge_entry_source.py -k legacy_capa_closure -q`.
   Result: **3 failed, 14 deselected, 3 warnings**, exit **1**, 0.33 s; actual length 537 > 500.
   Log `focused-20261026T165108840949.log` in the same SDD directory. Fixed by retaining the warning
   at the beginning and applying the original cap to the final content; final covering run below.
5. Initial panel characterization: `npm --prefix frontend test -- --run src/components/capa/CapaOutcomeReviewPanel.test.tsx`.
   Result **20 passed**, exit **0**, 2.18 s, confirming no panel implementation edit is needed.
   Completed task output `b2tb4v4cv.output`; final persistent frontend logs are listed below.

### Final covering checks (after the last source change)

Full affected backend command (verbatim, worktree root; only ordinary registered pytest mode):

```bash
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/capa/test_knowledge_api.py tests/capa/test_knowledge_sink.py tests/capa/test_capa_outcome_supplement.py tests/capa/test_capa_outcome_api.py tests/capa/test_capa_outcome_boundaries.py tests/capa/test_capa_outcome_d7.py tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_outcome_namespace.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_review_fixes.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_review_guard.py tests/capa/test_capa_review_source_guard.py tests/capa/test_capa_reviewed_writes.py tests/capa/test_capa_review_concurrency.py tests/capa/test_capa_post_review_fixes.py tests/capa/test_capa_update_freeze.py tests/capa/test_capa_advance_flow.py tests/capa/test_capa_advance_permission.py tests/capa/test_capa_d7_gate.py tests/capa/test_capa_d7_action_service.py tests/capa/test_capa_d7_api.py tests/capa/test_capa_d7_prevention_linkage.py tests/capa/test_capa_doc_gate_api.py tests/capa/test_capa_doc_gate_freshness.py tests/capa/test_capa_doc_gate_regression.py tests/capa/test_capa_verification_api.py tests/capa/test_capa_verification_conclusion.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_source_ref.py tests/capa/test_capa_api_d4_d5.py tests/capa/test_capa_link_fmea_linkage.py tests/capa/test_advance_warning.py tests/recommendation tests/recommendations tests/services/test_knowledge_entry_source.py tests/test_embedding_sync_worker.py tests/test_lessons_learned.py tests/test_capa_recommendation.py tests/test_capa_supplier_id.py tests/test_capa_advance_supplier_risk_trigger.py --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py -q -ra
```

Actual output/receipt:

```text
CHECK_COMPLETE: mode=pytest; exit_code=0; log=/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/focused-20261026T165335357306.log
821 passed, 3 warnings in 133.83s (0:02:13)
[exited with code 0]
```

- Includes final long-text bound regressions, detailed failed-rebuild tags/outbox/audit restoration,
  original D7/D8 lesson embedding/retrieval chain, knowledge fail-closed/concurrency/isolation tests,
  real production approval/rejection and historical reader, tenant namespace/current authority,
  immutable source versions and terminal/concurrent material writes.
- No skip, xfail or xpass in this selected run. Both Makefile graph exclusions retained. This is
  the actual Task 6 affected-set result, not a full baseline or the historical 2999-pass receipt.
- Backend warnings: three PydanticDeprecatedSince20 class-based Config deprecations; not suppressed.

Frontend commands and exact result wrappers (worktree root):

```bash
npm --prefix frontend test -- --run src/components/capa/CapaOutcomeReviewPanel.test.tsx src/pages/capa/CAPADetailPage.test.tsx src/api/capa.test.ts src/api/client.capaOwnership.test.ts src/components/capa/CapaChildOwnership.test.tsx > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log 2>&1; result=$?; tail -n 45 .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
npm --prefix frontend exec -- tsc --noEmit -p frontend/tsconfig.json > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log 2>&1; result=$?; cat .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
npm --prefix frontend run build > .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log 2>&1; result=$?; tail -n 35 .superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log; printf '\nEXIT_CODE=%s\n' "$result"; exit "$result"
```

Actual results:

```text
Test Files  5 passed (5)
Tests       121 passed (121)
Duration    8.74s
EXIT_CODE=0

npm notice run 'tsc' --noEmit -p frontend/tsconfig.json
EXIT_CODE=0

npm notice run tsc -b && vite build
vite v5.4.21 building for production...
✓ 6848 modules transformed.
✓ built in 7.12s
EXIT_CODE=0
```

Persistent frontend log paths:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-tests.log
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-types.log
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task-6-frontend-build.log
```

Observed frontend warnings (not suppressed): Vite React plugin esbuild/optimizeDeps.esbuildOptions
API deprecations and esbuild/oxc coexistence notice; Node localStorage ExperimentalWarning;
jsdom getComputedStyle pseudo-element not implemented messages. Build warns api/version.ts has
both dynamic and static imports and will not move into a separate chunk. Types emitted no warning.
No browser/provider behavior or full-repository baseline is inferred from these checks.

### Changed files, final self-review and remaining gates

All changed file paths:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/api/knowledge.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/schemas/knowledge.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_lessons_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_outcome_review.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/capa_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/knowledge_sink_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/recommendation_sources_extra.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_outcome_supplement.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_knowledge_api.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_knowledge_sink.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/recommendation/test_capa_lesson_embedding_chain.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/services/test_knowledge_entry_source.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/permissions.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
```

- Self-reviewed diff against Task 6 brief/context: exact markers, negative non-CAPA/no-closure
  projection cases, read-only legacy projections, text-only warnings, 500-character cap, unchanged
  D7 lessons/core/source references and approval receipt, scoped audit-only responsibility/nulls,
  private audit-body exclusion, original cleanup/savepoint/outbox failure ordering and UI fallback.
- All pre-existing test declarations/assertions are retained (only additions in existing tests).
  No source edits in the Task 5 panel, terminal/auth/core/HMAC policy, model/migration or provider
  adapter. Documentation is synchronized with actual implementation, not prospective features.
- `git diff --check` is clean. Local commit is authorized for this phase, subject:
  `fix(capa): distinguish unreviewed closure supplements` (commit containing this report).
- No unresolved Task 6 implementation defect identified in self-review. Non-fatal observed warnings
  remain as above. Old null-factory UPDATE audits deliberately remain unattributed; no inferred
  responsibility/backfill. This self-review and test result are NOT independent task acceptance.
- Next: controller's independent Task 6 spec/quality review. Live provider/browser/full make-check
  and later-task acceptance are separate gates and were deliberately not run here. No later task
  implemented; no controller ledger changed, push, merge or deployment.

## Task 7 report — genuine employee HTTP, tenant, provider and Chromium outcome review

**Status: BLOCKED, not Task7 done or independently accepted.** Base `f6198232`;
Tasks1–6 were not restarted. This complete named report is appended here instead
of creating a standalone report Markdown file, following the session restriction.
Local commit authorized: `test(capa): verify outcome review and post-close immutability`
(the commit containing this report). No push, merge, deploy or controller-ledger edit.

### Requirements, assumptions and implementation

- Read only Task7 brief/context plus focused existing interfaces, the Task4 Minor
  summary and the tail of this progress file. CodeGraph context returned unrelated
  symbols; its focused file query reproduced `database disk image is malformed`.
  Used the permitted bounded native discovery/precise reads. No index repair,
  rebuild, configuration/security modification or child agents.
- Existing registered random `_test` DB and installed interpreter/Chromium only.
  Real public migrations were reused, not recreated/reset/reseeded; read-only final
  witness finds public revision `20261009_agent_task_attachments`. Every run-owned
  business tenant executes real tenant migrations through `tv005_agent_task_attachments`.
  The current container fingerprint, owner label, loopback host/port, current DB/user
  are checked before lifecycle work; container ownership is checked again at cleanup.
- `owned_outcome_server` exposes `app`, `base_url`, `tenant_slug`, `report_id`,
  `editor_login`, `approver_login`, `session_factory`, `binding`, `nonce` plus scoped
  negative-test identities. Sessions are real binding-aware TenantSessions with
  real commits. New FastAPI app mounts actual auth/CAPA/product-line/FMEA/CP/knowledge
  routers, TenantContextMiddleware and narrow production outcome error handlers.
  No normal get_db/auth/permission/commit replacement. The existing login limiter's
  storage is isolated for the fixture, without changing its threshold/check.
- Two actual business tenants contain identical protection UUIDs but distinguishable
  material. Current roles are field_qe EDIT and manager APPROVE; terminal write matrix
  also logs in the real bootstrap admin. Synthetic legacy terminal records are
  **protection-only**, without fabricated approval receipts or document gates.
  Their verification rows are synthetic terminal material, not positive gate proof.
  An unbound legacy FMEA source correctly cannot reconstruct an approval version.
- The positive report is created over normal HTTP at D1. Executable live helpers
  cover D1/D2/D3 import and provider, manual containment execution, current-root-cause
  verification, implemented D5 measures, exact D6 `实施后复测合格`, real D7 dispositions,
  real D8 impact and decision/audit services, then pending. No D4/D5/D6 approval nodes.
  Empty-source and new-controlled-document cases are separate: the latter creates
  FMEA/CP over actual HTTP, publishes real versions and requires the actual provider
  to identify both new documents and the actual document audit to pass. Unexpected
  provider output is failure, never permission to fabricate a passed gate.
- Live pending HTTP assertions cover EDIT approval403, D6/verification stale409,
  mandatory rejection reason, real return to D7/resubmission, old-round409, and current
  FMEA/PLANNING source denials with no partial DTO or closure side effects. These
  downstream assertions are implemented but **not executed past D3** in this session.
- Browser spec uses normal UI login; its deliberate same-document identity switch
  calls the production auth-store `login` action with real credentials, not setState
  or injected APPROVE authority. A nonce-controlled window holds an actual completed
  authorized server response, not a mocked DTO/query/lock. Old request cancellation
  and fresh employee material are asserted without browser sleeps. Nonce endpoints
  only change real permissions/windows or read owned assertion data.
- Browser approval captures actual outgoing revision/round and compares it to the
  displayed server metadata. Required core/status/approve testids were added without
  removing existing data-e2e selectors; immutable core gets `data-readonly=true`.
  Positive closure invokes untouched production advance/knowledge/lateral services.
  An empty real lateral result is not claimed as a lateral provider invocation.
- Direct HTTP terminal matrix checks PUT/mixed PUT/adoption/create+patch verification/
  D7/link writes409 across EDIT/APPROVE/ADMIN with unchanged material, audit, embedding,
  knowledge, lateral and outbox snapshots. Legitimate closed supplement remains
  unreviewed and separate from core; archive is real HTTP. Archive-only supplement400
  versus core/mixed409 is preserved. Factory/PL/source denial precedes lock disclosure.
- Deferred rejection-specific Task4 source-row-wait Minor is now covered by three
  added rejection variants (source version, current planning privilege, current PL
  scope), each using actual PostgreSQL wait/blocker witnesses and unchanged original
  approval cases. Existing Task4 fixture/provider tests remain fixture evidence;
  their synthetic gate/closure collaborators are **not** live-provider acceptance.
- Controlled runner has explicit `live`/`acceptance` opt-in and loads only an existing
  authorized worktree `.env.e2e` whitelist: LLM_PROVIDER/API_KEY/MODEL/BASE_URL/TIMEOUT.
  No shell evaluation, interpolation, arbitrary environment passthrough or ambient
  Anthropic/OpenAI credentials/proxies. Invalid/missing test profile never falls
  back to ambient credentials. Node/Vite/browser get a separate safe whitelist and
  disposable employee credentials, never provider/DB credentials. Ordinary private
  run-owned.py clears keys and is not claimed as genuine live acceptance.
- Minimal integration defects discovered by real tests were fixed, rather than
  bypassed: version hashing qualifies `public.digest`, matching the existing tenant
  trigger without widening search_path; CP create response uses existing eager-loaded
  `get_control_plan`, avoiding post-commit MissingGreenlet on `items`. No migration,
  provider adapter, production advance, knowledge or lateral implementation changed.

### RED / GREEN / systematic debugging evidence

All paths below are under the isolated worktree; recorded exit codes are real.

1. Frontend immutable-core RED: two new terminal attribute tests failed because
   data-readonly was absent (20 existing tests passed), exit1. Minimal attribute
   addition GREEN: 22 passed, exit0. Logs:
   `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-readonly-red.log`
   and `task7-readonly-green.log` in the same directory.
2. Runner first RED was an explicitly disclosed collection failure (missing runner
   module), not proof of a production behavior defect:
   `focused-20261026T171226247353.log`, exit2. Genuine behavioral RED for invalid
   controlled timeout then failed `authorized_test_profile != invalid_test_profile`:
   `focused-20261026T172829983735.log`, exit1, 1 failed/3 passed. Timeout validation
   GREEN is included in the final full 35-test gate. Initial controlled API runner
   startup also exposed invalid empty numeric LLM_TIMEOUT (exit4,
   task7-api-20261026T171709712526.log); explicit safe timeout30 corrected that
   harness input without provider credentials or an authority bypass.
3. Genuine tenant setup RED: `focused-20261026T171502216291.log`, exit1, two setup
   errors `UndefinedFunctionError: function digest(text, unknown) does not exist`.
   Traced strict tenant search_path to the unqualified service call; the reviewed
   tenant trigger already qualifies public.digest. Minimal qualification plus
   independent real FMEA/CP producer/verifier tests are GREEN in the final API gate;
   the original version/control-plan regressions also pass.
4. Subsequent fixture mistakes were corrected, not counted as production RED:
   legacy source without an approval binding must conflict, not return200; link-fmea
   takes query parameters, not a JSON fmea_id. The terminal readable fixture and
   unbound-source negative are now separate, without manufacturing receipts/gates.
5. First actual Chromium run failed on an incorrect test locale assumption:
   `task7-browser-20261026T172320369036.log`, exit1. Accessibility evidence showed
   English `Reload review materials`; app stores language in `openqms_locale`, not
   i18nextLng. Corrected only the test preference. Genuine rerun passed, including
   actual held-response cancellation and same-document employee login.
6. Actual controlled-document HTTP RED exposed CP create500. Real exception was
   Pydantic attribute extraction -> MissingGreenlet for items, not an authority or
   provider denial. Provider-free isolated RED:
   `focused-20261026T173536652179.log`, exit1. Existing eager-loading service reuse
   GREEN: `focused-20261026T173603845907.log`, exit0, 1 passed. This regression is
   also part of the final complete API gate. No DTO/approval/gate fixture replaced it.

### Final commands, actual output and persistent exit markers

Working directory for all commands:
`/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel`.
Commands with the private runner enter this worktree's backend only. The allowed
main-checkout Python path is used solely as executable, not as a code/config source.

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python backend/tests/e2e/capa_outcome_runner.py api
TASK7_EXIT: mode=api; code=0; provider_config=not_requested
35 passed, 5 warnings in 38.17s

/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python backend/tests/e2e/capa_outcome_runner.py acceptance
TASK7_EXIT: mode=acceptance; code=1; provider_config=missing_test_profile
2 failed, 1 passed, 5 warnings in 23.38s
CHROMIUM_REAL: scenario=terminal protection; exit=0; 1 passed; retries=0; workers=1
LIVE_PROVIDER_BLOCKED: config=missing_test_profile; D3 report_status=blocked; report_error=None
```

`api` executes the entire requested outcome API/concurrency files plus runner tests.
`acceptance` executes the entire browser test file with no -k, no skips and no
xfail/xpass/deselection. Both live cases fail at the genuine D3 provider gate;
no downstream assertion is silently counted as passing. Final controlled runner
commands include `-q --tb=short -rA`; their result JSON records the full subprocess
argv and real exit code. Final logs/result JSON:

- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-api-20261026T175333395663.log`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-api-20261026T175333395663-result.json`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-acceptance-20261026T175414927310.log`
- `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-acceptance-20261026T175414927310-result.json`

Additional affected regression command (ordinary cleared-key runner, fixture/service
proof only, no live-provider claim):

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/run-owned.py pytest tests/fmea/test_fmea_version_factory_id.py tests/test_control_plan_item_id_stability.py tests/test_control_plan_uuid_dedup.py tests/capa/test_capa_outcome_review.py tests/capa/test_capa_outcome_sources.py tests/capa/test_capa_outcome_decision.py tests/capa/test_capa_outcome_supplement.py -q --tb=short
104 passed, 3 warnings in 31.75s; exit0
```

Persistent log/result: `focused-20261026T174139383746.log` and matching
`focused-20261026T174139383746-result.json` under the same absolute evidence directory.

Frontend commands and actual results:

```text
(cd frontend && node node_modules/vitest/vitest.mjs run src/components/capa src/pages/capa/CAPADetailPage.test.tsx src/api/capa.test.ts src/api/client.capaOwnership.test.ts)
20 files / 221 tests passed, 11.77s; EXIT_CODE=0
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
EXIT_CODE=0
node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.e2e.json
EXIT_CODE=0
(cd frontend && npm run build)
built in 6.48s; EXIT_CODE=0
```

Logs with persistent real EXIT_CODE lines:
`task7-final-frontend-tests.log`, `task7-final-frontend-types.log`,
`task7-final-e2e-types.log`, `task7-final-frontend-build.log`, all under
`/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/`.

Warnings were retained: 3 baseline Pydantic class-Config deprecations; websockets
legacy/server protocol deprecations in actual HTTP gates; Node localStorage
ExperimentalWarning, jsdom pseudo-element getComputedStyle messages, React/Vite
esbuild/optimizeDeps deprecations in frontend tests; static+dynamic api/version.ts
import warning in build. Earlier Chromium failure also recorded Node module.register
deprecations. No final skip/xfail/xpass; no historical 2999-test baseline was claimed.
Full make check and story/skill freeze are deliberately deferred to Task8.

### Resources, teardown and handling concern

- Only registered PG container `openqms_capa_outcome_pg_20261025_92f8027e`, its registered
  volume and two registered `_test` databases were used. No new DB, reset, reseed,
  recreation, migration baseline replacement, production/shared/seed DB or ClamAV
  operation. The application DB was not used for business test writes.
- Per-run journals identify only owned random tenant UUIDs/slugs/schemas, actual
  cleanup and closed sockets. No password, provider key/URL, access/refresh token or
  harness control nonce is stored in those journals. Only pre-allocated run slugs
  are cleaned, including a failed provisioning attempt; unrelated tenants are not
  enumerated for deletion. Core container/volume/databases remain for Task8.
- Final read-only resource witness:
  `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/task7-resource-check.py`
  exited0: container ID/owner verified, registered volume and both databases preserved,
  remaining outcome tenants=0; 28 tenant teardown journals verified; 2 Node
  teardown journal verified. Actual final Node journal records Vite port54298,
  Vite PID74676 exit0, Playwright PID74678 exit0. No PID from a journal is killed or
  reused as cleanup authority.
- Persistent witness:
  `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-final-resources.json`.
  Final Node evidence: `task7-node-resources-9bcdd21ca3bf42bc9ca39e7b8b1a2bc5.json`
  in the same directory. Final API/browser logs name their individual tenant journals.
- **Handling concern:** initial inspection mistakenly printed the private owned-test
  shell profile into tool output. Its credential values are not repeated here and
  were not sent to browser children. No authorized provider secret was loaded (the
  test profile is absent), no production config was read, and no credential rotation
  or profile change was performed. The transcript exposure of owned-test credentials
  remains disclosed for owner handling; this report does not claim perfect secret
  handling or silently change resource/security configuration to hide the mistake.

### Changed files and self-review

All paths are absolute; existing documentation/history was appended, not overwritten.

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/README.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/PROGRESS.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/docs/e2e.md
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/api/control_plan.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/app/services/version_service.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_outcome_api.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/capa/test_capa_review_concurrency.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_harness.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_progression.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/capa_outcome_runner.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/test_capa_outcome_review_browser.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/backend/tests/e2e/test_capa_outcome_runner.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/playwright.agent.config.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/e2e/specs/capa/outcome-review.spec.ts
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/components/capa/CapaOutcomeReviewPanel.test.tsx
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/frontend/src/pages/capa/CAPADetailPage.tsx
```

- Self-reviewed business/transaction/authority boundaries and every brief checklist.
  Original test cases/assertions retained; no existing guard weakened. Real lock
  waits, rollback side effects, current authorization precedence, strict tenant
  namespaces, historical binding and supplement/archive policy remain intact.
  Only two one-line backend integration fixes and minimal DOM semantics touch
  production. No Agent command/plugin/DIRECT/scanner/model delivery or broad settings.
- README/docs reflect actual implemented gate semantics, not a claimed live success.
  `git diff --check` clean before report append; final commit also checks it.
- **Unresolved external blocker:** no existing authorized worktree `.env.e2e`.
  The controlled runner deliberately does not use ambient general-purpose credentials.
  Actual business import returns blocked, not a provider HTTP result. Genuine D4+
  progression, pending EDIT403/stale409/rejection/resubmission, bound PLANNING/FMEA
  review denials, actual browser approval/receipt, knowledge sink and lateral close
  remain **unexecuted acceptance**, despite executable tests and independent fixtures.
- **Diagnostic/provenance limitation remains carried for final triage:** the real
  D3 blocked API exposes `report_error=None`; its internal missing-config catch does
  not preserve a provider exception class in that response. No invented error class,
  mock response or inferred provider success fills that gap. The inherited deferred
  diagnostic-provenance limitation is not marked resolved by this task. The separate
  rejection source-wait Minor is covered as described above.
- Next: owner supplies/locates an existing authorized **test** profile without exposing
  secrets, reruns the complete `acceptance` command and obtains independent Task7
  review. This report does not mark Task7 accepted/done. Task8 full freeze remains
  separate; no controller ledger was updated.

## Task 8 独立交接（2026-10-27 至 2026-10-29；非整片验收）

**下列早期段落为历史执行过程，以本节最后的2026-10-29最终独立交接为准；不是Task8/整片验收签字**。BASE `e1e04734`。完整报告位于本工作树 `.superpowers/sdd/2026-10-23-capa-outcome-review/task-8-report.md`，私有证据不含配置凭据/URL。

- [操作指南](docs/development/capa-outcome-review.md)已写；当前规格、runtime roadmap、权限和受影响API/services/前端README已同步。仅01.3 v2 /01.7 v3 /01.8 v2（均2026-10-27）和三个verify剧本改版，D7 pending与CP+FMEA范围保留；史料/其他故事日期不改。版本与本地链接/既有引用检查通过，不代表真实走查通过。
- 拒绝副作用 helper 增加 `D8_REJECTED` 审计缺席断言，提交真实审计的sentinel先RED后GREEN；覆盖52 passed /3既有warnings。首次完整新库 `make --silent check` 真正执行34:06，实际 **15 failed /3402 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，make exit2**，保留两项graph忽略，没有隐藏失败。
- 其中12项D3 gate fixture没有持久CAPA权限/产品线分配，1项SCAR把bypass-admin人为scope收窄；新增fresh授权正确忽略过期scope使原fixture失真。只修测试前置，不降授权或删断言：D3明确持久EDIT/产品线，SCAR使用非bypass用户的真实产品线分配并新增拒绝后未移动断言。覆盖 **45 passed /3 warnings /exit0**。另外两项为强制收集的真实live测试拒绝无opt-in，不能mock或新skip掩盖。
- 上述fixture更改使首轮源码冻结失效；保留原manifest/全量日志，最后测试变更后新冻结1391文件（SHA256 `f55b807222a64f21de695e4278d90cf2f43544a05e8f3800bfba77900d7cf228`），登记独立final attempt、严格零连接/精确所有权验证后仅刷新同一自有随机测试DB，完整检查重跑中（原结果不覆盖）。未重置application/shared/seed库，无新基础设施。
- 正向Task7/provider/知识/横向扩散仍因授权测试profile缺失BLOCKED；ClamAV专用gate因本轮无精确镜像/资源授权未跑。普通suite和终态保护不代替这些门禁。完整输出/退出码、manifest/实际public+tenant heads、临时资源清理及最终提交在报告最终节补齐。登记PG/卷/工作树和证据保留供Task7，最终删除依赖阻塞，不静默清掉假收口。

**第二轮失败与第三轮冷启动修正（真实记录）**：第二轮完整 **2 failed /3340 passed /12 skipped /3 xfailed /2 xpassed /5 warnings /75 errors，make exit2**。75项来自本轮D3 fixture新增UserProductLine分配时，fresh DB中DC-DC-100尚不存在；先前45项是在已填充库上跑，不能证明冷启动。仅补齐ProductLine缺失时创建并flush；中间一次导入位置IndentationError在收集前exit4，已更正，未当功能RED。全部8个D3/SCAR文件随后 **169 passed /3 warnings /exit0**。再次最后源码变更后1391文件冻结SHA256 `4310462d18bb2bb13e97d6f7fd10e05f06fbdc1deb4cda784a0437c18b21153b`；第三次独立登记attempt先精确所有权/零连接检查后只重建自有随机测试库，迁移后先冷跑D3 gate **12 passed /3 warnings /exit0**，实际product_lines前0/后0（fixture全回滚），不再次reset即继续真正完整make check。当前进程bufhx8lfc，尚无全量退出；未覆盖任何前两轮证据、未新增skip/ignore或降权限。


### 2026-10-29 最终独立交接（DONE_WITH_CONCERNS；无验收签字）

- 第三轮实际收据 `task8-full-verified-result.json`：child `make --silent check`，**2 failed /3415 passed /12 skipped /3 xfailed /2 xpassed /5 warnings**，pytest1961.72s，make exit2、总1973.92s。仅 `test_live_employee_http_provider_chromium_outcome_review` 与 `test_live_employee_controlled_source_modules_fail_closed` 因 `Live test-provider opt-in required` 失败；普通用例无失败或setup error。两项graph忽略、12skip/3xfail/2xpass保持原样，未增加全量排除/skip，不以历史2999或两项live失败冒充全绿。前两轮15fail/75error和中间调用/导入错误全部保留在完整报告。
- 2026-10-29恢复后没有第四次全量、重复reset或改网络/登录/配置；原第三轮真实收据已在2026-10-27T16:08:35Z落盘。精确自有容器身份检查通过且已运行无需resume，1391源码哈希仍为 `4310462d18bb2bb13e97d6f7fd10e05f06fbdc1deb4cda784a0437c18b21153b`。
- 恢复后补充17文件API/并发、终态、补充语义与R4a/R4b-1/R4b-2普通保护 **344 passed /5 warnings /exit0（343.56s）**；真实已安装Chromium终态保护 **1 passed /2 deselected /5 warnings /exit0（18.49s）**。该子集明确不跑两项live，完整suite的两项失败仍保留；终态夹具不当真实关闭证据。最终前端 **232 passed /24 files**，app/E2E tsc与生产build均exit0；均在最后源码修改后执行，无新依赖/浏览器/镜像。
- private `task8-run.py` 只静态解析登记profile，白名单环境、显式清空provider/embedding配置，普通环境E2E_MODE未设置而不是false，日志先脱敏再落盘。仅经静态parser加载自有登记项，未在工具记录输出profile正文/连接URL，未使用ambient/生产provider凭证；先前已披露配置误输出未重复、未静默轮换。所有实际argv、exit、skip/xfail/xpass/warnings及失败诊断见 `.superpowers/sdd/2026-10-23-capa-outcome-review/task-8-report.md` 和 `task8-evidence-inventory.json`。
- 实际catalog前后：自有app/test DB各168表、无新增/删除表，无CAPA候选发布表；public head **20261009_agent_task_attachments**。本轮真实迁移两临时tenant，前后head均 **tv005_agent_task_attachments**、表列表不变、无候选表，随后仅清理该两tenant。`task8-resource-final.json`证明当前所登记runner/browser/Vite无存活、自有outcome schemas为0、app/test其他连接及idle事务均0，核心PG/卷保留；未重置application/shared/seed库。
- 指南/规格/roadmap/权限/受影响README同步；01.3 v2、01.7 v3、01.8 v2及对应skill均为实际原契约修订日2026-10-27，本次仅更新交接状态，不乱改未变故事日期。3组版本一致、本地链接和既有引用checker、`diff --check`、最终manifest均有真实exit0/unchanged收据；来源权限和批准条件/驳回边界已自检。仅三个既有测试文件改动，未改生产行为、迁移、开关、自批或Agent/model/生产授权。
- **剩余阻塞/下一步**：本工作树授权.env.e2e仍缺，真实正向provider、浏览器、受控来源、知识/横向仍未通过；实际ClamAV专用gate本轮缺精确镜像/资源授权，未启动或清理他人环境。控制方负责最终整片独立复核。核心PG/container/卷/数据库登记、worktree和所有证据为Task7保留，最终破坏性清理是依赖BLOCKED，不标已完成。仅授权本地提交，实际提交号记私有完整报告；不push/merge/deploy，不勾Task8/计划完成，不改控制方ledger。

## Task8 review-fix round1 / I1 独立交接（2026-10-29；待复核）

FIX_BASE b16d7d19。reviewer指出并经真实空迁移库证实：移除admin_user后source ProductLine未建立，UserProductLine先flush会FK失败。仅在同一test插入四行缺失时创建default_factory下DC-DC-100并flush；viewer_user、CAPA EDIT、scope、目标、403及原line不变断言均保留，未改生产/公共fixture/其他契约。RED是SQL FK失败1 failed，不是collection/import异常；同一owned空库GREEN1 passed和D3controls12 passed，每次前后product_lines0、168表行数与迁移baseline完全一致。

新manifest1391文件SHA a8acea805fd51fba5b4c1494b3909e5dfb6a40ca8eba43b6c8d9b9c182077e07，最后源码修改后唯一新fullmake实际2 failed /3415 passed /12 skipped /3 xfailed /2 xpassed /5 warnings（make exit2），只余两项mandatory live无opt-in失败；保留原graph忽略与所有既有非pass，无新增掩盖。旧4310462d…及全部历史failed receipts仅作历史保留、不用于本轮新源码。冷检查后直接同库make，无第二次reset；仅精确自有test DB一次owner/identity/zero-workers验证重建，不动app/shared/seed库。

补充后端/前端/类型build/真实Chromium终态保护、实际public head20261009_agent_task_attachments与tenant headtv005_agent_task_attachments、无新candidate表、相同1391hash、diff/三组story-skill/链接及无临时runner/schema/连接事务已复查；逐项真实命令/结果/exit/warnings/rows证明在同一私有task-8-report.md的R1附录与task8-r1-*收据中。核心PG/卷/worktree/证据保留，最终破坏性清理依赖BLOCKED；profile/scanner外部权限条件未变，不调用生产/ambient凭证，不安装工具/镜像、不改auth/配置、不push/merge/deploy。源码仅此test四行，公共文档仅本PROGRESS当前状态；授权本地focused commit，提交号记私有R1报告；自检不等于控制方SCOPED复核，不标Task8/全片complete，不改controller ledger。


## FINAL REVIEW FIX — CAPA outcome-review I1 consolidated wave (not phase acceptance)

Recorded 2026-10-29T16:38:47.091250+00:00. **DONE_WITH_CONCERNS; Ready to Merge NO.** FIX_BASE `ee598784574dddadc28dd669bd7364e721786895`, initially clean tracked tree. This is the single consolidated fix wave for the final-review authority race, not a restart of Tasks 1–8 or an acceptance of this wave by its author. Controller must arrange one independent scoped rereview of FIX_BASE..the focused local commit. No child agents or controller-ledger/task-completion edits.

### Finding, surgical fix and self-review

Actual HEAD confirmed that verification create/update and document-gate `run_audit` admitted a current EDIT actor before source ProductLine/document waits but did not recheck current authority after those waits. Update also dirtied method/result/evidence before waiting and could autoflush them. Parent locking still protected terminal state; this was a distinct current-authorization race.

Only five tracked files change:
- `backend/app/services/capa_verification_service.py`: capture server actor UUID before awaits, use it for verification/audit attribution, recheck `current_capa_actor_target(..., EDIT)` after the complete source-lock set; validate/recheck before dirtying update fields. Omitted/null source-ref paths retain the ordinary parent admission and existing behavior.
- `backend/app/services/capa_doc_gate_service.py`: the same current actor/activity/role/namespace/target-scope check immediately after ProductLine and ordered document locks, before analysis revalidation and gate/audit mutation.
- `backend/tests/capa/test_capa_review_concurrency.py`: 32 real PostgreSQL source-wait races/positive controls, using existing committed fixtures and real service commits.
- `docs/development/capa-outcome-review.md`: operational/service guidance for this actual boundary.
- `PROGRESS.md`: this current handoff, with earlier receipts retained as historical.

Self-review: reuse the existing fresh current-access helper (its namespace/identity/permission/scope reads use no-autoflush), not a new global authorization framework. Hold existing parent-before-child/source ordering; the recheck is a fresh non-locking read against an already held parent, not reverse lock acquisition. No new policy, permission increase, provider change, migration, schema/table, or source-deletion CAPA requirement. Source callers retain their own existing source-module minima; the complete source deletion/minima regressions pass. Self-review is not independent acceptance.

### Functional RED/GREEN and transaction evidence

Exact driver for clean RED and GREEN from this worktree:
`/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/final-fix-run.py pytest tests/capa/test_capa_review_concurrency.py -k source_wait_material_writer -q --tb=short -rA`.

Clean behavioral RED **24 failed /8 valid controls passed /20 deselected /3 warnings /exit1** (10.47s), before any production edit. Each failing case reached the actual source-lock SQL Event witness and `pg_blocking_pids` wait after successful current EDIT admission; a third real committed transaction then disabled the actor, lowered CAPA EDIT to CREATE, or removed applicable ProductLine membership. Independent fresh current-access reads confirmed revocation before releasing the lock. After release, old code changed verification/material or gate decision/success audit. No collection/import/fixture failure is claimed as behavioral RED.

For transparency the first experimental run was **28 failed /4 passed**: the same 24 behavioral failures plus four wrong positive audit expectations (`blocked` rather than the fixture's legitimate version-bumped empty-keypoint `passed`). Only that test expectation was corrected before clean RED; the mixed run is preserved and not the claimed proof. `final-fix-red-green-evidence.json` classifies all three runs with log hashes.

After the minimal production fix, **32 passed /20 deselected /3 warnings /exit0** (10.07s): create/update plus audit of both FMEA and control plan, each blocked separately on ProductLine and document lock, all three revocations plus unchanged valid identity. Controls use the exact CAPA EDIT minimum, no RLS-bypass/admin role. Revoked cases check no pending ORM writes, compare full material/gate/audit/embedding/outbox snapshots within the writer transaction BEFORE rollback, and compare independent persisted state AFTER rollback. This prevents caller rollback from masking mutation/autoflush. Valid controls actually commit verification/linkage or gate audits. No fake permission, lock, commit or rollback.

### New freeze, one fresh full check, post-freeze validation

New **1391-file SHA256 freeze `87fb0a10615affa1d3ef3c3c4bee3db9273fc3896a23ccdea8146f07858a5b33`**, `final-fix-frozen-manifest.json`, after the last production/test change. The prior R1 `a8acea805fd51fba5b4c1494b3909e5dfb6a40ca8eba43b6c8d9b9c182077e07` and all older full receipts remain historical and do not verify this source. Docs/private SDD/deps/build caches are excluded consistently with prior manifests. Final `final-fix-manifest-verification.json`: all1391 hashes unchanged after all actual commands; no source/config/test change after freeze.

Exactly one guarded new prepare/reset of registered random test DB, then one distinct full child `make --silent check` (tracked background `bjv2lrhjs`), with no reset/check duplication while any DB worker was active. Full finished 2026-10-29T16:30:13.676866+00:00, **2 failed /3447 passed /12 skipped /3 xfailed /2 xpassed /5 warnings**, make exit2, 2057.31s total (pytest2045.01s). Only failures:
- `tests/e2e/test_capa_outcome_review_browser.py::test_live_employee_http_provider_chromium_outcome_review`
- `tests/e2e/test_capa_outcome_review_browser.py::test_live_employee_controlled_source_modules_fail_closed`

Both are the mandatory cases missing authorized live opt-in. **Full gate is NOT green**; ordinary tests have no failure/setup error. Existing Makefile graph exclusions, skip/xfail/non-strictXPASS remain unchanged, no added skip/ignore/fake gate. Exact nonpass list: `final-fix-full-nonpass-cases.txt`. Full backend failure stops make's frontend dependency, so separate post-freeze app/E2E types and production build were actually run, not presumed from make.

Post-freeze complete affected `tests/capa`, `tests/fmea` and control-plan/product-line regressions: **1113 passed /5 warnings /exit0**, 251.28s. Frontend **232 passed /24 files /exit0**; app/E2E TypeScript plus production build exit0. Separate real installed-Chromium provider-free terminal protection **1 passed /2 live deselected /5 warnings /exit0**, 11.68s. Deselection is only in this explicitly separate protection subset, never hidden in full make. Terminal fixtures prove protection, not real provider/closure acceptance.

Receipts below contain actual child argv/cwd, persisted exit, elapsed/finished metadata and captured redacted log paths; every paired `.log` is retained. Driver is existing allowed interpreter plus private `final-fix-run.py` modes `prepare|full|pytest|frontend|protection`, using the inspected static owned-profile parser, filtered child environment, URL/secret redaction and E2E_MODE ABSENT, not string false. No ambient/provider credential fallback. Catalog/resource/manifest/doc checks have their own JSON receipts.

| Receipt (under `.superpowers/sdd/2026-10-23-capa-outcome-review/`) | Actual child command | Exit | Actual summary |
|---|---|---:|---|
| `final-fix-frontend-20261029T155603203898-result.json` | `npx --no-install vitest run src/api/capa.test.ts src/pages/capa/CAPADetailPage.test.tsx src/components/capa src/api/agentTaskAttachments.test.ts src/api/agentTasks.test.ts src/api/capaD4TextPreview.test.ts src/api/client.agentTasks.test.ts src/components/agent/AgentTaskAttachments.test.tsx` | 0 | Test Files  24 passed (24) / Tests  232 passed (232) |
| `final-fix-frontend-20261029T155708002004-result.json` | `npx --no-install -c 'tsc --noEmit && tsc --noEmit -p tsconfig.e2e.json && npm run build'` | 0 | no test count; captured log records actual command output |
| `final-fix-full-result.json` | `make --silent check` | 2 | = 2 failed, 3447 passed, 12 skipped, 3 xfailed, 2 xpassed, 5 warnings in 2045.01s (0:34:05) = |
| `final-fix-prepare-result.json` | `make --silent check-test-db` | 0 | no test count; captured log records actual command output |
| `final-fix-protection-20261029T163512617428-result.json` | `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/e2e/test_capa_outcome_review_browser.py -k 'not live' -p final_fix_catalog_plugin -q -s --tb=short -rA` | 0 | 1 passed, 2 deselected, 5 warnings in 11.68s |
| `final-fix-pytest-20261029T155219193294-result.json` | `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/capa/test_capa_review_concurrency.py -k source_wait_material_writer -q --tb=short -rA` | 1 | 28 failed, 4 passed, 20 deselected, 3 warnings in 10.81s |
| `final-fix-pytest-20261029T155255070389-result.json` | `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/capa/test_capa_review_concurrency.py -k source_wait_material_writer -q --tb=short -rA` | 1 | 24 failed, 8 passed, 20 deselected, 3 warnings in 10.47s |
| `final-fix-pytest-20261029T155335439372-result.json` | `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/capa/test_capa_review_concurrency.py -k source_wait_material_writer -q --tb=short -rA` | 0 | 32 passed, 20 deselected, 3 warnings in 10.07s |
| `final-fix-pytest-20261029T163039054109-result.json` | `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/capa tests/fmea tests/test_control_plan_item_id_stability.py tests/test_control_plan_uuid_dedup.py tests/test_product_line_type_field.py -q --tb=short -rA` | 0 | 1113 passed, 5 warnings in 251.28s (0:04:11) |

Warnings retained, not suppressed: backend full/supplement/browser5 = three existing Pydantic class-config deprecations plus websockets/uvicorn deprecations; isolated RED/GREEN3 = Pydantic. Actual frontend diagnostic occurrence inventory (not test-failure counts): `{"final-fix-frontend-20261029T155603203898-result.json":{"pydantic_class_config_deprecation":0,"react_act_warning":155,"jsdom_pseudo_getComputedStyle":30,"antd_destroyOnClose_deprecation":40,"antd_other_deprecations":40,"vite_cjs_deprecation":0,"large_chunks_warning":0},"final-fix-frontend-20261029T155708002004-result.json":{"pydantic_class_config_deprecation":0,"react_act_warning":0,"jsdom_pseudo_getComputedStyle":0,"antd_destroyOnClose_deprecation":0,"antd_other_deprecations":0,"vite_cjs_deprecation":0,"large_chunks_warning":0}}`. `final-fix-evidence-inventory.json` includes all exact commands, summary lines, warning attribution, log SHA256 and private evidence-runner hashes. No dependency/toolchain refactor.

### Resource, schema, scope and handoff proof

Pre-reset exact registered container ID `a2826f8cb70aacebf742ec5ad09d73f76ec605900f348339f8cf7aabc7afc4c7`, owner nonce equality and image `pgvector/pgvector@sha256:bd12d6788a617f4147d5a2ae0b56d07921398adabfe5a033bd3f50c245df55a1` verified against registration, plus exact loopback endpoint/DB identity/owner, zero active DB sessions and owned recorded workers (`final-fix-resource-pre-reset.json`, `final-fix-fresh-db.json`). Only `openqms_r4a_capa_outcome_92f8027e_test` reset; `openqms_capa_outcome_app_92f8027e_test` and all shared/seed/other-worker DBs untouched. Safe owner fingerprint `abe7da11a2bd780865182f23305acc83d619990d6a008f7b24159172e86216f9`; no profile/credential/URL contents repeated. One metadata `ls -l` inspected the exact permitted interpreter symlink; no main-checkout source/config/secret access or cd.

Real before/after catalog proofs `final-fix-db-before-reset.json` and `final-fix-db-after-final.json`: both app/test public heads `20261009_agent_task_attachments`,168 public tables each, no added/removed/candidate-publication tables. Exact two protection fixture tenants observed before/after at `tv005_agent_task_attachments`, unchanged table lists/no candidate tables (`final-fix-tenant-before-protection.json`, `final-fix-tenant-after-protection.json`); both removed afterward (`final-fix-tenant-cleanup.json`). These are actual DB observations, not migration-file inference.

`final-fix-resource-final.json`: zero own recorded runner/browser/Vite workers, zero remaining outcome schemas, zero other app/test DB sessions/idle transactions; all post-prepare owned fixture journals show cleaned tenants/socket/server/node exits. Registered core PG/container/volume, registration, worktree, SDD workspace and all old/new evidence retained for pending live work. Final destructive cleanup remains dependency-BLOCKED. No scanner images/browser/dependency installation, network/security/credential changes, rotation, push/merge/deploy, child agents or controller-ledger edits.

Mechanical docs links and unchanged three story/skill version pairs pass (`final-fix-doccheck-result.json`, reference checker exit0); no unrelated story/skill date bump. Local diff/self-review and whitespace check passed. Authorized focused local commit follows these actual checks; post-commit receipt records its actual hash and unchanged manifest.

**Remaining gates / next step:** controller's ONE independent scoped rereview of this I1 wave; authorized worktree `.env.e2e` is still absent, so no real provider-positive/browser/controlled-source/knowledge/lateral claim; exact-authorized scanner resource/image gate NOT RUN/BLOCKED; eventual dependency-safe destructive cleanup. Do not mark Task8/phase complete or Ready to Merge. No requested policy changed.

## LIVEACCEPTANCERESUME — Task7, 2026-10-30

**Status: BLOCKED before application use; no new acceptance result or completion claim.**
Resume baseline was HEAD `83deef88`, confirmed by Git. The coordinator reports final
production source-wait fix `b375f26d` independently approved and the phase code review
closed; this resume changes no production/test source or contract and does not redo
Tasks1–6, the Task8 freeze, or full make check.

### User baseline and authorized profile

- Initial tracked status was exactly ` D .env.e2e.example`; that user deletion is
  preserved. It is not restored, staged or committed. No fully clean-tree claim.
- The selected, now user-authorized TEST profile is
  `/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.env.e2e`.
  `git check-ignore -q -- .env.e2e` exited0. Filesystem metadata confirmed regular
  file and not a symlink. The existing `provider_environment` whitelist parser
  returned `authorized_test_profile`; its output was only:
  `TEST_PROFILE_METADATA: regular=true; symlink=false; validation=authorized_test_profile`.
- No profile contents, model/endpoint values, keys, passwords, headers or tokens were
  displayed. Parser data stayed backend-local. No production/main-checkout config,
  ambient provider credentials or old agent transcripts were read. No profile,
  endpoint, login, network or security configuration was changed.
- The earlier missing-test-profile blocker is therefore superseded by successful
  local profile validation, **not** by a claimed provider or application success.

### Actual resource preflight and blocker

Before app use, a private read-only helper uses the existing owned profile loader,
then attempts to inspect only the registered container's ID/owner/running/paused/
endpoint/volume metadata. Only after those checks could it perform a read-only
current-database/current-user/health query. No start/unpause/reset/reseed/recreation
or cleanup action is implemented in this helper.

Actual command from the isolated worktree:

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/task7-live-resume-preflight.py
```

It failed at Docker metadata inspection with real category `CalledProcessError`,
exit1. A second bounded read-only invocation retained the same actual error in a
persistent log; it was for recording/reproduction, not a provider/API test retry.
Exact safe output:

```text
failed to connect to the docker API at unix:///Users/sam/.docker/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /Users/sam/.docker/run/docker.sock: connect: no such file or directory
PREFLIGHT_ERROR_CLASS=CalledProcessError
PREFLIGHT_EXIT_CODE=1
```

Read-only diagnosis corroborated the failure:

- `docker context show`: `desktop-linux`, exit0.
- `pgrep -x com.docker.backend`: no process found, exit1; no process was signalled.
- Socket metadata: `socket_exists=False`, `socket_is_socket=False`.
- `DOCKER_HOST` and `DOCKER_CONTEXT` override presence: both False; no values printed.

The Docker API is unavailable in the selected context. Consequently current actual
registered container ID/nonce, host mapping, volume and DB health **could not be
verified**. No stale historical resource proof is substituted for that check. No
private endpoint was guessed/rewritten. Docker Desktop was not started globally:
that could resume unrelated workloads beyond the exact owned-container scope.
No conclusion is drawn about changed ports, container loss, provider credentials,
provider request categories or application defects.

### Acceptance execution, observability, resources and evidence

Required complete command remains **NOT EXECUTED**, because its mandatory owned
resource/DB preflight could not pass:

```text
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python backend/tests/e2e/capa_outcome_runner.py acceptance
```

- New acceptance cases run: **0**. No pass, skip, xfail, xpass or provider failure is
  manufactured. All three real cases remain pending, without -k/exclusions; installed
  Chromium/retries0/workers1 and all prior assertions are unchanged.
- No application/employee HTTP, document-gate, advance, knowledge, lateral or Chromium
  operation was started in this resume. No provider invocation was initiated; there
  is no new provider usage/billing telemetry. No inference from historical
  `report_error=None` is made. Historical failed logs/results remain untouched.
- No test tenant, socket, server, Vite, browser, DB or container was created/changed,
  so this resume has no newly owned runtime resource to tear down. No shared/seed/
  application/production DB or other worker was touched. Core resource registrations,
  profiles, volume and DBs were not modified; their current health remains unverified
  while the daemon is unavailable. No destructive cleanup or scanner operation.
- Production/test source changes: **none**. Only this append-only report is a tracked
  change owned by this resume; private helper/log are ignored evidence. No proposed
  application/test-contract fix: no application execution reached that boundary.

Persistent evidence and helper, without secrets:

```text
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-live-resume-preflight.py
/Users/sam/Documents/Code/OpenQMS/.claude/worktrees/agent-module-permission-kernel/.superpowers/sdd/2026-10-23-capa-outcome-review/task7-live-resume-preflight-docker-unavailable.log
```

Next: owner/controller restores the Docker service within the authorized resource
scope, then verifies the SAME registered container ID/owner, current endpoint and
read-only DB health before invoking the complete acceptance command. This report
does not authorize a different context/container, recreation/reset, global service
restart, browser/dependency install or scanner image. If later application/test
failures require source changes, report the concrete reproduction/proposed narrow
fix before editing, as the existing freeze/reviews must then be revisited.

No Task7/Task8/phase acceptance or controller ledger was marked complete; no push,
merge or deployment. Any local report-only commit excludes the user-deleted example
and all test profile/evidence files; the worktree remains user-dirty afterward.

## Task 8 FINAL CLOSURE — 2026-11-01（UTC 收据 2026-10-31）

**独立验证交接 DONE_WITH_CONCERNS，不是 Task8/整片最终签收。** BASE `0052f8621440f4af324c21cfccf008218cc5dd35`；已复核源码 `00b8bd5d` 及 D3 前置修正/分层证据保持不变。仅待父级独立最终复核（包含私有配置 harness）和复核后的精确核心资源处置。下列均为本轮实际执行，不引用历史2999/3447作为当前结果。

### 私有配置根因与实证

- 旧 `task8-final-closure-full-result.json/log` 的 **3439 passed /11 failed /12 skipped /3 xfailed /2 xpassed /5 warnings，make2** 原样保留：私有 runner 在收集时全局载入 provider，使缓存的同一个 Settings 被所有用例看到；2项 no-LLM CAPA 预期422却200、8项 readonly browser 预期未配置provider却为True，以及同轮1项local-trial浏览器控制失败。正确的安全/默认关闭断言没有修改；没有应用缺陷修正、SDK/provider结果替身或新增skip/ignore/xfail。
- 接管发现未验证的 hookwrapper 在非 live 分支直接 return，真实配置 RED **1 failed /exit1**（`task8-pytest-20261031T153413155233-*`）；修正私有 hook 后，纯配置 **8 passed /0 warnings /exit0**（`153727914942`），覆盖正常、异常、实际pytest setup/call/teardown故障后的精确恢复和Node白名单，无付费调用。原草稿及全部旧收据保留。
- 只有精确 `tests/e2e/test_capa_outcome_review_browser.py::test_live_employee_http_provider_chromium_outcome_review` 的完整 fixture setup＋call＋teardown 临时应用本工作树授权 TEST profile 的5项既有LLM配置。整段pytest默认provider为空；原环境、Settings字段及fields-set在finally精确恢复，不替换Settings对象/导入引用，不改鉴权/门禁/提交。已核对的AI配置服务和provider_adapter按请求读取配置，没有需要清除的配置缓存；不增加生产生命周期修正。
- 实际混合 **14 passed /5 warnings /exit0（170.72秒）**，无skip/xfail/xpass/deselection：D4 no-LLM、全部8个R4 readonly浏览器、正常local-trial浏览器、CAPA三条分层用例，最后D5 no-LLM再次422；真实主链使用实际provider/员工HTTP/D8/Chromium/知识/横向，后两条仅是保护证据。日志有 `TASK8_PROVIDER_SCOPE` 和最终 `TASK8_PROVIDER_ABSENCE_AFTER_SUITE`。Node/Vite/browser保留已有nonce/backend/一次性员工登录等明确白名单，不接收DB/provider键；npm/npx只有系统环境。旧receipt的`node_environment=system-only wrapper`标签未覆盖直接Node的运行时白名单，解释在私有metadata-note，未重写原receipt。

### 新冻结、唯一新鲜完整门禁、全部后续验证

- 新manifest `task8-takeover-frozen-manifest.json`：**1390文件**，SHA256 **69a55eb9bb2df59377626aa81bd0de1b8436cd5b34cea1c5232b4f788aa2b456**。仅包含tracked源码/配置/测试，排除文档、依赖/构建、私有证据；用户已删除的tracked `.env.e2e.example` 明确作为缺失基线排除，不恢复、不stage、不提交。用户ignored TEST profile不修改或纳入清单。
- 精确登记container ID/owner nonce/image/端口、DB名/owner及**零活动worker/连接**核验后，仅重建登记随机TEST DB一次；application/shared/seed DB没有reset，没有终止worker。独占attempt记录和primary helper SHA256在 `task8-final-closure-r2-attempt.json`，原failure/fresh-DB日志均保留，输出使用新stem与0600脱敏文件。
- 实际命令（本worktree；解释器main路径仅执行，不读main checkout配置）：`/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python .superpowers/sdd/2026-10-23-capa-outcome-review/task8-final-run.py full`。其child是 **`make --silent check`**，不是自造替代门禁；私有pytest entry仅使plugin在Makefile的`PYTHONPATH=.`下可导入。真实live opt-in只配合精确node的配置scope；不将provider全局暴露。
- **实际完整结果：3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，pytest2168.07秒，make exit0，总2201.64秒，UTC完成16:19:59。** 完整case/结果见 `task8-final-closure-r2-full-result.json/log`；真实mandatory CAPA live passed且最终provider为空。只运行这一次新鲜full，无超时重置/重复full/盲目provider重试；等待真实后台完成，未轮询日志。
- 保留Makefile两项graph排除：`tests/test_graph_sync_worker.py`、`tests/test_graph_projection.py`。全部17条skip/xfail/xpass逐条保存在 `task8-takeover-full-nonpass-cases.txt`。普通suite的ClamAV专用环境skip不替代已通过的独立scanner gate；其余既有canonical snapshot/Redis/E2E_MODE skips及MES xfail/xpass未隐藏或修正。
- 完整退出后，补充受影响后端 `tests/capa tests/fmea`、规划ID稳定性/去重/产品线，以及D4 preview、readonly delivery、附件API/存储/恢复共 **1203 passed /5 warnings /exit0（395.07秒）**，无skip/xfail/xpass/deselection；收据 `task8-pytest-20261031T162129573385-*`。
- 后续前端实际 **24 files /232 passed /exit0**，目标为CAPA API/详情/组件及受影响Agent任务、附件和D4 preview API/组件；收据 `task8-frontend-20261031T162057808062-*`。接着实际 `npx --no-install -c 'tsc --noEmit && tsc --noEmit -p tsconfig.e2e.json && npm run build'` **exit0**，收据 `162111767655`；不安装依赖或浏览器。
- 最后实际Chromium终态保护及确定性FMEA/PLANNING逐模块撤权保护 **2 passed /5 warnings /exit0（20.22秒）**，显式选择两项，无deselection、无mock真实关闭；收据 `task8-pytest-20261031T162811209284-*`。每个fixture在真实租户中记录public/tenant heads及表列表，随后真实teardown，`TASK8_FINAL_TENANT_CLEANUP: remaining=0`。真正正向provider/关闭证据来自混合和完整suite中的mandatory live，不拿保护夹具冒充。
- Python warnings为3项既有Pydantic class-config及2项websockets/uvicorn弃用；前端原React act/jsdom getComputedStyle/组件弃用提示与浏览器Node弃用、合成租户缺R11风险配置等诊断仍在原日志，没有全局silence或扩大整改。Vitest没有统一warning计数，未伪造为零。

### Schema、资源、文档与剩余动作

- 实际before/after两个自有DB各 **168张public表**，表集合及public head **20261009_agent_task_attachments** 不变，无新增/删除候选表。真实fixture租户前后head **tv005_agent_task_attachments**、表集合不变、无候选表；未新增迁移、候选路由/开关、现场执行模型或生产配置。
- `task8-takeover-resources-final.json`：container ID/owner/image/独占卷挂载核验；两个自有DB其他连接和idle事务均0，全部临时tenant schemas为0，登记runner/子进程/Vite/browser已结束。原scanner随机项目当前containers/volumes/networks均0。没有全局Docker stop/prune或处理其他项目资源。
- Task7已验收的 `task7-acceptance-20261031T135252615462-*` **3 passed /5 warnings /exit0** 是一条真正主链＋两条独立保护链；`task8-scanner-20261031T135929361071-*` 是已授权真实ClamAV **7过程测试 /3 warnings＋1浏览器控制测试 /3 warnings，exit0**，ClamAV1.4.3/definitions28170。源码/镜像契约未变，不重跑不必要scanner/build/download；不把ordinary skip当其通过。
- 已保留并完成4份partial docs，补齐PROGRESS、当前spec、runtime roadmap及受影响frontend README的当前状态。**01.3 v2 /01.7 v3 /01.8 v2及三个skill的业务版本/日期仍为2026-10-27**，没有无关升级或重写历史；D7 pending、CP+FMEA、当前自批及R4b/Agent/R5/生产边界不变。机械版本/本地链接/源码引用/既有selector-API-audit检查和diff结果见 `task8-takeover-doccheck.json`，不冒充整个用户故事剧本走查。
- 源码1390指纹在full后、全部supplement后和doc-only提交后分别复核。每个命令、退出码、实际计数、全量case非pass、原失败根因、catalog差异及日志hash见 `task8-takeover-gate-inventory-v2.json`（v1派生索引保留；v2补齐failed-only RED摘要，未重跑测试）。全部primary helper与补充helper/证明的SHA256及最终doc-only commit见 `task8-takeover-seal.json`。私有完整交接：`.superpowers/sdd/2026-10-23-capa-outcome-review/final-closure-report.md`。
- **核心资源不删除**：已准备 `task8-final-closure-cleanup.py --dry-run` 与精确ID/卷/DB/零连接证明及仅供父级复核后执行的命令清单，当前只是DRY_RUN。parent独立review后按既有本片授权再次核验身份/零worker，才处置登记核心container/volume/DB；worktree、SDD、用户profile/删除及全部证据继续保留。没有静默轮换凭据、重述先前暴露值或操作远程密钥。
- **最终剩余**：父级独立最终复核和复核后的精确核心处置。仅授权并执行doc-only本地提交（实际号见seal/report），排除用户删除示例和所有ignored profile/evidence；不push/merge/deploy，不修改controller ledger，不提前勾Task8/整片完成。

## 最终验收与资源处置完成（2026-11-01）

- 八任务、44步骤均完成。整片代码复核、Task7分层验收复核，以及最终私有配置/原始证据/交接与清理计划复核均已通过，无未解决阻塞发现。真实AI正向主链与两条确定性保护链分开取证，不把保护前置视为AI门禁成功。
- 最终源冻结完整 `make check`：**3450 passed /12 skipped /3 xfailed /2 xpassed /5 warnings，exit0**；补充后端1203、前端232、app/E2E类型及build、真实主链/保护、ClamAV7过程＋1浏览器均通过。保留两项既有graph排除、所有17条非pass记录、警告与全部失败轮次，不声称所有测试均无条件执行或日志纯净。
- 最后处置前重新核验精确容器ID/owner/固定镜像/回环端点/专属卷及独占挂载、两库归属、零连接与零登记worker。只停止并删除本轮登记核心容器，删除其专属卷；两测试库随卷处置，后续inspect证明容器与卷均不存在。处置收据：`parent-core-disposal-20261031T170149851965.json`（本计划私有SDD目录）。Docker Desktop、镜像缓存、其他服务均未清理。
- 保留当前分支、worktree、用户TEST profile、用户删除的`.env.e2e.example`及全部报告/日志/seal/旧收据。用户删除不恢复、不提交。本片未push、合并、部署或开放生产/Agent/R5能力；现场效果与业务受控修订/任意重开仍按指南边界处理。后续重跑须重新登记隔离资源，不得使用旧连接或回退共享库。

## MES XFAIL/XPASS 测试整改完成（2026-11-01）

- 仅修改`backend/tests/test_mes_concurrency.py`：fixture在yield前保存connection/ic标量主键；删除4处过时的非strict xfail；不改生产服务、权限、接口、模型或迁移。
- 回滚测试执行真实采样写入和SPC重算后注入异常，由调用方rollback，再用独立会话断言ingestion、采样批、采样值及审计全部未持久化，并验证相同external_id可重试，删除永真断言。
- 推送用例调用真实process_outbox和REST连接器，仅替换外部HTTP传输；验证已提交claim、真实sent落库、不重复发送；重投用例在外部接收后模拟worker中断，走真实超时恢复与重领，核验claim token更换但event_id固定。外部接收方去重是明确的测试假设，不声称真实厂商保证。
- 同步失败用例通过真实REST校验和run_sync_round触发失败，从新Session确认failed、失败次数/错误、claim释放、checkpoint未推进及无订单落库；不再手改job状态或读取旧identity-map对象。
- 先记录4通过但原fixture teardown MissingGreenlet的RED，保存PK后4通过；中间本轮一次列名拼写NameError已修正，保留日志且不当作功能RED。模块最终正常及`--runxfail`均33通过/3 warnings。私有内存故障注入的提前commit、跳过推送、改变重投event_id、错误推进checkpoint各触发预期失败，随后未注入的模块重跑通过；未改写生产源码。
- 独立小范围复核Approved，无Critical/Important/Minor。证据在本工作树私有`.superpowers/mes-xfail-fix-20261101/`；原检查的3xfail2xpass及展开2failed2passed1teardown error记录在另一私有检查目录，均保留。
- 仅使用本轮明确获授权的缓存固定pgvector镜像与随机_test库、回环端口。核验owner/专属卷/网络及零连接后，临时项目已删除，容器/卷/网络剩余均0；没有恢复旧CAPA环境或使用共享/种子/生产库。一次迁移后的正常停机请求来源未确定，已核验并恢复同一容器/卷，无数据重置。
- 首次整改交接时未跑全站make check、未提交/push/merge/deploy；后续用户已授权按现行设计核对后独立提交并仅推功能分支，不创建PR/合并/部署。此改动作为后续测试维护差异审阅，不覆盖已完成CAPA阶段的原始冻结/验收收据。
