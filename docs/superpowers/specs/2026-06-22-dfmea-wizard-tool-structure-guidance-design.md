# DFMEA 向导：Step 0 工具驱动 Step 1 结构引导设计

- 日期：2026-06-22
- 分支：`fix/fmea-fixes`
- 状态：已与用户确认设计，待出实现计划
- 关联前置：`2026-06-20-dfmea-wizard-tool-trend-recommendations-design.md`（5T 工具/趋势推荐，已实现）

## 1. 背景与目标

DFMEA 向导 Step 0 的「工具」字段现仅作 5T 留档（存 `wizardScope.tool`，多选「、」分隔 string），不参与后续步骤。按 AIAG-VDA DFMEA 方法，所选分析工具应体现在后续结构创建中：边界图/接口矩阵 → 需创建 Interface 节点；P图/参数图 → 需创建 DesignParameter 节点。

目标：让 Step 0 选的「工具」在 Step 1 给出**针对性结构引导**，并在完成校验时**提示缺口**（警告，不阻塞完成），使分析过程符合质量体系对 DFMEA 创建步骤的要求。

**不改动**：「趋势」字段（保持纯 5T 留档）；Step 2-5 的生成逻辑（`dfmeaRules`）；✨AI 推荐按钮；孤儿组件 `GenerationWizard.tsx`；`canFinish` / 完成阻塞逻辑。

## 2. 现状

- `DFMEAWizardPage.tsx` Step 1（`renderStep1()`，约 213-304 行）支持 5 种结构节点：System / Subsystem / Component / Interface / DesignParameter，但仅暴露「+ 系统」「+ 接口」两个 `Button`——**DesignParameter 节点有类型但无创建入口**。`handleAddNode(type, parentId?)`（约 219 行）对 Interface 设 `interface_type: 'physical'`，其余走默认。
- `wizardScope.tool` 是「、」分隔 string；`parseScopeTokens`/`stringifyScopeTokens`（`utils/wizardScopeTokens.ts`，已实现）做 string↔string[]。
- `useWizardValidation(nodes, edges)`（`hooks/useWizardValidation.ts`）返回 `StepValidation { step3Complete, step4Complete, step5Complete, step5MissingCause, step5Unrated, warnings: number[] }`。**当前签名只接收 nodes/edges，不接收 wizardScope**——计算工具缺口需要所选工具，故需扩签名。
- Step 6 完成校验警告块在 `DFMEAWizardPage.tsx` 约 645-656 行（黄色 `#fff2f0` 块，列 `validation.warnings`）。
- `WizardGuidanceCard`（i18n 驱动 `wizard.guidance.stepN.*`）是现成引导位，但本设计的工具引导是**动态**的（依赖所选工具），更适合直接放 Step 1 内容区顶部，而非静态 guidance 卡。

## 3. 决策汇总（已与用户确认）

| 决策 | 选择 |
|---|---|
| 引导强度 | **提示 + 一键创建 + 完成校验缺口检查**（缺口仅警告，不阻塞 finish） |
| 映射范围 | **仅 3 个结构类工具**：边界图/接口矩阵 → Interface；P图/参数图 → DesignParameter。功能分析/FTA/DFMEA模板/历史经验教训库不映射 |
| 字段范围 | **仅「工具」字段**；「趋势」不动 |
| DesignParameter 入口 | **不加常驻按钮**；仅靠引导卡按需一键创建（YAGNI） |
| 映射表存放 | 放 **i18n**（`wizard.scope.toolStructureMap`），随语言切换 |

## 4. 工具→结构映射（i18n 配置驱动）

在 `wizard.scope` 下新增 i18n 对象 `toolStructureMap`（zh-CN + en-US 镜像），结构 `{ 工具存盘值: 节点类型 }`：

zh-CN `dfmea.json` `wizard.scope.toolStructureMap`：
```json
{
  "边界图": "Interface",
  "接口矩阵": "Interface",
  "P图/参数图": "DesignParameter"
}
```
en-US `dfmea.json` `wizard.scope.toolStructureMap`：
```json
{
  "Boundary Diagram": "Interface",
  "Interface Matrix": "Interface",
  "Parameter Diagram (P-Diagram)": "DesignParameter"
}
```

