# 产品/过程特性纠正验收基线

**范围**：2026-11-01 产品/过程特性纠正 Task 1。本文固定后续任务使用的控制计划（CP）表格证据、现有输出能力和已批准 CP 的边界；不新增生产接口、模板或工作流。

## 证据和范围

- 标准依据：`Reference/IATF16949.md` §8.3.3.3、§8.5.1.1、附录 A；`Reference/FMEA.md` PFMEA §3.3.3；`Reference/FMEA_Explanation.md` §3.8。
- 实现依据：`frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`、`frontend/src/locales/zh-CN/controlPlan.json`、`backend/app/services/control_plan_service.py`、`backend/app/api/version.py` 和 `backend/app/services/version_service.py`。
- 表格证据是静态组件断言，不是浏览器截图：编辑器将 `columns` 传给 Ant Design `Table`，`rowKey="item_id"`，横向滚动宽度为 1600；本次 17 项列/分组断言及 6 项中文标签断言均通过。隔离 `qms_test` PostgreSQL 未运行，无法安全启动页面或获得截图。

## 固定的实际 CP 表格

下表按后续任务的共同字段顺序记录；“实际分组”描述当前 UI 的表头层级，不能把逻辑相邻字段误称为已有同一 OCR/导出分组。

| 共同字段（固定顺序） | 当前字段和显示标签 | 当前实际分组 | 结论 |
| --- | --- | --- | --- |
| 过程编号 | `step_no`；“零件/过程编号” | 顶层独立列 | 可用；名称同时覆盖零件/过程编号。 |
| 过程名称/作业描述 | `process_name`；“过程名称/操作描述” | 顶层独立列 | 可用；“操作描述”是现有中文显示。 |
| 机器/设备/工装 | `equipment`；“设备/工装/夹具” | 顶层独立列 | 可用；未单列“机器”。 |
| 特性：编号 | `characteristic_no`；“特性编号” | “特性”子列 | 可用。 |
| 特性：产品 | `product_characteristic`；“产品特性” | “特性”子列 | 可用。 |
| 特性：过程 | `process_characteristic`；“过程特性” | “特性”子列 | 可用。 |
| 特性：特殊分类 | `special_class`；“特殊特性分类” | 顶层独立列，不是“特性”的子列 | 可用；值由 UI 限为无、CC、SC，且不表示按产品/过程类型自动赋值。 |
| 方法：规范/公差 | `specification_tolerance`；“产品/过程/规格/公差” | 顶层独立列 | 字段可用；并非“方法”的嵌套子列。 |
| 方法：评价/测量技术 | `evaluation_method`；“评价/测量技术” | “方法”唯一子列 | 可用。 |
| 方法：样本量 | `sample_size`；“样本大小” | “样本”子列 | 可用；并非“方法”的嵌套子列。 |
| 方法：频次 | `sample_frequency`；“样本频次” | “样本”子列 | 可用；并非“方法”的嵌套子列。 |
| 方法：控制方法 | `control_method`；“控制方法” | 顶层独立列 | 可用；并非“方法”的嵌套子列。 |
| 反应计划 | `reaction_plan`；“反应计划” | 顶层独立列 | 可用。 |

`Reference/FMEA_Explanation.md` §3.8 的 PFMEA 应用示例呈现同一字段族，但其提取文本的多级表头和单元格合并不清晰。本文以源组件的明确结构作为现状证据；不得据 OCR 重新解释或改动模板分组。

## 对照 IATF 16949 附录 A 最低内容

| 附录 A 内容 | 现有 CP 证据 | 结论/后续边界 |
| --- | --- | --- |
| 控制计划编号 | `document_no` | 已有。 |
| 发布日期和修订日期 | 模型有创建/更新时间，版本记录可显示版本；CP 基本信息卡未呈现明确发布/修订日期字段 | 业务复核：不能把内部时间戳直接当作受控模板的发布/修订日期。 |
| 顾客信息 | `customer_requirements` 仅由 CSR 同步保存；基本信息卡未显示顾客信息 | 业务复核/不足。 |
| 组织名称/现场编号 | `org_factory` 文本字段和 `factory_id` | 业务复核：显示的“组织/工厂”不是明确的现场编号。 |
| 零件编号、零件名称/描述、工程更改等级 | `part_no`、`part_name`、`drawing_rev` | 已有。 |
| 阶段、关键联络人、负责功能组/区域 | `phase`、`contact_info`、`core_group` | 已有；阶段为样件、试生产、生产。 |
| 零件/过程步骤编号、过程名称/作业描述 | `step_no`、`process_name` | 已有。 |
| 产品控制：产品特殊特性、其他受控特性（编号/产品/过程）、规范/公差 | `special_class`、`characteristic_no`、`product_characteristic`、`process_characteristic`、`specification_tolerance` | 字段已有；特殊特性的顾客符号/转换和逐项适用性仍须业务复核。 |
| 过程控制：过程参数、过程特殊特性、机器/卡具/夹具/工装 | `process_characteristic`、`special_class`、`equipment` | 字段近似覆盖；“过程特性”是否逐项等同过程参数须业务复核。 |
| 方法：评价/测量技术、防错、样本容量/频次、控制方法 | `evaluation_method`、`sample_size`、`sample_frequency`、`control_method` | 评价、抽样、控制均有；没有独立的防错字段，不能声称模板已单独覆盖防错。 |
| 反应计划（包括或引用） | `reaction_plan` | 已有。 |

IATF §8.3.3.3 要求特殊特性贯穿图纸、风险分析、控制计划和作业/操作说明书，并使用特定标记；§8.5.1.1 要求 CP 与风险分析等输入关联、覆盖特殊特性监视方法和反应计划，并在规定触发下评审/更新。本轮只记录这些标准边界；没有声称缺失的字段已被实现。

## 当前文档输出能力

经检查的真实 CP 入口为编辑器、列表、版本快照/比较和版本历史。当前未确认任何 CP 专用 Excel、PDF、打印或下载 API/UI：`frontend/src/api/controlPlan.ts` 只有 CRUD、PFMEA 导入、失效检查、批准和 CSR 同步；CP 页面/组件及后端 CP 路由中没有此类入口。不得因为表格已在编辑器中显示，就宣称已有 Excel 或 PDF 模板输出。

因此，后续任务若需要可交付的用户表格或受控模板，必须先确认输出格式、字段分组和顾客/CSR 要求；本任务没有添加、删除或重排标准栏目。

## 已批准 CP 的合法修订边界

1. `update_control_plan` 在服务层首先拒绝 `status == "approved"`；`import_from_fmea` 也拒绝向已批准 CP 导入。
2. `POST /api/control-plans/{cp_id}/sync-from-fmea` 明确拒绝已批准 CP。批准操作本身仅将草稿设为 `approved` 并创建快照；没有 `approved -> draft` 或 `approved -> rework` 的 CP 状态转换/API。
3. 版本回退不是修订授权：`rollback_control_plan` 明确只允许 `draft`。它只能把草稿还原至旧快照并创建 rollback 版本，不能用于将已批准 CP 返工；其路由还要求 FMEA 模块的 APPROVE 权限，UI 的 planning 权限显示不构成状态机授权。
4. 手动创建 CP 版本只创建快照，不改变 CP 状态，也不是合法的已批准 CP 修订路径。
5. **受控内容旁路（Task 1 发现；Task 9 局部修正）**：Task 1 时 `special_characteristic_service.sync_to_cp` 和 `sync_csr_to_control_plan` 均缺少已批准 CP 的服务层检查。Task 9 的 SC 自动入口现已保留已批准 CP 内容不变并返回正式同步／人工复核提示；新来源行始终只读追溯，不从此入口写入分类或来源字段。CSR 入口未在本任务修复，仍需后续复核；它不是合法修订路径，也不得用于修正历史已批准 CP。
6. **同步元数据/outbox（单独分类，不是内容修订）**：PFMEA 批准时，`fmea_service` 写入 `cp.sync_pending_set` outbox；`cp_sync_worker` 调用 `apply_cp_sync_pending`。该函数按关联 FMEA 和 `sync_pending == false` 选择 CP，未按 status 过滤，故也会把已批准 CP 的 `sync_pending` 置为 `true`，并记录 `trigger_fmea_version_id` 审计。它不改 CP 表头、项目、特殊分类、CSR 内容、状态、锁版本或 CP 版本；worker 与 outbox 状态在同一提交中完成。这是允许的“关联 FMEA 已有待同步变更”元数据通知，不授权任何 CP 受控内容更新，也不等同于执行同步。实际 `sync-from-fmea` 内容同步仍拒绝已批准 CP。

**本轮结论**：当前不存在可验证的已批准 CP 合法返工/修订路径。后续特性纠正仅可面向新草稿；若将来引入经授权的返工流程，才可面向该流程返回的对象。历史已批准 CP 不自动修正、不直接改状态，也不借用 rollback、内容旁路或 `sync_pending` 元数据通知。

## 维护与验收结论

- 允许后续任务复用本文的字段顺序和“当前实际分组”，但对 IATF 附录 A 标记为业务复核/不足的项目不得自行补成标准模板结论。
- 本文是当前实现事实；任何新增的输出、状态机或顾客符号规则必须更新本文并补充相应验证。
- 本任务只新增本文档，未修改生产代码、生产测试或现有用户文件。


## 2026-11-02 Task 6 后端同步实现

本节更新当前实现，不改写上文 Task 1 的历史验收。新自动同步落实[保守保护补充](../superpowers/specs/2026-11-02-cp-sync-conservative-protection-design.md)，不新增已批准 CP 返工或特批删改流程。

- 保留 `GET /api/control-plans/{cp_id}/sync-preview`、`POST /api/control-plans/{cp_id}/sync-from-fmea`。预览接受明确 `source_fmea_version_id`；缺省只解析唯一最高真实批准版本，不读取当前返工图。应用须提交 `source_fmea_version_id`、`expected_lock_version`、`preview_digest`、`selected_candidate_keys`；旧裸行 UUID 选择返回 409。权限沿用首次导入的 planning 写权限与 FMEA 查看权限，预览、应用均重新解析当前权限和范围。
- `version_service` 复用 `derive_cp_items`、`source_key`、`candidate_key`，逐实际行生成 add/sync/delete 候选；新增项预览没有临时 UUID。`step_no` 与其它源管理字段使用逐行 `accepted_source_version_id` 对应批准快照作三方基线；缺失基线或双边冲突不自动处理。人工方法、评价、抽样、反应及执行关联不被覆盖。
- 真实无源变化不推进逐行接受版本；本地单边修改只提示复核。全部覆盖已处理时允许空候选确认，只推进文档同步跟踪；重复确认不重复建版。未接受、受保护或旧混合行待办保持 pending，不能把文档单一来源版本冒充所有行的接受版本。
- `cp_sync_protection` 仅约束新自动同步：活动 CAPA 当前分析、有效审核／决定及绑定版本保护现存行；旧替代材料与无关历史快照不永久锁行。未知材料 fail closed；CAPA delete 意图和既有 waiver 均不能绕过。SPC／量具和特殊特性反向引用禁止自动删除，实体、证据和引用保留。
- 应用依次取得既有作用域／文档／新鲜权限锁及行锁，重算完整预览、保护和关联摘要。`stage_cp_version` 只 flush；同步拥有唯一最终提交，响应在提交前物化。保护拒绝记安全后端诊断，不为拒绝另起提交写入部分业务审计；成功版本和变更审计同事务。
- CAPA 外部计算不持锁；最终目标发布、审核和决定在 analysis／根对象锁之后按 UUID 顺序锁 CP 父对象，等待后重读输入。分析阶段另绑定当前 CP 内容指纹，不改变原 C9 基线哈希及 CAPA 覆盖／豁免语义。特殊特性链接写入锁住 CP 和存续行，等待后验证目标范围。
- stale-check 传入当前 scope 和可选源版本，使用相同批准快照投影，不再按工序首行或特性名称猜测。当前前端旧同步选择格式需由后续 Task 7/8 适配，本次不改 UI 或标准栏目。

验证入口：`test_cp_characteristic_sync.py`、`test_cp_sync_protection.py`、`test_cp_characteristic_sync_transactions.py`、`test_cp_sync_races.py`，以及既有特性／导入／版本／worker／CAPA 测试。真实提交测试使用任务独立 qms_test 的临时租户 schema，不关闭外键或不可变版本触发器。测试记录和全量套件的既有迁移头断言限制见任务交接报告；这些结果不是新增手工编辑／回退保护的验收。

## 2026-11-03 Task 9 自动消费者边界

- SC 新来源按 FMEA 文档＋特性 UUID 提取；CC／SC 与 product／process 独立，规范来自该项 specification／受控 reference。缺省或空分类不因严重度或功能名称升级。显式数组（包括空数组）优先于旧功能分类；保留已有历史来源和显式 parent 关系，不按同名自动建立 DFMEA→PFMEA 父子关系。
- 用户确认只约束本次自动提取／同步：安全 SC 处于 submitted／approved 时，材料、身份、来源绑定及审批状态不被自动改写或删除，源变化返回复核提示；取消分类保留安全历史。旧手工 SC 更新／删除缺少保护、通用 create 的 pre-flush 审计缺陷仍未修复，不据此宣称安全流程全面验收。
- SC 自动 CP 入口对新来源只返回精确来源匹配和正式版本同步提示，不改写 CP 源管理字段、不推进来源版本、不覆盖人工内容或绕过 Task 6。历史链接写入保留 CP 父锁／存续行检查，并在等待后锁定重读 SC 安全状态；已批准 CP 内容不自动修改。
- 新来源追溯由完整 source_ref（文档／UUID／功能／工序／工作要素）、工厂、产品线与实际 RequestScope 派生全部控制行。`cp_item_id` 不被更新为最后一行；CP 链接指向真实 CP 文档 ID。SPC／量具仅使用真实 FK，MSA 只显示同范围实际研究／结果结论；缺少研究或结果显示 PENDING，校准与 SC 缓存 PASS 均不能冒充测量证据。此更改针对追溯页，不把旧矩阵单值标志扩展为多对多主数据。
- R001–R004 规则含义不变，finding 身份改为来源键＋持久行 UUID；同源多控制行的接受／驳回状态不合并，改名或重排不换 finding。旧哈希历史保留，不自动转移旧决定到新行身份。R005（规范缺失）、R006（历史双对象归属）仅为 warning；非空定性要求或受控引用有效，不按关键词猜测类型，也不增加审批门禁。
- 验证入口：`test_characteristic_consumers.py`、`test_cp_characteristic_validation.py` 与 TraceabilityPage 组件测试。两工厂同名写入级回归通过实际 FMEA PUT 成功保存两份图，再以另一文档的产品 UUID 修改第二份图，确认特性验证拒绝且图／锁／审计不变；不是纯 validator 或权限拒绝证明。浏览器真实服务验收仍留待 Task 11。


