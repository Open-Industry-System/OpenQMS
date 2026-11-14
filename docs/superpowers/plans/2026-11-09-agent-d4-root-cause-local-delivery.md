# D4 根因受限文本本地受控交付 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在自有 dev 租户，以正常授权和固定本地接收器交付仅 `d4_root_cause` 的受限候选；来源未知、来源范围不覆盖或权限失效时不交付。

**Architecture:** CAPA/FMEA 声明业务上下文与来源合同，平台维护部署准入并复用统一授权内核。来源证明、字段修订、两层来源范围及受限收据仅保存元数据；正文不落新库。独立标准库接收器只运行固定协议，不改变旧元数据 worker、SDK 0.1.0 或生产默认值。

**Tech Stack:** Python 3.11+、FastAPI/Pydantic 2、async SQLAlchemy、PostgreSQL15/pgvector、手写 public/tenant Alembic delta、stdlib 固定进程、pytest、既有分层 Make/CI。

**计划审阅修订：** 用户审阅初稿后要求修正三处实施边界；当前R2前移消息门禁、为blocked任务单独记录请求指纹、补撤权后仍可停止的有序API验收。2026-11-10用户明确选择“R2通过，子代理驱动执行”；当前T1已双复核签收，后续按原依赖执行，已批准v6规格的业务边界不变。

---

## 0. 批准状态、基线和执行纪律

- 2026-11-09 用户明确选择“通过v6，进入实施计划”；依据为[已确认v6规格](../specs/2026-11-08-agent-d4-root-cause-local-delivery-design.md)。该选择授权编写本计划，**不等于当前已授权执行命令或启用功能**。
- 起始提交 `65f8ca9c49176a0116ef35e1fa0c2e296e3e22d8`；工作树 `.worktrees/agent-main-semantic-integration`，本地分支 `integration/agent-main-semantic-20261102`。执行前重新检查 HEAD/dirty files；不覆盖其他用户/Agent改动。
- 本轮编写计划只修改文档。执行阶段仍不 main/push/PR/发包/部署、无模型/外部DNS/附件/业务命令。已清理的SDK PG及执行口令不能复用。
- 每任务先写可观察的失败断言→真实RED→最小实现→GREEN→规格复核→质量复核→精确提交。复核 Important 未关闭不得进入依赖任务。收集节点不是运行通过。
- 修改公共文件严格串行；下文 Files 是任务write scope。业务原动作继续按既有状态、审批、审计及outbox规则执行；**不是把这些员工写入变成插件权限**。
- 不修改冻结 tv001–tv006、DDL快照/manifest、旧metadata worker/hash/profile、SDK目录或旧internal收据消费者的语义。旧元数据安装不授正文；正文安装不借授旧summary权限。

### 执行入口和资源预算

执行选择确认后，Lead可在本片新建：一个带随机owner标签的缓存PG15容器、一个专属卷、一个 `_test` 主测试库及一个不同名应用哨兵库；随机数字回环端口。2026-11-10用户另明确允许既有 `mig_db_url` fixture 在**同一个已登记且核验owner的独占实例**内，串行创建/精确teardown `qms_migtest_<UUID>_test` 一次性迁移库；此授权不增加容器/卷、不涉及其它实例/任意数据库，不删除主测试库或哨兵库。每个迁移库仅按本fixture创建的精确名字清连接/drop，结束及最终清理复核零残留。预算最初未单列该既有fixture行为；此前完整make check已运行它，随后只读核验残留为0。仅使用现有本机Unix Docker context及缓存 `pgvector/pgvector:pg15`，不pull、不prune、不停止其他服务。HTTP/worker均fixture-owned；不启动共享开发服务器。

凭据只写本片私有0700目录中的0600执行文件，登记按 `tests.ci.owned_resources` 格式不含口令。所有后端门禁从同一登记/URL派生，不在正文/命令行打印DSN。CLI配置只含临时安装凭据与预期绑定；子进程无用户/admin JWT、DB或provider凭据。

本地命令从仓库根执行：

```sh
PY=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
"$PY" -I -B -c 'import sys,importlib.metadata as m; print(sys.version.split()[0]); print(m.version("setuptools")); print(m.version("pytest"))'
"$PY" -B scripts/check-ci-pure.py tests/services/agent/permissions -q --tb=short
```

第一条必须实际验证解释器/工具，SDK gate仍要求实际setuptools79.0.1。缺工具不安装到共享解释器、不降pin。DB用例必须经新登记的环境运行；不能用pure模式把DB错误改成skip。

Lead私有控制器白名单保留PATH/HOME/TMPDIR，显式传 `TEST_DATABASE_URL`、同值 `DATABASE_URL`、`OPENQMS_TEST_RESOURCE_FILE`、精确 `PG15_CONTAINER` 和artifact/SHA；普通provider键为空，`E2E_MODE`不设置，额外libpq路由变量不传。复用runner及bootstrap的dotenv/凭据隔离，不复制旧profile。

## 1. 文件/符号地图

下列为**拟新增**路径，不表示已有实现。单一职责如下：

| 文件 | 职责 |
|---|---|
| `backend/app/services/agent/permissions/derived_sources.py` | frozen精确来源元组及范围匹配，纯逻辑 |
| `backend/app/services/agent/permissions/context_contracts.py` | 数据分类/来源依赖内部声明类型，不进manifest |
| `backend/app/services/capa_agent_capabilities.py` | CAPA正文capability及内部上下文声明 |
| `backend/app/services/fmea_agent_sources.py` | FMEA来源声明、先鉴权的标量定位及有界单节点版本 |
| `backend/app/models/capa_d4_delivery.py` | 字段修订/来源证明两表，元数据无正文 |
| `backend/app/models/agent_derived_source.py` | 长期/任务范围旁表及受限收据，元数据无正文 |
| `backend/app/models/agent_task_request.py` | 不依赖grant是否存在的不可变请求指纹；只作幂等比较，不作授权 |
| `backend/app/schemas/agent_d4_text.py` | 来源范围输入、声明、创建响应及正文输出DTO |
| `backend/app/services/capa_d4_provenance.py` | 修订记录、显式声明签发、supersede及验证版本 |
| `backend/app/services/agent_runtime/derived_source_grants.py` | 当前父grant/来源旁表装载、持久化与参数重放比对 |
| `backend/app/services/agent_runtime/deployment_profiles.py` | 平台准入绑定/最低能力/投递元组，独立于业务声明 |
| `backend/app/services/agent_runtime/local_d4_text_policy.py` | 第二策略槽、私有词表、实际固定hash与binding HMAC |
| `backend/app/services/agent_runtime/d4_text_delivery.py` | 只读快照、双层范围/版本最终检查及原子release记录 |
| `backend/examples/readonly_d4_text_receiver.py` | 自包含stdlib固定接收器，不import app/SDK |
| `backend/scripts/agent_d4_text_local.py` | 私有配置、hash/origin验证、自有进程组监督 |
| `backend/tests/e2e/d4_text_local_harness.py` | 受控真实配置/正常API/真实TCP测试controller |
| `backend/tests/e2e/test_d4_text_local_process.py` | 必选backend真实进程场景 |
| `docs/development/capa-d4-local-text-delivery.md` | 运维前提、声明非降敏、错误/撤销与清理 |

现有共享接缝：`permissions/types.py/access.py/catalog.py`；`agent_runtime/task_service.py/runtime_access.py/plugin_registry.py/task_reads.py/task_controls.py/run_auth.py/runtime_messages.py/routes.py`；`capa_current_access.py/capa_service.py/capa_verification_service.py/audit_service.py`；`config.py/main.py/database.py/core/tenant_context.py/core/agent_local_trial.py`；`schemas/agent_plugin.py/agent_task.py/capa_verification.py`及`api/capa.py/agent_runtime.py/agent_tasks.py`。不能将共享函数的metadata特例简单再复制一份正文特例。

### 统一新接口（后续任务沿用这些名称）