key 必须与 `toolPresets` 存盘值**逐字一致**（存盘值=所选语言文本，故映射随语言走、文案改了映射跟着走）。未在表中的工具不产生引导/不检查缺口。

## 5. 工具函数 `utils/wizardToolStructure.ts`（新增）

纯函数，依赖传入的映射表（i18n 取）+ 节点列表：

```ts
export type StructureNodeType = 'Interface' | 'DesignParameter';

/** 所选工具中、需要某 nodeType 的工具列表（去重保序）。 */
export function toolsRequiringNodeType(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodeType: StructureNodeType,
): string[];

/** 所选工具产生的结构缺口：工具→其要求的 nodeType，且该 nodeType 在图中数量为 0。 */
export function structureGapsForTools(
  selectedTools: string[],
  toolStructureMap: Record<string, string>,
  nodes: GraphNode[],
): Array<{ tool: string; nodeType: StructureNodeType }>;
```

- `toolsRequiringNodeType`：遍历 `selectedTools`，查表值===nodeType 的收集（去重保序）。
- `structureGapsForTools`：对每个所选工具，查表得 nodeType；若 `nodes.filter(n => n.type === nodeType).length === 0`，记 `{ tool, nodeType }`（同一 nodeType 多个工具可各记一条，便于 Step 6 文案点名具体工具；去重按 `tool`）。

## 6. Step 1 顶部：工具引导卡 + 一键创建

在 `renderStep1()` 顶部、现有 `<Space>…添加按钮</Space>` 之上，新增引导区。仅当选了结构类工具、且对应 nodeType 当前为 0 时显示。

```
┌─ 💡 根据所选分析工具 ────────────────────────────────┐
│ 你选了【接口矩阵】，建议为组件创建 Interface 节点，记录物理/信号/能量接口。 │
│                                          [+ 创建接口节点]            │
│ 你选了【P图/参数图】，建议创建 DesignParameter 节点，定义理想/非理想响应与控制因素。│
│                                       [+ 创建参数节点]              │
└──────────────────────────────────────────────┘
```

- 解析 `wizardScope.tool`：`parseScopeTokens(wizardScope.tool || '')`。
- 取映射表：`t('wizard.scope.toolStructureMap', { returnObjects: true }) as Record<string, string>`。
- 按 nodeType 分组渲染：对每个有缺口的 nodeType，取 `toolsRequiringNodeType(...)` 第一条工具名作文案主语，文案走 i18n `wizard.scope.toolGuide.<nodeType>`（`Interface` / `DesignParameter` 各一条），`+ 创建XX节点` 按钮文案走 i18n `wizard.scope.addInterfaceNode` / `addDesignParameterNode`。
- 一键创建：点击 → `handleAddNode(nodeType)`（Step 1 现有）。**`handleAddNode` 需兼容 DesignParameter**——当前仅对 Interface 设 `interface_type`，DesignParameter 走默认字段即可，无需改 `handleAddNode`（已兼容任意 type）。点击后节点加入，该 nodeType 计数变 1，引导行消失（重新渲染判定）。
- 引导卡样式：浅黄底 `#fffbe6`、圆角，与 Step 3 的 `#f6ffed` 推荐区风格呼应（黄=建议而非绿=自动）。

## 7. 完成校验缺口检查（Step 6，警告不阻塞）

### 7.1 扩展 `useWizardValidation` 签名

```ts
export function useWizardValidation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  selectedTools: string[],        // 新增：parseScopeTokens(wizardScope.tool)
  toolStructureMap: Record<string, string>,  // 新增：i18n 取
): StepValidation
```

`StepValidation` 新增字段：
```ts
structureGaps: Array<{ tool: string; nodeType: 'Interface' | 'DesignParameter' }>;
```
- 由 `structureGapsForTools(selectedTools, toolStructureMap, nodes)` 计算。
- **不加入 `warnings`**（不阻塞 finish、不强制）；`canFinish` 逻辑不变。
- `useMemo` 依赖加 `selectedTools`、`toolStructureMap`。

### 7.2 调用点更新

