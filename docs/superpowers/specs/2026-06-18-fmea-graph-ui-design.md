# FMEA 图谱轻量 UI 优化设计

日期：2026-06-18

## 背景

当前 FMEA 图谱页面在中文界面中仍直接显示英文节点/边枚举，例如 `HAS_PROCESS_STEP`、`AS_FUNCTION`、`EFFECT_OF`、`CAUSE_OF`。同时截图显示边标签压在线上、节点颜色和形状观感较粗糙、画布层级间距不足，影响中文用户理解图谱关系。

本次目标是做轻量修复：中文化图谱展示，并改善现有图谱视觉可读性；不更换图谱库，不重做图谱工作台。

## 目标

1. 图谱画布、图例、详情抽屉中的节点类型和边关系跟随当前语言展示。
2. 中文界面不再直接暴露已知英文节点/边枚举。
3. 英文界面继续显示英文术语，不被硬编码中文破坏。
4. 边标签清晰可读，不再直接贴在线上造成重叠。
5. 节点样式更统一，保留不同 FMEA 语义类型的颜色区分。
6. 保持现有缩放、适配视图、布局切换、节点详情功能不变。
7. 不改变后端 graph 数据结构和节点/边原始枚举。

## 非目标

- 不新增筛选面板、右侧工作台或复杂交互。
- 不更换图谱渲染库。
- 不调整 FMEA 编辑器的数据结构。
- 不改变枚举入库格式。
- 不处理跨 FMEA 知识图谱总览页的产品功能改版，只修图谱可视化展示层。

## 现有代码约束

- `GraphCanvas` 当前直接使用 `n.label` / `e.label` 生成 G6 节点类型和边标签；已知枚举缺失时会回退为默认样式或英文。
- `GraphLegend` 当前通过 `useTranslation("graph")` 使用 locale 文案，不能改成硬编码中文。
- 已有 PFMEA/DFMEA 图谱不只使用通用 `Function`，还使用 `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`。
- DFMEA 向导还会使用 `Interface`、`DesignParameter` 和 `HAS_PARAMETER`。
- 后端 Neo4j 投影白名单包括 `HAS_FUNCTION`，前端结构树也使用 `HAS_FUNCTION`。

## 中文化和 i18n 规则

新增 `frontend/src/utils/graphPresentation.ts`，但它只集中管理展示配置和翻译 key，不返回硬编码中文。

建议导出内容：

- `NODE_PRESENTATION`：节点类型到颜色、形状/尺寸、翻译 key 的映射。
- `EDGE_PRESENTATION`：边类型到翻译 key 的映射。
- `getNodeTypeKey(type: string)`：返回 `graph.nodeTypes.*` key；未知类型回退原始值。
- `getEdgeTypeKey(type: string)`：返回 `graph.edgeTypes.*` key；未知类型回退原始值。
- `getNodeStyle(type: string)`：返回节点颜色、边框、尺寸等样式；未知类型返回默认样式。

展示文案必须通过 `t()` 解析：

```ts
t(getNodeTypeKey(type), { defaultValue: type })
t(getEdgeTypeKey(type), { defaultValue: type })
```

因此需要在：

- `frontend/src/locales/zh-CN/graph.json`
- `frontend/src/locales/en-US/graph.json`

新增 `nodeTypes.*`、`edgeTypes.*`。现有 `legend.*` 可以继续保留，但实现时应尽量复用同一组节点配置，避免图例和画布各维护一份类型列表。

## 节点类型文案

### zh-CN

| 原类型 | 中文显示 |
|---|---|
| `System` | 系统 |
| `Subsystem` | 子系统 |
| `Component` | 零部件 |
| `ProcessItem` | 过程项 |
| `ProcessStep` | 工序 |
| `ProcessWorkElement` | 工作要素 |
| `Function` | 功能 |
| `ProcessItemFunction` | 过程项功能 |
| `ProcessStepFunction` | 工序功能 |
| `ProcessWorkElementFunction` | 工作要素功能 |
| `FailureMode` | 失效模式 |
| `FailureEffect` | 失效影响 |
| `FailureCause` | 失效原因 |
| `PreventionControl` | 预防控制 |
| `DetectionControl` | 探测控制 |
| `RecommendedAction` | 建议措施 |
| `Interface` | 接口 |
| `DesignParameter` | 设计参数 |

