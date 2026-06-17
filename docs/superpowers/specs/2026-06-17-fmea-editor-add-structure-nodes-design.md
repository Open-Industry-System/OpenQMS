# FMEA 编辑器左侧树内联添加结构/功能节点 — 设计

日期: 2026-06-17
分支: fix/dashboard-kpi-cards-truncation

## 问题

PFMEA/DFMEA 编辑页「失效分析」Tab 左侧"工序功能/结构功能"树,唯一按钮是「添加行」(`addRow`),它只在已选功能节点下新增失效分析行(FailureMode/Effect/Cause/Control),**不创建工序/功能节点本身**。

- PFMEA 无 wizard(仅 DFMEA 有)。新建 PFMEA 时后端只塞一个 `ProcessItem` 根节点(`fmea_service.py:117`),用户落地后无法手动加 ProcessStep / ProcessWorkElement / Function → 卡死。
- 「结构分析」Tab 的 `StructureTree` 组件被硬编码为 DFMEA 专用(`STRUCTURE_TYPES = ["System","Subsystem","Component"]`,按钮文案「添加系统」),对 PFMEA 过滤为空,无法加 PFMEA 节点。

## 范围

在「失效分析」Tab 左侧树的结构节点上增加**内联 `+` 下拉**,让 PFMEA 与 DFMEA 都能直接添加结构子节点和功能节点。`StructureTree.tsx`(结构分析 Tab)、`addRow` 语义、wizard 均不动 —— 外科式修改。

> 本设计是**扩展现有编辑器能力**,不是复刻 seed 或 wizard。seed 与 wizard 只覆盖了部分层级的节点/边组合(见下文),本设计把可加结构/功能的能力补齐到所有层级。

## 图谱模型与扩展说明

PFMEA/DFMEA 共用边类型与节点类型。结构链:

- ProcessItem/System —`HAS_PROCESS_STEP`→ ProcessStep/Subsystem —`HAS_WORK_ELEMENT`→ ProcessWorkElement/Component

功能挂接 —`HAS_FUNCTION`→ 按父层级映射的功能节点类型:

| 父结构节点 | 功能节点类型 |
|---|---|
| ProcessItem / System | ProcessItemFunction |
| ProcessStep / Subsystem | ProcessStepFunction |
| ProcessWorkElement / Component | ProcessWorkElementFunction |

> **关于 DFMEA 功能映射**:seed 示例只给了 `Subsystem→ProcessStepFunction`、`Component→ProcessWorkElementFunction`,**没有 System→ProcessItemFunction**;wizard(`DFMEAWizardPage.tsx:216`)也只给 Component 加 `ProcessWorkElementFunction`。本设计**扩展**为三个结构层级(ProcessItem/System、Step/Subsystem、WorkElement/Component)都允许挂功能节点。这是编辑器的新增能力,不强制与 seed/wizard 的既有示例一一对应。

## 关键决策

### D1: 左侧改为按 edges 构建的真树

当前 `FMEAEditorPage.tsx:1208` 是 `functionNodes.map` 平铺,缩进按 `node.type` 硬算,不看 edges。多分支 PFMEA/DFMEA 会错位,新增节点若仅 append 也会错位。

**改法**:左侧结构/功能区域改为**按 edges 构建**的树形渲染:从根(`ProcessItem`/`System`)沿 `HAS_PROCESS_STEP` → `HAS_WORK_ELEMENT` 遍历结构节点,每个结构节点下沿 `HAS_FUNCTION` 挂其功能子节点。缩进由树深度决定,不再由 type 推断。新增子节点天然落到父子树内,显示正确。

(无结构根的边界情况——例如历史数据缺根——退化为按现有平铺顺序展示,保证不报错。)

### D2: addRow 语义保留兼容(方案 B)

