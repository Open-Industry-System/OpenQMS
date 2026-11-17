# 固定 D4 本地接收器：Linux 有限越界隔离设计草案

日期：2026-11-15。状态：**v3.2 已获用户整份书面确认（“通过进行实施阶段”），进入独立实施计划编写；实现与Linux验收尚未开始**。

批准边界：用户批准本设计进入实施阶段；按本设计§9先编写并独立审阅TDD实施计划。专用Linux环境、软件安装/镜像获取、远程接入和资源创建/执行预算仍须明确授权，不从设计批准外推。旧资源和R4B-CLEANUP-01不变。

v3.2审阅收口：两位审阅者重新读取当前修订并核对claim/receiver实际行为；未发现阻止提交用户确认的Critical/Important，不沿用漏检的v3.1通过结论。P1关闭来自用户明确接受现有安装授权范围，而非新增单run保证；P2关闭是书面未决意图/迟到对象处理规则闭合，不是Docker创建收敛或回收能力已实测。

用户审阅纠正v3.1两项缺口：安装级secret不提供单会话单run的服务端保证；创建仍在途时首次零枚举不证明没有迟到容器。此前双复核未发现这两点，历史“可提交确认”结论不作为当前通过证据。用户明确选择接受安装现有授权范围、不保证单run、不改claim协议；P2按未决意图失效关闭修订。保证范围选择不是整份设计批准。

审阅收口：API全链日志、receiver自报收据/完成不可信、watchdog自身失效停止链三项Important均在规格层经限定复审关闭；随后独立整体质量审阅无阻止提交用户确认的Critical/Important。此为文档合同审阅，不是具体Linux能力检测、单元配置或真实有界隔离验证；后续实施计划及资源授权尚未取得。

v2 修订：独立规格初审提出的两项 Important（API 全链日志边界、receiver 自报收据/完成不可信）经限定复审在规格层关闭，不代表实现或平台可行性通过。

v3 修订：用户确认以 Docker Engine + systemd + nftables 为设计基线，并选择专用外层控制器直接启动固定 receiver；补充过滤规则所在命名空间、独立监督与有限资源预算。该选择不是安装、创建资源、远程接入或实际执行授权。

## 1. 已确认范围与基线

用户已选择下一片仅设计本地接收器进程/容器隔离，并确认：

- 面向 Linux 专用本地验收环境；本轮不创建环境或资源。
- 防护固定接收器被攻陷后的有限越界；信任宿主、内核和部署管理者，不声称抵抗内核逃逸、恶意宿主或恶意管理者。
- 沿用已验收 D4 单字段，无模型、无附件、不启用生产。

基线为本地集成分支 `dcda1d55`。[既有交付指南](../../development/capa-d4-local-text-delivery.md)记录功能验收及独立延期清理项 R4B-CLEANUP-01。此次设计不重新签收历史测试，不消费旧私有凭据，不处置旧资源。

[已批准 v6](2026-11-08-agent-d4-root-cause-local-delivery-design.md)只信任开发主机和固定执行物，不认证 OS 沙箱。本设计是新增部署约束，不修改 CAPA/FMEA 的业务授权、分类或数据来源合同。下述拓扑为建议，未因平台选择而自动获准实施。

## 2. 不变合同与非目标

1. 接收器仍是 `openqms.local-d4-root-cause-text` / `1.0.0` 的固定程序，profile 为 `local_d4_root_cause_text_v1`。
2. 只接收 `d4_root_cause` 脱敏候选，保持 `restricted/masked/redaction_candidate/not_approved`、`model_delivery_allowed=false`、`local_plugin_only`。隔离不是降敏批准。
3. 六步协议、固定消息、实际批次 ACK、一次 finish、unknown 语义不变；无自动重试、续租或容器自动 restart。
4. 服务端逐次检查当前身份、租户代际、epoch、目标、来源证明及固定父 grant 的 P/T 交集；容器、镜像、IP 地址或客户端自报 hash 不授予权限。
5. 保留数字回环 origin、真实 ASGI 回环 peer、拒绝 Forwarded/X-Forwarded-*；不放宽为 bridge 网段或 host.docker.internal。
6. 旧 metadata worker/hash/profile、SDK 十操作合同不变。正文和 runtime 默认关闭、dev-only、独立限时策略槽不变。
7. 不做任意插件、多租户恶意工作负载调度、模型/附件外发、R5 业务命令、R6 入口替换、R7 第二插件、生产部署、对象存储、远程证明或安全擦除承诺。