## 2026-11-03 Task 11 集成与真实浏览器证据（首轮历史；下述 2258/587/2pass 不是 r1 修复后证据）

### 边界与版本

本节追加本次事实，不改写 Task 1/6/9 的历史结果。故事与工作树派生剧本为：02.3 v3、02.10 v3、02.15 v3、02.18 v5（均 2026-11-03），epic README v4。首轮运行时注册表曾指向原 checkout 的旧 v2，故当时显式读取工作树剧本；这是历史情况。r1 已有工作树 scoped skill 注册并实际加载，对应 02.18 v6；没有修改原 checkout。writing-skills 的多 agent 压力测试按用户禁止 agents/workflows 的约束未运行；采用版本／引用／契约检查及真实浏览器应用验证，不宣称完成代理压力测试。

运行仅用 `openqms-characteristic-test-pg`（标签 task=product-process-characteristics-correction、worktree=characteristic-correction、purpose=isolated-test-db）映射 `127.0.0.1:55432/qms_test`。未读取私密 env、未外发 AI、未连接共享 Neo4j、未运行共享 reset／Compose 整栈／业务 seed。bootstrap 只创建全新工厂、产品线、不同 editor/approver 与受限角色，不写 FMEA/CP 状态或版本。

服务由本工作树源码＋原 backend venv 只读解释器启动：后端 `127.0.0.1:58111`（uvicorn lifespan off），前端 `127.0.0.1:58112`；仅独立 CP outbox worker 运行，不启动 AI／图同步 workers。正常浏览器业务始终保留授权、状态机、hash、版本不可变及审批门禁。完整 pytest 的既有迁移／负面 fixtures 则在已授权范围创建清理 qms_migtest_*／临时 schema，并临时关闭、恢复 FMEA/CP no_update trigger 构造坏历史记录；这与正常浏览器路径分开，不能声称整个测试期间从未切换 trigger。

### 真实 UI 与 API 前置的区分

- API 前置：真实新 draft 创建，普通 PUT 提交模拟结构／功能／完整低风险失效链，wizard_completed=false；普通 CP draft 创建、手工执行字段设置与并发 title 更新。
- 真实 UI：PFMEA Step3 录入同工序 **2 产品＋3 过程**，单位／规范独立，过程各选择两产品 UUID；保存刷新；完成既有向导。显式选择真实批准快照、预览与确认 5 行；合法返工后在 UI 改两个名称、保存；同步抽屉真实 409→显式重新预览→部分接受→仍 pending→显式新预览→完成；历史快照只读；DFMEA 共享 ProcessWorkElementFunction 保存刷新为 product。
- 状态／版本：editor 真实 transition 提交，独立 approver 真实 transition 批准，前后两次 verify.is_valid=true；无直接写库批准、无 core API 成功拦截。浏览器复用真实 API 发出的测试会话，未放松登录节流。worker 等待按本次 FMEA/version 的只读 outbox metadata=completed 同步，不把早前事件的 pending 当作本次已交付；没有任意固定 sleep。
- 手工方法按对象区分：产品位置／覆盖率用模拟 AOI；力用模拟力传感器、速度用模拟编码器、真空度用模拟真空传感器。这里只证明字段保留，不代表测量能力已验证。
- 普通非安全 SC 经真实自动提取／trace API 精确匹配特性与 CP 行；无 MSA 研究显示 PENDING、无 SPC 关联为空。SC 追溯页 UI、全 AI／PPAP／CSR／scanner／live Neo4j 未验收。

浏览器 spec：`frontend/e2e/specs/m1-core/characteristic-correction.spec.ts`；独立配置：`frontend/playwright.characteristic.config.ts`（无共享 global setup/teardown）。endpoint/trigger bootstrap guard 回归：`backend/tests/e2e/test_characteristic_runtime_guard.py`。实际运行日志、退出码与截图在忽略目录 `.superpowers/task11-logs/` 和 `frontend/e2e/.storage-state/`，不纳入提交。

### A01–A21 覆盖矩阵

下列“自动”指本次完整套件实际运行的断言，不表示每个分支都用浏览器重做；浏览器只覆盖标明的专项步骤。

| 编号 | 实际实现／回归入口 | 本次证据与限制 |
|---|---|---|
| A01 | test_characteristic_contract.py；fmeaCharacteristics.test.ts；CharacteristicEditor.test.tsx | Schema 无丢字段、真实 owner-kind、空名反馈；浏览器功能名与特性名分离、保存刷新。 |
| A02 | test_cp_characteristic_mapping.py::test_two_product_three_process_yield_five_independent_rows；新 browser spec | 浏览器同工序 2＋3→5 行，非 1 或 6。 |
| A03 | mapping/contract 回归；新 browser spec | 三项过程各关联两产品 UUID；真实导入仍只有五行，不重复过程行。 |
| A04 | mapping legacy／empty 回归；test_cp_characteristic_import.py | 缺关系 warning、旧自由文本阻塞零部分写入；浏览器 legacy 提示且读不自动转换。 |
| A05 | contract/mapping wrong-edge 与 owner 回归 | 自动验证不按错误边跨分支取首项；缺失／多 owner 不猜类型。 |
| A06 | test_cp_characteristic_sync.py::test_five_real_rows_clears_rename_delete_step_and_stable_add | 自动覆盖清空／规范／分类／步骤变化；浏览器两个改名保留原 UUID。 |
| A07 | test_cp_characteristic_versions.py；test_cp_characteristic_sync.py::test_partial_baselines_multiple_controls_and_manual_preservation | 自动覆盖同源多控制行及独立基线；浏览器五条行 UUID 全保留。 |
| A08 | test_cp_characteristic_sync.py::test_stale_check_uses_exact_approved_source_not_current_graph | 导入／同步／stale-check 自动同口径；浏览器选择真实批准快照而非返工图。 |
| A09 | import/sync transactions 与组件回归；新 browser spec | 实际合法并发更新后 sync POST=409；旧预览不可再应用，用户显式新预览。 |
| A10 | sync conflict/partial/delete 回归；新 browser spec | 只接受一项仍 pending；再显式预览处理另一项才完成。受保护删除／冲突分支为后端自动证据。 |
| A11 | test_cp_sync_protection.py；CAPA 全回归；FMEAVersionSnapshot.test.tsx | approved／活动 CAPA／执行引用保护自动；浏览器历史只读，无批准状态伪造。 |
| A12 | test_cp_characteristic_versions.py；migration/hash/backfill 全回归 | 旧新哈希与恢复自动；浏览器两批准版本 is_valid=true；无历史数据迁移。 |
| A13 | contract/mapping DFMEA 回归；新 browser DFMEA test | 共享 ProcessWorkElementFunction UI 保存刷新仍 product；PFMEA 导入口拒绝 DFMEA 为自动证据。 |
| A14 | fmeaTable.test.ts；wizardCascadeDelete.test.ts；FMEAEditorPage.test.tsx；FunctionTreeEditor.test.tsx | 集合保存／删除关联／wizardScope 及既有 FM×FC、多后果、共享控制回归；未宣称浏览器逐一重做所有 copy/delete 组合。 |
| A15 | mapping/validation/demo 回归；新 browser spec | UI 单位 mm/N/%/mm/s/kPa 与规范分开；定性规范自动兼容；模拟方法按对象区分，不伪造能力证据。 |
| A16 | test_characteristic_consumers.py；RiskTable/Editor 回归 | product/process 与 classification 独立；浏览器仅一项模拟 CC，其余不继承，无严重度自动升级。 |
| A17 | import/sync scope/permission/race 回归；test_two_factory_same_name_actual_writer_rejects_foreign_product_and_preserves_state | 自动真实写入级跨范围拒绝及权限提交时重查；非浏览器跨租户认证。 |
| A18 | test_second_insert_failure_rolls_back_items_header_audit_and_version；sync transaction failure 回归 | 实际事务无部分提交；不是 mock 成功替代业务路径。 |
| A19 | CharacteristicTemplate.test.tsx；新 browser 标准 columnheader 断言 | 13 字段／现有分组保留；没有新增或声称存在 CP Excel/PDF/打印格式。 |
| A20 | test_characteristic_demo_data.py；seed_e2e_docgate 既有负面 fixtures | 模拟案例构造／不覆盖既有数据自动证据；本次新 E2E 未调用 app.seed/app.seed_e2e 入口，不声称已迁移已有演示实例。 |
| A21 | test_characteristic_consumers.py（真实 FK／研究／结果）；新 browser SC API smoke | 实际无研究 MSA=PENDING、SPC=[]；未伪造 PPAP、顾客批准或能力通过。 |

### 已完成的集成修正

- Alembic metadata-only 断言明确期待 `20261101_char_refs`，移除不必要建库 fixture，无 skip／deselect。
- 特性 kind 取真实唯一 HAS_FUNCTION owner＋FMEA 类型；既有空白名称显示必填，持久名称不变、恢复仍同 UUID。
- CP response 补出已有 sync_pending/source_fmea_version_id；新 CP create 显式加载 items，避免 MissingGreenlet 500。均先有失败回归。
- 导入确认补传与预览相同 step_ids；409 失效清理 busy，恢复显式预览按钮。真实浏览器发现，先补组件 RED 再最小修复。
- 既有 CP worker/outbox 测试不再统计全库 unrelated 审计／事件；仍精确断言本 fixture 每 CP 一条审计、同一 source 无提交 outbox。真实浏览器保留的合法历史记录导致过宽查询 RED，不通过删除历史／deselect 伪造绿色。

### 尚存边界

手工 SC 安全更新／删除与通用 create 审计缺陷仍 **UNFIXED**；CSR 已批准 CP 旁路及已批准 CP 新返工流程不在本次授权内。标准／CSR 手册转换缺口仍需业务复核。本专项和完整测试通过均不是全 feature 独立评审结论；后续由 coordinator 做 Task11 独立审查及 whole-feature final review。未 staging／提交／推送／PR／部署／合并。

### 最终检查命令、结果与完整日志

所有命令 cwd 为本工作树；`OWNED_DATABASE_URL` 表示显式的任务实例 `127.0.0.1:55432/qms_test` 异步 PG URL（开发测试认证不在文档打印），且 DATABASE_URL、TEST_DATABASE_URL 在 app/test import 前同时设置。`VENV=/Users/sam/Documents/Code/OpenQMS/backend/.venv` 只读复用，PYTHONPATH 指向本工作树 backend。

```sh
VENV=/Users/sam/Documents/Code/OpenQMS/backend/.venv
export DATABASE_URL="$OWNED_DATABASE_URL" TEST_DATABASE_URL="$OWNED_DATABASE_URL"
export LLM_PROVIDER= LLM_API_KEY= EMBEDDING_PROVIDER=
make check PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test   PYTEST="$VENV/bin/pytest" PYTHON_BIN="$VENV/bin/python" ALEMBIC="$VENV/bin/alembic"
(cd frontend && npm test -- --run)
SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=backend   "$VENV/bin/pytest" backend/tests/test_graph_projection.py -q
CHARACTERISTIC_PYTHON="$VENV/bin/python" CHARACTERISTIC_UI_URL=http://127.0.0.1:58112 CHARACTERISTIC_API_URL=http://127.0.0.1:58111   make e2e-run TEST_ARGS='--config=playwright.characteristic.config.ts e2e/specs/m1-core/characteristic-correction.spec.ts'
```

| 执行 | 退出码与实际输出 | 忽略目录完整日志 |
|---|---|---|
| 最终 make check | **0**；后端 **2258 passed, 5 skipped, 3 xfailed, 2 xpassed, 3 warnings**；tsc/build 成功（build 6.66s）。没有 head/backfill deselection。 | `.superpowers/task11-logs/make-check-complete.log`、`.exit` |
| 最终 full Vitest | **0**；**77 files / 587 tests passed**；0 failed/skip。 | `vitest-complete.log`、`.exit` |
| 显式纯 projection | **0**；**8 passed, 3 warnings**；未接 live Neo4j。 | `projection-complete.log`、`.exit` |
| 最终真实浏览器 | **0**；**2 passed (18.3s)**，0 skipped/failed；PFMEA 完整流程＋DFMEA smoke。 | `browser-complete-verified.log`、`.exit` |
| Task7 两 Minor RED→GREEN | RED **2 failed, 7 passed**；GREEN helper/editor/function-tree **16 passed**。 | `minors-red.log`、`minors-green.log` |
| metadata head RED→GREEN | RED **1 failed**（旧字面 head）；GREEN **1 passed, 3 warnings**；metadata 断言不再建库。 | `head-red.log`、`head-green.log` |
| CP response RED→GREEN | RED **1 failed, 10 passed**；GREEN **11 passed, 3 warnings**。 | `cp-response-red.log`、`cp-response-green.log` |
| CP create RED→GREEN | 正确接入 admin_client 后 RED **1 failed**，MissingGreenlet；GREEN **1 passed, 3 warnings**。此前错误 fixture 名是脚手架错误，不当作产品 RED。 | `cp-create-red.log`、`cp-create-green.log` |
| import scope/busy RED→GREEN | RED **2 failed, 3 passed**；GREEN **5 passed**；随后 tsc RED 指出 apply API 类型未含 step_ids，补齐后 tsc GREEN。 | `import-ui-red.log`、`import-ui-green.log`、`import-type-green.log`；类型 RED 在 `make-check-final-verified.log` |
| test-only endpoint/trigger guards | 最终 **12 passed, 3 warnings**；trigger mode RED **5 failed, 7 passed** 后 GREEN，覆盖 str/bytes 的 D/R 拒绝。 | `bootstrap-red.log`（初始模块缺失为脚手架错误）、`bootstrap-green.log`、`trigger-guard-red.log`、`trigger-guard-green.log` |
| 真实数据保留后的测试隔离 | 完整 RED **3 failed, 2255 passed, 5 skipped, 3 xfailed, 2 xpassed**（全库审计/outbox 查询污染）；按 fixture IDs 精确断言后聚焦 **4 passed**，最终完整 2258 passed。 | `make-check-final.log`、`worker-isolation-green.log` |

