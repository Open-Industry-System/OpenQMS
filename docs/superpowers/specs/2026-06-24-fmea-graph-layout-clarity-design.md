# FMEA 图谱层次布局清晰度修复 — 设计

**日期：** 2026-06-24
**分支：** worktree-fmea-graph-layout（并入 `fix/fmea-fixes`）
**范围：** PFMEA + DFMEA 图谱 Tab 的层次视图（dagre 布局）

## 问题

在两种 FMEA 的图谱层次视图中，**失效原因（FailureCause）与失效模式（FailureMode）之间的关系表达不清，上下逻辑混乱**。

根因是边方向的不对称（非布局算法问题）：

| 边类型 | 数据模型方向 | 层次语义 |
|---|---|---|
| `FUNCTION_MAPPED_TO` | Function → Function | 链向下 ✓ |
| `HAS_FAILURE_MODE` | Function/Step → FailureMode | 链向下 ✓ |
| `EFFECT_OF` | FailureMode → FailureEffect | 模式→效果（父→子）✓ |
| `CAUSE_OF` | **FailureCause → FailureMode** | 原因是源，模式是目标 ✗ |

在当前 dagre LR 布局下，`EFFECT_OF` 把效果放到模式右侧（下游），但 `CAUSE_OF` 把原因放到模式左侧（上游），与 Function/ProcessStep 同列。于是原因看起来像模式的"父输入"，而效果挂在右侧——这正是"上下逻辑混乱"。

约束（来自项目记忆 `[[dfmea-graph-shared-edge-enums]]`）：FMEA 图数据模型在 PFMEA/DFMEA 间共享边枚举，**数据模型不可改动**，修复须在呈现/布局层。

## 方案

方案 2：核心反转 + 分支样式化。

### 1. 核心修复：CAUSE_OF 边渲染时反转

**文件：** `frontend/src/components/graph/GraphCanvas.tsx`，`toG6Data`（约 47–63 行）。

构建 g6 边时，若 `rawLabel === "CAUSE_OF"`，交换 `source`/`target`，使视觉上 `FailureMode → FailureCause`（父→子），与 `EFFECT_OF` 一致。

- 边 ID 仍用原始 `e.source-e.target-rawLabel`（如 `fc_1-fm_1-CAUSE_OF`），保持稳定：React key、高亮逻辑不受影响。
- 边标签仍走 `getEdgeTypeKey("CAUSE_OF", fmeaType)` → "失效原因"；在 `mode→cause` 箭头上读作"这是该模式的失效原因"，语义通顺。
- `endArrow: true` 现指向 `cause`（父→子）。
- `PREVENTED_BY` / `DETECTED_BY` / `OPTIMIZED_BY` 方向本就 `cause/mode → control`（父→子），不动。
- 后端、数据模型、seed、其余边类型完全不动。

修复后层次（TB）：
```
        Function
           |
       FailureMode
        /       \
 FailureEffect   FailureCause ──┬── PreventionControl
                                ├── DetectionControl
                                └── RecommendedAction
```

### 2. 布局方向 + 工具栏 UX

**`graphLayoutOptions`（约 68–103 行）：** 增加方向参数 `graphLayoutOptions(layout, direction)`：
- `direction: "TB" | "LR"`，仅 dagre 使用。
- `TB` → `rankdir: "TB"`（新默认）；`LR` → `rankdir: "LR"`（保留现有）。
- TB 下微调 `nodesep`/`ranksep`（纵向更高、横向更窄，避免兄弟节点重叠）。
- `force` / `compact-box` 不受 `direction` 影响，保持原样。

**新类型：** `GraphDirection = "TB" | "LR"`，独立于现有 `GraphLayout = "dagre" | "force" | "compact-box"`（union 不改）。

**状态持有：** `FMEAEditorPage` 持有 `direction` 状态，默认 `"TB"`，传给 `GraphCanvas` 与 `GraphToolbar`。

**工具栏（`GraphToolbar.tsx`）：**
- "层次图"按钮改为 `Dropdown.Button`（图标 `ApartmentOutlined`），菜单两项：`从上到下 (TB)`（默认选中）、`从左到右 (LR)`。
- 仅当 `layout === "dagre"` 时该下拉启用并显示当前方向；选 force/compact-tree 时禁用，tooltip 提示"仅层次布局可用"。
- `Force`、`Compact-tree` 两个按钮保留不动。

### 3. 分支边样式 + 图例

**`toG6Data` 边样式：** 按 `rawLabel` 分类着色，替换当前统一的 `EDGE_STROKE`。颜色取自现有节点配色，保证深色 UI（`#14161d` 背景）可读：

