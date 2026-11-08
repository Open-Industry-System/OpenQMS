# 产品／过程特性语义纠偏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 纠正 DFMEA／PFMEA 特性表达及控制计划生成、同步和演示数据，在标准控制计划结构不变的前提下建立逐项可追溯的控制要求。

**Architecture:** 在现有 FMEA 功能节点内新增结构化特性集合，JSONB 仍为事实来源，不新增图节点类型。首次生成、同步预览及差异检查共用纯映射规则，CP 行 UUID 保持业务身份，内部来源元数据负责特性级匹配。旧批准记录及历史哈希不改写。

**Tech Stack:** 沿用仓库配置中的 Python／FastAPI／Pydantic／SQLAlchemy／PostgreSQL、React／TypeScript／Ant Design、pytest／Vitest／Playwright；不新增运行时依赖。

## Global Constraints

- 设计依据：[已批准设计](../specs/2026-11-01-product-process-characteristics-correction-design.md)，2026-11-01 用户确认方向，并选择子代理逐任务实施与评审；同意使用独立 worktree。
- 控制计划内容依据 `Reference` 资料，不改变标准文档结构。
- 本阶段已获代码实施和独立测试数据库验证授权；不修改业务数据库、部署环境或 GitHub 内容。
- 不新增图节点类型，不改既有结构边枚举。
- 产品／过程类型与 CC／SC 特殊分类相互独立；不得按类型自动赋 CC 或 SC，也不把 CC／SC 当作全球统一含义。
- 缺少 `characteristics` 的旧图可正常读取、展示、导出和保存，不强制批量改写已批准数据。
- 已批准 FMEA／CP、历史快照、行 UUID、CAPA 门禁与来源删除保护不被绕过。
- 新建特性使用稳定 UUID，改名不换 ID；CP 同源多控制行合法，不以来源特性设唯一行约束。
- 仅用独立 `qms_test` 或一次性迁移测试库；不向 seeded `qms` 或业务数据库运行测试／迁移。
- 不提交、推送、清库、部署或回复 GitHub，除非用户另行授权。下述每任务的检查点不是提交授权；获准提交时只暂存该任务文件。
- 不未经用户选择启动多 Agent 或工作流。无额外授权时，后续采用 inline executing-plans。
- 缺失手册／CSR 仅阻塞依赖其特定要求的规则，不冒充已覆盖最新全部标准。

---

## 0. 执行方式与基线

所有任务按顺序执行；Task 2–3 的内部能力可以独立测试，但新映射的 UI 入口在 Task 4–8 配套完成前不对用户开放。文档记录的“通过”必须有本次真实输出，不能复用历史数字。

每个代码任务固定红绿循环：先添加该节给出的测试；运行指定文件确认因为目标行为缺失而失败；做最小实现；重新运行并记录通过／失败／跳过原因；检查范围和文档后进入检查点。不得将依赖缺失、测试库不可用当成预期 RED。

执行时用以下命令建立基线：

```bash
git status --short
make check
(cd frontend && npm test -- --run)
```

后端定向命令统一从仓库根目录执行。先用 `make check-test-db` 准备独立测试库，再使用本地 `.venv`；若没有该环境，按 Makefile 的现有环境选择，不临时升级依赖：

```bash
make check-test-db
(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. \
  TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5432/qms_test \
  .venv/bin/pytest tests/test_characteristic_contract.py -q)
```

上面的本地连接仅为 Makefile 当前开发默认；如果用户已有不同测试配置，沿用其显式安全配置，不打印真实凭据。后文“后端定向测试”指使用同一环境仅替换测试文件。完整基线异常先区分既有失败与本任务回归，不擅自修复无关模块。

## 1. 文件职责图

### 新增文件

| 文件 | 职责 |
| --- | --- |
| `backend/app/schemas/characteristic.py` | 特性、来源引用的 Pydantic 契约，不含数据库操作 |
| `backend/app/services/fmea_characteristics.py` | 文档内特性索引、类型／关系校验及来源键 |
| `backend/app/services/cp_characteristic_mapping.py` | 纯快照→CP 候选行、问题、差异及稳定候选键 |
| `backend/alembic/versions/20261101_characteristic_refs.py` | CP 来源 JSONB 与特殊特性来源 ID 的兼容迁移 |
| `frontend/src/components/fmea/CharacteristicEditor.tsx` | 同一功能下多特性录入，模式约束由父页面显式传入 |
| `frontend/src/utils/fmeaCharacteristics.ts` | 特性更新、复制、关系删除及稳定身份辅助函数 |
| `docs/development/characteristic-correction-acceptance.md` | 参考依据、模板基线、执行证据、剩余限制 |

### 主要既有文件

- FMEA：`backend/app/schemas/fmea.py`、`backend/app/services/fmea_service.py`、`backend/app/services/graph_projection_service.py`；`frontend/src/types/index.ts`、`frontend/src/utils/fmeaTable.ts`、`frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`、`PFMEAWizardPage.tsx`、`FMEAEditorPage.tsx`、`deleteRowHelpers.ts`；`frontend/src/components/pfmea/FunctionTreeEditor.tsx`。
- CP：`backend/app/models/control_plan.py`、`backend/app/schemas/control_plan.py`、`backend/app/schemas/version.py`、`backend/app/services/control_plan_service.py`、`backend/app/services/version_service.py`、`backend/app/api/control_plan.py`、`backend/app/api/version.py`。
- 消费者：`backend/app/models/special_characteristic.py`、`backend/app/schemas/special_characteristic.py`、`backend/app/services/special_characteristic_service.py`、`backend/app/services/cp_validation/rule_engine.py`、`frontend/src/pages/planning/special-characteristic/TraceabilityPage.tsx`。
- 前端交互：`frontend/src/api/controlPlan.ts`、`frontend/src/api/version.ts`、`frontend/src/components/control-plan/ImportFromFMEAModal.tsx`、`frontend/src/components/version/SyncPreviewDrawer.tsx`、`frontend/src/utils/controlPlanDiff.ts`；相关 `zh-CN`／`en-US` locale。
- 演示与文档：`backend/app/seed.py`、`backend/app/seed_e2e.py`、`docs/modules/planning.md`、局部 README、有关用户故事与 verify skill、`PROGRESS.md` 的本任务条目。

