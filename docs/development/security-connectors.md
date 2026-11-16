# 外部连接器的凭据与出口边界

2026-11-16 安全修复适用于 MES REST、ERP REST 和管理端 AI 配置测试。

## ERP REST 出口配置

ERP APPROVE 权限只授权管理业务连接，不授权任意使用后端网络。后端执行
ERP 测试和定时同步前，使用部署配置 `ERP_ALLOWED_ORIGINS` 检查精确 HTTP(S)
origin 及其全部 DNS 解析地址。默认 `{}` 禁止所有 ERP REST 请求；mock 与入站
ERP 数据接口不受影响。后端可以正常启动，不会因未配置 REST 出口而中断其他模块。

生产部署在 `.env.production` 中添加一行**不加外层引号**的 JSON，例如：

```dotenv
ERP_ALLOWED_ORIGINS={"https://erp.factory.example:443":["10.20.30.15/32"],"http://erp-gateway.internal:8080":["192.168.40.0/24"]}
```

策略由运维维护，不能经连接器 API 修改。优先使用最小的 `/32`、`/128` 或专用
子网；同时允许公网、RFC1918 内网和 IPv6 ULA 的显式目标。origin 包含协议、
主机名和有效端口；省略默认端口等价，主机名不区分大小写。origin 条目不应包含
业务路径。CIDR 必须规范书写，不允许带主机位的网络地址。

`production-compose.sh` 只从固定 `.env.production` 接收这个可选设置，忽略 shell
中的同名值；旧 env 文件缺少该项时注入 `{}`。新初始化文件和示例默认也是 `{}`。
`oracle-production-remote.py` 的受信 controller 同样接受该可选项，并从固定文件
导出实际策略；旧文件缺项或留空时导出 `{}`，不接收调用者的同名 ambient 环境值。
Preview 的 `preview.env` 继续只包含其原有五个独立值；受信 `compose.preview.yml`
为 backend/graph-worker 明确写死 `ERP_ALLOWED_ORIGINS: '{}'`，不继承生产 ERP 目标。

**Oracle 升级需要有意重新安装受信 controller。** controller 的 Python loader、
生产/preview Compose 和 edge Caddy 配置是 root 安装的独立副本，普通代码发布不会
更新它们。运维应在审查后的可信 checkout 中，按既有安装流程显式执行
`sudo bash scripts/install-oracle-controller.sh`，再恢复自动发布；该安装使用部署锁并
重新生成 controller 校验清单。只更新应用镜像会遗漏新的 env 契约和 edge body cap。
本次代码修复没有执行安装或部署，也没有读取或更改真实 `.env.production`。

后端负责 ERP 定时同步；graph-worker 不执行 ERP 出口请求。直接运行 Python 后端
时可在其受控环境或 `.env` 中设置；开发 Compose 将 `.env`/受控 shell 中的该 JSON
传给 backend，缺项或空值默认 `{}`，graph-worker 不接收该设置。

每次逻辑请求先解析 DNS：全部结果必须落入该 origin 的 CIDR，否则拒绝。即使
配置了宽泛 CIDR，也拒绝 loopback、link-local（包括云元数据地址）、unspecified、
multicast 及映射到这些 IPv4 地址的 IPv6。验证后 HTTPX 连接的是选定的数字 IP，
同一次请求的重试保持该 IP；Host 和 TLS SNI 保留批准的主机名，证书验证仍开启。
客户端禁用环境代理与重定向，因此重试、二次 DNS 解析、代理环境和 Location
不能把请求带到另一个目标。下一次逻辑请求重新检查 DNS。部署仍应限制服务账号
可访问的网络；allowlist 代表对目标及其 DNS/CIDR 管理权限的信任。

ERP base URL 不允许 userinfo、query、fragment 或混淆的 IP/authority。
静态 endpoint 只能是以 `/` 开头的相对路径，禁止 `//`、query、fragment、反斜杠、
百分号编码及 `.`/`..` 路径段；业务分页/游标由 connector 的 params 构造。方法只允许
GET 和 POST。账号、密码、token 等必须放入 `auth_config` 的专用字段。

历史配置中不安全的 URL/path 不会回显给 VIEW 用户，也不能执行。响应只序列化
经过类型验证的白名单字段，业务 field_mapping 仅保留实际 ERP 列名的映射；
未知扩展、auth_config、retention 等非白名单内容不回显。升级前应盘点遗留含
URL 凭据的连接，在批准 origin 下重新录入凭据并移除 URL 中的凭据；不要将旧
URL 复制到日志或工单中。修复不会自动解密或迁移真实外部凭据。

## MES 的目标绑定

MES 更新比较规范化 origin、connector 类型和 auth 类型。跨越这些边界时，
丢弃保留的 auth_config，只接受本次显式重输的明文凭据，不复用客户端提交的
`*_encrypted`、`*_hash` 或掩码值。相同 origin 的普通更新继续保留凭据。

新存储的 REST 出站凭据使用 Fernet 将 origin/auth 上下文与明文一起认证。
连接器在发送前校验绑定；将密文复制到另一目标或改变 auth 类型会被拒绝。
Bearer、API key、Basic 的用户名和密码均受此约束。重定向保持禁用。

升级前旧 MES REST 出站密文没有目标绑定，**升级后会拒绝使用**；由有权限的
操作者在确认原目标后重新录入凭据。系统不会自动为旧密文追认一个可能已被修改
的目标。入站 API key hash 不需要因升级而重新生成；目标边界变更会清除保留的
整个 auth_config，包含旧入站 hash。

## AI 配置与测试

非持久化 AI 测试只使用本次显式输入的 API key；空值或 `********` 不会从数据库
或环境补出隐藏密钥。LLM 与 embedding 均适用，embedding 的 LLM key fallback
也只能来自本次显式输入。测试结果会提示重新输入，不会保存测试值。

保存 AI 配置时，对会消费密钥的 provider，变更有效 provider/origin 必须重新输入
对应密钥；检查包含 embedding provider、base URL 和 API key 对 LLM 设置的
fallback。原目标的掩码保存继续保留密钥；不使用 API key 的本地 provider 可正常
配置。API 返回可理解的 400，验证在任何配置写入或 provider 重建前完成。

## 验证入口

纯隔离回归 `backend/tests/test_connector_security.py` 使用合成密钥、内存 Fernet、
替代 DNS 答案和 HTTPX MockTransport，验证原目标发送、目标重绑拒绝、legacy
响应脱敏、Host/TLS SNI、重试固定 IP 与重定向拒绝，不访问真实 provider。
生产 env 回归位于 `test_production_compose_wrapper.py` 和 `test_init_production_env.py`。
数据库回归还包括 `test_ai_config_service.py`、`test_erp.py`、`test_mes_concurrency.py`；
只在独立、登记的测试 PostgreSQL 上运行。
