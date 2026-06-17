# FMEA 编辑器左侧树内联添加结构/功能节点 — 设计

日期: 2026-06-17
分支: fix/dashboard-kpi-cards-truncation

## 问题

PFMEA/DFMEA 编辑页的「失效分析」Tab 左侧"工序功能/结构功能"树,唯一的按钮是「添加行」(`addRow`),它只在已选功能节点下新增失效分析行(FailureMode/Effect/Cause/Control),**不创建工序/功能节点本身**。

- PFMEA 无 wizard(仅 DFMEA 有)。新建 PFMEA 时后端只塞一个 `ProcessItem` 根节点(`fmea_service.py:117`),用户落地后无法手动加 ProcessStep / ProcessWorkElement / Function → 卡死。
- 「结构分析」Tab 的 `StructureTree` 组件被硬编码为 DFMEA 专用(`STRUCTURE_TYPES = ["System","Subsystem","Component"]`,按钮文案「添加系统」),对 PFMEA 过滤为空,无法加 PFMEA 节点。

## 范围

在「失效分析」Tab 左侧树的结构节点上增加**内联 `+` 下拉**,让 PFMEA 与 DFMEA 都能直接添加结构子节点和功能节点。`StructureTree.tsx`(结构分析 Tab)、`addRow` 语义、wizard 均不动 —— 外科式修改。

## 图谱模型(来自 seed,PFMEA/DFMEA 共用边类型)

- 结构链: ProcessItem/System —`HAS_PROCESS_STEP`→ ProcessStep/Subsystem —`HAS_WORK_ELEMENT`→ ProcessWorkElement/Component
- 功能挂接: 任一结构节点 —`HAS_FUNCTION`→ 对应层级 Function 节点
  - ProcessItem/System → ProcessItemFunction
  - ProcessStep/Subsystem → ProcessStepFunction
  - ProcessWorkElement/Component → ProcessWorkElementFunction

## 交互设计

结构节点上显示 `+` 下拉(仅 `canEdit('fmea')`),菜单按父节点类型决定可加子项:

| 父节点 | 菜单项 | 新节点 | 边类型 |
|---|---|---|---|
| ProcessItem / System | + 工序 / + 子系统 | ProcessStep / Subsystem | `HAS_PROCESS_STEP` |
| ProcessItem / System | + 功能 | ProcessItemFunction | `HAS_FUNCTION` |
| ProcessStep / Subsystem | + 工作要素 / + 组件 | ProcessWorkElement / Component | `HAS_WORK_ELEMENT` |
| ProcessStep / Subsystem | + 功能 | ProcessStepFunction | `HAS_FUNCTION` |
| ProcessWorkElement / Component | + 功能 | ProcessWorkElementFunction | `HAS_FUNCTION` |

功能节点是叶子,不显示 `+`;其下失效分析行仍由顶部「添加行」创建。

## 新建表单

复用 `StructureTree` 的 Modal 模式:名称(必填)+ 规范/要求(选填)。保存:
- 生成 `id = n${Date.now()}_${rand}`,severity/occurrence/detection 初始 0。
- 追加到 `nodes`,加对应 `edge`。
- 若新建的是功能节点,自动 `setSelectedFunctionId(新id)`,便于紧接着「添加行」。

## 实现位置(全部在 `FMEAEditorPage.tsx`)

- 新增 `addStructureChild(parentNode, childKind)` 回调 + Modal state。
- 在树节点 render(约 1217–1253 行)加 `Dropdown` 触发器。

## i18n

`fmea.json` 新增键(zh-CN + en-US):`editor.addStep` / `addWorkElement` / `addFunction` / `addSubsystem` / `addComponent` 及 Modal 标题/字段。

## 不做(YAGNI)

- 不加根节点兄弟新增(后端已建一个根)。
- 不改 `addRow` / `StructureTree` / wizard。
- 不限制单节点功能数。

## 验证

- `npm run build`(tsc + vite)通过。
- 手动:新建 PFMEA → 左侧树加工序→工作要素→功能 →「添加行」→ 保存 → 重开确认图谱持久化。
- 同样验证 DFMEA(System→Subsystem→Component→Function)。