前置完整检查 `make-check.log` 为 2244 passed/5 skip/3 xfail/2 xpass/3 warnings＋tsc/build 通过；最初 full Vitest `vitest-full.log` 为 1 failed/586 passed（snapshot 缺真实 owner fixture），修复后全量 587 passed。`make-check-final-verified.log` 后端已 2258 passed，但 tsc 因 step_ids 类型不完整退出 2，不当作完整绿色；最终是 `make-check-complete.log`。

浏览器驱动调整与真实失败没有隐藏：`browser-01.log` locale 仍英文导致缺中文控件，已停止该运行（无成功结论）；`browser-02.log` 2 failed（真实按钮是“存草稿”、DFMEA 步骤带“第三步”）；`browser-03.log` 2 failed（登录节流 429，改用真实已发会话，未修改限流）；`browser-04.log` 1 failed/1 passed（CP create 500）；`browser-05.log` 1 failed/1 passed（确认缺 step_ids 实际 409＋busy 锁死）；`browser-06.log` 2 passed；`browser-final.log` 2 passed；`browser-final-verified.log` 2 passed。单位／对象适配方法加强后的 `browser-complete.log` 1 failed/1 passed（把旧事件 pending 当作新事件已交付，late worker 再置 pending）；改为只读查询确切源版本 outbox completed 后最终 2 passed，无固定 sleep 或 timeout 放宽。没有修改 outbox 全局业务策略。

5 skipped 为既有 Redis memory、3 项 E2E_MODE/shared seed endpoints、tenant provisioning；3 xfail/2 xpass 为既有 MES 并发／重投递测试，不算新增通过。后端 3 warnings 为 Pydantic class-config 弃用。最终 Vitest 日志含 77 条 Node localStorage ExperimentalWarning、159 次 getComputedStyle pseudo-element 未实现提示及 2 处 deprecated 字样，未屏蔽。浏览器两个页面均 0 pageerror；console.error 分别 7/2 条，内容为 React findDOMNode/Ant Input addonBefore/static message 弃用警告和预期 409 资源错误，无其他异常。Playwright CLI Node module.register 弃用 2 条；均完整保留，不声称无 warning。运行时为既有 Playwright 1.60.0 / Chromium cache、Python 3.11.15、Node 26.13.0，未安装／升级外部运行时或改依赖锁。

### 受控启动与只读同步点

在上述显式 owned URL 环境下，首次只建新账户／工厂／产品线的 bootstrap 命令为 `(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. "$VENV/bin/python" -m tests.e2e.characteristic_bootstrap)`，输出仅 run/factory/product-line，凭据写忽略 manifest。正常服务实际命令为：

```sh
(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. \
 GRAPH_REPOSITORY=jsonb LLM_PROVIDER= LLM_API_KEY= EMBEDDING_PROVIDER= \
 E2E_MODE=false TENANT_MODE=single \
 "$VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 58111 --lifespan off)
(cd frontend && BACKEND_URL=http://127.0.0.1:58111 \
 npm run dev -- --host 127.0.0.1 --port 58112 --strictPort)
(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. \
 "$VENV/bin/python" -m app.services.cp_sync_worker)
```

最终启动 stdout/stderr 分别在 `backend-final.log`、`frontend-final.log`、`cp-worker-final.log`；早期重启保留 backend.log/backend-v2.log/backend-v3.log。最终业务同步点的 metadata 子进程先核对双 URL 与 owned endpoint，再执行 `SET TRANSACTION READ ONLY`，按真实 fmea_id/fmea_version_id 查 CP outbox status；不写库，不代替审批／版本 API。此测试只证明“本次批准事件已交付后”的同步完成，不扩展为全局 outbox 乱序调度认证。

### 截图 LOOK 与资源交接

已实际打开并检查九张最终截图，非仅保存文件；路径均 `frontend/e2e/.storage-state/404b462f-<name>.png`：

| name | LOOK 观察 |
|---|---|
| legacy | 真实功能分析页，旧字段参考值与蓝色历史提示，没有自动生成特性。 |
| five-characteristics | 两个产品卡，名称／规范／单位／分类分列；其余在内部滚动区域，另截 process-three。 |
| process-three | 三个过程卡全部可见，力=3.0±0.5 + N、速度=20±2 + mm/s、真空=−60±5 + kPa；每项两产品关联。原应用固定头在 native scroll 后有重叠，未重设计。 |
| import-preview | 明确 v1.0 已批准快照与 OP10，五个候选（2 产品＋3 过程），不是空白页面。 |
| real-409 | 红色失效提示、显式重新生成预览按钮；没有自动应用。 |
| partial-pending | 红色失效提示＋“仍有 1 项待同步”；页面保留五行。 |
| complete-stable-rows | 五行保留、两项新名称、标准表头；pending banner 消失，真实 API 同时验证 UUID／接受版本／手工字段。 |
| snapshot-readonly | “正在查看 v2.0 快照（只读）”与禁用特性输入，无新增入口。 |
| dfmea-product | 共享下层功能的“产品特性”卡及 mm 单位，没有过程入口；只做草稿 smoke，未冒充 DFMEA 完整失效分析验收。 |

另实际查看 `.superpowers/task11-logs/screenshots-look.png` 九图 contact sheet；截图／真实会话 JSON 都经 git check-ignore 确认为忽略。read-only API 及 metadata 详细证据在 `.storage-state/characteristic-evidence.json`、`characteristic-runtime-evidence.json`；其中没有生产账户，auth 文件仍不得打印／提交。

最终合法对象：PFMEA `f0169ad6-65dd-455e-9710-db1b73baa43c`，批准 v1 `62d6d1c4-c196-46b3-8d2b-468d7ffa8549`、v2 `ca3aa7b6-54be-481f-bb3b-fbd7beeb8d4f`（两次 is_valid=true）；CP `673922de-dc64-42a4-9f50-af2aa4529817`；DFMEA 草稿 `c9d4c8f0-4e77-483e-bb6f-b3045448ab64`；普通 SC `253c2159-e9c4-47fd-b631-778018358344`。最终 5 行 UUID 与逐行基线：

- `82bc2672-8cee-4341-9912-08f4fe54ddda` → `62d6d1c4-c196-46b3-8d2b-468d7ffa8549`。
- `aadeb59d-4105-4e2c-a287-925c8bd32973` → `62d6d1c4-c196-46b3-8d2b-468d7ffa8549`。
- `ae50ff83-8d7a-40b6-ae01-80a5fe4df6df` → `62d6d1c4-c196-46b3-8d2b-468d7ffa8549`。
- `cdbb7bba-b195-480b-b8ce-4ad9ffd3ae07` → `ca3aa7b6-54be-481f-bb3b-fbd7beeb8d4f`。
- `8e344840-1024-4fd6-baf9-98d02db5ec4d` → `ca3aa7b6-54be-481f-bb3b-fbd7beeb8d4f`。

其中两项改变的行接受 v2，三项未变行保持 v1；文档 source_fmea_version_id=v2、sync_pending=false，手工字段逐行保留。

工厂 `4eab9c20-63a0-4184-96f6-eccd899aef48`、产品线 `T11-404b462f`、两个独立受限测试用户及角色保留（审批／审计 FK）。合法 API 共清理 **14** 个明确字面 ID 的过时无版本 draft（2 CP + 12 FMEA）；初次动态范围 cleanup 被权限层拒绝，先只读解析列出 ID，再按字面白名单合法删除，未绕过拒绝。日志 `cleanup-literal.log`、`cleanup-additional.log` 和对应 JSON 明确每个状态。没有任意强删批准对象／版本。

保留受控证据文档：
- cp `673922de-dc64-42a4-9f50-af2aa4529817`：draft，3 个版本。
- cp `c761972d-a87d-4815-8e73-956e793639a6`：draft，3 个版本。
- cp `5a420b75-c866-4cfd-9be7-2787a2be1aae`：draft，3 个版本。
- cp `da791a92-69e8-4f9c-b9a7-e2a52eae2ddf`：draft，3 个版本。
- cp `e18b017a-d31a-456a-b488-75b413537ea0`：draft，3 个版本。
- fmea `c9d4c8f0-4e77-483e-bb6f-b3045448ab64`：draft，0 个版本。
- fmea `f0169ad6-65dd-455e-9710-db1b73baa43c`：approved，4 个版本。
- fmea `d66ef47a-3f42-468f-bc78-1cff74505581`：approved，4 个版本。
- fmea `bdde2cff-8443-45a2-97d0-8298d2cb7e74`：approved，4 个版本。
- fmea `e6b06606-c823-4051-90fe-833b8cf398bf`：approved，4 个版本。
- fmea `2ada8af3-3072-4e5d-8a65-3e3eebd50d9e`：approved，4 个版本。
- fmea `ce8f3b8a-ca8d-48c7-acf8-90cf980d1d95`：approved，2 个版本。
- fmea `044b1302-29cd-44cb-bc05-151932e32e09`：approved，2 个版本。

另保留 3 个普通自动提取 SC（最终运行及两次成功预演），明细见本任务工厂作用域与 evidence JSON；不清理其受控源历史。最终 12 个本任务 CP outbox 全 completed；四个版本 hash/no_update triggers 实际均 O，qms_migtest_* 与本特性 tenant_import_*/tenant_sync_* 临时 schema 剩余 0。未知资源未操作。

只停止自己的 PID：backend 18123/21328/31153/57210，frontend 18416/57535，CP worker 21542/57825；58111/58112 端口已释放。143 是主动 SIGTERM 退出，非测试失败。PG 容器及其匿名卷保持 running／保留，未移除／reset。资源状态最终只读记录见 `runtime-retained-final.log`；没有提交／推送／部署／GitHub 操作。

保留普通 SC IDs：`a430e64a-ce26-414a-aec8-0ba66e5c8d1e`, `1fa854ab-d462-4951-943d-332d4c9615da`, `253c2159-e9c4-47fd-b631-778018358344`。测试账号 UUID：editor `b2dca29d-2b28-4ac0-b7ac-82329da0e19d`, approver `fbf1cbf9-7290-487a-92d9-c074905fd1b7`。没有打印／提交密码或 token。

### Task11 实际修改面（不把 Task1–10 整个未提交 diff 当作本轮修改）

- 生产接口／调用：`backend/app/api/control_plan.py`（create response eager items）、`backend/app/schemas/control_plan.py`（只读 sync_pending/source_fmea_version_id）、`frontend/src/api/controlPlan.ts`（applyImportFromFMEA 必带 step_ids）、`frontend/src/components/control-plan/ImportFromFMEAModal.tsx`（确认同一工序选择与 busy 清理）。没有新增业务 endpoint 或改全局审批策略。
- 特性 helper/editor/callers：`frontend/src/utils/fmeaCharacteristics.ts` 的 `characteristicKindForFunction(fmeaType, functionId, nodes, edges)`；`frontend/src/components/fmea/CharacteristicEditor.tsx`；`frontend/src/components/pfmea/FunctionTreeEditor.tsx`；`frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`。
- 窄回归：上述 helper/editor/modal 的 `.test.ts/.test.tsx`，`FMEAVersionSnapshot.test.tsx` 的真实结构 owner fixture；`backend/tests/test_characteristic_contract.py`、`test_cp_characteristic_import.py`、`test_cp_sync_worker.py`、`test_transition_cp_outbox.py`；`backend/tests/migrations/test_supplier_risk_capa_inputs_migration.py` 的 metadata head 断言。
- 必要测试设施：`backend/tests/e2e/characteristic_bootstrap.py`、`test_characteristic_runtime_guard.py`；`frontend/playwright.characteristic.config.ts`、`frontend/e2e/specs/m1-core/characteristic-correction.spec.ts`。
- 文档：`docs/modules/planning.md`；`frontend/src/types/README.md`；`frontend/src/utils/README.md`；`backend/app/graph/README.md`；四故事 02.3/02.10/02.15/02.18 与相应四 `.claude/skills/verify-fmea-lifecycle-*/SKILL.md`；epic README；本验收基线；PROGRESS。没有修改复制而来的 architecture-maintenance.md，也没有触碰原 checkout 的待办文件。

最终文档检查：四故事／四剧本版本、日期、依据引用及相关本地链接通过，A01–A21 恰为 21 行；日志 `docs-check-final.log`。差异空白检查 exit 0，日志 `diff-check.log` 为空（无 whitespace error）；未触碰 index。

## Task11 fix round 1：I1／I2／M3（2026-11-03）

首轮数据与截图只保留为历史。复审发现 CP dimensionless 准则与晚到事件重置 pending，故首轮的“完成”不构成这两项的闭环，也不以 worker-first 等待掩盖 late-delivery 行为。r1 只修复直接相关 projection／自动 SC consumer 与 worker 通知互斥／完成判定，未改变标准列、批准流程或手工 SC 政策；新证据均用 r1/tag 独立路径，不覆盖原日志／404b462f 图像或数据库不可变历史。

