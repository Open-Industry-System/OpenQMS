# 元数据只读 Python SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付标准库同步、零运行时依赖的SDK wheel，封装十个既有plugin runtime接口，并以独立进程及正常策略HTTP证明协议兼容。

**Architecture:** SDK置于独立src包，不导入后端。DTO/codec、整体deadline transport、client生命周期分别拥有明确边界；服务端继续独占身份、授权、来源及业务规则。只允许现有平台运行操作，不开放业务写、模型或正文附件交付。

**Tech Stack:** CPython3.11+、stdlib http.client/ssl/socket/io/queue/threading/json/dataclasses、setuptools.build_meta、pytest开发依赖、现有owned PG15/normal-policy HTTP fixture与CI收据。

---

## 0. 批准、基线与执行纪律

- 依据：[已审SDK规格](../specs/2026-11-03-agent-metadata-python-sdk-design.md)。用户已明确审查通过，并要求计划明确整体timeout及finish超限/解码/绑定错误的unknown语义。
- 现有应用/CI代码基线 `64241d09aecf5e0f4ba8e4199b5d37b44c471b36`；规格落文基线 `25ec470987e7d63c34a19340f6a1a087fda8205c`。本计划前的规格澄清只是文档，不宣称SDK代码已存在。
- 唯一写工作树 `.worktrees/agent-main-semantic-integration`，分支 `integration/agent-main-semantic-20261102`。不改其他工作树、不更新main、不push/发布包/部署。
- 不改app runtime/授权/数据库模型/迁移/feature默认值、catalog/profile、fixedworker/hash/CLI。原固定worker真实进程验收必须保留。
- 每个行为先最小RED，确认正确断言失败后GREEN；不能拿collection、fake transport或本轮之前CI数字替代真实验收。所有临时安装/venv/PG/HTTP端口均为本片自有资源。
- 初始可用最低版本解释器为 `/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python`（3.11.15），不是本工作树的backend/.venv；另有python3.12（3.12.16）、python3.13（3.13.13）。setuptools79.0.1的集成bdist_wheel命令已确认可import；build/wheel外部distribution未安装，不能假设python -m build可用。

## 1. 文件/符号地图与依赖

| 文件（新建，除标注Modify） | 单一职责 |
|---|---|
| `sdk/python/pyproject.toml`, `README.md` | 包元数据、无runtime deps、使用与准入边界 |
| `sdk/python/src/openqms_agent_sdk/errors.py` | 安全异常与发送/unknown信息，不保留raw异常 |
| `sdk/python/src/openqms_agent_sdk/models.py` | frozen/slots DTO、tuple集合、隐藏敏感repr |
| `sdk/python/src/openqms_agent_sdk/_codec.py` | 十操作严格request与response codec，已知字段投影 |
| `sdk/python/src/openqms_agent_sdk/_deadline.py` | Deadline、BoundedResolver、raw socket IO与dial |
| `sdk/python/src/openqms_agent_sdk/_transport.py` | origin/固定路由/每请求连接/预算及HTTP分类 |
| `sdk/python/src/openqms_agent_sdk/client.py`, `__init__.py` | 安装/run client及十方法、finish生命周期、公开导出 |
| `sdk/python/tests/unit/` | 无网络fake clock/socket/transport协议反例 |
| `sdk/python/tests/loopback/` | 自有临时HTTP慢滴/redirect/提前close反例，无DB |
| `sdk/python/scripts/check-sdk.py`, `build-wheel.py` | 独立检查/受控离线构建与wheel验证，不变成runtime依赖 |
| `sdk/python/examples/metadata_session.py` | 明确fixture-only、只输出安全ID/计数/状态的样例 |
| `backend/tests/e2e/test_agent_sdk_process.py` | 正常策略、真实TCP、安装wheel的独立SDK进程兼容 |
| `backend/tests/e2e/sdk_process_support.py` | 私有stdin协议、进程监督/故障响应包装，测试专用 |
| Modify `Makefile`, `.github/workflows/test.yml` | 独立SDK gate及backend wheel前置，不改手动准入 |
| Modify `backend/tests/ci/test_workflow_contract.py`, `test_layer_selection.py` | 新gate/SDK目录docs-check及interop分类契约 |
| Modify `PROGRESS.md`, `docs/architecture.md`, `docs/development.md` | 当前事实、命令/证据/剩余门禁 |