实施时先看相关局部 AGENTS.md。上表未列出的生产文件只有在定位到本任务具体消费者并说明原因后才修改，不进行全仓整理。

## Task 1: 固定标准表格和实施基线

**Files:**
- Create: `docs/development/characteristic-correction-acceptance.md`
- Read: `Reference/IATF16949.md` §8.3.3.3、§8.5.1.1、附录 A；`Reference/FMEA.md` PFMEA §3.3.3；`Reference/FMEA_Explanation.md` §3.8。
- Read: `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx` 及真实存在的文档输出入口。

**Interfaces:** Produces 后续任务共用的表格字段顺序、分组与现有能力记录，不新增生产接口。

- [ ] **Step 1:** 运行第 0 节基线命令，记录当前分支、HEAD、工作区已有修改、测试结果和环境限制。不要将用户已有修改混入本任务。
- [ ] **Step 2:** 按下面清单逐项记录实际表格，附当前页面截图或组件断言。只定位实际存在的输出，不根据 PRD 宣称已有 Excel／PDF：

```text
过程编号 | 过程名称/作业描述 | 机器/设备/工装
特性：编号 | 产品 | 过程 | 特殊分类
方法：规范/公差 | 评价/测量技术 | 样本量 | 频次 | 控制方法
反应计划
```

- [ ] **Step 3:** 逐项对照附录 A 最低内容。已有模板内容不足或 OCR 分组不清的项记录为业务复核，不擅自添加／删除标准栏目；无法核实的原始模板部分停止相关模板改动。
- [ ] **Step 4:** 查明已批准 CP 的合法修订路径。当前 `update_control_plan`、同步接口拒绝 approved，不能用直接改状态或 rollback API 假定具有修订授权。若无合法路径，明确本轮只对新草稿和经合法流程返工的对象开放，历史批准案例不自动修正。
- [ ] **Step 5:** 文档链接和 `git diff --check` 通过后做检查点。资料检查不阻塞后续纯内部兼容能力；用户表格或修订语义需变动时先确认。

## Task 2: 特性契约及 FMEA 读写兼容

**Files:**
- Create: `backend/app/schemas/characteristic.py`、`backend/app/services/fmea_characteristics.py`、`backend/tests/test_characteristic_contract.py`
- Modify: `backend/app/schemas/fmea.py`、`backend/app/services/fmea_service.py`、`frontend/src/types/index.ts`
- Test: `backend/tests/test_fmea_schema_extensions.py`、`backend/tests/test_fmea_approval_gates.py`

**Interfaces:**
- `Characteristic`：`id: UUID`、`kind: Literal['product','process']`、`name: str`、`specification/unit/classification/reference: str | None`、`related_product_characteristic_ids: list[UUID]`。
- `CharacteristicSourceRef`：`mapping_version: int`、`fmea_id: UUID`、`step_id/function_id: str`、`work_element_id: str | None`、`characteristic_id: UUID`、`accepted_source_version_id: UUID | None = None`。最后一项为逐行最后接受的真实来源版本，纯映射时为空、实际应用时由服务填入；不进入 source_key。
- `validate_characteristics(fmea_type: str, graph: dict) -> None`：仅校验存在的新集合，旧图无集合不改写；错误使用既有 `ValueError` 约定。
- `source_key(ref: CharacteristicSourceRef) -> str`：稳定 JSON 编码 `fmea_id, step_id, function_id, characteristic_id`，不包含名字、版本、排序。

- [ ] **Step 1: RED** 添加真实 round-trip 测试，确认现有 Schema 丢失特性字段；不要先写实现：

```python
import uuid
from app.schemas.fmea import GraphNodeSchema

def test_function_characteristics_round_trip():
    cid = str(uuid.uuid4())
    node = GraphNodeSchema.model_validate({
        'id': 'sf1', 'type': 'ProcessStepFunction', 'name': '准确贴装',
        'characteristics': [{'id': cid, 'kind': 'product', 'name': '偏移量',
                             'specification': '≤0.05 mm'}],
    })
    saved = node.model_dump(mode='json')
    assert saved['name'] == '准确贴装'
    assert saved['characteristics'][0]['id'] == cid
    assert saved['characteristics'][0]['name'] == '偏移量'
```

运行 `tests/test_characteristic_contract.py`，预期因为 `characteristics` 不存在／被过滤而失败。

- [ ] **Step 2:** 契约实现以以下字段声明为起点，字段类型与本节 Interfaces 一致；旧图与显式空集合区分：

```python
# GraphNodeSchema 中；不删除 requirement/specification/classification
characteristics: list[Characteristic] | None = None
```

在图整体写入服务调用 `validate_characteristics(fmea.fmea_type, graph)`；单节点 Schema 不尝试根据全局父关系判定层级。仅旧集合缺失允许兼容；新集合拒绝重复 UUID、空名称、非法层级、悬空／跨工序／错误类型关系。