### en-US

英文 locale 使用对应业务英文：`Process Item`、`Work Element`、`Process Item Function`、`Process Step Function`、`Work Element Function`、`Recommended Action`、`Interface`、`Design Parameter` 等。

未知节点类型在 zh-CN/en-US 下都显示原始枚举值。

## 边关系文案

### zh-CN

| 原关系 | 中文显示 |
|---|---|
| `HAS_PROCESS_STEP` | 包含工序 |
| `HAS_WORK_ELEMENT` | 包含工作要素 |
| `WORK_IN` | 包含工作要素 |
| `HAS_FUNCTION` | 包含功能 |
| `AS_FUNCTION` | 定义功能 |
| `FUNCTION_MAPPED_TO` | 定义功能 |
| `HAS_PARAMETER` | 包含参数 |
| `HAS_FAILURE_MODE` | 导致失效 |
| `EFFECT_OF` | 产生影响 |
| `CAUSE_OF` | 由原因引起 |
| `PREVENTED_BY` | 预防控制 |
| `DETECTED_BY` | 探测控制 |
| `OPTIMIZED_BY` | 优化措施 |
| `HAS_NODE` | 包含节点 |
| `HAS_CHILD` | 包含子项 |

### en-US

英文 locale 使用可读短语而不是下划线枚举，例如：`Has Process Step`、`Has Work Element`、`Has Function`、`Defines Function`、`Has Parameter`、`Has Failure Mode`、`Effect Of`、`Cause Of`、`Prevented By`、`Detected By`、`Optimized By`。

未知边类型在 zh-CN/en-US 下都显示原始枚举值。

## 视觉设计

### 节点

- 统一使用圆角矩形作为默认节点形态，减少截图中多种形状混用造成的噪音。
- 语义颜色保持区分：
  - 系统/过程项/工序：蓝色系。
  - 子系统/零部件/工作要素：青色系。
  - 功能类节点：绿色系。
  - 失效模式：红色强调。
  - 失效影响/失效原因：橙黄色系。
  - 控制/措施：绿紫灰色系。
  - 接口/设计参数：紫色/蓝色系。
- 节点增加细边框、轻阴影、适度内边距。
- 节点文字居中，过长名称必须限制在节点宽度内，最多 2 行，超出显示省略号，不改变原始数据。
- 对 `FailureMode` 可保留轻微强调色，但不再使用过于突兀的菱形作为默认形态，优先保证整体整洁。

G6 v5 目标节点 label 参数：

```ts
node: {
  style: {
    labelText: translatedOrRawNodeName,
    labelFontSize: 12,
    labelFill: "#1f2937",
    labelPlacement: "center",
    labelTextAlign: "center",
    labelWordWrap: true,
    labelMaxWidth: 120,
    labelMaxLines: 2,
    labelTextOverflow: "ellipsis",
  },
}
```

如果当前 G6 版本或类型定义不支持 `labelMaxWidth`，则使用其兼容属性 `labelWordWrapWidth: 120`。如果两者表现不同，优先采用实际能在浏览器中限制文本宽度的属性，并在实现记录中说明。

### 边

G6 v5 目标样式参数：

```ts
edge: {
  type: "line",
  style: {
    stroke: "#9aa7b8",
    lineWidth: 1,
    endArrow: true,
    labelText: translatedEdgeLabel,
    labelFontSize: 11,
    labelFill: "#4b5563",
    labelPlacement: "center",
    labelOffsetY: -4,
    labelPadding: [2, 6],
    labelBackground: true,
    labelBackgroundFill: "#ffffff",
    labelBackgroundFillOpacity: 0.92,
    labelBackgroundRadius: 4,
  },
}
```