顺序：Task1 → Task2(codec)与Task3(transport)可并行 → Task4(client) → Task5(wheel) → Task6(真实HTTP)与Task7(CI) → Task8收口。并行写scope不重叠；__init__由Task4最后统一导出。Lead独占任务间公共文件/文档/最终index与测试资源，implementer不stage/commit。

### 公共内部接口（任务间必须一致）

- `ClientConfig(base_url, tenant_slug=None, timeout=10.0, response_budget=4*1024*1024)`；timeout有限数字1..120，非bool；response budget64KiB..16MiB，请求固定1MiB。配置不自动读env/profile。
- `SDKError(operation, *, kind, status=None, may_have_been_sent=False, outcome_unknown=False)`为所有安全异常的基础签名；operation/kind只用库内固定安全名，不带raw内容。捕获底层错误后先取安全元数据，尽量在except块外抛出，避免保留自己的raw异常context；不保存original/response对象，默认traceback用from None，不承诺清除调用方debugger的任意局部内存。
- `Deadline(timeout, operation, *, clock=time.monotonic)`：`remaining()`、`check()`，一次操作唯一end，不能按阶段重建。
- `_RequestState(operation)`：`may_have_been_sent=False`，首次HTTP部分send可能发生前置True；DNS/TCP/TLS不置True。
- `EncodedRequest(body: bytes|None, query: tuple[tuple[str,str],...])`，`WireResponse(status:int, body:bytes, may_have_been_sent:bool)`；body repr隐藏。
- `encode_request(operation, parameters)->EncodedRequest`：只取本计划十操作允许参数，严格验证；无任意上传字段。
- `decode_response(operation, body, *, view='report', run_id=None, task_id=None, finish_status=None)`：严格JSON/DTO/绑定，返回下表DTO；无raw/extra缓存。
- `Transport.exchange(operation, *, token, request, deadline)->WireResponse`：只接受闭合operation常量；HTTP非成功抛安全HTTPError，其他异常携带may_have_been_sent。
- `InstallationClient(config, installation_id, secret)`拥有一个Transport/Resolver；`claim_run(request_key=...)`返回借用该transport的RunClient。parent需比run client活得久；close只释放本地资源，不发送finish/control。
- `RunClient.claim`只公开不含token的RunClaim元数据；token为私有引用。RunClient.close/有效finish不关闭parent transport；parent.close使所有借用client不能再发HTTP。

## Task 1: 包、错误与DTO基础

**Write scope:** pyproject/README、errors.py、models.py、初始__init__.py、tests/unit/test_foundation.py。

- [ ] 写基础RED：在配置SDK src路径的独立pytest中用`importlib.util.find_spec('openqms_agent_sdk')`断言存在，再验证SDKError安全表示、Config数值边界和DTO tuple/frozen；不先写生产实现。
- [ ] 运行 `PYTHONPATH=sdk/python/src "$PY" -m pytest --noconftest -c /dev/null sdk/python/tests/unit/test_foundation.py -q`，应为“包尚不存在/接口缺失”的断言失败，不连接DB。
- [ ] 配置包：

```toml
[build-system]
requires = ["setuptools==79.0.1"]
build-backend = "setuptools.build_meta"
[project]
name = "openqms-agent-sdk"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
readme = "README.md"
[tool.setuptools.packages.find]
where = ["src"]
include = ["openqms_agent_sdk*"]
```