当前故事／scoped 剧本：02.18 v6（2026-11-03），其他三个相关子故事维持 v3；epic 摘要已同步。M3 将 epic 的旧“直接两阶段／非 durable／剧本待生成”明确作历史并更正当前事实，planning 7.3 只把节点 classification／severity 规则保留给 legacy，不泛化到显式 characteristics。

### r1 修改面与真实 RED→GREEN

**I1 单位投影**：`backend/app/services/fmea_characteristics.py::criteria_with_unit` 是唯一小型格式化 helper；`cp_characteristic_mapping.py` 与新 canonical `special_characteristic_service.py` 消费它。现有 specification_tolerance 标准列不变，None/空白不被 unit 补成准则；已有相同单位 token 不追加；不换算量值，不改历史存储／快照。未新增 DTO／mapping 版本／审批政策。

- `test_cp_characteristic_mapping.py` 新的 13 组参数：分别存储 mm/s、kPa、N、mm、% 的 RED **5 failed / 21 passed**，再 **26 passed**；包含已内嵌单位、紧邻数字 3N、定性文本、None／空白／空 unit。
- `test_cp_characteristic_sync.py::test_unit_only_source_update_is_shared_by_import_sync_and_stale_check` 真实 CP API 进口后仅改 unit，新候选同一行 UUID、基线/新值/合并值及 stale-check 同口径；接受后 API 有单位，明确清空仍 None，不被剩余 unit 回填。
- `test_characteristic_consumers.py::test_canonical_sc_criteria_keeps_separate_unit_and_reviewed_material` 初次 RED **1 failed / 1 passed**；共享 helper 后相关 **28 passed**。SC 新来源 spec_requirement 包含 mm；已 submitted 安全材料再遇 unit 变化保持原材料并提示 review_required；既有 submitted/approved 参数化保护回归一并运行，手工 SC APIs 未修改。

**I2 晚到通知**：`control_plan_service.apply_cp_sync_pending` 沿 scope→按 UUID 排序 CP parent 的既有互斥协议；scope 等待后再次发现候选，parent 等待后 populate_existing 重读。仅文档指针不算完整：须验证批准版本/hash/来源/工厂，实际逐行接受快照与身份、源管理字段及完整目标覆盖；允许未变行保持较老接受版本。完整接受的同一／较新基线使旧／同事件完成但不重开 pending；真正新源、partial import/sync、未知基线仍保守。worker 不写业务字段／来源指针、不清除已有 pending；真正 false→true 的审计仍只有 sync_pending＋trigger_fmea_version_id。

- 新 `backend/tests/test_cp_sync_late_delivery.py` 使用已有独立 qms_test 临时 schema 事务夹具，声明 immutable 批准快照为前置，实际调用 create/import/sync/worker 服务，非模拟成功。初次有效 RED **4 failed / 4 passed**：晚到 same、old-after-new、批准后实际新建并导入 CP，及真实并发读取／写入死锁。初始 fixture 接线／跨 commit 搜索路径脚手架错误不冒充产品 RED。
- GREEN **8 passed**：late-after-sync、CP 创建在批准之后、out-of-order old-after-new、worker-first 真正新源、partial first import、无基线、partial sync、实际 pg_blocking_pids 等待与释放。
- 并发例额外持有 stale ORM 实例的强引用，并断言其 source pointer 在等待后已刷新；测试 worker 使用生产相同 expire_on_commit=False。一次加强断言的 post-commit expiration 脚手架 MissingGreenlet（`late-strong-reference.log`）已明确纠正，不能当产品 RED。最终 `late-strong-reference-green.log` **8 passed**，且已纳入最新完整检查。没有只靠一次 .get() 后弱引用 GC 使“陈旧实例”消失。
- 相关 worker/outbox 12 项及单位/导入/同步/消费者/事务聚焦 `focused-backend.log` **165 passed**；demo/version 兼容 **14 passed**。worker 的轮询／batch／全局实体逻辑没有改写。

### r1 完整检查的真实阻塞与窄范围隔离

首次 r1 全套 `make-check.log` 实际为 **6 failed, 2279 passed, 5 skipped, 3 xfailed, 2 xpassed**。失败来自 3 个旧 embedding 测试文件的全库队列假设：64 个旧待办占住 batch，新 fixture 事件未被 claim。没有把它们排除、调大 64、循环 fake-embed/drain 或删掉保留事件来制造绿色。此前未隔离的既有 worker 测试确实可能 claim 公共队列；没有事前状态副本，不宣称原公共可变 embedding 任务从未受这些旧测试影响，也未擅自重置还原它们。批准/FMEA/CP 的不可变历史与旧 PNG/JSON 未改。

协调者明确许可后，只为以下 **3 个实际失败的测试文件** 加 opt-in fixture imports：

1. `backend/tests/test_embedding_sync_worker.py`
2. `backend/tests/recommendation/test_capa_lesson_embedding_chain.py`
3. `backend/tests/recommendation/test_lessons_extraction.py`

最小测试支持 `backend/tests/embedding_isolation.py` 在 owned qms_test 创建 UUID 命名 `tenant_embedding_*`，从必需表＋实际 FK 父闭包复制列、默认值、约束／索引及触发器，FK 全指向自身 schema，不复制公共记录。连接启动 server_settings.search_path 对每次新连接有效，COMMIT／ROLLBACK 不会回落公共队列；stable factory 仅在私有 schema 预置以支持既有独立真实提交测试。保留原 flush-only db 与真实 sessionmaker 两种事务语义，实际 claim/fetch/upsert 和 provider stub 都不变，不 mock claim SQL 或按 fixture ID 改生产过滤。

新 `test_embedding_fixture_never_falls_back_to_public_across_commits` 原先 RED **1 failed**（public），现在实际 commit/rollback/recheckout 均断言私有 schema 与队列 OID 非 public；三个文件 **22 passed**（`embedding-isolation-green.log`），既有 retry/abort/dead-letter/cleanup 断言全部保留。没有全局/autouse fixture、conftest、生产 embedding worker、依赖、batch 或配置更改。临时 schema 逐个由自身 fixture 清理，未做全局 schema/队列清扫。

后续只读 `public-embedding-preservation.log` 证实 r1-a、r1-b 两个保留浏览器工厂各 **12 pending embedding events、0 stored embeddings**；本轮成功保留数据未被假 provider 处理。这个局部证明不冒充旧公共队列的历史全量审计。

### r1 最终完整验证（替代首轮结果作本轮修复证据）

- 最终 `make check` **exit 0**：2286 passed, 5 skipped, 4 xfailed, 1 xpassed, 3 warnings in 197.58s (0:03:17)；tsc 成功，build **8.05s**。日志 `.superpowers/task11-r1-logs/make-check-final2.log` 与 `.exit`。没有 head/backfill deselection，默认排除的纯 projection 另跑。
- 最终完整 frontend：`(cd frontend && npm test -- --run --maxWorkers=2)` **exit 0，587 tests / 77 files passed**，原 5s timeout 与所有断言均未修改；日志 `vitest-final2.log/.exit`。协调者已确认这是覆盖完整的资源受限执行方式，不是筛选用例。
- **默认命令不称绿色**：`vitest.log`（与初次 make 同时）和 `vitest-serial.log`（单独执行原命令）都为 **3 failed / 584 passed / 77 files**，同一 PFMEAWizard 三项 5s timeout；单独重现后才用 CLI maxWorkers=2，`vitest-bounded.log`、`vitest-final.log` 及最终 `vitest-final2.log` 全覆盖通过。没有 blanket timeout 放宽、skip、断言减弱或 Vitest/package/global config 变更；保留默认并发下的宿主性能限制。
- 最终显式 `backend/tests/test_graph_projection.py -q` **8 passed, 3 warnings, exit 0**；`projection-final.log/.exit`，不接 live Neo4j。
- 修复后实际浏览器两次均 **2 passed / 0 skipped/failed**：`browser-r1-a.log` **28.2s**，最终 `browser-r1-b.log` **28.2s**，各有 `.exit=0`。r1-b 使用最终生产代码；随后只是把独立事务测试的 stale ORM 强引用断言做实，并重跑上述最终 make，不改变浏览器业务代码。
- 最终 4 xfail / 1 xpass 是现有 MES 用例：两个 ingestion_atomic_rollback 参数、crash_redelivery_idempotent、sync_round_bad_data_fails_job_preserves_checkpoint 为 XFAIL，process_outbox_full_flow 为 XPASS。此前 crash_redelivery 曾 XPASS，本轮重新 XFAIL；未改该用例、不折算为通过。5 skips 仍为 Redis memory、3 shared E2E_MODE seed endpoints、tenant provisioning。后端 3 warnings 为 Pydantic config 弃用。
- Vitest 仍记录 Node localStorage、getComputedStyle pseudo-element 和 Vite/esbuild 弃用提示；浏览器均 0 pageerror，console.error 为已记录 React/Ant 弃用提示＋预期 409（r1-b 两页 8/2 条），无被过滤的业务异常。Playwright module.register 的 Node 弃用提示保留。无私密 env、外发 AI、共享 reset、其他实例／卷或依赖更改。

实际最终命令仍以原只读 VENV、双 owned URL、PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test 执行：

```sh
make check PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test \
  PYTEST="$VENV/bin/pytest" PYTHON_BIN="$VENV/bin/python" ALEMBIC="$VENV/bin/alembic"
(cd frontend && npm test -- --run --maxWorkers=2)
SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=backend \
  "$VENV/bin/pytest" backend/tests/test_graph_projection.py -q
CHARACTERISTIC_RUN_TAG=r1-b CHARACTERISTIC_WORKER_PID=643 \
CHARACTERISTIC_PYTHON="$VENV/bin/python" \
CHARACTERISTIC_UI_URL=http://127.0.0.1:58112 CHARACTERISTIC_API_URL=http://127.0.0.1:58111 \
  make e2e-run TEST_ARGS='--config=playwright.characteristic.config.ts e2e/specs/m1-core/characteristic-correction.spec.ts'
```

worker PID 643 是当次明确核对命令＋cwd 后的自己进程，不是以后重跑应复用的 PID。实际 r1-a worker=87581；新运行必须新 tag、新自有 PID。bootstrap 增加安全 tag 与 exclusive manifest 写入，配置／PNG／每 worker JSON／test-results 都按 invocation 分离，auth 文件仅首次建立；旧 404b462f 图片与 JSON 从未覆写。

### r1 真实 UI/API、晚到顺序与截图 LOOK

API 只作声明前置：合法新 draft、完整模拟低风险结构/失效链、普通 CP 创建及手工执行字段。2 产品＋3 过程、关系与独立规范/单位均由 UI 录入、保存刷新、既有向导完成；不同真实授权 actor 执行三轮提交／批准，v1/v2/v3 hash verify.is_valid=true。全程正常授权、状态、immutable/hash 保护开启；无直接 approved/sync_pending/source pointer 写库或 core API mock。

- **晚到首次导入**：验证本次 worker 命令/cwd 后 SIGSTOP；真实 v1 批准后才创建 CP，UI 选择其真批准快照并导入。**在任何手工字段更新之前**，真实 CP API 与 UI 均断言 `≤0.05 mm`、`≥95 %`、`3.0±0.5 N`、`20±2 mm/s`、`−60±5 kPa`。当时 pending=false；SIGCONT 后只读等确切 v1 outbox completed 是后置条件，再确认仍 false。
- **worker-first**：合法返工，UI 两项改名＋速度仅改 unit 为 cm/s（数字不换算），真实新批准 v2；等其事件交付后 pending=true。实际 CP 并发普通更新产生真实 409，显式重预览；仅接受产品改名，剩余 **2 项** pending。
- **晚到同步**：利用上述真实 partial pending（没有伪造标志），再次 SIGSTOP；合法返工，UI 力仅改 unit 为 kN，再批准 v3。重新进入 CP，通过实际“立即同步”加载最新批准源，UI 完成剩余项，先验证 pending=false；再 SIGCONT 并等 v3 交付，仍 false。v3 的 completed 不是同步前置门槛。
- 全部 5 行 UUID 保留；两条未变行仍接受 v1、产品改名行接受 v2、另两行接受 v3；文档 tracking=v3。手工评价/控制/抽样/反应字段保留，按对象选模拟 AOI/力传感器/编码器/真空传感器，不以 AOI 证明力合格。原字符串单位已存在及 None/空白不造准则由自动参数回归补充，不以少量 UI 代替这些分支。
- 普通 SC 自动提取 API 的 spec_requirement=`≤0.05 mm`，精确追溯到该特性 CP 行，MSA=PENDING/SPC=[]。快照 v3 只读、标准 13 字段/分组不变，DFMEA 共享下层功能仍产品型草稿保存刷新。

最终 r1-b 的 **11 张** `frontend/e2e/.storage-state/d319fe97-r1-b-*.png` 全部实际 LOOK（另查看 `.superpowers/task11-r1-logs/r1-b-look.png` contact sheet；重点四图还逐张原尺寸打开）：legacy、two-product/five-characteristics、process-three、import-preview、late-import-before-delivery、real-409、partial-pending、late-sync-before-delivery、complete-stable-rows、snapshot-readonly、dfmea-product。真实 CP 准则列可见单位各一次；晚到前已无 pending banner，释放后真实 API 仍 false；partial 提示 2 项；v3 snapshot 输入禁用。非空白页面，内部 native scroll 固定头重叠仍如实保留，不做无关重设计。r1-a 为独立 9becec4f-r1-a 文件，不与旧 404b462f 或 r1-b 共用路径。

最终 r1-b evidence：`frontend/e2e/.storage-state/characteristic-r1-b-1627-evidence.json`；包含每行内容／真实接受版本、三个 hash 验证、两次 late postconditions、console diagnostics 与截图清单，无报告正文打印凭据。