当前 `fmeaTable.ts:29` 的 `FUNCTION_NODE_TYPES` 把结构节点(ProcessItem/Step/WorkElement、System/Subsystem/Component)也当作可挂 FailureMode 的 header,`FMEAEditorPage.tsx:235` firstFn 选取同理。即 **addRow 对结构节点也生效**(FailureMode 直接 `HAS_FAILURE_MODE` 挂到结构节点)。

**决策:保留此兼容行为,不改变。** 结构节点和功能节点都可被选中并 addRow;功能节点是结构树的叶子(它本身不再加结构子节点),但失效分析行既可挂在功能节点也可挂在结构节点下。文档明确此点,避免"功能节点是叶子→其下才有失效行"的误导。

## 交互设计

结构节点上显示 `+` 下拉(仅 `canEdit('fmea')`),菜单按父节点类型决定可加子项:

| 父节点 | 菜单项 | 新节点 | 边类型 |
|---|---|---|---|
| ProcessItem / System | + 工序 / + 子系统 | ProcessStep / Subsystem | `HAS_PROCESS_STEP` |
| ProcessItem / System | + 功能 | ProcessItemFunction | `HAS_FUNCTION` |
| ProcessStep / Subsystem | + 工作要素 / + 组件 | ProcessWorkElement / Component | `HAS_WORK_ELEMENT` |
| ProcessStep / Subsystem | + 功能 | ProcessStepFunction | `HAS_FUNCTION` |
| ProcessWorkElement / Component | + 功能 | ProcessWorkElementFunction | `HAS_FUNCTION` |

功能节点是叶子,不显示 `+`(其下及同级结构节点下的失效分析行仍由顶部「添加行」创建,见 D2)。

## 新建表单

复用 `StructureTree` 的 Modal 模式。字段:

- 名称(必填)
- 规范 specification(选填)
- 要求 requirement(选填)

> `GraphNode` 同时有 `requirement` 与 `specification`(`types/index.ts:55`),数据模型允许并存(seed `psf_1` 两者都有)。Modal 提供两个独立字段,直接写入对应属性,不按节点类型二选一。

保存:
- 生成 `id = n${Date.now()}_${rand}`,severity/occurrence/detection 初始 0。
- 追加到 `nodes`,加对应 `edge`(`source`=父, `target`=新节点, `type`=上表边类型)。
- 若新建的是功能节点,自动 `setSelectedFunctionId(新id)`,便于紧接着「添加行」。

## 实现位置(全部在 `FMEAEditorPage.tsx`)

- 提取两个小 helper,避免巨大页面里内联条件变脆:
  - `STRUCTURE_CHILD_MAP`: 父 type → `{ childType, edgeType, labelKey }`,覆盖上表四类(结构子节点 / 功能节点 × 三层级)。
  - `functionTypeFor(parentType)`: 父结构 type → 对应功能节点 type。
- 新增 `addStructureChild(parentNode, childKind)` 回调 + Modal state。
- 在树节点 render 加 `Dropdown` 触发器。
- 左侧树渲染改用按 edges 构建的递归(D1)。

## i18n

`fmea.json` 新增键(zh-CN + en-US):`editor.addStep` / `addWorkElement` / `addFunction` / `addSubsystem` / `addComponent` 及 Modal 标题/字段(`specification` / `requirement`)。

## 不做(YAGNI)

- 不加根节点兄弟新增(后端已建一个根)。
- 不改 `addRow` 语义(D2 保留兼容) / `StructureTree` / wizard。
- 不限制单节点功能数。

## 验证

- `npm run build`(tsc + vite)通过。
- 手动单链:新建 PFMEA → 左侧树加工序→工作要素→功能 →「添加行」→ 保存 → 重开确认图谱持久化。
- 同样验证 DFMEA(System→Subsystem→Component→Function)。
- **多分支**:两个 ProcessStep(或两个 Subsystem)下分别添加 WorkElement/Function,确认:显示层级正确(按 edges 排布不串位)、选中目标正确、保存后重开仍正确。
- 结构节点直接 addRow(方案 B 兼容)仍可用:在 ProcessStep 上直接「添加行」,确认不回归。