- [ ] errors实现安全operation/kind/status/`may_have_been_sent`/`outcome_unknown`元数据；不插入输入值、URL、body或底层exception args。提供ConfigError、ValidationError、TransportError、RequestTimeout、HTTPError、ProtocolError、ResponseTooLarge、UnknownOutcome、ClientClosed/ClientBusy。UnknownOutcome始终True；包装用`raise safe_error from None`。
- [ ] models实现以下完整字段合同（UUID、aware datetime，集合tuple；输出私有/free text均repr=False）。dataclass不冒充类型运行时校验，codec负责验证：

| DTO | 字段 |
|---|---|
| RunClaim | run_id/task_id UUID；lease_epoch>=0；lease_expires_at aware；accepted_message_seq>=0；has_resume_checkpoint bool；无公开token |
| ClaimEnvelope（私有） | claim:RunClaim；token:str repr=False |
| Capability/Capabilities | id/allowed/required/projection(masked/raw/None)；capabilities tuple |
| RuntimeMessage/MessageBatch | message_id/sequence>=1/content隐藏；batch_id UUID或None/messages<=20/accepted_sequence>=0 |
| MessageAck/MessageHistory | accepted_sequence>=0；messages<=20/next_sequence>=0/complete bool |
| Verification | verification_id UUID/conclusion pending,passed,failed/is_verified bool |
| CapaContext | receipt_id/source_capa_id/report_id/factory_id UUID；projection_id固定masked.v1/data_class internal；document_no<=50/status,severity,product_line_code<=20隐藏；updated_at aware；digest lowerhex64；verifications None[report]或tuple[verifications] |
| EventPayload | stage None或str1..100/message None或str1..1000/completed,total None或int0..1e6；不加completed<=total规则 |
| ResultPayload | explanations/support/opposition/missing_information/conditional_recommendations五个tuple，默认空，每组<=20、每文1..2000，repr隐藏 |
| Source | receipt_id/source_capa_id UUID；projection_id固定masked.v1/digest lowerhex64/data_class internal |
| RuntimeEvent | event_id/task_id/run_id UUID；event_type/payload隐藏/sources0..20 |
| RuntimeResult | result_id/task_id/run_id UUID；data_class restricted/payload隐藏/sources1..20 |
| ReadonlyCheckpoint | checkpoint_id/task_id/run_id UUID；lease_epoch/tenant_generation/accepted_message_seq>=0；update_sequence>0；created_at aware；sources1..20 |
| FinishResult | task_id/run_id UUID；task_status/run_status沿服务端enum；lease_epoch>=0 |

- [ ] GREEN基础测试，并验证repr递归不包含`secret-sentinel`、`token-sentinel`或自由文本sentinel；普通UUID/数值可诊断但不自动日志。README明确fixture-only/业务只读不是零平台写。

## Task 2: 严格codec（Task1后可与Task3并行）

**Write scope:** `_codec.py`、tests/unit/test_codec.py、test_requests.py、test_responses.py；不改models/errors公共合同。

- [ ] 先测试以下请求映射和上下边界；全部十操作都有准确method/path/body/query的正向control，缺字段/extra身份/bool当int/任意对象str化必须在transport前失败：

| operation | method/path | 唯一允许输入 |
|---|---|---|
| claim | POST /claim | installation_id、secret20..200、request_key1..100，无Bearer |
| capabilities | GET /capabilities | 无body/query |
| claim_messages | POST /messages/claim | limit1..20默认20 |
| ack_messages | POST /messages/ack | batch_id、through_sequence>=1 |
| capa_context | GET /capa/context | report_id None时省略，view report/verifications |
| record_event | POST /events | key1..100、type progress/query_completed、EventPayload、receipt_ids0..20；query_completed至少1 |
| save_result | POST /results | key、ResultPayload、receipt_ids1..20 |
| save_checkpoint | POST /checkpoints | key、receipt_ids1..20，不含state/epoch/cursor |
| message_history | GET /messages/history | cursor0..2^63-1、limit1..20，规范十进制 |
| finish | POST /finish | status completed/failed，仅此字段 |