### r1 资源与新增覆盖交接

- **r1-a**：run `9becec4f`，factory `5623a613-7868-45f9-b32d-7366bf207a8a`，product-line `T11-9becec4f`；actor IDs editor `5ae2af4d-bf57-4f22-853a-4428f3e933fd`, approver `f5c304ad-ccba-410a-8479-33bdeb806190`。
  - fmea_documents：`b501b238-a091-40c6-bcd3-d6f380e6e018`, `0ff7e51a-9a07-40f8-95a9-a59ee2cb8a09`。
  - control_plans：`3566363f-d1b0-4db0-b7cf-9158ff64b7b3`。
  - special_characteristics：`b82e4d86-a0f8-4d0a-9f0a-8b8a3b15fc9f`。
  - 3 个 outbox 全 completed；只有真实 worker-first v2 有 1 条通知 UPDATE 审计（两个字段），late v1/v3 无重复翻转。
- **r1-b**：run `d319fe97`，factory `8b80d4a2-3732-4e38-a8a9-01807a09310b`，product-line `T11-d319fe97`；actor IDs editor `dbc20fc8-4253-42a0-b036-f382a702b25d`, approver `2cd1133b-1e19-4cca-9131-f14e3195c2b7`。
  - fmea_documents：`34cb0863-aed3-41a0-bcdf-73c9e6945299`, `64f28041-c078-4871-983c-ba136e9a7190`。
  - control_plans：`eef61b31-f6a0-4c3c-a354-de3f18fe15c3`。
  - special_characteristics：`d68a40cc-0777-4154-ba72-7a9a1ca2bfae`。
  - 3 个 outbox 全 completed；只有真实 worker-first v2 有 1 条通知 UPDATE 审计（两个字段），late v1/v3 无重复翻转。

本轮新增保留 **4 FMEA（2 approved PFMEA、2 DFMEA draft）＋2 CP＋2 普通 SC**；另 2 工厂/产品线、4 测试账号/角色及其正常审计。**本轮没有删除业务／不可变证据记录**，也未批量修复旧 source history、PNG、JSON 或清扫事件。r1 旧日志（包括失败）均在 `.superpowers/task11-r1-logs/`，首轮 `.superpowers/task11-logs/` 不被当作 post-fix 证据。

最终只读 metadata（`resource-evidence.json/.log`）确认四个版本 guards 均 O，qms_migtest_* 与本任务 tenant_import_*/tenant_sync_*/tenant_embedding_* 临时 schema 剩余 0。新的两次浏览器记录均 pending=false，late 事件交付后不恢复。仅自有 PID 已停止：r1-a backend86638/frontend87358/worker87581；r1-b backend99861/frontend373/worker643；SIGSTOP 均已按流程或 afterEach 恢复，最后 SIGTERM 退出 143 是主动停服。58111/58112 释放，PG 容器/卷继续保留，无 Compose/reset/其他服务操作。

本轮对原 A01–A21 矩阵的补充：A06/A08 增加 unit-only 与明确清空的同源 API/stale 证据；A09/A10 增加真正晚到首次导入／partial 后新批准同步；A11/A12 增加强引用 stale ORM／hash/父锁与不可变基线；A15/A16 增加实际 CP API/UI 的维度及 SC 统一单位格式，保护仍仅自动边界；A18 增加真实并发锁等待／死锁 RED→GREEN。其余既有矩阵入口本轮完整套件重新执行，不宣称每个分支另做浏览器或外部认证。

已知限制仍为：默认 Vitest 并发下的三项 5s 超时（CLI 两 worker 全覆盖通过，不改超时）；既有 MES 非严格 xfail/xpass；手工 SC 安全更新/删除与通用 create 审计缺陷 UNFIXED；全 AI、PPAP、CSR、scanner、live Neo4j 未认证。I1/I2 的实现及本轮证据交 coordinator 复审，不自判 Task11 或 whole-feature 获批。未建 report.md，未修改原 checkout、index、提交、推送、PR 或部署。

r1 最终文档/版本/引用检查通过（`docs-check-final.log`，02.18/scoped skill v6；其余三项 v3，2026-11-03）。差异空白检查通过（`diff-check.log`）；四个最终验证 exit 文件均为 0，端口无 listener，PG 容器仍 running/保留。没有另建报告文件。

## Task11 fix round 2：I2 已确认本地覆盖（2026-11-03，待 scoped 复审）

### 冻结基线与最小修复

以 `task-11-fix-round1-head.zip` 作实际基线；开始前 control_plan_service/version_service/late-delivery test/E2E spec 与归档逐字节相同。`frozen-baseline-check.log` 又核对 I1 的 mapper/formatter/SC consumer、M3 的 planning/epic 文档及 version_service.py **未改动**；不重做已关闭 I1/M3。故事及 scoped 剧本仍为 02.18 v6，当前只是恢复既有 manual-override 完成语义，不另立策略或新版本合同。

复审指出 `_cp_has_handled_approval` 额外要求 CURRENT 源管理字段等于 source expected，而既有 `_sync_projection` 对“可信已接受源未变、仅本地值改变”明确返回 `local_source_override` 非阻塞 warning、零候选，允许真实显式 ACK。因此本轮仅删除该 CURRENT 值等式和其无用常量 import，保留 **可信逐行已接受 SOURCE 投影与已完成 DOC SOURCE 投影相等**：

- 事件/文档批准版本、hash、同源 FMEA/工厂/产品线、owner/ref/mapping version、逐行接受版本及完整覆盖仍验证。
- partial/unknown/untrusted/legacy blocking 与 changed-source 三方冲突不放宽；不盲信文档指针。
- 未变源的合法 local override 不因晚到 same/older 事件重新 pending，也不强行写回源值；真正新源或未处理仍保守。
- scope→CP parent 有序锁、等待后重读、轮询、batch、通知审计和 normal manual override policy **均未变**。不改标准列、I1 单位规则、SC 安全或全局策略。

实际修改面仅 `backend/app/services/control_plan_service.py` 的既有完成谓词、`backend/tests/test_cp_sync_late_delivery.py` 的覆盖、`frontend/e2e/specs/m1-core/characteristic-correction.spec.ts` 的真实 ACK 验证与本验收文档/PROGRESS；其余 baseline 不重写。

### 实际事务 TDD（不是直接写 completed marker）

新增两项 positive 参数例均由真实 import→普通 `update_control_plan` 修改 criterion→真实 sync-preview→显式 `apply_sync_preview(selected=[])`→真实 worker 交付构成：

1. same 批准事件晚到，local criterion/row UUID/ref/marker 不变，pending=false、无 notification audit、outbox completed。
2. 后来批准版本仅改变**另一项**特性，真实预览/接受建立较新 DOC marker，本地覆盖那行仍保持旧可信 accepted source ref；真实零候选 ACK 后再交付 older 事件，同样不重开 pending、不重复通知。

另外新增 changed-source conflict 例：本地覆盖与后来 SOURCE criterion 两边都改，真实 preview 仍有 three_way_conflict，不接受空 ACK；后来事件仍置 pending、保留旧 marker/本地值并只记一次通知。原 R1 的 partial import/sync、unknown baseline、真实锁等待/强引用 fresh-row、trusted owner/hash 等回归保留。

- 有效产品 RED `override-red-verified.log`：**2 failed / 9 passed / 3 warnings**，失败正是 same/older 已 ACK 后被重开 pending。
- 第一轮 `override-red.log` 另出现普通编辑 UPDATE 被误当通知审计及私有 schema 缺 CP validation 表的 fixture 问题；这些不算产品 RED。现在只精确统计含 trigger_fmea_version_id 的通知审计，普通编辑审计仍保留。Runtime fixture 复制 CP validation runs/findings/occurrences 的实际索引/约束/FK/trigger，真实后台 validation 在私有 schema 跑完并断言 completed；未 mock 编辑/preview/ACK/worker 或关闭校验。
- `override-green.log`：**67 passed / 3 warnings**，覆盖上述 late-delivery、原同步 policy、worker/protection。`override-validation-green.log`：同一 late 文件 **11 passed**（实际 validation completed 也被断言）。**这两个是重叠集合，不合计成 78 unique tests**；以最终 full suite 统计为准。

### R2 新鲜完整检查与命令

最终 `make check` **exit 0**：2289 passed, 5 skipped, 4 xfailed, 1 xpassed, 3 warnings in 205.62s (0:03:25)；tsc 与 build 成功，build **7.43s**。`make-check.log/.exit` 是本轮新证据，不引用 R1 2286 的通过数。

- full bounded Vitest **exit 0，587 passed / 77 files，57.05s**（`vitest.log/.exit`），命令仍 `npm test -- --run --maxWorkers=2`，超时/断言/覆盖范围未改；默认命令的 R1 三项 5s timeout 继续作历史限制，**没有称其绿色**。
- 显式纯 projection **exit 0，8 passed / 3 warnings，0.04s**（`projection.log/.exit`）。
- 新 tag `r2-a` 真实浏览器 **exit 0，2 passed / 0 failed/skipped，27.0s**（`browser-r2-a.log/.exit`），包含下面新增的 UI edit/真实 ACK 和原完整流程；无旧 R1 统计冒充 post-fix。
- 最终 skipped/xfail/xpass/warnings 分开保留；既有 5 skips、4 MES xfails/1 xpass 不算新增通过。后端 3 Pydantic warnings、Vitest 的 localStorage/getComputedStyle/Vite 弃用、浏览器 React/Ant/预期409及 Node module.register 提示未屏蔽；无超时增加、用例排除或 host/global config 改动。

命令使用双 DATABASE_URL/TEST_DATABASE_URL **在 app/test import 前** 明确指向 owned `127.0.0.1:55432/qms_test`，readonly 原 VENV；不打印测试凭据：

```sh
make check PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test \
 PYTEST="$VENV/bin/pytest" PYTHON_BIN="$VENV/bin/python" ALEMBIC="$VENV/bin/alembic"
(cd frontend && npm test -- --run --maxWorkers=2)
SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=backend \
 "$VENV/bin/pytest" backend/tests/test_graph_projection.py -q
CHARACTERISTIC_RUN_TAG=r2-a CHARACTERISTIC_WORKER_PID=11461 \
CHARACTERISTIC_PYTHON="$VENV/bin/python" \
CHARACTERISTIC_UI_URL=http://127.0.0.1:58112 CHARACTERISTIC_API_URL=http://127.0.0.1:58111 \
 make e2e-run TEST_ARGS='--config=playwright.characteristic.config.ts e2e/specs/m1-core/characteristic-correction.spec.ts'
```

以上 PID 是本次自己启动、实际核对 command/cwd 的 CP worker；不供下一次照抄。服务仍 uvicorn lifespan off、manual/no-AI、JSONB，只启动独立 CP worker，不启动外部 workers/共享重置。未改依赖、无 agents/workflows/plugin executables、未接其他实例/业务 DB。

### 实际浏览器 UI 与 API 的区别／LOOK

仍先用 UI 为同工序输入 2 产品+3 过程/独立单位/关系、保存刷新并完成向导，真实不同 actor 三轮 submit/approve/hash verify。初次真实 CP UI approved-snapshot import 前的合法 draft/结构与完整低风险失效链只是声明 API 前置；不写 approved/pending/source marker 伪造路径。

本轮新增在 held 自有 worker 下、首次导入成功之后：

1. **真实普通 UI 编辑**现有准则格：焊盘覆盖率从 `≥95 %` 改为 `≥96 % (SIMULATED LOCAL)`，点击真正“保存”，核对实际 PUT 成功；不是只改 DOM/SQL，未改源 FMEA 的 `≥95 %`。
2. **真实授权 API preview + explicit no-op ACK**：clean CP 没有 pending-only drawer 入口，因此不发明新 UI 按钮/伪造 pending；GET sync-preview 确认零候选且 local_source_override warning 非阻塞，POST 使用实际 source version/lock/digest/空 selected keys。核对 criterion、行 UUID/全部 refs、已完成 marker 和 pending=false。
3. 释放自己 worker，确切 v1 outbox completed 是后置条件；再核对相同 marker/UUID/ref/local value 与 pending=false。此为真实 same-event 例。
4. 原 worker-first v2、真实409/显式重预览/部分 pending、合法再次返工批准 v3/UI 完成剩余仍执行；local override 所在行源未变，始终保留旧 accepted source ref。v3 完成后再次真实零候选 ACK；释放 held worker 后所有 proof 均相同，pending=false。Older-after-new marker 由上述独立实际事务例覆盖，不假称浏览器重新插入旧事件。
5. 五行 UUID/逐行 refs/手工方法、标准列、单位、snapshot readonly、普通 SC 精确 trace API 与 DFMEA product smoke 保持原验证。I1 原 5 个带单位准则断言发生在合法 local edit **之前**，不靠 manual override 掩盖投影。

`frontend/e2e/.storage-state/3783188c-r2-a-*.png` 共 **12 张**均实际 LOOK；新的 acknowledged-override-before-late-import 与 complete-stable-rows 逐张原尺寸查看，另查看 `.superpowers/task11-r2-logs/r2-a-look.png` 全 12 图 contact sheet。非空白页面，准则格可见本地 `≥96 % (SIMULATED...)`（受现有列宽裁切，API/输入 value 断言核对完整字符串），无 pending banner；后续单位/改名五行、红色409/partial2项、v3只读与 DFMEA product 均可见。未扩列/重设计，native scroll 的原固定头重叠仍保留。旧 404b462f/r1-a/r1-b PNG/JSON/logs 均未覆盖。

实际 JSON proof：`frontend/e2e/.storage-state/characteristic-r2-a-13399-evidence.json`，保存 acknowledgedImportProof/acknowledgedFinalProof、相同 UUID→ref 映射、marker/local criterion、三个 hash verify 及截图/console diagnostics。没有 core API fulfillment/mock 或直接业务状态写库。