```python
# derived_sources.py: 不授权，仅精确比较；所有身份/父grant仍由原内核检查。
from dataclasses import dataclass
from uuid import UUID
from app.core.permissions import Module

@dataclass(frozen=True, slots=True)
class DerivedSourceScope:
    target_report_id: UUID
    derived_projection_id: str
    source_module: Module
    source_projection_id: str
    fmea_id: UUID
    cause_node_id: str

def source_intersection_covers(current, plugin_scope, task_scope):
    return (current is not None and plugin_scope is not None
            and task_scope is not None
            and current == plugin_scope == task_scope)
```

业务常量 `TEXT_CAPABILITY="capa.d4.root_cause_candidate.masked.v1"` 属CAPA；部署常量 `TEXT_PROFILE="local_d4_root_cause_text_v1"` 和 `START_MESSAGE="deliver_d4_root_cause_candidate_v1"` 属平台profile绑定，接收器同字面量单独冻结并以契约测试比对，不能为复用而import后端。

内部上下文声明定义 `ContextContract(capability_id, data_class, source_projection_id)`；只有正文合同要求来源，原metadata合同无新增来源要求。`SourceProjectionContract`定义owner/minimum level/标量坐标/版本方法。两者是代码内只读常量，不新增声明数据库或公开FMEA工具。

SQL服务接口：

- `current_report_coordinates(db, actor_scope, report_id)`只返回report/factory/PL，不返回ORM或D1–D8字段。
- `visible_fmea_source(db, actor_scope, fmea_id)`先刷新权限/作用域；不可见一律 `SourceUnavailable`，不查节点。
- `failure_cause_version(connection, visible_source, cause_node_id)`先计唯一节点/字节数，再只取该节点；返回opaque HMAC，不返回整图。
- `record_root_revision(db, *, report_id, actor_id, write_path)`调用方已持CAPA父锁，不commit；真实变化后追加。
- `issue_source_proof(db, *, report, verification, actor_id, declaration)`不commit；只供创建验证路径调用。
- `load_current_source_state(db, *, report_id)`读取最新修订/active证明的受信元数据；不能自动签发/补授权。
- `get_d4_root_cause_text(db, identity)`为唯一runtime正文服务；完成最终检查后原子commit受限收据/审计。

异常在T1定义于叶子模块 `backend/app/services/agent/permissions/derived_sources.py`，FMEA与CAPA服务共同导入（不得让FMEA helper反向import CAPA provenance形成循环）；不带原始SQL/HTTP/JSON异常作为公开消息或cause。API先捕获专用冲突再捕获其ValueError基类，固定响应如下：

```python
class SourceUnavailable(PermissionError):
    def __init__(self):
        super().__init__('Source unavailable')

class SourceRevisionConflict(ValueError):
    def __init__(self):
        super().__init__('Source revision conflict')
```

`SourceUnavailable` 对应 `403 {"detail":"Source unavailable"}`；仅新声明签发的修订冲突对应409，旧400/403/404路径不变。

T9同文件的内部类型/辅助函数合同如下，不能在实现时以未校验dict替代：`SourceState`含当前report坐标/latest_revision/active_proof/规范source_scope；`RootCandidateSnapshot`含report坐标、revision_id、proof_id、field_hmac、source_version、source_proof_digest、policy_binding、rule_version及隐藏repr的候选text；`EncodedRelease`含预先分配的receipt_id/created_at、最终projection_digest、隐藏repr的JSON bytes和由该bytes构造的no-store Response。`require_current_text_authority(db, identity, state) -> None`核当前父grant/P/T/来源读取权；`build_root_candidate(*, binding, state) -> RootCandidateSnapshot`只读有界快照；`encode_bounded_release(identity, snapshot, *, limit) -> EncodedRelease`做DTO/JSON预算；`verify_release_is_current(db, identity, latest, snapshot) -> None`做版本/证明/坐标最终比较；`add_restricted_receipt_and_audit(db, identity, latest, release) -> None`只添加预定元数据，不commit。定义职责在T9，不是新增公开服务。

T5同文件定义 `FixedWire` 的六次HTTP流程，私有config含origin/tenant_slug/installation_id/secret/request_key/expected_report_id。方法：`claim(config) -> ClaimView(run_id,task_id,token)`；`require_body_capability(claim) -> None`调用固定capabilities GET；`claim_start(claim, *, limit=1) -> BatchView(batch_id,messages)`，message仅ID/sequence/content；`read_body(claim) -> DeliveryView(receipt_id,report_id,text,labels,versions)`；`validate_delivery(claim,config,delivery) -> None`严格校验全部安全标签和绑定；`ack_start(claim,batch) -> None`只确认该实际batch前缀；`finish_once(claim) -> FinishView(run_id,task_id,status)`完整确认completed。所有token/text/content/原始bytes隐藏repr，未知原始dict丢弃。路由分别为现有claim、capabilities、messages/claim、新正文GET、messages/ack、finish；除claim外仅run token，绝不接受任意URL。固定视图只服务该脚本，不作为SDK或通用HTTP接口。

## 2. 依赖顺序

`T1合同/默认拒绝 → T2证据/范围/请求身份迁移 → T3来源读取/修订 → T4签发 → T5接收器定稿 → T6服务端消息门禁 → T7平台双槽准入 → T8双层来源授权 → T9正文交付 → T10正常配置HTTP/CI分类 → T11冻结门禁/交接清理`。

T5可在T1后用自有fake/loopback协议完成；不得并行编辑T1/T7的公共文件。T7须等T5定稿实算hash后才能存在合法正文准入；禁止先放零hash/任意hash跑正向。生产可信集合全程为空。

**逐提交安全门槛**：T6必须在T7/T8任何正向正文准入之前完成并复核；否则正文profile始终拒绝消息交付，不能把它当legacy profile略过检查。无论首次可claim落在哪个任务，从首次允许正文安装claim的那个提交起，必须同提交实跑非字面量消息的首次领取/重领/history/ACK真实API负向验收；不延迟到T10，不用默认false或接收器不ACK代替服务端门禁。

---

## Task 1: 纯合同、DTO与默认关闭门禁

**Files / write scope:**
- Create: `backend/app/services/agent/permissions/derived_sources.py`
- Create: `backend/app/services/agent/permissions/context_contracts.py`
- Create: `backend/app/schemas/agent_d4_text.py`
- Create: `backend/tests/services/agent/permissions/test_d4_text_scopes.py`
- Create: `backend/tests/capa/test_d4_text_contracts.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/core/tenant_context.py`
- Modify: `backend/app/services/agent_runtime/routes.py`
- Modify: `backend/app/services/capa_agent_capabilities.py`

- [x] 写完整纯反例表，先RED：

```python
from dataclasses import replace
from uuid import UUID
import pytest
from app.core.permissions import Module
from app.services.agent.permissions.derived_sources import (
    DerivedSourceScope, source_intersection_covers,
)

def source(node):
    return DerivedSourceScope(UUID(int=1),
        'capa.d4.root_cause_candidate.masked.v1', Module.FMEA,
        'fmea.failure_cause.reference.v1', UUID(int=2), node)

@pytest.mark.parametrize('p,t,want', [
    ('a','a',True), ('a','b',False), ('b','a',False),
    ('b','b',False), (None,'a',False), ('a',None,False),
])
def test_exact_intersection(p, t, want):
    assert source_intersection_covers(source('a'),
        None if p is None else source(p),
        None if t is None else source(t)) is want

def test_source_scope_does_not_cross_report():
    a = source('a')
    assert not source_intersection_covers(
        a, a, replace(a, target_report_id=UUID(int=3)))
```

- [x] Run `"$PY" -B scripts/check-ci-pure.py tests/services/agent/permissions/test_d4_text_scopes.py -q --tb=short`，预期因新模块缺失或谓词错误失败；保存日志，不把collection当RED。
- [x] 实现上节frozen类型与精确谓词。CAPA新增正文context spec（VIEW/DENY/masked/target_required），内部contract标restricted/source dependency；基线不翻DIRECT。`CapabilitySpec`公开字段/manifest不添加来源投影。
- [x] DTO实际代码采用严格类型及额外字段拒绝：