- [ ] 先跑RED：`PYTHONPATH=sdk/python/src "$PY" -m pytest --noconftest -c /dev/null sdk/python/tests/unit/test_codec.py sdk/python/tests/unit/test_requests.py sdk/python/tests/unit/test_responses.py -q`。
- [ ] 编码逐操作构造，不通用asdict全上传；JSON采用ensure_ascii=False、allow_nan=False、紧凑separators，统一检查1MiB请求预算。UUID只接受UUID或显式合法UUID字符串；key与文本不擅自strip/改值，来源不自行改变服务器排序去重语义。
- [ ] 解码使用严格UTF8、拒NaN/Infinity和重复对象键，再按已知字段生成DTO。未知additive字段逐层丢弃，不能保留raw/extra。测试示例：

```python
def test_report_context_does_not_invent_children(report_response):
    value = decode_response('capa_context', report_response, view='report')
    assert value.verifications is None

def test_history_cursor_may_return_to_watermark():
    payload = b'{"messages":[],"next_sequence":3,"complete":true}'
    page = decode_response('message_history', payload)
    assert page.next_sequence == 3 and page.complete
```

- [ ] report view不要求children、不用report-only重算完整digest；verifications view要求显式tuple。source_capa_id=report_id、显式requested report_id以及带task/run的响应绑定都检查，不能解JWT猜target/factory。
- [ ] table-driven反例覆盖missing/错误类型/关键enum/naive timestamp/重复键/known projection或data_class变化；unknown可选capability ID不强迫升级，未知字段秘密不在DTO/repr。
- [ ] GREEN全部codec测试，不修改服务器schema/canonical目录。

## Task 3: 整体deadline与标准库transport

**Write scope:** `_deadline.py`、`_transport.py`、tests/unit/test_deadline.py、test_resolver.py、test_transport.py、tests/loopback/test_deadline_http.py。Task1依赖，禁止改client/codec。

### 明确timeout合同

一次SDK操作在编码前创建`D=monotonic()+timeout`；DNS、全部地址候选、TLS、partial sends、status/headers/chunk framing/body/trailers、decode与binding共享它。成功收到一字节不能重置T。CPU/C与OS调度不是hard realtime，CPU阶段前后及返回DTO前check，晚到结果不得返回成功。

每client最多一个懒启daemon DNS worker、一个outstanding job，每job独立有界result queue+cancelled标志。worker仅getaddrinfo，绝不持有token/body、创建socket或发送HTTP。caller按remaining等待，timeout后丢弃迟到结果；旧解析卡住时后续resolve fail-fast，不创建新worker或无限排队。close不无限join。不能宣称取消OS DNS，也不声称任意多个client的全局线程数有界。

- [ ] 先RED fake clock测试：DNS、多候选connect、TLS、partial writes、每次raw read都消费同一budget；deadline在最后decode/binding之后超限也不能返回成功。
- [ ] 实现Deadline核心（operation为安全固定名）：

```python
class Deadline:
    def __init__(self, timeout, operation, *, clock=time.monotonic):
        self._clock, self.operation = clock, operation
        self._end = clock() + timeout
    def remaining(self):
        left = self._end - self._clock()
        if left <= 0:
            raise RequestTimeout(self.operation, kind='deadline')
        return left
    def check(self):
        self.remaining()
```

- [ ] 实现BoundedResolver：锁内设置busy/job代次，不持锁做DNS；独立结果queue防跨请求串结果，所有候选从getaddrinfo结果直接按数字sockaddr连接，不再次调用socket.create_connection(host)。DNS失败信息转安全kind，不含host/原exception args。
- [ ] 每个候选前settimeout(D.remaining)，失败close后再check；TLS使用原hostname作SNI/验证名，`do_handshake_on_connect=False`后重算remaining再handshake。默认verify开启，不提供不安全context配置。
- [ ] 在BufferedReader下接deadline，保持真实makefile IO refs；不能仅在response.read外包timeout。核心：