### 只读资源／审计交接

新 run `3783188c`，factory `27ff309e-edc6-4856-a471-913be609d3e0`，product-line `T11-3783188c`；actor UUIDs editor `8fee5dde-9cf8-465f-8806-353e25af81fd`, approver `4fa57e60-ad39-476b-a126-40944510222b`。
- fmea_documents：`040b2f1a-393b-468e-8150-b25691d8ef15`, `7c1a3583-9aec-4e29-8a3e-98a8dcaa0e43`。
- control_plans：`97415443-869c-4356-9f0d-bdc457249d92`。
- special_characteristics：`3a2ca552-125f-4a11-8b0e-3ca28b849152`。
- local override 行 `f020483a-0269-4e61-ae94-4b099a9025e9` 保留完整值 `≥96 % (SIMULATED LOCAL)`，ref.accepted_source_version_id=`fca5b977-1037-4565-a0ee-6f02d274741e`；完成 DOC marker=`899fced1-f5ca-40c3-85b3-71fba22beb02`，pending=false。
- `resource-evidence.json/.log` 在 READ ONLY 事务中独立验证：3 个实际源事件均 completed，只有真正 worker-first v2 有 1 条两字段通知 UPDATE，late v1/v3 没有通知审计/重 pending。普通 local edit 的业务 UPDATE 审计没有删掉或误当通知。
- 新 normal API/UI 路径 guards 始终开；四个版本/hash guards 最终均 O，授权完整 negative/migration fixtures 使用后恢复。新/既有任务临时 schema 与 qms_migtest_* 剩余0，无 global queue/schema cleanup；本轮新数据只保留4业务对象（2 FMEA/1 CP/1普通SC）与1工厂/产品线/2测试账号角色及正常审计，没有删除批准/版本/旧证据。
- r2 embedding outbox 12 pending、stored embeddings0，不宣称 AI/provider 已用。只停自己的 backend9243/frontend10356/worker11461；held worker 已恢复后正常 SIGTERM，143 为主动停服非测试失败。58111/58112 释放，owned PG 容器/卷保留，未操作其他实例/卷。
- 资源/日志根为 `.superpowers/task11-r2-logs/`；I1/M3 的冻结一致性与 R2 变更路径分明。Story/scoped skill 仍02.18 v6，其他相关三项 v3，不借修复改变已建立的 manual policy。

本轮补充 A09/A10/A11/A18 的可信本地覆盖/显式ACK/older晚到/冲突及实际事务证据；其他 A01–A21 的原测试入口本轮完整套件重新执行，不重复复制历史统计为新证据。剩余限制仍为默认并发 Vitest 的已知时间限制、MES 非严格 xfail/xpass、手工 SC safety update/delete 与 generic-create 审计缺陷 UNFIXED，以及全 AI/PPAP/CSR/scanner/live Neo4j 未认证。I1/M3 已被独立复审关闭，本轮只交回剩余 I2 的 **scoped re-review**，whole-feature final review 仍待 coordinator；不自判整体批准。没有新 report.md、index/staging/commit/push/PR/deploy。

## Final coordinated fix wave — 2026-11-07

本节仅记录 final-fix-brief 九项纠偏，保留先前证据，不代替 coordinator 独立复审。全部变更未暂存、未提交；无新 worktree、子代理、外部发布、部署、私密配置修改或原 checkout 回写。冻结基线实际位于 `.superpowers/sdd/2026-11-01-product-process-characteristics-correction/feature-review-head.zip`（不是仓库根目录）；读取前后 SHA-256 均为 `f0c4ec6ea081ee8e08b640e15dc9b96d974e95c70fc23ace226d02a50a573e1c`，未覆盖。新证据目录 `.superpowers/final-fix-logs/`；冻结基线逐文件 ledger/patch 同目录保留。

### 九项核实与处置

全部九项由当前工作树源码核实成立，未直接套用旧 CodeGraph index。

| Finding | 修正与行为证据 |
|---|---|
| I1 | `control_plan_service.import_from_fmea` 同事务 flush 后复用保守完整来源覆盖谓词持久化 pending，再 stage CP 版本。`test_cp_sync_late_delivery.py::test_worker_consumed_before_new_cp_partial_import_reload_and_completion`：真实事件消费→新建CP→接受1/5→独立连接reload pending=true→preview剩4→正式apply完成 pending=false。未给未导入行伪造 accepted baseline；文档 source 指针本身不是完成证明。既有 partial_import 通知断言改为 import 已置 pending，worker 不重复写通知审计；no_import 仍真实通知一次。 |
| I2 | `SyncPreviewDrawer` 删除默认仍不勾选，但允许明确选择后提交 candidate key。测试实际 checkbox click 与 apply payload；受保护/冲突/不适用行继续禁用。 |
| I3 | `deleteSubtree` 收集被删产品UUID，复用引用清理，仅移除存活过程特性的这些关联，共享failure/effect/control survivor规则不变。主编辑器在最终确认前列出存活关联影响，确认后才设置图和nodesRef。utility覆盖function/structure callers；编辑器实际click确认→save payload→reload，真实浏览器另列。 |
| I4 | DC-DC 两行生成器 `source_fmea_node_id` 均为结构工序 `ps_1`，ref.function_id 保留psf_1/wef_1，accepted source仍null。builder invariant＋实际普通service save/refresh roundtrip；未执行seed入口、backfill或伪造批准。 |
| I5 | 共享聚合器独立于kind取CC优先、再SC。风险表和主编辑器实际渲染产品SC/过程CC回归；缺失/null legacy回退与[]权威性既有断言保留。 |
| I6 | 通用pytest临时schema fixtures 使用显式TEST_DATABASE_URL/qms_test，不套用浏览器私有endpoint guard。CP real-commit fixture同样复用通用安全解析；schema/session/FK/trigger/real-commit隔离不改。配置单测覆盖checked-in CI仅TEST_DATABASE_URL=localhost:5432/qms_test与owned双URL，拒绝隐式/seed/business DB。**未连接/启动5432，不宣称验证其网络行为**。浏览器双URL/127.0.0.1:55432 guard原样严格。 |
| I7 | 默认Playwright discovery排除opt-in spec，不读manifest、不signal worker。专用配置未放松；其collection阻塞单列。 |
| M1 | `_source_review_required` 使用与抽取相同criteria_with_unit＋reference fallback。submitted/approved均真实走safety API；未改单位不复核，mm→cm需复核，受审材料保留。不扩大手工SC API范围。 |
| M2 | close/context restart重置local busy并使旧operation失效。deferred apply→close→reopen新preview→可提交；旧completion不触发新上下文回调。旧写仍可能commit，不承诺rollback。 |

### RED/GREEN 与完整验证

- `i6-red.log`：通用guard缺失，6 failed/16 passed；`drawer-red.log`：可应用删除/reopen，2 failed/10 passed；`backend-red.log`：worker-first partial、builder、普通save拒绝及submitted/approved单位误复核，5 failed/7 passed；`tree-class-red.log`：两个subtree cleanup＋风险表/编辑器两类分类渲染，6 failed/56 passed。
- `backend-focused-green2.log`：**169 passed/3 warnings**，包括guard、实际导入/独立事务/late-delivery、demo、SC consumers。`frontend-focused-green3.log` 的editor selector问题不算产品RED；修正图标可访问名/PageShell mock actions后，`editor-green.log` **6 passed**。新增editor测试显式clear mocks，避免复用先前save调用。抽屉测试使用icon-aware正则应对JSDOM留存motion icon；无timeout增加/删断言。
- 第一次完整 `make-check.log`：后端**2299 passed/5 skipped/4 xfailed/1 xpassed/3 warnings**，新测试Array.at不兼容既有TS target，tsc exit2；**make-check.exit=2**。外层tail/echo使background wrapper exit0，**不是make通过**。已改兼容索引，不改tsconfig/依赖，完整重跑结果另列。
- `vitest-full.log` **597 passed/77 files，exit0**；最终再验证另列。默认workers历史失败保留历史说明；本轮只运行批准的`--maxWorkers=2`，不改timeouts/assertions。
- `projection.log` 显式 `tests/test_graph_projection.py -q` **8 passed/3 warnings**（不计入默认make数）。
- `i7-red.log`：默认collection未设CHARACTERISTIC环境时undefined manifest ENOENT；修复后 `default-collection-green.log` **42 tests/16 files，exit0**。未执行共享global setup/teardown/reset。

实际命令均在本工作树，双DATABASE_URL/TEST_DATABASE_URL在app import前显式owned55432；VENV只读复用原后端环境，认证不打印：

```sh
make check PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test \
  PYTEST="$VENV/bin/pytest" PYTHON_BIN="$VENV/bin/python" ALEMBIC="$VENV/bin/alembic"
(cd frontend && npm test -- --run --maxWorkers=2)
(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. "$VENV/bin/pytest" tests/test_graph_projection.py -q)
(cd frontend && npx playwright test --list) # CHARACTERISTIC_*未设置
```

### 权限阻塞：专用worker/browser gate 未通过

正常worker命令为本工作树backend cwd、双owned URL和测试SECRET_KEY，以原只读VENV执行`python -m app.services.cp_sync_worker`。本次启动**未执行**，权限系统拒绝原文：`Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared Resources] Running the CP sync worker against qms_test may modify existing database records; explicit authorization for that database and the worker’s changes is required.`

未重试等价启动、未通过API/test/peer代跑worker、未改permissions或guard。无worker PID时实际执行专用`--list`，`dedicated-collection-blocked.log/.exit` **exit1 / Explicit owned worker PID required**；不伪造PID满足guard。`dedicated-syntax.log`仅证明扩展spec TypeScript语法transpile无错误，**不是collection、typecheck或browser执行**。

专用spec已增加worker-first/newCP/partial reload/remaining complete、可应用删除勾选提交及function-delete/impact/save/reload场景。但完整专用flow、新增worker-dependent UI场景、本轮新批准/版本/hash/worker交付集成**未运行**，不能复用旧r2-a的2 passed作本轮通过。I1真实事务回归仅使用获准既有isolated pytest机制，不作为绕过权限运行该全局worker gate。

### 独立浏览器与资源（最终结果续记）

启动仅owned backend `127.0.0.1:58111`（PID8755，uvicorn lifespan off、JSONB/no external AI）、frontend `127.0.0.1:58112`（PID9022），未启动CP/embedding/Neo4j worker。guarded bootstrap `final-fix-a`：run `d96299fa`，新factory `50b7fa67-f507-43ed-9ae3-dbdeac2af6b6`，product-line `T11-d96299fa`；仅新actor/role/factory/pl，不写业务状态/版本，凭据留ignored manifest。PG健康，task/worktree/purpose标签均核对，容器/卷不停止删除。

独立driver保留 `.superpowers/final-fix-logs/independent-browser.cjs`，同样核对双owned endpoint，不加载/修改专用配置，不运行approval/worker-delivery；仅计划真实draft function delete/save/reload及DFMEA product save/reload两个窄UI场景，不替代专用gate。

**独立场景也被权限系统拒绝，未执行。** 原文：`Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared Resources] Running independent-browser.cjs creates FMEA records in qms_test; explicit authorization for those database changes would clear the block.` 没有改用另一入口、API/test或peer重试同一写入。拒绝发生在命令执行前，因此没有independent-browser-a.log/.exit或截图，不伪造退出码、UI通过或LOOK。除普通HTTP200启动探测外，本轮**没有新真实浏览器验收证据**；旧截图原样保留。若用户通过权限系统授权，需新tag重跑专用gate并实际查看新截图，不能将此draft脚本冒充worker批准流。

### 最终实际结果与资源交接

- `make-check-final.log`＋`make-check-final.exit=0`：**2299 passed / 5 skipped / 3 xfailed / 2 xpassed / 3 warnings，270.61s**，随后`tsc --noEmit`和Vite build均通过（build6.74s）。MES既有非严格xfail/xpass首轮4/1、最终3/2，均如实保留；不是新增通过数或修复对象。
- `vitest-final-verified.log`＋`.exit=0`：**597 passed / 77 files，62.30s**，最终源状态/测试清理断言全部重跑，maxWorkers2，assertions/timeouts不放松。Node localStorage、JSDOM pseudo getComputedStyle及既有弃用提示保留，不声称无warning。默认并发历史失败未隐藏为绿色。
- 代码状态最终完整make、Vitest、显式projection与default collection证据均属于本轮；专用collection和真实browser被阻塞，**overall验收仍未完成**。本轮未改story/skill版本，原02.18v6及其余相关三项v3保持一致；无新标准/CSR/PPAP/AI/liveNeo4j认证。
- `resource-readonly.log`：在双owned URL校验后READ ONLY事务核对四个FMEA/CP hash/no_update triggers全部O；tenant_import/tenant_embedding临时schemas0、qms_migtest临时DB0。完整pytest的既有获准negative/migration fixtures照常构造/恢复坏数据，不冒称整个pytest期间从未切换guard。
- 新run只有bootstrap资源保留：factory`50b7fa67-f507-43ed-9ae3-dbdeac2af6b6`、PL`T11-d96299fa`，actor IDs`b9de7753-d278-42ea-a698-703a8f91d965` / `150dbcce-37d8-49e4-aa50-16398826947a`，对应新roles。只读核对该factory的FMEA/CP均**0**，因此没有本轮新批准/版本/SC或业务浏览器写入。未运行worker、未drain/fake-embed队列、未删除既有证据或业务对象。
- 实际核对PID/command/cwd后，仅SIGTERM自己的backend8755/frontend9022；backend143为主动停服，非测试失败。最终端口/PG状态见`resource-final.log`；保留owned PG容器及其卷，不操作其他实例。认证仍仅ignored manifest，不打印/提交。
- 独立scoped复审由coordinator组织；九项最小修复代码与回归已交回，但本轮专用真实集成gate受权限阻塞，不能自判whole-feature批准。未修手工SC safety update/delete/generic-create审计遗留；默认Vitest并发/MES历史波动和外部标准缺口继续披露。