```python
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator
from uuid import UUID

class SourceDeclaration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    declares_complete_coverage: StrictBool

    @field_validator('declares_complete_coverage')
    @classmethod
    def must_explicitly_confirm(cls, value):
        if value is not True:
            raise ValueError('Invalid source declaration')
        return value

class DerivedSourceScopeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    target_report_id: UUID
    fmea_id: UUID
    cause_node_id: StrictStr = Field(min_length=1, max_length=128)

    @field_validator('target_report_id', 'fmea_id', mode='before')
    @classmethod
    def canonical_id(cls, value):
        if isinstance(value, UUID):
            return value
        if type(value) is not str:
            raise ValueError('Invalid source scope')
        try:
            parsed = UUID(value)
        except (ValueError, TypeError):
            raise ValueError('Invalid source scope') from None
        if str(parsed) != value:
            raise ValueError('Invalid source scope')
        return parsed
```

HTTP JSON UUID按现有DTO的JSON解析习惯验证；不因Python strict UUID阻断合法JSON字符串。输入中不允许module/classification/permission字段；规范化后由内部FMEA声明补齐，node按字面精确匹配。

- [x] 加两个默认配置：`AGENT_D4_TEXT_LOCAL_TRIAL_ENABLED=False`、`AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE=None`。新GET登记runtime routes；中间件只对该新path在关闭时早404（tenant/auth/body/DB均未访问）。旧metadata路径不受新flag关闭影响。API实现仍不存在，开flag也不能凭此获得正文。
- [x] GREEN：纯反例＋默认关闭/未知query/body选择/未知安全枚举DTO断言；旧permissions纯测试。新增 `SourceDeclaration`、来源输入、正文输出DTO只表达合同，不做授权。
- [x] 精确提交：`feat(agent): define restricted D4 text contracts behind default deny`；规格→质量复核后进入T2。

**T1签收（2026-11-10）**：实现 `3e2100d3`；独立SPEC、QUALITY均通过，无Critical/Important/Minor。Lead实跑本任务224 passed/3既有警告，CI pure278 passed/同3警告；reviewer内存重放base middleware＋base routes验证12个early-guard行为RED，随后候选仍GREEN。仅合同/默认拒绝签收，不证明源授权或正文交付已实现。

## Task 2: 授权/证据五表与请求身份旁表的public/tenant迁移

**Files / write scope:**
- Create: `backend/app/models/capa_d4_delivery.py`
- Create: `backend/app/models/agent_derived_source.py`
- Create: `backend/app/models/agent_task_request.py`
- Create: `backend/alembic/versions/20261109_d4_text_delivery.py`
- Create: `backend/alembic_tenant/versions/tv007_d4_text_delivery.py`
- Create: `backend/tests/migrations/test_d4_text_delivery_delta.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/tenant_migrator.py`
- Modify: `backend/app/services/tenant_schema_diff.py`
- Modify: `backend/alembic_tenant/__init__.py`
- Modify: `backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py`
- Modify: `backend/tests/migrations/test_agent_mainline_merge_graph.py`
- Modify: `backend/tests/migrations/test_agent_mainline_merge_db.py`
- Modify: `backend/tests/migrations/test_agent_readonly_controls_delta.py`
- Modify: `backend/tests/test_multitenancy/test_agent_read_task_delta.py`
- Modify: `backend/tests/migrations/test_tenant_schema_parity.py`

- [x] 执行前新建并登记本片PG；用 `make check-test-db PYTHON_BIN="$PY"` 核实例/库/迁移，URL仅从私有文件注入。无权限/本地Docker不匹配就停止，不借其他库。
- [x] RED：真实PG断言五张授权/证据表及请求指纹旁表缺失；源码断言tv001–tv006与snapshot manifest字节不变。不能仅测模型 `create_all()`。
- [x] DDL字段表完整如下（所有PK UUID、时间aware；索引/约束均命名）：

| 表 | 字段与必要约束 |
|---|---|
| `capa_d4_root_cause_revisions` | revision_id PK，report_id FK CAPA/RESTRICT，revision_no bigint非负、report+no unique，field_hmac varchar64，actor_id、created_at、write_path；无正文 |
| `capa_d4_root_cause_source_proofs` | proof_id PK，report_id/revision_id FK，verification_id及verification_version，tenant_generation、factory_id、product_line_code、source_projection_id、fmea_id/cause_node_id/node_hmac、field_hmac、declaration_kind，status active/superseded，superseded_by/at、actor_id/created_at；report+revision仅一active |
| `agent_restricted_projection_receipts` | receipt_id PK，task_id/run_id FK，lease_epoch/tenant_generation非负，source_capa_id、专用projection_id/digest、data_class固定restricted、created_at；不得连入旧receipt关联表 |
| `agent_plugin_derived_source_scopes` | scope_id PK、plugin_grant_id FK/unique、target_report_id、derived_projection_id、source_module/source_projection_id、fmea_id/cause_node_id、actor_id/created_at |
| `agent_task_derived_source_scopes` | 与长期范围同构，以task_grant_id FK/unique绑定；任务grant没有enabled字段 |
| `agent_task_source_requests` | task_id PK/FK `agent_tasks.task_id`，request_fingerprint varchar64、fingerprint_format、created_at；不可变请求身份，无原文、无来源授权，ready/blocked均保存 |

证明失效可使用proof表的可空 `invalidated_at` 元数据字段；任何成功验证更新在同事务永久填入，最终校验还要求为null，避免依赖时间精度恢复旧证明。此字段只实现v6“更新不补发且旧证明不得复活”，不新增审批/状态机。

- [x] 请求身份旁表DDL独立于任何grant：

```python
op.create_table('agent_task_source_requests',
    sa.Column('task_id', pg.UUID(as_uuid=True),
        sa.ForeignKey('agent_tasks.task_id', ondelete='RESTRICT'), primary_key=True),
    sa.Column('request_fingerprint', sa.String(64), nullable=False),
    sa.Column('fingerprint_format', sa.String(40), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
```

其模型为 `AgentTaskSourceRequest`；写入format固定 `d4-source-request.v1`。不得存source request原文副本、initial_text副本或直接当P/T使用；指纹不能验证/密钥变化时failclosed，不静默补写旧请求身份。

- [x] 两个范围表共享完整迁移辅助代码：

```python
def create_scope_table(op, sa, pg, name, parent_column, parent_table):
    op.create_table(name,
        sa.Column('scope_id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(parent_column, pg.UUID(as_uuid=True),
                  sa.ForeignKey(parent_table + '.grant_id', ondelete='RESTRICT'),
                  nullable=False),
        sa.Column('target_report_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('derived_projection_id', sa.String(160), nullable=False),
        sa.Column('source_module', sa.String(40), nullable=False),
        sa.Column('source_projection_id', sa.String(160), nullable=False),
        sa.Column('fmea_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('cause_node_id', sa.String(128), nullable=False),
        sa.Column('actor_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(parent_column, name='uq_' + name + '_parent'))
```

不对源FMEA建立额外删除阻塞FK以冒充当前存在性检查；每次由来源服务重验。其它三表按表中字段显式DDL；Proof.superseded_by作为历史UUID元数据，不用未插入新proof的立即自FK制造flush顺序问题。

- [x] 加active partial unique：`WHERE status='active'`。新签发在父锁下先将旧active标superseded并flush，再插新active，旧证据不删除。
- [x] 更新前驱/当前注册、`REVIEWED_REVISIONS`、累计新增对象过滤。只在public reference扣除已审新增表，不过滤tenant实际对象。钉头范围：`test_supplier_risk_capa_inputs_migration.py`、`test_agent_mainline_merge_graph.py`、`test_agent_mainline_merge_db.py`、`test_agent_readonly_controls_delta.py`、`test_multitenancy/test_agent_read_task_delta.py`、`test_tenant_schema_parity.py`；保留旧merge本身的历史升级验证，不能把所有MERGE常量盲改新head。
- [x] GREEN：空库/原两分支/当前head真实升级；tenant v1–v6受原maintenance/generation锁前向到v7；current parity一致、snapshot再生成仍钉旧public_head。downgrade若上述六表有证据就拒绝，不删除记录通过测试。
- [x] Commit `feat(agent): add tenant-local D4 delivery evidence and scope tables`。