```python
class DeadlineRaw(io.RawIOBase):
    def __init__(self, raw, sock, deadline):
        self.raw, self.sock, self.deadline = raw, sock, deadline
    def readable(self): return True
    def readinto(self, target):
        self.sock.settimeout(self.deadline.remaining())
        count = self.raw.readinto(target)
        self.deadline.check()
        return count
    def close(self):
        try:
            if not self.closed: self.raw.close()
        finally:
            super().close()
```

- [ ] Socket门面makefile仅支持HTTP使用的rb：真实`raw=sock.makefile('rb',buffering=0)`后包DeadlineRaw，再io.BufferedReader。门面close调用真实sock.close，不shutdown/detach/os.close、不自己改私有_io_refs；connection提前close后response依靠raw ref仍可读。
- [ ] 发送不用SSLSocket.sendall的固定timeout循环，而是逐次partial send：

```python
view = memoryview(body)
while view:
    real.settimeout(deadline.remaining())
    state.may_have_been_sent = True
    sent = real.send(view)
    deadline.check()
    if sent <= 0:
        raise TransportError(operation, kind='connection_closed', may_have_been_sent=True)
    view = view[sent:]
```

- [ ] 选择直接http.client+urllib.parse，每请求新连接，Connection:close；不经过urllib.request/global opener，因此无自动proxy/netrc/cookie/redirect。仍须处理http.client.getresponse的will_close提前关闭；finally先response.close再connection.close，所有失败关闭真正owner且不复用超时流。
- [ ] origin只root、无userinfo/query/fragment；HTTP仅loopback，localhost实际IPv4、HTTPS原hostname仍用于TLS验证。固定operation表拒任意URL/路径。tenant header空值/控制字符拒，所有body有界bytes，不支持任意file-like上传。
- [ ] 读取Content-Length预算预判及N/N+1，实际bytes检查，unsupported encoding拒绝；fixed-length提前EOF不能当完整成功；只解析支持JSON成功体。非2xx不给错误body进入异常，3xx不follow，5xx保留可能发送标志。
- [ ] GREEN unit后运行自有127.0.0.1:0 loopback案例：slow status/header、chunk-size/CRLF/trailer、fixed/chunked/EOF body滴流、100 Continue、Connection:close后完整body。证明T不是N*T；连接/线程/端口由fixture关闭，无live DNS或远端地址。SDK unit不把这些网络案例伪装pure。

## Task 4: 十方法client与finish统一unknown

**Write scope:** client.py、最终__init__.py、tests/unit/test_client.py、test_finish.py、test_credentials.py。依赖Task2/3。

- [ ] FakeTransport记录每个exchange且返回明确WireResponse；先RED验证十方法固定route、安装secret仅claim body、run Bearer仅九方法、无自动ACK/轮询/POST重试/凭据域fallback。
- [ ] 所有方法用一个私有调用管线：创建D→本地validate/encode→D.check→exchange→D.check→decode→task/run binding→D.check→返回。Config/encode/request budget错误必须0次exchange。
- [ ] finish的外层guard包住整个发送后链；明确4xx拒绝按HTTPError，其他无法确认完整成功统一UnknownOutcome。必测分类：

| 已可能发送后的结果 | finish必须怎样 |
|---|---|
| timeout/断链/半body/500/503/redirect | unknown=True，不重发 |
| Content-Length/实际body超预算 | unknown=True，不泄漏普通ResponseTooLarge为“未完成” |
| invalid UTF8/JSON/重复键/NaN/缺字段/错误DTO | unknown=True |
| wrong run/task、status不一致、最终deadline已过 | unknown=True |
| 明确409未ACK/401/403/404/422/400/410 | 安全HTTPError，不靠错误JSON解析，不断言任务全局未完成 |
| 完整成功、绑定及deadline均正确 | 成功关闭本地run、清token引用 |

- [ ] 先写反例：

```python
@pytest.mark.parametrize('fault', ['oversize','decode','schema','wrong_run','wrong_task','late'])
def test_finish_post_send_faults_are_unknown(finish_client, fault):
    client, wire = finish_client(fault)
    with pytest.raises(UnknownOutcome) as raised:
        client.finish(status='completed')
    assert raised.value.outcome_unknown is True
    assert wire.calls == 1
    assert client.state != 'closed_successfully'
```