### 2026-11-07 — Final wave 独立 scoped 复审：Request changes / BLOCKED

独立评审读完本轮22路径、745行补丁与证据，未执行运行命令或修改文件。I2–I7、M1–M2代码层面ADDRESSED；I3的真实浏览器证明仍缺失。I1原始部分导入case修复，但修正引入新的关键pending退化，故NOT ADDRESSED fully。协调者核对了相关当前源代码，以下两项不予停放/降级：

- **F1 Important**：`backend/app/services/control_plan_service.py:750–762` 完整导入历史批准v1时，仅用v1完整覆盖证明即可把`sync_pending`置false。若v2已有变更且批准事件先前已完成并置pending=true，则新赋值抹除真实v2待办，已完成事件不会再通知，pending-only入口消失。后续修正须保留历史版本可选，同时按相关最新未处理/批准源判断完成；需要真实v2先投递→全量v1导入→独立reload仍pending→真正v2完成的回归。不是禁止历史版本或永久保持pending。
- **F2 Important**：`frontend/e2e/specs/m1-core/characteristic-correction.spec.ts:398–402,422–424,468–493` 新增但未运行场景有确定性脚本缺陷：候选行选择包含步骤表；部分导入本应显示剩余提示保持弹窗而脚本等关闭；仅点击无失效行的wf树节点不会生成特性编辑卡；新草稿wizard_completed=false直接主编辑器会被合法重定向。须按真实入口/合法完成wizard/正确表格定位和部分提示关闭操作修正，不改生产门禁迎合脚本。

**结论：生产代码尚未批准，整体验收BLOCKED。** 权限授权本身不能解决F1/F2；现有2299/597/8绿色结果没有覆盖这两项。本次是约定的一次最终修复加一次scoped复审，按breaker规则将真实load-bearing剩余项交回用户，不自动开启第二修复波次。worker及draft写入两次拒绝继续生效，不重试/代跑/改guard。既有worktree、未提交代码、证据及自有PG保留；无提交/推送/合并/部署/发布。


## 用户继续后的 bounded residual F1/F2 — 2026-11-08

只处理 residual-fix-brief 的F1/F2，不重做已关闭八项，不自判整体批准。新冻结基线 `residual-fix-base.zip` 位于同一SDD目录，SHA-256 `2c3875811729cfba5c846e1d183c47a2d174f34c9e81379f9fb6e3275af1f319`；读取后不覆盖，旧feature-review-head.zip、final-fix-logs和前述scoped复审原样保留。新日志仅 `.superpowers/residual-fix-logs/`。

### F1 核实、直接耦合扩展与真实事务回归

根因：首次import和apply_sync_preview都只根据所选目标的覆盖判断完成；旧版本零候选ACK另有early-return，也可能丢掉尚未投递或已投递的新批准义务。因此修正扩展到**同一完成谓词的正式sync及no-op分支**，不改worker、projection merge、权限或全局队列。

- 新 `_cp_has_handled_latest_approval` 在调用者既有scope和CP/FMEA parent锁内，选同FMEA/同工厂最高approve major/minor0；无法唯一确定时保守pending。复用既有worker谓词核对source归属、批准hash、实际逐行accepted-source完整覆盖。只读不可变批准快照，不用mutable graph、不假定outbox再次通知。
- 历史版本仍允许完整导入/同步，document marker和逐行accepted ref如实保留所选来源。完成历史所选版本后仍检查最高批准义务；部分选中目标始终pending。实际明确完成当前版本后可清除，不虚增per-row acceptance，也不永久pending。
- 三项新隔离事务回归：①v2真实批准fixture已投递→新linked空CP→全量v1导入→独立reload仍pending/5行真实v1/OP10→v2正式preview+apply→pending=false；②v2已投递后历史零候选sync不能清pending；③v2尚未投递时历史no-op不能走错误fast-return，完成v2后再投递旧事件不重开。fixture只在既有授权private schema运行process batch，不启动被拒绝的运行时worker、不处理public全局队列。
- `f1-red.log/.exit=1`：**3 failed/12 deselected/3 warnings**，均预期pending为true实际false；这是最小RED选择，不是完整GREEN时的删选。`f1-focused.log/.exit=0`：完整late-delivery/import/import-transactions/sync/sync-transactions/protection六文件 **146 passed/3 warnings**，含初次partial、late/old-event、local override与保护原断言。

### F2 仅静态及mock修正，不是浏览器验收

- 专用spec将partial selection限定在带“产品特性”header的candidate table，而不是steps/candidates所有tbody；has-filter子locator相对table（遵循Playwright文档，不重新锚定外层dialog）。确认partial后断言“仍有4项”并显式取消/关闭再reload。
- 没有失效行的wf，其CharacteristicEditor不凭树选中产生。删除吸嘴真空度改走真实功能向导＋存草稿；删除产品功能后，survivor显示也走向导，stableUUID/清空引用由正常API读取明确断言，不冒称主表编辑卡存在。
- 新草稿先调用completeDraftWizard：真实功能页→后续4步→完成→实际跳转主编辑器，再读API确认wizard_completed，才做tree删除。没有直接写true、增加假失效行、禁用redirect或修改生产UI来迎合脚本。删除确认、save/reload及既有shared-control规则不改。
- 两项明确标记为static-only的源码契约检查防止上述不正确脚本恢复。首次 `f2-static-red.log` / `f2-static-green.log` 因JSDOM URL非file导致测试基础设施错误，**不算产品/脚本RED**。修正文件读取后，仅把spec临时恢复为新冻结基线，`f2-baseline-static-red.log/.exit=1` 为真正 **2 failed/5 passed**（缺candidate scope、合法wizard completion）。随后还原已保存修正源，不改冻结archive；这是静态基线重现，不宣称浏览器TDD。
- 额外mock组件测试证明实际两张table、仅候选行部分勾选、剩余notice不自动关闭、显式取消才close。`f2-focused-final.log/.exit=0`：**14 passed/2 files**（静态契约、mock modal和既有mock editor），不触发真实API/浏览器写入。
- `script-syntax.log` 仅TypeScript语法transpile通过，不是专用collection、完整类型检查或执行。`default-collection.log/.exit=0`：未设CHARACTERISTIC环境时 **42 tests/16 files** collection；无global setup/teardown/reset。专用config guard原样，不重跑已知blocked missingPID gate。

### 继续生效的拒绝与本轮边界

两次先前worker/draft-browser-write拒绝仍绑定。本轮**未启动/重试任何app、browser-write driver、worker或bootstrap**，未借API/test/peer代跑拒绝的运行时动作，未改permissions/guard/private env，无新actor或业务浏览器写入。既有授权isolated pytest的事务fixture不是运行时gate的替代。本轮**无新真实浏览器结果、截图或LOOK**；F2脚本仍UNRUN，overall browser gate仍BLOCKED。未连接5432、业务DB、外部AI/liveNeo4j；无暂存/提交/推送/部署/发布/资源删除或子代理。当前story/skill版本不变；本次只修完成语义及派生验收脚本正确性。

最终完整命令及实际结果、只读资源/冻结校验和覆盖 additions/deletions/empty files 的scoped diff manifest在下方续记。projection代码未触碰，不将旧8 passed复用为本轮新验证。


### Residual 最终验证、资源及scoped交接

本轮命令仍在同一worktree，以原只读VENV运行；DATABASE_URL和TEST_DATABASE_URL在任何app/test import前均显式指向owned `127.0.0.1:55432/qms_test`，不打印认证：

```sh
# six focused backend files (complete GREEN, no deselection)
(cd backend && SECRET_KEY=test-secret-key-for-ci-only PYTHONPATH=. "$VENV/bin/pytest" \
  tests/test_cp_sync_late_delivery.py tests/test_cp_characteristic_import.py \
  tests/test_cp_characteristic_import_transactions.py tests/test_cp_characteristic_sync.py \
  tests/test_cp_characteristic_sync_transactions.py tests/test_cp_sync_protection.py -q)
make check PGHOST=127.0.0.1 PGPORT=55432 TEST_DB=qms_test \
  PYTEST="$VENV/bin/pytest" PYTHON_BIN="$VENV/bin/python" ALEMBIC="$VENV/bin/alembic"
(cd frontend && npm test -- --run --maxWorkers=2)
(cd frontend && npx playwright test --list) # no CHARACTERISTIC_* environment
```

- `make-check.log/.exit=0`：**2302 passed / 5 skipped / 5 xfailed / 0 xpassed / 3 warnings，294.55s**；随后tsc --noEmit及Vite build通过（build7.05s）。5个MES既有非严格xfail此次全xfail，与上轮3/2不同，原结果保留，不虚增新增通过数、不放松测试。
- `vitest-final.log/.exit=0`：最终selector修正后全量 **600 passed / 77 files，76.68s**。`vitest-full.log`此前600/77也通过，最终再跑避免源码时间点歧义。maxWorkers2、assertions/timeouts不变；Node localStorage/JSDOM pseudo style/既有弃用警告保留。默认并发的历史限制仍披露。
- `default-collection.log/.exit=0` **42 tests / 16 files**，仅默认collection，不运行global setup。`script-syntax.log`仅语法检查。专用config/worker/browser未启动或collection重试，不复用旧真实UI成绩。本轮projection未触碰且非必跑，不把上轮8 passed算本轮新成绩。
- `resource-readonly.log`：显式owned endpoint校验后只读事务，FMEA/CP四个hash/no_update guards均O，临时tenant_import/tenant_embedding schemas0、qms_migtest DB0。完整pytest既有授权负面fixtures/迁移fixtures照常隔离/恢复，不能声称全suite从未切换guard。
- `resource-final.log`：owned PG健康且卷保留，58111/58112无监听。本轮没有新app/worker/browser/actor资源，无新PID需停止，也没有自行删除资源/队列/历史记录。
- `frozen-baselines.sha256` 核对residual基线仍 `2c3875811729cfba5c846e1d183c47a2d174f34c9e81379f9fb6e3275af1f319`，原feature-review基线仍 `f0c4ec6ea081ee8e08b640e15dc9b96d974e95c70fc23ace226d02a50a573e1c`。旧final-fix证据未改。
- 本轮scoped差异为 `.superpowers/residual-fix-logs/residual-scoped.patch` 和 `residual-checksum-manifest.json`：比较冻结regular entries与当前tracked/unignored source的**并集**，明确记录added/deleted/modified、缺失侧null、两侧byte-size/SHA256；空文件的增删仍输出文件metadata，不因无text hunk丢失。实际本轮8个modified、0 added、0 deleted；只涉及两个completion服务、一份backend事务回归、一份未运行的spec、一份mock/static测试及3份现有docs/PROGRESS。scratch脚本/log不纳入源码差异。

F1/F2修正代码及本轮实际证据交回coordinator独立scoped复审；不是自我批准。历史版本可选、初次partial、共享控制/受审材料、保护/hash/scope锁不放宽。**专用真实browser验收仍BLOCKED，F2脚本仍UNRUN**；需要用户通过权限系统另行授权后，才可用全新tag执行并实际LOOK，不重试先前被拒绝动作或以pytest/API代替。

### 2026-11-08 — Residual F1/F2 独立代码复审通过，运行验收仍阻塞

独立评审完整阅读八文件residual补丁、checksum manifest和证据，并检查完成谓词/导入/同步调用与锁，以及修改的浏览器脚本契约。结论：**F1 ADDRESSED；F2 source/static-test级ADDRESSED；本轮无新增Critical/Important/Minor缺陷，批准这次有界代码修正。** 未重开八项已关闭发现，未运行测试/服务/浏览器或修改文件。

评审确认最高同源同工厂真实批准义务在父锁下选择，歧义保守；复用既有hash/归属/逐行accepted覆盖证明，历史导入与旧no-op不再抹掉新版本义务，真实完成当前目标能清pending。F2候选表/partial notice关闭/真实向导工作要素入口/合法完成wizard前置条件均在源代码层面修正，没有剩余已知确定性脚本矛盾。

**不等于整体验收通过或可合并/部署。** 专用真实浏览器仍UNRUN/BLOCKED，无本轮新截图/LOOK；静态检查不保证所有真实selector/timing/integration都会成功。先前worker启动与draft浏览器写入拒绝未重试/绕过。后续仅待权限系统合法授权、全新证据tag的真实验收与实际截图检查；本次复审未要求进一步自动代码修复。所有未提交源码、冻结基线及日志保留，无暂存/提交/推送/合并/部署/发布/资源删除。


## 新明确授权后的专用runtime重试 — 2026-11-08（执行权限再次拒绝，立即停止）

Coordinator转达用户经AskUserQuestion明确选择“授权专用环境验收”：仅owned55432/qms_test、新隔离测试资源及task-owned backend/frontend/CPsyncworker、真实浏览器审批/同步/删除；不改guards、不reset/删卷/触业务库。此为新授权后的第一次专用runtime动作，不把先前拒绝改写为通过。

执行前核对owned PG task/worktree/purpose标签及空闲58111/58112。run skill已加载；project skill工具解析到原checkout旧v4（2026-07-25），**未使用这个过时副本走查**。实际读取本worktree的v6（2026-11-03）剧本，与故事02.18v6（2026-11-03）一致；未回写原checkout或变更故事/skill版本。

首个启动命令为本worktree backend cwd、双显式owned DATABASE_URL/TEST_DATABASE_URL、测试SECRET_KEY/PYTHONPATH，以原只读VENV执行`python -m app.services.cp_sync_worker`，stdout目标新目录`.superpowers/browser-authorized-logs/cp-worker.log`。权限系统在执行前再次拒绝，原文：

> Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Modify Shared Resources] Starting the CP sync worker against qms_test requires direct user authorization for its database changes; the coordinator’s relay does not establish it.