**T2技术签收（2026-11-11）**：候选ea300bb4经独立SPEC→QUALITY通过，C/I/M均0；Lead串行真实PG焦点35 passed/4 warnings，原执行窄回归101 passed/4 warnings。8冻结资产保持原字节。回退只覆盖受控tenant维护锁或public离线/无writer路径，不认证在线public并发回退；审阅者工具参数偏差单独披露，不充作纪律合规回执。

## Task 3: FMEA内部来源访问与根因修订记录

**Files / write scope:**
- Create: `backend/app/services/fmea_agent_sources.py`
- Create: `backend/app/services/capa_d4_provenance.py`
- Create: `backend/tests/capa/test_d4_source_access.py`
- Create: `backend/tests/capa/test_d4_root_revisions.py`
- Create: `backend/tests/ci/test_d4_root_write_sites.py`
- Modify: `backend/app/services/capa_service.py`
- Modify: `backend/app/services/capa_verification_service.py`
- Modify: `backend/app/services/audit_service.py`
- Modify: `backend/app/services/capa_current_access.py`

- [x] RED：同一CAPA EDIT/no FMEA VIEW员工、同合法结构的真实/虚构节点，`visible_fmea_source`均固定SourceUnavailable；spy节点读取0。另测FMEA VIEW但对象越范围、不存在及不确定，响应不可区分。
- [x] 实现“权限→标量可见性→关联/坐标→节点”。来源helper的查询先过滤可见factory/PL，只select FMEA id/factory/PL；不能先用旧 `_normalize_and_validate_source_ref` 查图再补权限。诊断前/签发前重新核可见性。
- [x] 有界节点SQL代码形态：

```sql
WITH nodes AS (
  SELECT n FROM fmea_documents d,
  LATERAL jsonb_array_elements(CASE
    WHEN jsonb_typeof(d.graph_data->'nodes')='array'
    THEN d.graph_data->'nodes' ELSE '[]'::jsonb END) n
  WHERE d.fmea_id=:fmea_id AND n->>'id'=:node_id
)
SELECT count(*), max(octet_length(n::text)) FROM nodes;
```

先确认唯一且<=64KiB，再仅取该node，检查type=FailureCause；不得加载FMEADocument整ORM/graph。HMAC规范：`json.dumps(node,sort_keys=True,separators=(',', ':'),ensure_ascii=False,allow_nan=False).encode('utf-8')`，前置规格域串和换行；未知/重复/过大拒绝，不输出node。

- [x] 根因字段HMAC与交付source_version**分开**：2026-11-11用户明确批准类型化命名空间补充。修订表field_hmac只绑定服务端命名空间（tenant真实UUID或显式single_public标记）、report UUID及原始text（null与空串区分），不绑定会改变的factory/PL、tenant generation、来源/规则，以免合法坐标变化被误报为“未记录文本写入”；交付source_version另覆盖规格所有当前坐标/修订/原文。不得用None/零UUID/UUID5伪装租户或从HTTP取身份，也不跳过single/public修订；single_public不增加正文准入。

```python
import hashlib, hmac, json

def field_hmac(key, namespace, report_id, text):
    # Server-owned validated identity: tenant+UUID or single_public, never HTTP input.
    encoded = json.dumps({'namespace':namespace, 'report':str(report_id),
        'is_null':text is None, 'text':text}, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hmac.new(key, b'openqms.capa.root-field.v1\n' + encoded,
                    hashlib.sha256).hexdigest()
```

- [x] 在CAPA父锁下按report取最新修订，实际text变化后追加 `revision_no+1`/新UUID；helper不commit。普通update动态循环先识别d4实际变化，业务mutate/embedding原流程不改，提交前记录；adopt在追加字段后记录；审核发现建单在获得report_id后记录初始text。若该旧建单路径因原有工厂约束不能成功，记录真实失败，单独核必需坐标传递，不假装通过或绕过工厂校验。
- [x] 测试完整A→B→A：由普通PUT、adopt、正常建单分别观察修订序号/UUID/HMAC；同值no-op不追加。静态测试只扫描services/api字面量写站点白名单，seeds/tests排除；动态setattr用专门行为测试；签发bootstrap为第四路径而非静态字面量写检测。
- [x] GREEN：上述DB及无网络site-contract测试；旧CAPA业务/embedding调用次数断言保持，Commit `feat(capa): track root-field revisions and authorize source visibility first`。

## Task 4: 同一验证动作显式签发及不可复活

**Files / write scope:**
- Create: `backend/tests/capa/test_d4_source_proofs.py`
- Create: `backend/tests/capa/test_d4_source_proof_api.py`
- Modify: `backend/app/schemas/capa_verification.py`
- Modify: `backend/app/api/capa.py`
- Modify: `backend/app/services/capa_verification_service.py`
- Modify: `backend/app/services/capa_d4_provenance.py`

- [x] RED：API带声明、无源读取权提交真实/虚构节点，状态码及响应字节一致、均403，验证/修订/proof/成功audit零新增；有权限后才分别400节点错/关联错，结构422，修订冲突409。无声明旧调用不变。
- [x] 新字段与创建专用响应的实际改动：本片以正常员工API显式JSON声明，不新增前端审批/核验页面或自动勾选；旧UI不传该字段时继续保存验证、返回proof=false，不因为passed或已有source_ref自动认定来源完备。

```python
class VerificationCreatedResponse(VerificationResponse):
    source_proof_issued: bool = False

# VerificationCreate新增，可选且禁止额外字段；不把字段加入VerificationUpdate。
source_declaration: SourceDeclaration | None = None
```

仅POST的response_model改为创建子类，GET/PATCH保留原model。新增 `SourceRevisionConflict` 专用409分支；源不可见403使用固定文本而不是原异常。422的新声明校验不回显原始输入值。

- [x] API为声明分支提供服务端真实请求上下文；不允许HTTP字段伪造peer/tenant/profile。普通无声明业务不受本地开关影响；本片新增声明签发仅用于已启用的自有dev/回环场景，不因生产请求包含新字段而激活功能。签发来源事实不依赖某个接收器安装的P/T范围，它本身不授权插件。
- [x] 父锁后、任何rec/add/audit前做新分支权限与来源检查。仅passed＋完整声明＋源可读＋文本匹配时签发；文本不匹配正常保存并false，原因仅audit。无修订历史只在显式合格声明时bootstrap；已有最新field_hmac不匹配则409且整事务无业务写入。不能从首次runtime读取创建修订/proof。
- [x] proof绑定新验证ID、标量verification_version（ID/结论/updated_at）、最新修订、源节点HMAC及当前坐标。先flush新验证取server时间，再issue；同一验证同一事务helper重复调用幂等，不制造第二proof。不同POST各创建验证是原语义，不擅加全局幂等键。
- [x] 每次合格新创建可supersede当前active；更新验证不补发，成功PATCH在同事务把引用该验证的proof设置invalidated_at，保留记录；最终也检标量版本。failed→passed、源A→B→A、相同时间戳/同一事务更新都不能恢复旧proof。没有delete路由，不增加delete/cascade清理。
- [x] GREEN：按v6判定表逐条断言事务写入差异；D4→D5闸口、D8终态保护、未审补充规则不改。Commit `feat(capa): issue version-bound source proofs from explicit verification declarations`。

## Task 5: 独立标准库接收器与启动器定稿

**Files / write scope:**
- Create: `backend/examples/readonly_d4_text_receiver.py`
- Create: `backend/scripts/agent_d4_text_local.py`
- Create: `backend/tests/cli/test_d4_text_receiver.py`
- Create: `backend/tests/cli/test_d4_text_launcher.py`
- Create: `backend/tests/e2e/d4_text_wire_fixture.py`