程序与策略证据见[接收器](../../../backend/examples/readonly_d4_text_receiver.py)、[现有启动器](../../../backend/scripts/agent_d4_text_local.py)、[真实 peer 检查](../../../backend/app/core/agent_local_trial.py)、[正文策略](../../../backend/app/services/agent_runtime/local_d4_text_policy.py)。

## 3. 建议拓扑：专用网络命名空间，不共享宿主网络

```text
可信宿主管理者 / 有限部署控制器
  ├─ 创建并配置专用 network namespace、过滤规则和 cgroup
  ├─ 可信 API 容器：专用业务测试身份、独立 UID、独立 PID/mount namespace
  │    └─ 单 worker，仅监听该 network namespace 的 127.0.0.1:固定端口
  └─ receiver 容器：只共享上述 network namespace
       ├─ 独立 PID/mount/IPC/UTS namespace、不同非零 UID
       ├─ 只读最小执行环境 + 有界私有 tmpfs
       └─ 仅可 TCP connect → 127.0.0.1:固定 API 端口
```

共同网络命名空间让接收器和 API 的回环指向同一栈；API 仍从真实 socket 获取回环 peer。它**本身不提供出口隔离**，必须同时满足下一节的按接收器身份强制过滤；不能把 `--network=container:...` 单独当作安全方案。不得使用宿主 host network、宿主 PID、privileged、Docker socket 或宿主根目录挂载。

API 和部署控制器属于可信计算基。API 自己访问专用测试数据库所需的网络能力不能转授 receiver；API 使用的 DB 凭据、策略文件、HMAC 密钥和员工/admin JWT 不挂入 receiver。接收器安装 secret 和随后 run token 是其合法持有的权限，不承诺对接收器自身隐藏。

共同网络栈可能暴露其他本地监听服务，故命名空间内只允许必要的固定 API listener；启动前枚举监听器，出现未登记 listener 即拒绝启动。未来增加 listener 必须重新审阅出口策略。

## 4. 网络强制边界与失效关闭

- 推荐由可信控制器在 receiver 启动前配置 Linux 内核出站过滤，按不可伪造的 receiver 内核 UID 或经验证的 cgroup 身份匹配；用户命名空间映射后的真实身份必须核验，不能按容器内 UID 字符串猜测。API 使用不同内核身份。
- receiver 只允许到固定 `127.0.0.1:API_PORT` 的 TCP；其余 IPv4、全部 IPv6（本片选 IPv4）、UDP、DNS、外网、网关、链路本地/云 metadata 和其他回环端口全部拒绝。不因已存在连接而给 receiver 泛化的 established 放行；其重传/ACK只能属于该允许元组。
- 使用 cap-drop ALL、no-new-privileges、固定 UID、禁止 setuid 提权与 namespace 变更，防 receiver 改身份、过滤器或路由。禁止 AF_PACKET/raw、AF_UNIX、netlink 等旁路；seccomp/LSM 的具体组合须用真实运行验证，不能凭配置名推断有效。
- receiver 不允许 bind/listen、传递 FD 到外部服务、访问宿主 Unix socket；标准库实际所需 syscall 由后续计划实测固定。TLS、随机数和时间调用不能为了方便而关闭证书验证或扩大网络。
- 启动规则加载失败、身份匹配不确定、规则被替换、listener/端口不符、隔离能力不可用时拒绝运行；不得退回现有非沙箱 launcher。运行中检测策略失效必须终止整个 receiver cgroup，且不得宣称这一检测能追溯撤回已发字节。
- 网络规则是 L3/L4 边界，不声称仅能访问六条 HTTP 路由。允许端口上的每个请求仍须通过服务端自身权限检查；不能笼统宣称恶意请求都被拒绝。平台本身和已授权 API 通道仍属可信边界，不保证对受信平台的隐蔽信道或信息流非干扰。
- 被攻陷 receiver 可将秘密放入未知路径、query、header、body，甚至畸形 HTTP。专用 API 从 HTTP parser、ASGI server、框架、中间件到应用/异常收集器的全部日志链均不得记录这些攻击者控制原文或原始异常；只允许服务端固定路由标识、固定错误码及经过独立验证的安全元数据。没有匹配路由或解析失败时使用固定占位标识，不能回显 request-target。现有 recovery 特定路径过滤不足以满足本条，普通 access log 和解析错误日志必须单独覆盖。日志边界不成立即禁止秘密交付；本要求不授权将正常业务审计关闭，也不声称撤回已合法提交的平台记录。