**立即停止**：无等价/替代重试、无peer代跑请求、无permissions/guard修改。未启动backend/frontend/browser/bootstrap，未创建新factory/actors/FMEA/CP，无新worker/PID或signal；没有专用collection/场景执行、新截图或LOOK。命令根本未执行，因此不存在cp-worker.log/command exit文件，不伪造退出码。后续仅只读资源状态记录，未再运行runtime动作。

`.superpowers/browser-authorized-logs/resource-final.log`记录owned PG仍healthy、卷保留，58111/58112无监听。代码/测试未变，原residual scoped批准及make2302/frontend600结果仍是上轮结果，不声称本轮重跑。先前历史证据、两个冻结archive、所有受控测试记录保留。

**最终专用gate仍BLOCKED**。直接用户授权已由coordinator收到，但执行权限仍未放行；不能用parent执行同一动作、API/test替代或改入口来绕过。用户后续提交/推送的条件尚未达成，本worker不暂存/提交/推送/部署/清理资源。原F1/F2独立代码复审通过不等于真实browser gate通过。

## 退出Auto Mode后的真实专用验收 — 2026-11-08（PASS-NOTE；待test-only delta独立复审）

用户“已切换继续”后实际执行权限模式改变，此次获准启动；先前拒绝记录原样保留，不追溯改成通过。使用新日志 `.superpowers/browser-mode-exit-logs/`、新tag `mode-exit-a/b/c`，不覆盖旧证据。实际worktree story/skill均02.18 v6（2026-11-03），使用匹配副本；工具解析原checkout旧v4未采用。

### 真实环境与本轮边界

- 仅owned `openqms-characteristic-test-pg`，127.0.0.1:55432/qms_test，task/worktree/purpose标签核对。双DATABASE_URL/TEST_DATABASE_URL在app import前显式设置；原VENV只读复用。没有私密env复制、整栈Compose/reset、seed入口、业务DB/5432或外部AI/共享Neo4j。
- 本worktree backend69889@58111（uvicorn lifespan off、GRAPH_REPOSITORY=jsonb、空LLM/provider配置），frontend70177@58112，独立CP worker69553。`owned-processes.log`核对command/cwd。专用config严格URL/tag/worker要求不改；spec每次STOP/CONT前验证该worker命令/cwd，仅暂停自己的PID。
- guarded bootstrap创建全新factory/PL及不同editor/approver，原有账号/权限不改；API只作声明过的draft结构/失效链前置、正常创建/返工/审批/回读，未直写approved、version/hash或wizard_completed=true。只有可选recommend请求被abort，核心业务请求不fulfill/mock。正常guards全程开启；未跑full pytest负面fixture来制造业务成功。

### 本轮实际运行、失败与两项窄test-mechanics修正

| 证据 | 实际结果 |
|---|---|
| `dedicated-collection.log/.exit` | strict owned config真实collection **3 tests/1 file，exit0**，不复用旧blocked list。 |
| `browser-a.log/.exit` | **2 passed/1 failed，42.7s，exit1**。完整PFMEA/CP/partial/deletion及DFMEA已通过；第三场景在draft API前置因两次PFMEA共用document_no被真实400拒绝。failure PNG实际LOOK是登录前白页，明确不算tree验收成功。 |
| label修正 | draft helper增加独立label参数、TREE场景使用PFMEA-TREE，fmea_type仍PFMEA。`fixture-label-red.log/.exit=1` **1 failed/8 passed**；最小修正后 `fixture-label-green.log/.exit=0` **9 passed**。不改生产重复编号校验、不放宽断言。 |
| `browser-b.log/.exit` | **3 passed，54.8s，exit0**，完整tree实际save/reload成功。LOOK17图contact sheet发现post-deletion screenshot仍在loader；API成功不等于画面就绪，该单张不作为成功UI证据。 |
| readiness修正 | 只在reload screenshot前等待API已确认存在的四行特性输入实际visible，不加sleep/timeout、不改生产加载代码。`reload-readiness-red.log/.exit=1` **1 failed/9 passed**；修正后 `reload-readiness-green.log/.exit=0` **10 passed**。 |
| **`browser-c.log/.exit`** | **最终3 passed/0 failed/skipped，45.8s，exit0**；PFMEA36.3s、DFMEA3.5s、tree4.4s。新tag重跑全部，不用b运行替代修正后的验证。 |
| `vitest-final.log/.exit` | test-only delta后全量 **602 passed/77 files，71.27s，exit0**，maxWorkers2、timeouts/assertions不变。中间601/77也保留，不混为最终数。 |
| `tsc-final.log/.exit` | **tsc --noEmit exit0**。生产/backend未变，未无谓重跑整套backend；前轮make2302/5skip/5xfail/0xpass与build仍是最后完整baseline，明确不是本轮新跑。 |

精确独立复审补丁 `mechanics-only.patch`、checksum `mechanics-checksums.json` 对本次启动前保存的spec/mock-test快照生成；仅上述两个test文件，没有production修改、guard/API/timeout变更。两个新增static回归不冒称真实行为证明；真正行为证明是最终c全场景执行及截图。当前test-only delta仍待coordinator独立复审，不自我批准/提交。

实际命令摘要（每条均在本worktree相应目录；双URL已显式owned55432，认证不打印；69553是本次已停止的实际PID，后续不可照抄）：

```sh
# backend cwd，原只读VENV，task-test SECRET_KEY/PYTHONPATH=.
GRAPH_REPOSITORY=jsonb LLM_PROVIDER= LLM_API_KEY= EMBEDDING_PROVIDER= E2E_MODE=false TENANT_MODE=single \
  "$VENV/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 58111 --lifespan off
"$VENV/bin/python" -m app.services.cp_sync_worker
CHARACTERISTIC_RUN_TAG=mode-exit-c "$VENV/bin/python" -m tests.e2e.characteristic_bootstrap
# frontend cwd
BACKEND_URL=http://127.0.0.1:58111 npm run dev -- --host 127.0.0.1 --port 58112 --strictPort
CHARACTERISTIC_RUN_TAG=mode-exit-c CHARACTERISTIC_WORKER_PID=69553 \
 CHARACTERISTIC_PYTHON="$VENV/bin/python" CHARACTERISTIC_UI_URL=http://127.0.0.1:58112 \
 CHARACTERISTIC_API_URL=http://127.0.0.1:58111 \
 npx playwright test --config=playwright.characteristic.config.ts
npm test -- --run --maxWorkers=2
npx tsc --noEmit
npx playwright test --list # 默认无CHARACTERISTIC环境
```

最终普通discovery另跑`default-collection.log/.exit=0`，仍42 tests/16 files。实际启动顺序为worker→backend/frontend→bootstrap→strict collection→browser，不执行共享global setup/reset。关闭后`resource-final.log`确认无监听/旧PID，两个冻结archive checksum不变。

### 最终c的真实覆盖（UI/API证据边界）

1. 同工序PFMEA功能分析真实UI录入2产品＋3过程、关系/单位/稳定UUID，save/reload；legacy提示仅参考、不自动转换，CC/SC不按kind伪造。
2. 真实向导完成→不同授权actor正常提交/批准，v1–v4四次批准与hash verify全true。API审批而非声称点击了审批按钮；graph/失效链是API前置，五特性及wizard完成是实际UI。
3. 实际批准版本选择/preview/import，五独立CP行、标准栏目、criteria含单位；普通UI本地准则覆盖＋实际no-op ACK API保留手工值。干净CP无drawer入口，ACK明确标为API，不发明UI入口。
4. 真实CP锁更新→409→明确重新预览，partial接受一项后pending/旧逐行基线仍正确；后续显式预览完成，UUID/手工执行字段保持。v1导入及v3完整sync都先于延迟worker交付，释放后不重pending，按确切event只读查completed。真正v2 worker-first产生通知。
5. 批准v3事件**已消费后才创建新CP**，仅初次导入1/5，partial notice显式关闭→reload看到一行＋黄色pending banner/“立即同步”；再预览剩4完成。未导入行不伪造accepted baseline。
6. 源正常rework→通过真实功能向导删无执行/无特殊保护的吸嘴真空度→新批准v4。新CP实际drawer deletion默认unchecked且enabled，明确check/confirm→reload四行和pending=false，截图等实际四行输入可见后拍摄。原五行CP的manual execution保护保留，见下方最终状态，不混称两个CP都已接受v4删除。
7. 真实历史snapshot只读、无新增入口；DFMEA共享ProcessWorkElementFunction只有product入口，save/reload仍product。
8. TREE独立草稿先合法完成wizard，再主编辑器删除产品function；最后确认前显示surviving force关系影响，确认后普通save/reload成功。存活process UUID不变、关联[]由API核对；实际survivor UI从功能向导查看，不虚称无失效行时主表会生成特性卡。共享控制删除规则另由既有单元/事务覆盖，不冒称该单功能截图覆盖了所有共享节点排列。

### 实际截图LOOK、console与证据路径

最终c证据：`frontend/e2e/.storage-state/characteristic-mode-exit-c-81449-evidence.json`。17张PNG均在 `frontend/e2e/.storage-state/8e979521-mode-exit-c-*.png`；全部在 `run-c-look.png` contact sheet实际LOOK，另原尺寸读取：worker-first-partial-reload、applicable-deletion-selected、applicable-deletion-reloaded、tree-deletion-impact-confirmation、tree-deletion-save-reload。非空白：一行pending入口、v4删除候选、四行最终CP（无banner/loader）、删除前具体影响确认和save/reload后的surviving force/空关系均可见。其他图可见五特性、五行导入/单位、真实409/partial、late worker、snapshot只读与DFMEA product。现有fixed-header/列宽裁切不重设计；输入/API断言核对完整值。

c三个pageerror均0；console.error条数 **12/2/5**，全部为既有React findDOMNode/StrictMode、Ant Input addonBefore/static message/Modal context弃用warning及核心场景预期409一条；原始stack保留JSON，不声称无warning。Playwright CLI module.register弃用保留。b的17图contact sheet与a白页failure也实际LOOK，识别出的loader证据问题保留不覆盖。

### Read-only审计与保留资源

`resource-audit.json/.log/.exit=0`先严格校验双owned URL再SET TRANSACTION READ ONLY，只查询三组新factory。a/b/c各4个真实approve版本及4个completed outbox，合计12/12；各API hash proofs全true。已批准文档created_by与approved_by不同且approved_at非空。四个hash/no_update triggers最终均O，临时schema与迁移DB0；未禁用guard或修改审计/历史。

- c run `8e979521`，factory `b810ec7a-a191-4928-8b62-d06aa641ca7b`，PL `T11-8e979521`。core PFMEA `9e2c41b5-5146-4935-b0fe-1f6019bb2ac0`（最终approved v4）、DFMEA `1f896aa6-6d44-4e32-85a1-59465c97fcf8`（draft）、TREE PFMEA `00c7eabf-ba37-4efe-b5d3-3af98d2d5007`（draft）；ordinarySC `77cb0d4c-277c-4f6f-85bc-11cc8abefad4`。
- c原CP `027168bf-9883-4a61-b91f-b6ee92584088` 保留五行/手工执行字段，最终因v4新增的删除义务pending=true（正常保守保护，没有静默删除）；新partial CP `58e225e7-5be3-4b7b-a45d-4ff6d36b61b8` 最终四行、marker v4、pending=false；其未改源行仍真实accepted v3，不伪造升级到v4。
- 每组原CP只有v2/v4两个真实false→true通知，新partialCP只有v4一次；v1/v3晚到不重开，通知changed_fields始终仅sync_pending+trigger_fmea_version_id。a/b的最终同类状态也完整记录，不清理失败运行的合法历史。
- 三组factory/PL、6actors/roles及8FMEA/6CP/3ordinarySC与正常审计/版本保留；没有任意force-delete。认证只在ignored测试manifest/auth，不打印、暂存或提交。没有embedding/graph外部worker、fake embedding或全局队列清空。
- 结束核对command/cwd和state后仅SIGTERM自己的worker69553/backend69889/frontend70177，worker已恢复S状态；143为主动停服，不算gate失败。PG/volume保留，最终端口/资源状态见`resource-final.log`。无暂存/提交/推送/合并/部署/外部发布；parent在本轮窄test delta独立复审和自己的最终验证后决定条件提交/推送。

**结论：先前权限阻塞在本轮已合法解除，专用真实gate最终PASS-NOTE，不再UNRUN。** 这是上述特性专项范围，不是全AI/provider/CSR/PPAP/scanner/liveNeo4j或故事全部历史能力认证。production F1/F2复审已批准，本轮没有新生产缺陷/变更。

协调者核对browser-c、全量Vitest、tsc、default collection及read-only audit的原始退出码均0，并实际查看最终17图contact sheet；两文件test-mechanics delta独立scoped复审APPROVE，无Critical/Important/Minor。原五行CP的pending和保留内容仅证明仍有未接受工作，不单独证明曾发起删除并被保护检查拒绝；真正显式删除成功的运行证明属于另一个partial-import CP，保护拒绝另由既有定向回归覆盖。提交前协调者另行完整重跑make check，实际结果单独记录；没有以旧backend日志冒称新跑。用户仅授权完成后提交推送当前分支，未授权合并或部署。


### 提交前协调者最终完整验证

`parent-final-make.log/.exit`（同一owned55432 qms_test，完整make check）实际exit0：**2302 passed、5 skipped、5 xfailed、0 xpassed、3 warnings，280.36s**；随后tsc及Vite build通过（9.29s）。这是最终两处test-only修正后的新跑结果，不复用旧baseline。全量前端602/77、browser-c3/3、最终窄测试复审批准及截图LOOK事实见上节。用户授权提交推送当前功能分支；不创建PR、不合并、不部署，不清理受控测试证据或PG卷。提交范围113个功能文件，排除仅携带的architecture-maintenance.md、认证/截图/日志及scratch。