- [ ] **Step 3:** 添加文档级用例：DFMEA 共用 ProcessWorkElementFunction 仍只允许产品特性；PFMEA 步骤下 product、工作要素下 process；4M 名称不代表 equipment；定性规范和空具体量值合法。不同工厂同名节点不构成关系。
- [ ] **Step 4:** 添加 API 保存→读取、新旧快照恢复用例，确认 `wizardScope`、新字段和既有风险字段保留；更新时使用 `model_fields_set`／现有部分更新方式，不能把缺省 None 当作清空请求。统一集合一旦明确存在，即使 `[]` 也不能回退旧 classification 生成幽灵特性。
- [ ] **Step 5: GREEN / checkpoint** 运行本任务三份测试，前端 tsc；记录 A01、A05、A13 的契约证据，不开放新生成入口。

## Task 3: 纯映射器与稳定候选键

**Files:**
- Create: `backend/app/services/cp_characteristic_mapping.py`、`backend/tests/test_cp_characteristic_mapping.py`
- Uses: Task 2 契约与校验；无数据库或图投影依赖。

**Interfaces:**
- `MappingIssue(code: str, node_id: str, blocking: bool, message: str)`，冻结 dataclass。
- `MappedCPItem(source_ref: CharacteristicSourceRef, fields: dict[str, str | None])`，冻结 dataclass。
- `MappingResult(items: tuple[MappedCPItem, ...], issues: tuple[MappingIssue, ...])`，冻结 dataclass。
- `derive_cp_items(*, fmea_id: UUID, fmea_type: str, graph: dict, step_ids: tuple[str, ...]) -> MappingResult`。
- `candidate_key(action: str, source_ref: CharacteristicSourceRef, item_id: UUID | None) -> str`：用 SHA-256 编码 action、source_key、真实 item_id（新增为 None）；不是权限令牌。

- [ ] **Step 1: RED** 在新测试文件定义完整图 `product_process_graph` fixture：工序 `s1`、机器工作要素 `w1`（Machine）、步骤功能 `sf1`、工作要素功能 `wf1`；合法类型边；sf1 含两项 product，wf1 含三项 process，一项过程特性关联两项 product。特性 ID 全部用固定 UUID 字符串，以免顺序断言随机失败。

```python
def test_two_product_three_process_yield_five_rows(product_process_graph):
    from uuid import UUID
    from app.services.cp_characteristic_mapping import derive_cp_items
    result = derive_cp_items(
        fmea_id=UUID('00000000-0000-0000-0000-000000000001'),
        fmea_type='PFMEA', graph=product_process_graph, step_ids=('s1',),
    )
    assert not any(i.blocking for i in result.issues)
    assert len(result.items) == 5
    assert sum(bool(i.fields.get('product_characteristic')) for i in result.items) == 2
    assert sum(bool(i.fields.get('process_characteristic')) for i in result.items) == 3
    assert all(not (i.fields.get('product_characteristic') and
                    i.fields.get('process_characteristic')) for i in result.items)
```

运行该文件确认缺模块／行为缺失的 RED；fixture 自身必须先能合法构造。

- [ ] **Step 2:** 逐边类型解析，按工序、功能、特性数组顺序生成独立控制行；将当前对象规范及分类填入对应行。实现明确的初稿字段起点：

```python
fields = {
    'step_no': step.get('process_number') or '',
    'process_name': step.get('name') or '',
    'product_characteristic': characteristic.name if characteristic.kind == 'product' else None,
    'process_characteristic': characteristic.name if characteristic.kind == 'process' else None,
    'specification_tolerance': characteristic.specification,
    'special_class': characteristic.classification,
}
```

设备仅从明确 Machine 工作要素取得；product 行存在多台候选机器则空值加提示，不把第一台当真实来源。不把 unit 重复拼入已含单位的规范；本轮无需引入数值公差解析器。

- [ ] **Step 3:** 增加无关系警告、旧函数 blocking issue、错误边忽略／拒绝、DFMEA 拒绝、选中工序无效拒绝、多对多不重复、名称／规范变化不改变 source_key／candidate_key 的测试。显式空选中集合返回选择错误，不解释为全选。
- [ ] **Step 4: GREEN / checkpoint** 所有纯测试通过；A02–A05、A16 的证据明确。映射器不生成方法、抽样、反应计划或 AI 判断。

## Task 4: CP 来源存储、快照与特殊特性身份基础

**Files:**
- Create: `backend/alembic/versions/20261101_characteristic_refs.py`、`backend/tests/migrations/test_characteristic_refs.py`、`backend/tests/test_cp_characteristic_versions.py`
- Modify: `backend/app/models/control_plan.py`、`backend/app/schemas/control_plan.py`、`backend/app/services/version_service.py`、`backend/app/services/control_plan_service.py`
- Modify: `backend/app/models/special_characteristic.py`、`backend/app/schemas/special_characteristic.py`、`frontend/src/types/index.ts`、`frontend/src/types/specialCharacteristic.ts`

**Interfaces:**
- CP ORM 可空 `source_characteristic_ref: dict | None`，API 响应使用 Task 2 的强类型引用。该字段为服务端管理，不在通用写请求接受任意来源替换。
- SpecialCharacteristic 可空 `source_characteristic_id: UUID | None`；原 `source_node_id` 保留函数／旧节点身份，`sc_category` 使用已有 product／process 枚举。
- 不给 CP 特性来源建唯一约束；SC 提取按文档＋特性 ID 匹配，旧记录维持旧身份直到人工确认。