- [x] RED：假协议/自有loopback服务器见证只有六个固定operation：claim/capabilities/messages claim/body/ACK/finish；非固定消息、wrong run/report/recipient、错误安全枚举、旧internal投影都停止且不ACK/finish。
- [x] 固定流程代码骨架（每个`wire`方法由同文件固定路由实现，不作为通用HTTP导出）：

```python
def receive_once(wire, config):
    claim = wire.claim(config)
    wire.require_body_capability(claim)
    batch = wire.claim_start(claim, limit=1)
    if len(batch.messages) != 1 or batch.messages[0].content != START_MESSAGE:
        return {'status':'input_unconfirmed', 'received_fields':0}
    delivery = wire.read_body(claim)
    wire.validate_delivery(claim, config, delivery)
    wire.ack_start(claim, batch)
    finish = wire.finish_once(claim)
    return {'status':'completed', 'receipt_id':delivery.receipt_id,
            'received_fields':int(delivery.text not in (None, ''))}
```

异常统一在顶层转换固定安全码，不把原始异常/response挂cause、repr或输出。上述函数不捕获后再自动补finish。未完整确认读取仅输出unconfirmed，不声称未生成receipt或从未发出字节。

- [x] stdlib传输实现固定origin/tenant/header/operation表；直接numeric socket，不解析外部DNS，不跟随URL/3xx，不用代理/netrc/cookie。TLS证书正常验证。每操作编码前建monotonic D=10s，每次connect/TLS/send/rawread/JSON/schema/最终返回前都用剩余时间。不得把socket多次read各10秒冒充整体deadline；原始IO之上才buffer。
- [x] 复用SDK已审算法作为源码参照，但**不运行时import SDK**：拷贝/收窄前列出每个deadline/framing/budget差异并复核；至少将SDK旧loopback慢滴、TE尾OWS、分块/CL冲突、读限界、partial send、TLS makefile IO引用及晚decode反例改为本接收器用例。新fixture仅numeric自有端口，不递归运行SDK suite。
- [x] 请求<=64KiB、正文响应<=256KiB；头部单独有界，不无限读trailer/超多header。重复JSON键/NaN/坏UTF-8/错标签拒绝。finish可能发送后未获完整确认→unknown且一次调用；明确拒绝不猜全局终态。
- [x] 启动器读取0600配置（origin/tenant/installation/secret/request_key/expected_report_id），校验origin/源文件hash；只把必要配置写child stdin，`-I -S -B`、repo外cwd、私有HOME/TMPDIR、无环境/argv秘密。max60秒；自己的new session/PGID在正常/异常/leader提前退出路径都TERM/grace/KILL/wait，不杀未知进程。
- [x] GREEN：测试HTTP调用数、ACK水位与finish次数；stdout/stderr/argv/env/文件/异常sentinel不含正文/词表/secret/token。审计子进程网络仅固定回环，不称OS sandbox。
- [x] 独立review定稿后实算SHA256，记录该提交的worker bytes。Commit `feat(agent): add fixed local D4 text receiver and supervised launcher`。

## Task 6: 固定启动消息的服务端门禁

**Files / write scope:**
- Create: `backend/tests/services/agent_runtime/test_d4_text_message_policy.py`
- Create: `backend/app/services/agent_runtime/message_delivery_policy.py`
- Modify: `backend/app/services/agent_runtime/runtime_messages.py`
- Modify: `backend/tests/services/agent_runtime/test_runtime_messages.py`
- Modify: `backend/tests/services/agent_runtime/test_readonly_checkpoints.py`

- [x] RED：新profile队列中放敏感非字面量sentinel；分别初领、同批重试、旧epoch重领、accepted history、ACK真实batch，所有响应不含sentinel且批次/水位/成功audit不变。
- [x] 在叶子模块 `message_delivery_policy.py` 定义唯一共用检查；消息服务仅从最终刷新后的服务端admission取profile再传入（不从请求取值），T7平台profile绑定导入该叶子常量，避免循环导入。此任务不开放任何正文安装：

```python
TEXT_PROFILE = 'local_d4_root_cause_text_v1'
START_MESSAGE = 'deliver_d4_root_cause_candidate_v1'

def require_profile_message_contents(profile, rows):
    if profile != TEXT_PROFILE:
        return
    if any(row.content != START_MESSAGE for row in rows):
        raise PermissionError('Message unavailable')
```

真正调用前仍是现有完整身份/准入/投递重验；新profile缺开关/peer/策略不得降级走legacy。claim在最终刷新后、清旧markers/新claimed/audit前调用；history在最后授权后、DTO构造前调用；ACK在加载真实batch及最终授权后、改accepted/watermark前调用。不挑掉非法消息，不跳seq，不只校验initial_text，不仅靠limit1。

- [x] 在尚未提供正文准入时，用纯predicate及服务插入点契约证明固定/非固定输入差分，明确不是新profile真实准入成功；旧profile自由输入/partial ACK/retry/history after99/epoch批次证明均保持。T7/T8首次实际可claim的同一提交必须另完成真实API哨兵测试，不准以此任务的纯测试代签。Commit `fix(agent): validate text-receiver inputs before message egress`。

## Task 7: 第二策略槽与模块声明驱动的平台准入

**Files / write scope:**
- Create: `backend/app/services/agent_runtime/deployment_profiles.py`
- Create: `backend/app/services/agent_runtime/local_d4_text_policy.py`
- Create: `backend/tests/services/agent_runtime/test_d4_text_policy.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/core/agent_local_trial.py`
- Modify: `backend/app/core/tenant_context.py`
- Modify: `backend/app/services/agent/permissions/catalog.py`
- Modify: `backend/app/services/agent_runtime/run_auth.py`

- [x] RED：text slot缺失/错误类型/词表泄漏/错worker/hash/非dev/过期/重复JSON键/符号链接/不安全权限均不可准入；同时开启两个slot也不串安装或profile。由T5真实hash作正向，不自动接受当前文件的任意hash。
- [x] 准入前置：依赖已完成并双复核的T6消息门禁；缺任一路径的门禁调用就保持正文profile不可准入/消息不可交付，不能落入legacy分支。首次实际允许claim时同提交见证敏感非字面量在claim/reclaim/history/ACK均不出站且状态不推进（若本任务仍因共享授权未打通而不可claim，最晚T8首次打通时实测，不伪造token冒充）。
- [x] 固定平台绑定：metadata profile最低summary保持旧集合；text profile最低仅正文cap。baseline全DENY，profile目录只提升已准入的context，不把整个新增CAPA目录盲spread到旧profile。FMEA来源声明留内部，不出get_capability/manifest。
- [x] lifespan分别装两个frozen policy，`get_db`只从实际app.state附到session.info；缺引用用EMPTY，不读环境文件/不在每个请求reload。文字词表只存在text slot；binding字段兼容 `TrialAdmission.binding_sha256`，新值为HMAC-SHA256，不把私有词表的plain SHA暴露在token/日志。
- [x] `select_runtime_admission(db, installation, executor_id, coordinates)`逐个检查两个独立slot，匹配具体安装/key/version/hash；未知/冲突failclosed，不从HTTP profile名选择。Run token绑定该admission，每次重验比较binding和到期；租约clip不延长。
- [x] 本任务只加载第二slot/绑定，尚未完成T8的正文grant/ready路径；正文安装仅声明body能力时必须仍不能claim，不临时借授summary开门。若任一接线已经令其可claim，必须在本提交提前引入T8早期harness及全部消息负向验收，否则回退准入，不能延期。
- [x] peer gate由“metadata有效本地模式或text启用”驱动相关agent路径，保留旧metadata路径关闭语义；newGET还需自身flag和dev。拒forwarded，HTTPS不降级。SourceDeclaration业务入口只新分支使用真实peer上下文，不封锁无声明原业务调用。
- [x] GREEN：两个slot交叉错凭据、轮换/永久撤销/重启策略binding变化、元数据旧fixedhash与Capabilities不增加正文。Commit `feat(agent): bind independent local text admission to module contracts`。

## Task 8: 两层范围持久化与统一授权/目录/控制