**可行性关口：** 在任何真实正文交付前，必须用无秘密的替代攻击程序在与 receiver 完全相同的 UID、namespace、cgroup、mount、seccomp/LSM 和网络规则下证明允许元组可达、所有禁止类别不可达；如内核/运行时不能稳定区分 API 与 receiver 的出站身份，停止此拓扑设计，不放宽回环或改用 host network。

## 5. 文件、凭据与执行信任锚

- receiver 镜像按不可变 digest 固定，记录基础镜像、Python/stdlib、构建输入和运行配置；不用浮动 tag、不运行时安装依赖、不隐式 pull。实施资源和镜像获取权限另行确认。
- 保留现有 receiver 的审核字节不变作为首选；镜像 digest 和部署清单是新增信任锚，不替代现有 worker SHA256。现有服务端只能证明其自身固定文件与策略一致，不能证明远端容器实际执行环境；不新增 HTTP 自报证明。
- receiver 只读根文件系统，不挂 checkout、用户 HOME、宿主 tmp、服务端配置或 DB 目录；必要 Python/stdlib/证书和运行库是显式只读白名单。最小设备集，不开放宿主设备。
- 唯一可写区是有明确大小/inode限制的私有 tmpfs，nodev/nosuid/noexec；禁止宿主持久卷、共享 tmp、core dump。tmpfs 不等于不落 swap，验收宿主须关闭 swap 或具明确受信的加密 swap 策略；不宣称内存安全擦除。
- 专用控制器读取 owner-only 配置后，通过不落日志的 stdin 管道一次传入；不放 secret 于 argv、环境、镜像层或 Docker inspect 可见字段，不把配置文件挂入 receiver。关闭非必要继承 FD。部署控制器不接收任意镜像、命令、挂载和 runtime 参数。
- 用户已选择专用外层控制器直接启动固定 receiver，不在容器内执行现有 launcher。外层读取配置仍保留 owner/0700目录、owner/0600普通文件、单硬链接、路径逐组件no-follow与64KiB上限，严格验证既有六字段。经校验的配置仅通过附着的stdin管道传入固定 `python -I -S -B` 入口，关闭后不重连或重放；容器内不创建配置副本或临时receiver代码副本。旧launcher保持不变且不成为失败回退路径。控制器输入不允许任意命令、image、路径或Docker参数；receiver映像和部署清单由可信管理员离线固定。
- receiver stdout/stderr 全部视为不可信，实时有界读取后丢弃，不解析或转发自报 UUID、状态和计数。即使是 canonical UUID、退出码0和自报 completed，也不是可信收据或业务完成证据；合法 UUID 可编码秘密。隔离控制器只输出自己观察到的固定基础设施状态（例如 isolation_exited、isolation_terminated、isolation_unknown），不输出正文接收数、收据ID或 completed；基础设施正常退出不等于交付成功。正常固定 receiver 内部仍保留既有六步及 finish unknown 合同，但其输出不成为隔离控制器的可信确认来源。需要核对业务事实时，由有权员工通过既有受控平台入口查看；本片不新增收据验证接口、不让控制器持有员工/admin JWT。未来如需自动确认，必须另行设计绑定本次 task/run/交付且 receiver 无法指定的可信平台证据。
- 禁用容器持久日志驱动，原始 stdout/stderr 不进入普通日志或错误诊断；超限时终止整个 receiver cgroup，控制器内存始终有界。现有 launcher 对 communicate 结果事后检查长度不是对恶意无限输出的内存防护，不能直接冒充满足本条。此处只保证不转发攻击者控制的输出载荷，不承诺消除进程退出/时间等隐蔽信道。

## 6. 进程、资源和生命周期