- [ ] **Step 1: RED** 用现有 `db/default_factory/admin_user` fixture 构造一 CP、两条同源明细，调用 `create_cp_version`，断言行 UUID 与完整 source_characteristic_ref 进入快照且两行均保留。另测旧快照缺字段恢复后不保留未来来源引用。运行 `tests/test_cp_characteristic_versions.py`。
- [ ] **Step 2:** 用 Alembic ScriptDirectory 在执行时取真实单一 head，创建手写迁移；多 head 时停止检查而不自动生成 merge。迁移内容明确为：

```python
def upgrade():
    op.add_column('control_plan_items', sa.Column('source_characteristic_ref', postgresql.JSONB(), nullable=True))
    op.add_column('special_characteristics', sa.Column('source_characteristic_id', postgresql.UUID(as_uuid=True), nullable=True))

def downgrade():
    op.drop_column('special_characteristics', 'source_characteristic_id')
    op.drop_column('control_plan_items', 'source_characteristic_ref')
```

revision 固定 `20261101_char_refs`，down_revision 填执行时实际查得的 head，不在业务库升级／降级；降级仅在空的迁移测试库验证，生产回退遵循设计限制。

- [ ] **Step 3:** 更新 ORM、快照构建、比较及恢复字段。通用 CP 更新保持已存来源元数据且验证现有 item_id 所属；新手工行来源为 None；不得让客户端重绑定已有来源。旧快照恢复在允许的状态下显式将缺失来源置 None，历史快照原内容及哈希不重算。
- [ ] **Step 4:** 在 `mig_db_url` 一次性库测试旧行升级保留、两列 nullable、metadata reflection、upgrade head 以及空库降级；版本测试涵盖特性集合和 CP 引用、item_id、哈希和缺字段恢复。
- [ ] **Step 5: GREEN / checkpoint** 运行上述测试及 `tests/test_control_plan_item_id_stability.py`、`tests/test_control_plan_uuid_dedup.py`、`tests/capa/test_capa_doc_gate_preflight.py`。迁移不包含数据回填。

## Task 5: 首次导入的预览、应用及访问边界

**Files:**
- Create: `backend/tests/test_cp_characteristic_import.py`
- Modify: `backend/app/api/control_plan.py`、`backend/app/schemas/control_plan.py`、`backend/app/services/control_plan_service.py`、`backend/app/services/cp_characteristic_mapping.py`
- 必要事务适配：`backend/app/services/version_service.py` 及对应版本／导入测试。2026-11-01 实施核对发现原 CP 版本写入器会内部提交，必须拆出无提交阶段以满足本任务已确认的事务原子性；不修改全局租户依赖或无关调用语义。
- 必要锁顺序适配：`backend/app/services/permission_service.py` 的权限替换写入及其真实双会话回归。2026-11-01 Task 5 独立评审发现新导入的父角色锁与现有 DELETE→INSERT 权限替换存在死锁交错；统一为替换前先取得对应角色父锁，保持现有权限规则、函数签名和提交所有权，不削弱导入对缺失授权插入的保护。

**Interfaces:**
- `stage_cp_version(db, cp, change_type, change_summary, user_id, source_fmea_version_id=None) -> ControlPlanVersion`：复用现有快照、哈希、锁和审计逻辑，仅 flush，不 commit／refresh。原 `create_cp_version` 保持签名与提交／刷新行为，作为兼容包装器，不复制快照逻辑。新导入独占最后一次提交，提交前准备响应，提交后不再读取业务表。
- 保留 `POST /api/control-plans/{cp_id}/import-from-fmea` 为应用入口；增加同资源 `POST /{cp_id}/import-from-fmea/preview`。
- 请求：`fmea_id, source_fmea_version_id, expected_lock_version, step_ids`；应用附加 `preview_digest, selected_candidate_keys`。旧 `step_nos` 仅在唯一匹配时解析，禁止和 `step_ids` 同时冲突指定。
- 响应：`source_fmea_version_id, expected_lock_version, mapping_version, preview_digest, items, issues`；每项有 candidate_key、source_ref、fields。应用返回已有行列表形状，不新增分页约定。
- 预览 digest 为重新派生结果的规范 JSON SHA-256，包含 CP ID／锁版本、来源版本／快照哈希、工序选择、映射版本、候选与 issues；它不提供授权，实际应用仍重新检查作用域及状态。

- [ ] **Step 1: RED** 数据库测试先固定批准 PFMEA 版本和 draft CP；预览后不产生 CP 行，应用后产生五条；再应用同源不会增加行。以下断言必须存在：

```python
assert preview['source_fmea_version_id'] == str(approved_version.version_id)
assert len(preview['items']) == 5
assert all('candidate_key' in row for row in preview['items'])
assert len(created_items) == 5
assert {row.source_fmea_node_id for row in created_items} == {'s1'}
assert all(row.factory_id == cp.factory_id for row in created_items)
```

测试构造所需 approved_version、cp、created_items 使用本文件真实 db fixture 和服务／API，不用未定义 helper；读取 RequestScope 的现有 API 测试 fixture 模式建立用户，不靠修改生产权限绕过。