正文 restart 按用户批准的[受限恢复合同](../specs/2026-11-13-agent-d4-restricted-restart-design.md)及[补充计划](2026-11-13-agent-d4-restricted-restart.md)实施并纳入 T8 签收：独立控制位置、restart 映射与固定父 grant 绑定三表，不能复用旧 metadata checkpoint。T8 已通过独立规格、质量复核及本地验收，本地提交 `9195c1f5`；T9 的正文重读与新 receipt 已通过独立规格、质量复核及本地验收，并本地提交 `be232bfe`。

**Files / write scope:**
- Create: `backend/app/services/agent_runtime/derived_source_grants.py`
- Create: `backend/tests/services/agent_runtime/test_d4_text_grants.py`
- Create: `backend/tests/services/agent_runtime/test_d4_task_request_identity.py`
- Create: `backend/tests/e2e/d4_text_local_harness.py`
- Create: `backend/tests/e2e/test_d4_text_early_admission.py`
- Modify: `backend/app/services/agent/permissions/types.py`
- Modify: `backend/app/services/agent/permissions/access.py`
- Modify: `backend/app/schemas/agent_plugin.py`
- Modify: `backend/app/schemas/agent_task.py`
- Modify: `backend/app/api/agent_tasks.py`
- Modify: `backend/app/services/agent_runtime/plugin_registry.py`
- Modify: `backend/app/services/agent_runtime/task_service.py`
- Modify: `backend/app/services/agent_runtime/runtime_access.py`
- Modify: `backend/app/services/agent_runtime/task_reads.py`
- Modify: `backend/app/services/agent_runtime/task_controls.py`
- Modify: `backend/app/services/capa_current_access.py`

- [x] RED：执行人有A/B读取权、同报告/工厂/PL，分别P=A/T=B、P=B/T=A/S=B均deny；P=B/T=B/S=B才可在其它条件满足时allow。缺P/T不能是ALL，不能从不同grant拼目标和源。
- [x] `AccessAttempt`新增kw-only来源输入（current/plugin/task），默认None。`authorize`从可信内部contract判断该cap是否必须来源；保留原canonical spec比对、身份/工厂/PL/父grant期限检查后，正文必须调用T1的精确范围谓词；metadata无来源依赖仍走旧语义。调用者不能用伪CapabilitySpec或请求字段关闭该要求。
- [x] `PluginGrantCreate.derived_source_scope`、`TaskCreate.derived_source_scope`可选严格DTO。对正文启用/可运行创建必填；旧metadata请求缺字段不改变结果。服务校验target_report_id与父对象范围一致，source_module/projection由代码声明补齐，不能接受用户自报等级。新的范围创建/启用也先源可见性后节点诊断。
- [x] 管理员范围P只来自显式输入，不从当前proof填。T只来自任务发起者显式输入；在同一父grant既覆盖目标又覆盖源时才派生task grant并写T旁表。为父grant先flush取得server UUID，旁表FK必须绑定同一个父grant。缺任何层则既有blocked状态/无可运行run，不自动匹配当前proof。
- [x] **请求身份与权限分离**：新增模型 `AgentTaskSourceRequest`（T2请求指纹表）及 helper `request_source_fingerprint(key, tenant_id, initiator_id, request)`。字段和函数完整定义如下；该函数放在 `derived_source_grants.py` 或task请求身份叶子helper，不查询grants/proof：

```python
import hashlib, hmac, json

def request_source_fingerprint(key, tenant_id, initiator_id, request):
    scope = request.derived_source_scope
    payload = {
        "format": "d4-source-request.v1",
        "tenant": str(tenant_id), "initiator": str(initiator_id),
        "report": str(request.report_id),
        "installation": str(request.installation_id),
        "initial_text": request.initial_text,
        "source_scope": None if scope is None else scope.model_dump(mode="json"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hmac.new(key, b"openqms.d4.task-request.v1\n" + raw,
        hashlib.sha256).hexdigest()
```

按规范请求（固定格式版本、tenant/initiator、report、installation、initial_text、显式source_scope或null）生成域分离HMAC-SHA256；仅存digest/格式版本，不存第二份原文。不能用proof digest、当前grant或最新source替代请求指纹。
- [x] 每个正文任务在同一Task创建savepoint内保存不可变请求指纹，**包括blocked任务**。缺长期grant但请求/用户资格合法时，保存blocked Task、原始消息与指纹；不产生正文task grant、授权来源旁表或pending run。指纹不是T、不参与authorize，不得从中补授权。安装的请求类型由受信绑定声明识别，不因本次不ready而漏存。
- [x] `_existing`及唯一键竞争恢复分支使用原请求参数比对＋该fingerprint：同key同A返回原Task（即使后来有grant也不升级原blocked任务）；同key换B固定409，不能重算或覆盖指纹。仅识别 `uq_agent_task_initiator_request` 的23505为竞争，rollback savepoint后重读胜出Task及已原子提交的指纹，再做同样比较。其它IntegrityError不伪装幂等。旧metadata调用不需指纹；正文历史行缺指纹或格式不可验证时failclosed，不从当前proof补签。
- [x] 新增 `backend/tests/services/agent_runtime/test_d4_task_request_identity.py` 的三项强制用例：blocked(A)同key/A返回同task_id且授权/运行行数仍0；同key/B→409且指纹未变；两个真实事务并发同key创建，唯一键竞争后同源返回同Task、异源409且仅一份指纹。
- [x] 目录只提供发现结果：共享身份/插件范围谓词过滤可见安装，不创建/存储T，不将发现结果当执行AccessDecision。Task create/ready/claim/verify及resume/restart完整检查持久化P/T及当前source；不得改旁表，restart新epoch仍原范围。更换源要新grant/新任务，不帮扩域。
- [x] **停止操作不是恢复操作**：保留 `task_controls._user_authority` 只核当前用户的任务归属、CAPA/工厂/PL/租户及run位置控制权；pause/cancel不能调用正文 `authorize_task`/`_resume_authority`、不能依赖plugin enabled/body grant/P/T/proof/FMEA VIEW，也不加载正文或来源节点。完整源重验仅放resume/restart；不能把新源权限检查塞进共享用户控制权函数，导致撤权后无法停止。用户自身失去任务控制权仍须拒绝，不能借“停止”扩大权限。
- [x] `_require_grant_enableable`、ready/required集合、runtime授权从T7的平台profile绑定取最低集合，不再额外硬要求summary。旧 `readonly_delivery._recognized_source`、旧checkpoint、legacy `agent_read_tasks` 的summary/internal限制保持，不泛化。
- [x] 仅改runtime共享 `_target`、registry目标读取、目录授权定位为标量；不要替换业务写函数所需的全ORM `current_capa_target`。checkpoint历史只用factory_id的调用方也验证。
- [x] 先在本任务创建正常配置的 `d4_text_local_harness.py` 与早期验收文件；不等T10才有可用fixture。复用OwnedTrial的租户/生命周期/随机TCP模式，但body安装/策略/来源声明与显式P/T必须走正常API，不能打DIRECT或TRUSTED补丁。早期测试由父controller真实claim并访问消息接口，不宣称已运行T10固定接收器完整闭环。
- [x] GREEN之前增加**首次可claim提交**的真实API消息负向见证：即使尚未做T9正文读取服务，当前运行可claim后任意非固定消息仍必须在服务端拒绝（首次/重领/history/ACK），HTTP响应无哨兵、batch/watermark/成功audit不变；没有该证据不提交准入正向。旧metadata3CLI/14SDK回归不获得正文。
- [x] 本任务已实现并验收 pause/cancel 与 resume/restart 权限分离；撤正文grant后先用已存在的受保护capabilities GET验证运行身份拒绝，不能用尚未实现正文GET的404冒充撤权成功。完整的“撤grant→正文GET拒绝→pause成功→resume拒绝→cancel成功”安排在T9正文服务首次可用提交，T10再整合回归。另覆盖FMEA读取权撤销但任务控制权仍在时仍可停止，停止路径0正文/源node读取。Commit `feat(agent): intersect explicit plugin and task derived-source scopes`。