| 边类型 | 颜色 | 说明 |
|---|---|---|
| `EFFECT_OF` | `#fa8c16` 橙，实线 | 效果分支 |
| `CAUSE_OF` | `#ff7875` 红粉，实线 | 原因分支，与橙区分 |
| `PREVENTED_BY` | `#73d13d` 绿，实线 | 预防控制 |
| `DETECTED_BY` | `#722ed1` 紫，实线 | 探测控制 |
| `OPTIMIZED_BY` | `#8c8c8c` 灰，实线 | 优化措施 |
| 其余结构链（`HAS_*`、`FUNCTION_MAPPED_TO` 等） | `EDGE_STROKE` 中性白 | 骨架 |

不加虚线——颜色即区分。`endArrow` 保留。高亮逻辑里把 `stroke` 覆盖为 `#ff4d4f` 的既有行为不变。

新增一个边颜色查找（可放 `graphPresentation.ts`，导出 `getEdgeStyle(rawLabel)`，返回 `{ stroke, lineWidth }`，复用 `EDGE_STROKE` 默认），`toG6Data` 调用它。

**图例（`GraphLegend.tsx`）：** 在现有节点类型列表下方加一段"边类型"，用同样的 Tag 样式展示上表 6 条（颜色色块 + 本地化标签）。
- 新增 `GRAPH_EDGE_LEGEND` 导出（`graphPresentation.ts`）：列出 6 个 `(edgeType, colorKey)`。
- 新增 i18n key（`graph` 命名空间，zh + en）：`edgeLegend.title`、各边类型的展示名（可复用现有 `edgeTypes.*`）。

### 4. 边界情况

- **默认从 LR 变 TB：** 可见行为变化，但层次更清晰是目标，且 LR 一键切回。可接受。
- **多原因/多效果：** 一个 FailureMode 分出 N 效果 + M 原因，每原因再分控制——TB 下变宽，dagre 自动布局处理；`autoFit: "view"` 已在。
- **DETECTED_BY 源可能是 FailureMode 或 FailureCause：** 保持原边方向，控制措施挂在其真实源节点下，不强行归并。
- **高亮/暗化：** 反转后 g6 边的 `source/target` 为视觉值；高亮判定"两端都在 `highlightNodes`"逻辑不受影响。
- **force / compact-box：** 反转 CAUSE_OF 在 `toG6Data` 层对它们同样生效，但 force 无方向语义、compact-box 仍是 LR 树——影响中性或略好，不专门处理。
- **DFMEA：** 反转与着色均在共享呈现层，自动覆盖 DFMEA；DFMEA 边标签 override（`HAS_PROCESS_STEP→包含子系统` 等）保持。

## 测试

在 `GraphCanvas` / `graphPresentation` 现有测试基础上新增：

1. `toG6Data` 对 `CAUSE_OF` 边输出 `source=FailureMode 节点, target=FailureCause 节点`，边 ID 保持 `causeId-modeId-CAUSE_OF`。
2. `toG6Data` 对 `EFFECT_OF` 边方向不变。
3. `toG6Data` 边颜色按 `rawLabel` 正确分类（6 类）。
4. `graphLayoutOptions("dagre", "TB")` 返回 `rankdir: "TB"`；`("dagre", "LR")` 返回 `"LR"`。
5. `GraphToolbar` 在 `dagre` 下方向下拉可用；非 dagre 下禁用。

## 不做（YAGNI）

- 不改后端、数据模型、边枚举、seed。
- 不改 `force` / `compact-box` 布局算法与方向。
- 不收起边标签、不加分支摘要徽标（方案 3 内容，明确排除）。
- 不引入新布局算法或新节点类型。
- 不改 `NodeDetailDrawer` 的 RPN 计算（其 `CAUSE_OF` 查询用原始 `allEdges`，不受渲染反转影响——`toG6Data` 不改 `allEdges`）。

## 涉及文件

- `frontend/src/components/graph/GraphCanvas.tsx`（`toG6Data`、`graphLayoutOptions`、props）
- `frontend/src/components/graph/GraphToolbar.tsx`（方向下拉、`GraphDirection` 类型）
- `frontend/src/components/graph/GraphLegend.tsx`（边类型图例段）
- `frontend/src/utils/graphPresentation.ts`（`getEdgeStyle`、`GRAPH_EDGE_LEGEND`）
- `frontend/src/pages/FMEAEditorPage.tsx`（持有 `direction` 状态、下传）
- `frontend/src/locales/*/graph.json`（zh + en 新 key）
- 测试文件：对应 `*.test.tsx` / `*.test.ts`