- [ ] **Step 2:** 服务校验双方 tenant／factory／product line、CP 写权限、源读权限、来源版本归属和批准依据；不能仅信当前 FMEA status 或版本号，须核对版本 change_type／批准快照的实际语义。找不到唯一真实批准源时明确拒绝。
- [ ] **Step 3:** 应用事务按既有顺序锁 CP 及必要授权记录，重新查状态／锁版本，重算 digest 和候选键；只接受本次候选。对已存在单一自动行原样返回／提示改用同步，不把导入变为无预览覆盖；同源多控制行提示人工歧义。创建新行、写 source_ref（accepted_source_version_id 填实际批准版本）、审计并递增 CP lock_version；版本记录真实源版本，事务失败全量回滚。
- [ ] **Step 4:** 添加旧调用缺失预览信息返回 409＋重新预览指引、旧 step_nos 重复歧义、空选择、非法候选、过期锁、越权／跨工厂／跨产品线、approved CP、旧自由文本源、源版本不属于 FMEA、创建第二行时注入异常回滚测试。不要返回授权之外的源名称。
- [ ] **Step 5: GREEN / checkpoint** 后端定向测试通过，API 文档明确此次兼容变化。旧客户端仅能安全失败并重新预览，不静默改变来源版本。

## Task 6: 版本同步、差异检查及三方冲突

**Files:**
- Create: `backend/tests/test_cp_characteristic_sync.py`
- Modify: `backend/app/services/version_service.py`、`backend/app/services/control_plan_service.py`、`backend/app/services/cp_characteristic_mapping.py`、`backend/app/api/version.py`、`backend/app/schemas/version.py`
- 用户于 2026-11-02 确认的补充：[控制计划同步保守保护细则](../specs/2026-11-02-cp-sync-conservative-protection-design.md)。允许新增聚焦的 `backend/app/services/cp_sync_protection.py` 及保护／真实并发测试；允许 `capa_doc_gate_service.py` 和必要局部 helper 参与 CP 输入锁及新鲜度协调；特殊特性关联写入仅限必要的目标存在性／锁适配。不引入特批删改流程，不改变手工更新／回退或 CAPA 覆盖规则。

**Interfaces:**
- 现有 `GET /api/control-plans/{cp_id}/sync-preview` 支持明确 `source_fmea_version_id`；缺省只选唯一可证明的最新批准版本，不再任取最新 snapshot。
- 现有 `POST /api/control-plans/{cp_id}/sync-from-fmea` 使用 source version、expected lock、digest、selected_candidate_keys；旧 selected_item_ids 缺少稳定上下文时 409，不尝试猜新增 UUID。
- `build_sync_preview` 和 `apply_sync_preview` 保留现有服务位置，内部使用 Task 3–5 契约；候选动作 `add/sync/delete`，另用 `issues/conflicts` 标记不可自动应用项。
- 源管理字段集显式含 `step_no`；人工管理字段不自动覆盖。

- [ ] **Step 1: RED** 同工序五行分别改名、规范清空、分类取消、来源删除；预览保留对应 item_id，各字段差异准确。为新增项调用预览两次，candidate_key 相同，且跨两次请求确认成功；现有随机新增 UUID 的错误不能继续存在。
- [ ] **Step 2:** 移除 `existing_by_node: dict[step_id, item]` 的单值匹配；按 source_key 索引到行列表。遍历源目标集合与已有来源集合，列出每个实际行，人工行及历史混合行只报告待确认，不自动删除。
- [ ] **Step 3:** 使用上次实际接受源版本的快照派生字段作为三方基线；初次导入版本须可定位到实际行来源。局部同步时更新 Task 2 已定义的服务端 `accepted_source_version_id`，记录每行最后接受的真实版本，不用全 CP 单一版本伪装每行均一致；Task 4 已保存该引用的完整内容，source_key 不包含来源版本。

```python
# missing 通过字段存在性识别，不用 truthiness 表达清空。
source_changed = new_value != base_value
local_changed = current_value != base_value
conflict = source_changed and local_changed and current_value != new_value
```

没有可靠基线时显式人工冲突；来源有意清空为 None／空串必须呈现。过程方法、频次、反应计划及 spc_chart_id／gauge_id 等人工字段保留，只提示复核。

- [ ] **Step 4:** 原有应用在请求时重新构造随机新增 UUID 的行为改为稳定 candidate_key 选择；实际新增时才分配 UUID。锁住 CP 后检查 digest，按选项处理，保留既有 CAPA 保护、版本审计及已批准不可写规则。未接受变更仍保持 pending；每行接受版本真实记录。删除来源特性不自动删除量具／SPC／历史证据。
- [ ] **Step 5:** 补并发、部分接受、再次同步、手工多控制行、改工序号、旧无基线记录、跨版本快照、受审删除保护用例；运行本文件、Task 4–5 文件及 `tests/test_cp_sync_worker.py`、`tests/test_transition_cp_outbox.py`。A06–A12 和 A18 必须有证据，不能只验证内部辅助函数。

## Task 7: FMEA 录入、图表往返及图投影

**Files:**
- Create: `frontend/src/components/fmea/CharacteristicEditor.tsx`、对应 `.test.tsx`；`frontend/src/utils/fmeaCharacteristics.ts`、对应 `.test.ts`
- Modify: PFMEA `FunctionTreeEditor.tsx`、DFMEA `DFMEAWizardPage.tsx`、FMEA 编辑／删除入口及相关 graph diff／normalize 消费者。
- Modify: `backend/app/services/graph_projection_service.py`；Test: `backend/tests/test_graph_projection.py`
- Test: `frontend/src/pages/planning/fmea/DFMEAWizardPage.test.tsx`、`frontend/src/pages/planning/fmea/FMEAVersionSnapshot.test.tsx`、`frontend/src/pages/planning/fmea/deleteRow.test.tsx`

**Interfaces:**

```typescript
interface CharacteristicEditorProps {
  value: Characteristic[] | null | undefined;
  allowedKind: 'product' | 'process';
  productOptions: { id: string; name: string }[];
  readOnly: boolean;
  onChange: (value: Characteristic[]) => void;
}
// frontend/src/types/index.ts 中 Characteristic 对应 Task 2 JSON 输出。
```