- [ ] unknown可把本地run标为uncertain来阻止意外再发，但不能标成远端failed/completed；不自动查询user/admin API。parent installation client不自动claim新run。
- [ ] 有效finish后任何旧run client调用本地拒绝且0 HTTP；close无HTTP、无自动finish、无安全擦除承诺。
- [ ] GREEN全部client及repr/exception链sentinel测试，公开API只导出确定的classes/methods，无任意get/post/request。

## Task 5: wheel独立性与SDK检查入口

**Write scope:** scripts/check-sdk.py、build-wheel.py、tests/unit/test_packaging_contract.py、README、examples/metadata_session.py。

- [ ] RED检查SDK wheel不存在时明确失败，不skip；METADATA的Name/Version/Requires-Python/Requires-Dist及包文件范围有断言。
- [ ] 在本轮临时source副本构建（不污染共享venv/源码），已有setuptools79支持离线构建：

```bash
"$PY" -m pip wheel --no-deps --no-build-isolation --no-index \
  --wheel-dir "$OWNED_WHEEL_DIR" "$OWNED_SDK_SOURCE"
```

OWNED_WHEEL_DIR/OWNED_SDK_SOURCE必须由该检查入口新建且验证属于本轮目录，不能指向用户目录；不隐式pip install未知构建器。

- [ ] venv不带system-site-packages；ensurepip后用新venv的pip `--disable-pip-version-check install --no-index --no-deps wheel.whl`，不把后端依赖或PYTHONPATH源码注入子进程。
- [ ] 在离repo的tmp cwd以`python -I`验证package/API可import、backend/provider模块不存在/未import、无runtime Requires-Dist。实际以3.11/3.12/3.13可用解释器做wheel/runtime smoke；每项区分实际结果，不拿PATH3.13当3.11证据。
- [ ] check-sdk脚本分unit（fake无网络）、loopback（自有TCP无DB）、wheel三个显式层；复用现有stdlib/pytest gate_results模块的统计方式，不能importbackend pure bootstrap（它依赖Pydantic/psycopg）。SDK独立job仅装pytest与setuptools开发工具，不装backend requirements。
- [ ] 无网络unit入口在pytest前加SDK测试专用stdlib audit guard，禁止意外Python connect/DNS/bind；loopback层不装该guard，由fixture严格自有端口与清理。收据包含真实selected/pass/fail/error/skip/xfail/xpass/warnings/exit，不把collection当通过。
- [ ] fixture-only样例只读显式stdin配置（测试controller输入临时凭据），不读.env/profile，不打印secret/token/message/payload；无任意worker执行入口，不改官方CLI/hash。

## Task 6: 安装wheel的真实normal-policy HTTP兼容

**Write scope:** backend/tests/e2e/test_agent_sdk_process.py、sdk_process_support.py；SDK测试probe可置于sdk/python/tests/support/。

- [ ] 复用owned_local_trial+local_trial_server，父侧正常admin grant/用户task/精确短期策略；不使用改canonical DIRECT的旧process_tenant。真实SDK进程不使用ASGITransport，不给其user/admin JWT或DB URL。
- [ ] wheel由Task5已构建路径显式传入`OPENQMS_SDK_WHEEL`；缺失立即失败、不skip。fixture只离线安装现有wheel；不在每条测试中联网build。
- [ ] child用独立venv python -I、tmp cwd、最小env、stdin pipe输入安装secret及后续操作。父侧监督有限时限，finally回收自有进程；stdout只安全计数/ID，caller保存key，协议probe不eval/exec消息。
- [ ] RED→GREEN覆盖十接口正常流：claim/capabilities/message batch/ACK/context两view/event/result/checkpoint/history/finish；父侧Witness证实实际HTTP、新receipt/同digest、平台记录与CAPA业务snapshot不变。SDK通信成功不是SDK新worker准入。
- [ ] partial ACK/已覆盖ACK、history after99返回水位、同key同payload ID相同/改payload409、checkpoint位置变更、未ACK finish409、完成epoch fencing；暂停/restart/revoke/跨目标/租户/来源失权由父侧正常user/admin API插入，SDK不含控制方法。
- [ ] finish成功commit之后在测试响应层注入oversize/坏JSON/wrong run或task/断连，父侧证实任务实际completed且SDK统一unknown，calls=1。故障包装只在测试app，不能改生产handler或扩权。
- [ ] 保留旧fixedworker/CLI原样真实回归及字节hash前后检查，记录两种验收并列，不把fixture策略批准当SDK生产部署批准。