- receiver 为独立 cgroup，限制 memory、pids、CPU、文件描述符及输出预算；数值由后续实测定稿，不以未测的任意配置当保证。禁止创建新 namespace、ptrace 跨进程、mount、bpf、修改 cgroup 与访问容器运行时。
- 隔离镜像不携带业务/DB/provider 包或凭据。移除 shell/工具仅缩减攻击面，不作为主要安全边界。
- 正常固定receiver一次启动只执行一次claim六步流程；这只是程序行为，不是被攻陷时的服务端保证。现有安装secret配合新request_key可领取同安装下其他合格run，即使它们属于同一报告且各自P/T均合法；expected_report_id也是客户端校验，不能限制恶意代码。用户已明确选择接受安装现有授权范围，不新增服务端会话/run绑定，不改claim协议。被攻陷receiver在存活期间可通过新request_key领取该安装下其他当前合格运行；范围仍受服务端每次安装、任务、身份、目标、策略与P/T来源授权约束，但本隔离会话不保证只领取一个run，也不以expected_report_id作为对恶意代码的安全边界。验收须设置同安装同报告两条均合格的ready任务，真实见证不同request_key可领取两条，诚实记录该可达范围；另设超出当前授权的任务拒绝反例，不把前者误判为隔离失败或将后者省略。此次平台不新增会话凭据、run绑定或自动secret撤销；容器终止不使已泄露的安装secret失效，发现泄露须走既有正常管理员撤销/epoch流程，不能宣称本地回收替代服务端撤销。外层总会话不超过现有60秒；启动/隔离检查时间另有明确有界预算，不能让队列无期限保有凭据。关闭自动 restart/retry。
- 超时、控制器异常、receiver leader 提前退出或 Docker 客户端退出时，按完整资源身份回收 receiver 容器的全部进程并验证 cgroup 无残留；setsid/double-fork 不应逃出 cgroup。不能只 kill 客户端或原进程组。
- 控制器自身崩溃的孤儿回收必须有独立的可信监督机制和有界期限；实施前须明确由何者监督，不依赖已经崩溃的进程。API 与数据库生命周期不随 receiver 失败被误停。
- 本地终止不等于平台 pause/cancel/finish，也不释放远端租约；finish 可能已发时保持 unknown。任务善后走既有正常控制 API，不把 supervisor 变为代持员工 JWT 的自动补偿器。

## 7. 必须通过的分层验收（尚未执行）

| 层 | 必须验证的证据 |
|---|---|
| 纯配置/启动拒绝 | digest/worker hash错、UID映射错、危险挂载/capabilities/host namespace、缺规则、未登记listener、自动restart均在秘密交付前拒绝 |
| 网络真实反例 | 允许固定回环API可达；同栈其他端口、容器网关、DNS UDP/TCP、IPv6、外网、metadata、Unix/raw/netlink等旁路被内核拒绝；不将连接超时当唯一拒绝证据 |
| 文件/身份真实反例 | 读不到宿主和API秘密；不能写只读文件、改UID/规则、ptrace API、开新namespace、挂载设备；私有临时区超限受控 |
| 生命周期真实反例 | 无限输出/内存/派生进程、setsid/double-fork、leader早退、客户端失联、控制器崩溃均有界；完整ID/cgroup实证无残留，不误伤API/其他任务 |
| 协议回归 | 原固定receiver六步、正文绑定、ACK与finish unknown、无重试、默认关闭和真实peer拒代理头仍通过；旧metadata/SDK不扩权 |
| 正常策略真实链 | 仅合成数据，在新授权专用环境，以正常配置与真实TCP交付；P/T换源拒绝、撤权GET拒绝→pause成功→resume拒绝→cancel成功，停止不读正文/源node |
| 泄漏/持久化 | stdout/stderr/日志/inspect/镜像层/非业务日志落盘哨兵无正文、token、secret；允许API端口发送含秘密哨兵的未知路径、query、header/body及畸形HTTP，核对parser、access log、应用与异常收集器完整链；不只检查正常六步 |
| 输出真实性 | 伪造completed、合法UUID编码秘密、自报计数、退出码0及无限输出均不能使隔离控制器转发载荷或宣称业务完成；验证只生成自身固定基础设施状态，原始输出不留存 |
| 冻结/交接 | 最终源码、镜像digest、运行配置和内核规则清单一致，独立规格→质量复核，分层门禁和清理证据逐项记录；未运行项明示NOT_RUN |

攻击替代程序仅用于验收隔离边界，不进入正文准入集合，不接触真实业务资料或provider。外网反例优先使用自有合成网络目标，不扫描公共服务；具体资源预算与操作授权在实施计划审阅时确定。