- [ ] **Step 1: RED** 渲染编辑器并新增两个特性；断言 name／specification／classification 分开保存；改名 id 不变；DFMEA 下层功能只显示 product；legacy 提示不触发 onChange。运行新增 Vitest 文件确认缺组件失败。
- [ ] **Step 2:** 用现有 Ant Design 组件和中文样式实现多特性卡片，不引入视觉重构。挂接 PFMEA／DFMEA 实际编辑入口；旧 requirement/specification 可作为待确认预填但必须用户明确接受。新数组存在时不继续把旧字段当权威源。
- [ ] **Step 3:** 辅助函数按以下方式保留功能信息和其它节点字段；创建／复制采用 `crypto.randomUUID()`，文档副本需建立旧→新特性 ID 映射后改写关系，不能复制 ID 形成同文档冲突：

```typescript
const nextNodes = nodes.map(node =>
  node.id === functionId ? { ...node, characteristics: nextCharacteristics } : node
);
```

删除被引用特性时列出关联影响，确认后删除相关引用，不自动重指向第一项；共享函数仍被使用时不因删除失效链行而删其特性。图表、diff、dirty hash、undo／恢复如实际存在的路径均保留集合；不重新实现未存在的功能。

- [ ] **Step 4:** Neo4j 不能直接存对象数组作为属性。纯投影把集合序列化到独立 `characteristics_json` 字符串属性，不新增节点或动态标签；新增投影／JSONB parity 测试，解码后与源一致。仅当集合字段明确存在时序列化；新特性读取依旧以 JSONB 为准，不引入跨后端降级写入。

```python
props['characteristics_json'] = json.dumps(
    node['characteristics'], ensure_ascii=False, sort_keys=True, separators=(',', ':')
)
```

- [ ] **Step 5: GREEN / checkpoint** 运行本任务前端用例、现有 PFMEA/DFMEA wizard 用例、前端 tsc；单独运行 `tests/test_graph_projection.py`（当前 make check 默认忽略此文件，必须显式覆盖）。实际 Neo4j 集成没有授权环境时标注限制，不把纯投影测试当集成通过。

## Task 8: CP 预览交互与标准表格回归

**Files:**
- Create: `frontend/src/components/control-plan/ImportFromFMEAModal.test.tsx`、`frontend/src/components/version/SyncPreviewDrawer.test.tsx`、`frontend/src/pages/planning/control-plan/CharacteristicTemplate.test.tsx`
- Modify: `frontend/src/api/controlPlan.ts`、`frontend/src/api/version.ts`、`frontend/src/types/index.ts`、上述组件、CP 编辑页、`frontend/src/utils/controlPlanDiff.ts`、相关 locale。

**Interfaces:** 前端请求／响应严格对应 Task 5–6；selection 使用 candidate_key 而非新增候选 item_id；实际 existing item_id 只作为行身份。

- [ ] **Step 1: RED** mock 预览返回五条候选、一个关系警告；断言预览前不发写请求，确认后请求包含版本、锁、digest 及 selected_candidate_keys；409 后要求重新预览且不自动再次应用。
- [ ] **Step 2:** UI 保留原表头和分组，导入弹窗增加“预览→确认”；不可应用项禁选、原因可见；删除默认不选；部分接受后显示仍有待同步项。切换 CP／源版本／工序时清空旧预览与选择，使用现有取消／卸载保护。
- [ ] **Step 3:** 无新来源引用的历史行显示复核提示，不自动拆分；新生成行产品／过程单列填写，工序重复／合并维持 Task 1 基线。客户端提交不得通过 object spread 把服务端来源元数据写入可变请求；修改已有行保留 item_id。
- [ ] **Step 4:** 模板回归用实际表头 label／分组断言，不用整页快照掩盖内容变化：

```typescript
expect(screen.getByText('产品特性')).toBeInTheDocument();
expect(screen.getByText('过程特性')).toBeInTheDocument();
expect(screen.getByText('反应计划')).toBeInTheDocument();
expect(screen.queryByText('内部来源元数据')).not.toBeInTheDocument();
```

实际翻译键及表头合并断言按 Task 1 捕获基线实现；不能为适配测试换列名。`controlPlanDiff` 对元数据比较使用内容等价，不用对象引用 `!==` 制造永久冲突。

- [ ] **Step 5: GREEN / checkpoint** 运行三个新文件、`CPVersionSnapshot.test.tsx`、API 刷新／身份切换相关既有测试、前端 tsc/build；图形输出只有实际存在时才添加对应对照，不新增导出产品。

## Task 9: 特殊特性、校验、CAPA 及执行关联消费者

**Files:**
- Create: `backend/tests/test_characteristic_consumers.py`、`backend/tests/test_cp_characteristic_validation.py`
- Modify: `backend/app/services/special_characteristic_service.py`、`backend/app/services/cp_validation/rule_engine.py`、`frontend/src/pages/planning/special-characteristic/TraceabilityPage.tsx`
- Regression: `backend/tests/capa/test_capa_doc_gate_preflight.py`、CP 行 UUID 稳定性测试、现有 safety 审批相关测试。

**Interfaces:** Task 4 的 SC source_characteristic_id 和已有 sc_category/spec_requirement；Task 2 来源键；Task 3 派生规范。保留历史 node-based 分支但不混同新旧身份。