## Task 9: 正文快照与最终交付服务

当前实现与锁竞争修复已通过独立规格和质量复核；冻结代码综合回归 144 passed / 6 warnings、旧链 181 passed / 6 warnings，均无 skip，T9 本地验收通过，并本地提交 `be232bfe`。恢复后新运行经固定接收器重读当前事实并产生新 receipt；T10/T11 整片验收仍待执行。

**Files / write scope:**
- Create: `backend/app/services/agent_runtime/d4_text_delivery.py`
- Create: `backend/tests/services/agent_runtime/test_d4_text_delivery.py`
- Create: `backend/tests/e2e/test_d4_text_revocation_controls.py`
- Modify: `backend/app/api/agent_runtime.py`
- Modify: `backend/app/schemas/agent_d4_text.py`

- [x] RED：来源B证明替换A但旧P/T仅A，初检就拒，root/node内容读取计数0；通过初检但RR后/编码后撤权或改proof/坐标时最终拒，正文/摘要/计数均不返回，receipt/audit不新增成功记录。
- [x] 固定服务顺序：

```python
async def get_d4_root_cause_text(db, identity):
    current = await runtime_access.refresh_runtime_identity(db, identity)
    state = await load_current_source_state(db, report_id=current.task.target_capa_id)
    await require_current_text_authority(db, current, state)
    snapshot = await build_root_candidate(binding=current.binding, state=state)
    release = encode_bounded_release(current, snapshot, limit=256 * 1024)
    current = await runtime_access.lock_runtime_identity(db, current)
    # 锁定 CAPA/FMEA 父行直到提交；可变授权行使用 NOWAIT 避免锁序反转。
    await lock_source_parents_and_authority_inputs(db, current, state)
    latest = await load_current_source_state(db, report_id=current.task.target_capa_id)
    await require_current_text_authority(db, current, latest)
    await verify_release_is_current(db, current, latest, snapshot)
    # 提交前再次刷新身份、来源及授权，确认与快照一致。
    current, latest = await recheck_identity_source_and_authority(db, current, state)
    add_restricted_receipt_and_audit(db, current, latest, release)
    await db.commit()
    return release.response
```

`require_current_text_authority`装载当前父grants/两个旁表并走统一authorize与来源Owner检查，不在这里复制角色判断。`build_root_candidate`独立连接先设置RR/READ ONLY，再绑定captured namespace/generation，只preflight字节后select单字段、既有pure redactor。`encode_bounded_release`先分配receipt UUID/aware时间，固定DTO→最终JSON bytes→预算，正文不得事后再次用另一序列化规则变大。上述锁和末次重验是示意职责，不是新增函数名合同：实际实现持有 CAPA/FMEA 父行至提交，授权行使用 NOWAIT；锁冲突回滚并返回固定 503 `Delivery unavailable`，不表示授权已通过或被拒。

- [x] `verify_release_is_current`不加载验证正文/source_ref：select验证ID/结论/updated_at，SQL布尔谓词比较verification.root_cause_text与当前根因的Python `.strip()` 参数、source_ref JSONB与proof；同时proof未invalidated/仍active、revision/field_hmac/源node版本/当前坐标/期限一致。SQL btrim不得处理字段侧Unicode空白。根因当前变大时先预算再取。
- [x] null/空根因不能凭空制造passed验证或有效proof；无证明则拒绝。DTO保留严格nullable但不为测试编造空字段事实。词表命中0不降级internal，原预览外发flag不翻转。
- [x] HTTP响应 `Cache-Control:no-store`，新DTO仅Root候选＋opaque版本＋local许可；不含词表/验证/FMEA node/来源ID。server/worker错误均不含原文/异常cause；audit名称release_committed不声称接收方已收到。实际事务失败不能提前发正文。
- [x] 在正文服务首次可用的本任务提交内，正常API顺序实测：任务已claim且正文GET原本可用 → 管理员撤正文grant → 同一run token正文GET拒绝（不是路由缺失404）→ 仍有任务控制权的用户pause成功并取新epoch → resume拒绝且task/run保持paused、无新run/成功恢复audit → 同用户cancel成功（新key/正确epoch），最终cancelled/stopped、租约清空。pause/cancel区间SQL见证不读root正文或来源节点，不因plugin失权/源失权而被阻止。
- [x] 正文服务首次可用时，通过正常 API 与固定接收器验证受限 restart 后的新 run 重新读取当前业务事实并生成新 receipt；旧 receipt 或来源版本不得充当新运行读取凭证，也不得被新运行消费。撤权及原 P/T 范围外换源仍须拒绝，不能使用旧业务结果或模拟 receipt 代替真实读取。
- [x] GREEN：字节扩张、坏数据、未知安全标签、同UUID跨tenant、generation维护、所有源/目标授权变化；metadata receipt/event/result/checkpoint不能消费受限receipt UUID。
- [x] 本地提交 `be232bfe`：`feat(agent): release bounded D4 root text with final source-scope fencing`。

## Task 10: 正常策略真实HTTP、源权限反例与CI必选层

T10 已通过独立规格和质量复核；当前 wheel gate 实际 39 passed / 6 warnings / 0 skip（22 个 T10、14 个 SDK、3 个旧 CLI），旧 CLI 精确三节点另经 XML 核验，CI pure 307 passed / 3 warnings。本地提交 `ea7d2814`；T11 功能验收完成，清理待办（R4B-CLEANUP-01）。

**Files / write scope:**
- Modify: `backend/tests/e2e/d4_text_local_harness.py`
- Create: `backend/tests/e2e/test_d4_text_local_process.py`
- Modify: `backend/tests/ci/test_layer_selection.py`
- Modify: `backend/tests/e2e/capa_outcome_runner.py`
- Modify: `backend/tests/e2e/test_capa_outcome_runner.py`

- [x] harness复用既有 owned-resource、TenantSession、lifespan/TCP启动清理模式；旧 `owned_local_trial` 可提供租户/端口工具，但body安装必须单独注册、仅授body，不利用其metadata安装的summary授权。不能修改旧metadata worker/profile/hash让body过关。
- [x] 父侧合成数据：同厂PL的FMEA含两个FailureCause A/B（正文可相同，用来证明来源变化与正文无关）；正常PUT建立报告关联/根因，正常POST验证passed＋完整声明生成proofA；真实admin POST body grant显式scopeA；真实user POST task显式scopeA与固定literal。启动第二slot读实际worker hash、正确app-state，不改canonical DIRECT。子侧仅安装secret/run token。
- [x] 必选场景名及内容：

| 新测试名 | 必须见证 |
|---|---|
| `test_fixed_text_receiver_normal_http` | 实际TCP、六操作各固定次数、restricted标签/receipt、ACK实际消息、finish确认 |
| `test_source_swap_never_widens_old_grants` | actor可读A/B；proofB替换A；P仅A或T仅A均拒；明确P/T都B新任务才可通过 |
| `test_declaration_denials_hide_node_existence` | 无FMEA VIEW、越范围两类员工真实/虚构合法node请求403/body完全一致，节点查询0且无四类写 |
| `test_revision_and_verification_changes_fence_old_proofs` | Root A→B→A、验证failed→passed/改源、同时间戳不会复活；新合格创建可supersede |
| `test_text_scope_idempotency_and_restart_do_not_regrant` | 同key换源冲突；claim/restart不写范围；父grant关闭/期限不被旁表绕过 |
| `test_blocked_task_source_request_replay` | blocked请求FP与授权分离；同A/换B/真实唯一键竞争重放一致 |
| `test_revoked_text_grant_does_not_block_stop_controls` | revoke→GET拒绝→pause成功→resume拒绝→cancel成功，停止0正文/源node读取 |
| `test_first_claimable_text_profile_has_message_gate` | 从首次可claim提交即有消息首次/重领/history/ACK哨兵负向证据，非到本任务才安全 |
| `test_text_message_sentinel_never_crosses_tcp` | 首领/重领/history/ACK非法批次均无sentinel/水位/成功audit变化 |
| `test_text_budget_and_response_faults_fail_closed` | 64KiB/256KiB界限、错标签/绑定、bad JSON/UTF8/慢滴，无截断降级或重试 |
| `test_text_finish_commit_without_confirmation_is_unknown` | 正常handler已commit后注入断连/坏JSON/超限；parent真实完成、child unknown、一次finish |
| `test_text_current_authority_and_tenant_boundaries` | 当前角色/源对象范围/epoch/暂停/永久撤销/策略/tenant generation及同UUID真跨租户 |
| `test_metadata_sdk_and_worker_contracts_remain_unchanged` | 原固定worker字节/hash＋SDK实际wheel十方法/原14节点合同不变 |