## 8. 已选运行时与监督设计（待验证）

用户已选择专用 Linux 主机、rootful Docker Engine、systemd、nftables；本草案进一步要求 cgroup v2 和受支持的 seccomp。内核、Docker/systemd版本及LSM具体清单必须由后续专用环境能力检测固定，不假定当前macOS满足。缺任一强制能力就拒绝运行，不降级rootless/host network或关闭过滤。

### 8.1 可信管理与过滤位置

外层控制器和独立监督器属于可信宿主管理面，可访问Docker管理接口；此权限绝不传入API或receiver容器。它们只消费管理员固定的部署清单及本次生成的精确资源登记，管理API不暴露给receiver。rootful Docker并不意味着receiver以root执行。

nftables规则由宿主可信管理面**进入共同专用network namespace配置该namespace的OUTPUT路径**，不是仅在宿主FORWARD或宿主OUTPUT链加规则。回环流量不经过宿主FORWARD，不能据其无命中认定阻断有效。优先以真实内核socket UID匹配receiver，API使用不同UID；如启用userns-remap，必须核对实际映射，并证明允许及拒绝命中同一映射。无法识别身份即拒绝，不以宽网段放行代替。规则原子加载，IPv4/IPv6拒绝覆盖及链优先级须实证无更早宽放行旁路；规则和namespace绑定随资源登记冻结。

创建receiver前先建专用可信API环境、固定listener和规则；receiver启动时无凭据，固定程序只等待stdin。完成其完整容器ID、namespace inode、内核UID、cgroup路径与规则读回复核后，才可送入配置；准备失败关闭stdin并精确回收receiver。保留namespace引用直至receiver所有进程消失，避免API重建导致重新附着到不同namespace。API容器重启/替换、Docker daemon恢复或宿主重启都使本次会话失效，禁止自动恢复或喂入旧凭据。

### 8.2 独立systemd监督与精确回收

不是将Docker客户端放入systemd unit就宣称容器被监督。采用两个独立可信单元：控制器负责一次启动/attach/有界IO；独立watchdog负责登记资源的绝对期限和控制器存活。watchdog不得由控制器子进程承担，不接受receiver心跳作为续期。单元禁止自动重跑交付；宿主重启后的登记扫描只做精确核验与停止残留，不启动receiver。

登记在凭据交付前原子写入root-only目录，包含本次nonce、完整容器ID、镜像digest、daemon身份、network namespace、cgroup身份、控制器单元和单调期限。受信启动顺序须防“容器已创建但未登记”窗口：先持久记录创建意图及唯一nonce，再创建并绑定完整ID；未完成绑定的意图由watchdog只按精确nonce枚举核验，歧义保留且拒绝新交付，不扩大为按前缀删资源。Docker可能已受理创建但尚未返回或出现在枚举中：创建结果未明确收敛前，单次或多次零匹配均不能关闭登记，也不能据此证明无孤儿。创建调用失联/超时则保留本nonce未决意图并阻止本验收实例下一会话及秘密交付；持续有界核查迟到结果，发现目标后重新核完整身份并精确回收。期限内仍无法确认时记录isolation_unknown，持久未决意图保持关闭准入，不无限等待或静默清理登记；后续可信维护仅可继续核验/回收，不恢复交付。只有可信创建结果明确未产生对象且不存在仍在途请求，或已核验并回收目标且创建请求已收敛，才可关闭此意图。验收必须故障注入“请求已受理、控制器退出、首次枚举为空、随后目标出现”，证明期间下一会话被拒、迟到容器精确回收且其他容器未受影响；准备期不得向迟到容器发送凭据。watchdog先就绪才允许创建receiver；可检查准备期孤儿，不能只覆盖已拿到秘密的会话。

watchdog本身由可信systemd manager持续监督，而非只发一次readiness：设计要求受systemd核验的就绪通知、最长2秒的watchdog活性期限和有界停止期限；不得把receiver或控制器的消息当作watchdog续期。控制器与该watchdog建立BindsTo及启动顺序依赖，失去活性就停止控制器并关闭配置stdin；另设由systemd执行的root-owned固定停止处理器，覆盖watchdog异常、正常提前退出、被kill及停止后的ExecStopPost路径，不只依赖OnFailure。处理器不由已失效watchdog自身执行，也不使用receiver提供的命令或资源路径；按下一段的精确身份规则终止receiver全部cgroup任务，并独立核验。容器并非systemd单元普通子进程，所以仅KillMode或停止controller unit不算回收。