- [ ] **Step 1: RED** 同一工序的步骤功能含 product CC、工作要素功能含 process SC，提取为独立特性且类型／规范正确；另用同一函数两项同类型但分类不同的特性，证明不按函数 ID 合并，也不把 CC／SC 当作产品／过程类型。与 CP 的匹配必须逐项正确，不能把工序首个 CC 复制给所有行；不得通过旧同步入口绕过新来源的批准版本、人工覆盖和保守保护要求，必要时只建立精确追溯并报告需进入正式版本同步的差异。来源特性改名不生成新 sc_id；取消分类不静默删除安全审批记录。
- [ ] **Step 2:** 新集合只从逐项显式分类提取，不因函数名字或 severity 自动赋 CC；旧 severity-based 安全建议保持为历史兼容信息，不伪装成已确认新特性。新来源禁止同名自动挂接另一 DFMEA／工厂的 parent_sc；跨 DFMEA→PFMEA 只显示显式已有依据，否则待人工确认。
- [ ] **Step 3:** 现有 `cp_item_id` 为单值不能表达一个特性多控制行。新来源追溯查询以 source_ref 匹配全部 CP 行作为只读派生列表；不覆写单值让最后一行冒充全部覆盖，不新增多对多主数据平台。来源匹配须限定文档／工厂／产品线及 RequestScope。
- [ ] **Step 4:** 新校验按行身份＋来源键分隔状态，保留 R001–R004 含义，新规则用 R005（规范缺失）、R006（历史双对象归属复核）warning；如执行时编号已被占用，选择连续未占用编号并同步测试／文档，不覆盖。明确受控规范引用与定性要求可满足对应字段；不以关键词强制判定特性类型。

```python
char_key = source_key(ref) if ref else (item.source_fmea_node_id or item.step_no or '')
stable_key = f'{char_key}|{item.item_id}'
```

缺字段的 legacy 测试对象用现有兼容方式访问；不能未经批准让新 warning 成为全局审批阻断。

- [ ] **Step 5:** 验证 SPC／gauge 外键保持、无权限关联拒绝、MSA 缺失不造合格、CP 项 UUID 与 CAPA target_key 仍相同，以及本次自动路径的受控材料保护。用户已明确选择：仅约束本次自动提取／同步，不能改动或删除 `safety_approval_status=submitted/approved` 的安全特殊特性材料，源变化仅提示复核；不修改旧手工更新／删除入口、不新增修订／删除或安全审批流程。旧手工入口缺少保护及原有创建审计缺陷单独记录，不能声称已修复。若自动路径仍需未定义的新政策，报告具体阻塞，不绕过保护。
- [ ] **Step 6: GREEN / checkpoint** 运行两份新测试和上述回归；记录 A11、A16–A18、A21。未能运行的真实服务验收单列，不借此改安全审批状态机。

## Task 10: 贯通演示数据和版本基线

**Files:**
- Create: `backend/tests/test_characteristic_demo_data.py`
- Modify: `backend/app/seed.py`、`backend/app/seed_e2e.py`
- Regression: `frontend/e2e/specs/m1-core/capa-story-doc-gate.spec.ts` 及 canonical 输入消费者。

**Interfaces:** 示例使用 Task 2 特性契约及 Task 3 同样的映射口径；固定演示 UUID／规范号只代表示例，不表示真实顾客文件。

- [ ] **Step 1: RED** 对 seed 中规范化图与 CP 数据建立纯断言：同为 DC-DC 100W 产品；无空载转速／RPM；贴装偏移量≤0.05mm、贴装力3.0±0.5N分别控制；AOI 只对应位置；特殊分类无依据默认空。把构造数据提取为同模块可测试的纯构造函数，数据库插入仍由既有 seed 执行。
- [ ] **Step 2:** 用固定 UUID 为产品／过程特性赋身份，功能名保留功能含义。把 E2E “定位销磨损检测”从过程特性改为实际对象“定位销磨损量”并在方法中写检测活动；若业务没有可信限值，保留缺失提示而非随意填值。
- [ ] **Step 3:** 主示例独立明细完整填写：位置每件 AOI、每件结果；贴装力每次动作监控；反应计划包括隔离范围与恢复确认。所有演示数值／文件号明示模拟；不得捏造 MSA、PPAP 或顾客批准。原 seed approved 记录若内容不完整，改为新环境中的 draft，不迁移既有业务状态。
- [ ] **Step 4:** 同步 E2E canonical snapshot、差异预期和哈希构造；不能直接改已批准快照数据或数据库触发器来通过测试。seed 已存在跳过行为不变；不新增按单号强制覆盖脚本。
- [ ] **Step 5: GREEN / checkpoint** 运行纯示例测试、Task 3 映射测试和 CP canonical／CAPA 门禁相关后端测试。只在独立 E2E 环境且获得执行授权后运行 seed；现有演示环境修复另需明确授权及合法修订路径。

## Task 11: 文档、用户故事、浏览器验收及整体检查