`DFMEAWizardPage.tsx` 约 47 行 `const validation = useWizardValidation(nodes, edges);` 改为传 4 参：
```ts
const toolStructureMap = t('wizard.scope.toolStructureMap', { returnObjects: true }) as Record<string, string>;
const selectedTools = parseScopeTokens(wizardScope.tool || '');
const validation = useWizardValidation(nodes, edges, selectedTools, toolStructureMap);
```
（`toolStructureMap`/`selectedTools` 可在组件顶层算一次；注意 `t` 在组件内已可用。）

### 7.3 Step 6 渲染缺口块

在现有完成校验警告块（约 645-656 行，红底 `#fff2f0`）**下方**新增黄色块（仅 `validation.structureGaps.length > 0` 时显示）：
```
⚠ 你选了【接口矩阵】但未创建任何 Interface 节点，建议补全以体现该分析方式。
⚠ 你选了【P图/参数图】但未创建任何 DesignParameter 节点，建议补全以体现该分析方式。
```
- 文案 i18n：`wizard.page.structureGap`，插值 `{tool}` / `{nodeType}`（nodeType 用 `wizard.typeLabels.Interface` / `DesignParameter` 翻译）。
- 用户仍可点 Finish（警告不阻塞）。

## 8. i18n 新增（zh-CN + en-US 镜像，`wizard.scope` 下）

- `toolStructureMap`（对象，见 §4）
- `toolGuide.Interface`：`"你选了【{{tool}}】，建议为组件创建 Interface 节点，记录物理/信号/能量接口。"`
- `toolGuide.DesignParameter`：`"你选了【{{tool}}】，建议创建 DesignParameter 节点，定义理想/非理想响应与控制因素。"`
- `addInterfaceNode`：`"+ 创建接口节点"`
- `addDesignParameterNode`：`"+ 创建参数节点"`

`wizard.page` 下新增：
- `structureGap`：`"你选了【{{tool}}】但未创建任何 {{nodeType}} 节点，建议补全以体现该分析方式。"`

## 9. 测试

- **`utils/wizardToolStructure.test.ts`**（新增）：
  - `toolsRequiringNodeType`：选 [边界图, P图/参数图] + nodeType=Interface → [边界图]；nodeType=DesignParameter → [P图/参数图]；去重保序；未映射工具不返回；空选→[]。
  - `structureGapsForTools`：选 [接口矩阵] + 无 Interface 节点 → [{tool:'接口矩阵', nodeType:'Interface'}]；有 Interface 节点 → []；未选结构类工具 → []；选 [边界图, 接口矩阵]（同 nodeType）+ 无 Interface → 两条缺口（各点名工具）。
- **`hooks/useWizardValidation.test.tsx`**（已存在，扩展）：
  - 选 [接口矩阵] + 无 Interface → `structureGaps` 含一条；有 Interface → 空；未选结构类工具 → 空。
  - `canFinish` / `warnings` 不受 `structureGaps` 影响（缺口不进 warnings、不阻塞）。
  - 签名变更：现有用例补 `selectedTools=[]`、`toolStructureMap={}` 两参以保持绿。
- **回归**：`npm test -- --run`（前端）。`npm run build`（tsc --noEmit）。

## 10. 范围边界（不动）

- 「趋势」字段；Step 2-5 生成逻辑（`dfmeaRules`）；✨AI 推荐按钮；`GenerationWizard.tsx`。
- `canFinish` / 完成阻塞逻辑（缺口仅警告）。
- DesignParameter 常驻按钮（仅引导卡按需）。
- `handleAddNode` 实现（已兼容任意 type，无需改）。

## 11. 风险与权衡

- **映射 key 与存盘值漂移**：若日后改 `toolPresets` 文案而忘改 `toolStructureMap`，映射静默失效。缓解：两者同处 `wizard.scope`，spec 注明 key 必须逐字一致；测试用真实 preset 文本做 key 断言。
- **缺口「误报」**：用户选了接口矩阵但确实不需要 Interface 节点（如纯功能分析）→ 持续黄警。可接受（仅警告不阻塞，且用户可忽略）；不引入「忽略该警告」开关（YAGNI）。
- **签名变更影响面**：`useWizardValidation` 现有调用点仅 `DFMEAWizardPage.tsx` 一处（已确认无其他调用方）；现有测试补参即可。