首次stdin写入前须重新核watchdog本次实例、活性与登记的一致性；失活信号/依赖停止一旦被检测，立即禁止继续写入，终止控制器并执行精确回收。不能承诺watchdog实际死亡到systemd检测间零字节交付，也不能撤回管道已缓冲字节，故这一窗口必须由独立停止处理器有界终止receiver，并在攻击测试中实际计时。失活使本会话永久失效；不自动恢复watchdog交付职能。若需恢复维护扫描，只允许处理登记及停止残留，不重放配置、不续期、不启动新receiver。可信systemd manager/内核同时失效不在本片保证范围。验收必须分别在readiness后、首次stdin写入前及交付中kill watchdog，并覆盖SIGSTOP导致活性超时、正常提前退出、失败处理超时，证明有界停止、不重放配置、不误停API。

watchdog或控制器停止receiver时先核daemon、完整ID、owner、cgroup与namespace；禁止按名称猜测或操作其他资源。TERM仅为短暂宽限，之后通过Docker强制停止并检查完整receiver cgroup；daemon不可用时仅可对预先登记、当前身份重新核验一致的专属cgroup使用内核终止机制，不能凭历史路径杀进程。最终须证明容器不运行且cgroup无任务；不能核验时报告isolation_unknown、保留证据、禁止后续秘密交付，不伪称回收成功。API、数据库及其他容器不随此动作停止。

### 8.3 预算建议与证据范围

以下是待用户书面审阅、后续真实反例验证的有限初值，不是已测性能：

| 项目 | 拟定限制 |
|---|---|
| 准备期 | 最多30秒，不传安装secret；超时由独立watchdog回收准备期孤儿 |
| 交付会话 | 从首次配置字节交给stdin起不超过60秒；无retry/restart |
| 独立检查/终止 | watchdog检查间隔不超过1秒；systemd对watchdog活性期限最长2秒；检测失败后禁止继续写入，TERM宽限0.2秒，强制终止及核验目标5秒；失效到检测存在有界窗口，不承诺零交付，超时明确unknown并阻止下一会话 |
| receiver资源 | memory上限128MiB，禁额外swap；pids最多16；CPU最多单核；nofile最多64；私有tmpfs最多8MiB/128 inodes |
| 原始输出 | stdout+stderr合计最多4KiB，实时分块丢弃；超限终止，控制器不缓存无界数据 |
| 业务响应 | 保持现有256KiB响应与每次10秒操作deadline，不放宽协议预算 |

上述期限在可信内核/systemd正常调度前提下验证，不承诺宿主挂死时的硬实时回收。交付截止后的回收宽限不延长合法会话预算；准备期、交付期、回收期分开记录。资源不足导致正常固定receiver无法完成时先停止、保留失败证据并重新审阅预算，不能自动提高限制。Docker memory/pids/CPU及独立监督必须从真实容器/cgroup状态读回，不只检查命令行参数。

## 9. 复审关口与交付限制

以下均须关闭后才编写可执行实施计划：

1. 独立复核共同netns/按内核身份过滤的可行性，特别是用户命名空间、IPv6和连接跟踪旁路。
2. 复核已选外层控制器直启分工、凭据管道和有界输出合同，不沿用对可信程序成立而对恶意程序不成立的假设。
3. 复核独立systemd watchdog、创建意图/完整ID绑定、生命周期预算与资源上限；具体实现必须在后续TDD计划中逐项实证。
4. 已选Docker Engine/systemd/nftables不等于具体主机可用；内核/LSM能力、版本及专用验收环境仍由用户另行提供或批准，当前不存在资源可用性或操作授权推断。
5. 用户审阅书面设计；随后单独编写并审阅TDD计划、资源预算和精确清理规则。

仅设计不要求启动应用或执行完整make check；本轮只验证引用、文档差异和合同一致性。不存在本片测试通过、镜像构建、容器创建、生产可信部署或R4b全部完成的结论。

既有R4B-CLEANUP-01继续独立延期，不为本片复用旧凭据或扩大清理权限。后续R5/R6/R7仍按[路线](../plans/2026-09-26-agent-task-plugin-runtime-roadmap.md)独立规格/计划推进。