## Task 7: Make/自动CI/分类与文档

**Write scope:** Makefile、.github/workflows/test.yml、backend/tests/ci/test_workflow_contract.py、test_layer_selection.py、docs/development.md、sdk README。

- [ ] 先RED：check-sdk不依赖check-test-db/服务端依赖；interop节点明确backend；docs-check识别sdk/；新sdk-checks job无PG/Secrets/backend requirements/continue-on-error，checkout不保留凭据。
- [ ] 新Make目标check-sdk-unit、check-sdk-loopback、check-sdk-wheel、check-sdk聚合，显式SDK_PYTHON_BIN（默认python3，可指向核验解释器）。`check`加入check-sdk；backend job在真实HTTP验收前build wheel并把路径明确传给pytest子进程（runner资源白名单仅新增此专用路径，不携带任意环境）。
- [ ] 自动workflow新增sdk-checks Python3.11/3.12/3.13矩阵，无数据库/模型secret；安装明确开发工具版本，执行make check-sdk，保留其安全收据。每job保持五个provider变量空值、E2E_MODE不设置、contents read、checkout persist-credentials false；不更改手动main-only gate。
- [ ] 现有workflow test遍历新增job但不锁exact job集合；新增SDK自身contract，不重写旧backend/browser/frontend证据链或清理规则。新增可选route不让旧SDK失败，SDK支持的既有route被删除/改变则compat失败。
- [ ] 本地用清洁env运行workflow/classification pure回归和SDK三个独立检查；有actionlint则跑，无工具不安装/不声称通过。

## Task 8: 独立复核、完整门禁与交接

**Write scope:** SDK/后端协议必要修正按发现归属；PROGRESS、docs/architecture、独立SDK交接文档。

- [ ] 每Task完成做规格→质量两阶段复核，Important先修；不以implementer通过自报代替Lead源码/diff/实际测试。共享公共文件有序修改，所有变动可追溯本片。
- [ ] 重新冻结实际执行文件与SDK wheel hash、记录各解释器版本；新建本片独占PG15/登记/nonce/随机回环端口，不复用已清理的CI资源。
- [ ] 运行SDK unit/loopback/wheel与真实HTTP、固定CLI回归；再相关backend及完整deterministic backend/browser/前端/SDK组合门禁。重新核node集合，不能套旧3850/3831或历史3827通过数。
- [ ] 真实provider仍NOT_REQUESTED；scanner是否需重跑按实际影响与授权，不借旧通过数。任何必选层skip/零选中/xfail/xpass不算通过，原baseline可选未配置项独立报告。
- [ ] 全部后台jobs/required teammates收齐后核精确owner/ID/卷/零client/子进程，再清理本片自有资源；raw credential/JUnit不提交，过滤日志/wheel/hash/收据按边界保留。
- [ ] 更新已实现事实、限制和后续R4b/R5/R6/R7；仅在本地分支提交经复核成果，main/push/包发布/部署/准入均不执行。

## 自审覆盖

规格§1–3→Task1/4；§4–5→Task2/6；§6与本次finish审查补充→Task4/6；§7整体deadline与安全→Task3/4；§8固定worker→Task6；§9独立wheel/CI→Task5/7；§10交接→Task8。timeout整条路径及finish所有post-send校验失败都有独立反例，不留隐式自动重试或权限升级。