**Files:**
- Create: `frontend/e2e/specs/m1-core/characteristic-correction.spec.ts`
- Modify: `docs/modules/planning.md`、`frontend/src/types/README.md`、`frontend/src/utils/README.md`、`backend/app/graph/README.md`、`PROGRESS.md` 的相关条目。
- Modify: `docs/user-stories/US-E2E-02-fmea-lifecycle/US-E2E-02.3-pfmea-step3-function.md`、`US-E2E-02.10-dfmea-step3-function.md`、`US-E2E-02.15-editor-row-crud.md`、`US-E2E-02.18-version-snapshot-cp-sync.md`；更新关联 README 汇总版本。
- Modify: `.claude/skills/verify-fmea-lifecycle-pfmea-step3-function/SKILL.md`、`verify-fmea-lifecycle-dfmea-step3-function/SKILL.md`、`verify-fmea-lifecycle-editor-row-crud/SKILL.md`、`verify-fmea-lifecycle-version-snapshot-cp-sync/SKILL.md`。
- Modify: Task 1 验收证据文档。
- 集成收尾：修正 `backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py::test_single_alembic_head` 对已新增 `20261101_char_refs` 的预期，并移除该纯元数据断言不需要的建库 fixture；不得用跳过／排除替代。
- 收尾 Task 7 已登记的两个 Minor：前端按实际 `HAS_FUNCTION` 所属结构及 FMEA 类型确定特性类型，空白既有名称显示必填反馈；只改相关 helper／编辑器／调用点和回归，不改标准表格或业务审批。
- 用户已授权隔离完整检查与本地真实浏览器验收。为避免共享 reset／私密配置，允许必要的精简 test-only bootstrap、独立 Playwright 配置与端点防护测试；只在任务专用实例与新建测试数据上运行，不外发 AI 请求，正常业务验收不关闭保护。

**Interfaces:** 对外当前事实以真实实现为准；设计不自动替代模块文档，验收结果必须注明故事及脚本版本。

- [ ] **Step 1: RED** E2E 从合法新草稿开始：同一工序的步骤功能录入两项产品特性、工作要素功能录入三项过程特性→保存刷新→完成既有审批→选择批准版本预览 CP→生成五条明细→改特性并再次审批→CP 同步预览与接受→刷新确认行身份／内容。浏览器复用安全适用的 auth、api-client 和 cleanup 思路，测试数据唯一命名并清理，不能用真实业务单据；不得依赖会运行共享重置的全局 setup。
- [ ] **Step 2:** 增加 legacy 只读提示、409 重新预览、部分接受 pending 和标准表头保持场景。Playwright 核心断言：

```typescript
await expect(page.getByText('元器件贴装偏移量', { exact: true }).first()).toBeVisible();
await expect(page.getByText('贴装力', { exact: true }).first()).toBeVisible();
await expect(page.getByText('空载转速', { exact: true })).toHaveCount(0);
```

真实定位器按应用最终 accessible labels 编写；不能通过直接写库绕过源批准来构造通过路径。

- [ ] **Step 3:** 更新四个故事及四份 verify skill 的版本声明和步骤，再运行验收；模块文档说明旧图兼容、结构化字段、预览条件、approved 限制和标准不变。不修改无关进度条目，不将新功能目标写成早已实现。
- [ ] **Step 4:** 执行整体验证并记录实际结果：

```bash
make check
(cd frontend && npm test -- --run)
# Graph projection 被 make check 默认排除，另用第 0 节环境显式执行：
# backend/.venv/bin/pytest tests/test_graph_projection.py -q
make e2e-run TEST_ARGS='e2e/specs/m1-core/characteristic-correction.spec.ts'
```

最后一条仅在已有获准 E2E 环境、相应授权文件和服务就绪后执行。需要启动／初始化时先核对 `docs/e2e.md` 及现有项目验收 skill；不运行 e2e-reset，不自行改真实连接。外部服务、scanner 或 provider 不可用如实记录，不把 skip／xfail／xpass 混为通过。

- [ ] **Step 5:** 按下面覆盖表填入测试文件、运行命令、实际证据和剩余限制；执行 `git diff --check`，确认未改标准结构、无无关文件、没有历史批准数据迁移。按验证结果更新 PROGRESS，不先宣布完成。
- [ ] **Step 6: final checkpoint** 向用户交付结果、证据和未完成项。只有用户另行授权才提交／推送；授权提交也不代表可回复 GitHub、合并或部署。

## 验收覆盖表

| 设计验收项 | 主要任务 | 必须提供的证据 |
| --- | --- | --- |
| A01、A05、A13 | 2、3、7 | Schema round-trip、文档级关系校验、DFMEA／PFMEA 页面用例 |
| A02–A04 | 3、5 | 2＋3→5、关系不重复、旧数据零部分写入 |
| A06–A10 | 5、6、8 | 真实数据库导入／同步、稳定键、清空、冲突、部分接受与并发 |
| A11–A12 | 4、6、9 | 行 UUID、旧／新哈希、恢复、CAPA 保护回归 |
| A14 | 7 | 复制／删除／图表往返及 wizardScope、多后果既有语义不变 |
| A15–A16 | 3、7、9、10 | 类型与分类独立、单位／方法正确、定性准则兼容 |
| A17–A18 | 5、6、9 | 权限变化、跨作用域、提交时重查、失败回滚 |
| A19 | 1、8、11 | 结构基线、表头与实际输出对照；未实现输出格式明确标记 |
| A20–A21 | 9、10、11 | seed 不覆盖既有数据，无伪造证据，执行关联保持 |

## 计划自审与发布边界

- 计划包括首次导入、版本同步、差异检查、快照恢复、图表往返、图投影、特殊特性及 CAPA 消费者，没有只修一条路径。
- `accepted_source_version_id` 在 Task 2 定义、Task 4 保存、Task 5 首次填入、Task 6 逐行更新，不是新增标准表格列；前后端契约保持同名同义。
- SC 只补内部特性身份，不建设跨模块特性主数据；同名自动跨文档配对对新来源禁用。
- 来源版本的批准资格、旧客户端安全失败和 approved CP 合法修订在实施前核实；不以测试通过代替业务授权。
- 标准、CSR 和模板原件缺口单列，不能将本计划完成表述为全部五大工具合规。
- 每个任务完成后暂停核对范围与证据；涉及已批准设计的实质变化先回用户确认。用户已授权按本计划实施；提交、推送、业务环境修改和 GitHub 回复仍需另行授权。