如果当前 G6 版本或类型定义不支持部分 label background 属性，则 fallback 为：

1. 保留中文边标签。
2. 使用更浅边线 `#b6c2d1`。
3. 设置 `labelOffsetY: -4` 或 `labelOffsetY: -6`。
4. 保持 `labelFontSize: 11`，避免回退到截图中的小灰字。

### 布局和画布

- 单个 FMEA 默认 `dagre` 布局保持 `rankdir: "LR"`。
- `dagre` 候选参数：

```ts
layout: {
  type: "dagre",
  rankdir: "LR",
  nodesep: 70,
  ranksep: 110,
  controlPoints: false,
  animation: true,
}
```

- 非 dagre 布局保持现有布局类型，但不强塞 dagre-only 参数。
- 画布背景使用浅灰色，减少纯白大面积留白感。
- 图例继续以小卡片方式呈现，但节点类型来自同一配置和 i18n key。

## 实现方案

1. 新增 `frontend/src/utils/graphPresentation.ts`，集中维护节点/边展示配置、样式和翻译 key。
2. 在 `frontend/src/locales/zh-CN/graph.json` 和 `frontend/src/locales/en-US/graph.json` 增加 `nodeTypes.*`、`edgeTypes.*`。
3. 更新 `GraphCanvas`：
   - 接入 `useTranslation("graph")`。
   - 将边 label 从原始枚举转换为 `t(edgeTypes.*)`。
   - 用 `getNodeStyle()` 设置节点样式。
   - 用 G6 label background / offset / padding 优化边标签可读性。
   - 为 dagre 布局增加明确的 `nodesep`、`ranksep`。
4. 更新 `GraphLegend`：
   - 从 `graphPresentation.ts` 读取节点类型列表和颜色。
   - 文案使用 `nodeTypes.*`，不要再维护独立且不完整的 `legend.*` 类型列表。
5. 更新 `NodeDetailDrawer`：
   - 节点类型显示使用 `nodeTypes.*`，不要直接显示原始英文枚举。
   - 与画布、图例使用同一个 `getNodeTypeKey()` / `t()` 路径，保证语言切换后三处同步。
   - 仅节点 ID 保持原始值；节点类型不能再直接渲染 `node.label`。
6. 补充单元测试覆盖：
   - 已知节点类型都有翻译 key。
   - 已知边类型都有翻译 key。
   - 未知节点/边类型回退原值。
   - 样式函数对新增类型 `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`、`Interface`、`DesignParameter` 不回退默认样式。

## 验证标准

- 前端构建通过。
- 图谱展示配置测试通过。
- 手动打开 FMEA 图谱页，确认：
  - zh-CN 下，画布边关系显示中文业务短语。
  - en-US 下，画布边关系显示英文业务短语，不显示硬编码中文。
  - 图例、画布、详情抽屉节点类型随语言切换一致变化。
  - 详情抽屉节点类型不再直接显示 `FailureMode` 等原始英文枚举。
  - 长节点名称最多 2 行，超出显示省略号，不横向溢出节点边界。
  - 已知类型 `ProcessItemFunction`、`ProcessStepFunction`、`ProcessWorkElementFunction`、`Interface`、`DesignParameter` 不再显示为默认样式或英文枚举。
  - 已知边 `HAS_FUNCTION`、`HAS_PARAMETER` 不再显示英文枚举。
  - 边标签可读，不明显压在线上。
  - 节点样式更统一，颜色仍能区分 FMEA 语义类型。
  - 缩放、适配视图、布局切换、节点点击详情仍可用。

## 风险和约束

- 如果 G6 label 背景属性在当前版本表现不符合预期，只做 fallback 样式，不引入自定义边渲染或更换图谱库。
- 对未知枚举回退原值，避免隐藏后端数据异常。
- 本次只处理展示层，不能修复复杂图在极端数据量下天然拥挤的问题。