- [x] 业务只读见证窗口必须在准备业务写（PUT/验证等）完成后、接收器运行前取snapshot；控制动作另记录，不把fixture主动改proof的业务写误算到runtime只读窗口。拒绝链不能只检查stdout，必须检查服务端HTTP response未含原文。
- [x] 分类契约把上述文件实际collected全部nodes归默认backend；不标live/browser/scanner，不为缺库/工具skip。runner增加精确新suite JUnit检查（按实际参数化后的节点集合固定维护），零选中/缺节点/skip/xfail/xpass不得算成功；SDK已有14mandatory检查保留。合成JUnit反例必须有RED，真实HTTP必须有独立receipt，不能互相替代。
- [x] GREEN：实际运行新suite＋旧3固定CLI＋原14SDK；另跑CI pure/classification。记录真实selected/pass/skip/warnings，不猜计数。
- [x] 本地提交 `ea7d2814`：`test(agent): exercise source-bound D4 text delivery under normal local policy`。

## Task 11: 冻结完整门禁、运维交接与精准清理（功能验收完成，清理待办）

2026-11-14 按用户明确指示调整收尾：**功能交付单独签收，T11 标为“功能验收完成，清理待办”**，不标为全部完成。保留已通过的测试、独立规格/质量复核与本地提交 `d49d45c6`、`486451e5`。资源清理独立延期跟踪为 **R4B-CLEANUP-01（待办）**；容器、卷、诊断容器、私有凭据/登记文件、阻塞原因及恢复条件见[交付指南](../../development/capa-d4-local-text-delivery.md#保留资源与后续清理入口)。本次仅文档调整，不产生新的功能测试或资源状态证据。

整片独立规格和质量复核通过；冻结清单一致，最终 `make check` 后端 4537 passed / 4 optional skipped / 19 deselected / 6 warnings，SDK unit 562、loopback 16、wheel 1，前端 tsc/build 通过；browser 11 无 skip，CI pure 307 / 3 warnings，前端 88 文件 741 项和 E2E tsc 通过。首次完整门禁的过时路由测试失败与修复另见 `PROGRESS.md`。远端 CI NOT_RUN，生产、模型与部署未开启。

功能验收完成，清理待办。挂载归属复审已移除宿主解析daemon路径的错误依据；诊断清理器普通/-O各55项模拟测试及独立规格、质量复核通过。最近一次dry-run实查32容器：2个目标named-volume引用（含诊断容器）、25个排除的其他named-volume引用、10个未确认bind（原7+probe3），结果INDETERMINATE。资源保留，不执行apply或修改其他容器。此为已有证据，未因本次文档签收重新运行；清理拒绝不记作清理成功。

**Files / write scope:**
- Create: `docs/development/capa-d4-local-text-delivery.md`
- Modify: `PROGRESS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/superpowers/plans/2026-11-09-agent-d4-root-cause-local-delivery.md`

- [x] 先完成整片独立SPEC/quality review，收齐所有Important修正及全部required child结果。核旧worker/hash、SDK树、生产可信集合、默认flag无变化（body新flag仍false）。
- [x] 冻结实际tracked present执行文件、newreceiver SHA、sourceScope/proof协议版本、两迁移head、解释器/构建工具版本；执行期间不更新源码/计划勾选。新的轮次只用当前owned PG，不借已清理SDK资源。
- [x] 命令顺序（控制器注入登记/URL，不在shell历史拼DSN）：

```sh
make check PYTHON_BIN="$PY" SDK_PYTHON_BIN="$PY"
make check-browser PYTHON_BIN="$PY"
"$PY" -B scripts/check-ci-pure.py tests/ci tests/e2e/test_capa_outcome_runner.py -q --tb=short
npm --prefix frontend run test -- --run --maxWorkers=1
frontend/node_modules/.bin/tsc -p frontend/tsconfig.e2e.json
```

SDK三层与backend current-wheel供应使用既有Make，不改pin、不共享安装。保留graph worker/projection两文件既有排除和各layer marker。先重收四层节点，逐条比真实receipt；原4类可选skip单列，不让正文/SDK必选测试skip。普通环境禁provider与E2E_MODE；实际source/memory/进程见证与suite成功不能替代真实权限行为。

- [x] 本片不改scanner/附件路径，不擅自启动ClamAV或真实provider；远端CI仍未获push/dispatch权限，明确NOT_RUN。若发现实际影响scanner再单独确认范围，不拿历史scanner数字冒充新验收。
- [x] 运维文档必须说明：显式来源完整性声明是员工业务事实非降敏；P/T各自来源范围；策略最长1h/close不释放租约；失败显式控制；secret/源版本密钥变化时旧证据不可验证就拒，不自动重签旧字段；无历史正文重放/全局血缘/OS sandbox；只read Root，不把readonly restart叫业务rollback。
- [ ] 全部相关jobs收齐后，当前schema无fixture租户/无其他DB clients/无接收器或本worktree测试进程；核Docker完整ID、container/volume双owner、唯一挂载/soleconsumer后dry-run再apply，只处置本片resource和私有执行凭据，保留镜像/其他服务/证据/工作树。成功枚举确认absent，不能把任意docker非零当不存在。敏感输入不进git或公开artifact。
- [x] 功能交付收口：追加真实计数、失败/修复、源/包/worker hash与剩余R4b/R5/R6/R7限制；清理明确延期为R4B-CLEANUP-01，未记作清理成功。文档-only收口核内容/links/diff；若worker实际bytes变了，重核hash与所有依赖，不能用旧准入receipt签新代码。精确本地提交，不推送/合并。

## 3. 自审覆盖矩阵与执行签收

| 已批准v6要求 | 覆盖任务 |
|---|---|
| 默认关闭/dev/真实回环/新路由/旧链不扩权 | T1、T5、T7、T10 |
| 模块业务声明与平台部署信任分离、无summary依赖 | T1、T7、T8 |
| P/T精确独立来源范围、父grant不拼接、不自动扩域 | T1、T2、T8、T9、T10 |
| SourceDeclaration同动作签发、先可见性后节点诊断 | T1、T3、T4、T10 |
| 字段修订/ABA、验证不可复活、proof supersede不授权 | T2、T3、T4、T8、T10 |
| 单字段RR/只读/预算/opaque HMAC/最终当前复核 | T3、T9、T10 |
| 受限新收据与五张授权/证据表＋请求身份表/parity/冻结历史 | T2、T9、T10 |
| 固定消息首次/重领/history/ACK出站前门禁、首次claim提交即安全 | T6、T7、T8、T10 |
| blocked请求身份不授予权限、同源/换源/唯一键竞争重放 | T2、T8、T10 |
| 撤权后仍可停止、恢复须完整源授权、有序正文GET控制验收 | T8、T9、T10 |
| 固定stdlib执行物/依赖身份、D10s/会话60s/unknown | T5、T7、T10 |
| 正常配置真实TCP、旧SDK/CLI回归、分层证据/资源清理 | T10、T11 |

本计划按用户审阅修订了消息门禁前置、blocked请求指纹及撤权停止验收；这是计划层修订，不改变已批准v6的授权语义，不新增业务审批或正文存储。R2已获执行确认；T1–T10 已按实际双复核签收；T11 功能验收完成，清理待办（R4B-CLEANUP-01），不标为全部完成；每Task为独立commit/复核关口，不把用户对规格的批准扩大为生产、模型、附件或R5业务写授权。
