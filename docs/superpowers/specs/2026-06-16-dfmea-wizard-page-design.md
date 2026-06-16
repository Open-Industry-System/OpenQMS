# DFMEA 生成向导独立页面设计

## 概述

将 DFMEA 生成向导从 Modal 改造为独立全页，支持草稿保存、步骤间自由跳转、每步引导卡片解释。

## 方案选择

**渐进式改造（方案 A）**：复用现有 API 和数据结构，向导数据序列化到 `graph_data` JSONB 字段，仅前端新增页面组件。

## 1. 路由 & 导航

- **路由：** `/fmea/wizard/:id` — 仅接受已有 `fmea_id`
- **入口：** 保持 FMEAListPage 的创建 Modal 不变。用户选择 DFMEA 类型并提交后，`createFMEA()` 创建 draft 文档（后端自动注入初始 System 节点），然后 `navigate('/fmea/wizard/{id}')` 进入向导页面
- **草稿恢复：** 列表中 `status=draft` 的 DFMEA 行显示"草稿"标签，点击跳转 `/fmea/wizard/{id}` 继续向导（而非直接进入编辑器）；非 draft 状态的 DFMEA 点击仍跳转 `/fmea/{id}` 编辑器
- **退出：** 顶部"返回列表"按钮回到 `/fmea`；完成向导后跳转 `/fmea/{id}` 编辑器
- **退出确认：** 点击"返回列表"时，如果文档仅有初始 System 节点（即用户未填写任何实质内容），弹确认对话框"当前草稿为空，确定要放弃吗？确定后草稿将被删除"。如果用户确认放弃，调用 `DELETE /fmea/{id}` 删除空草稿后返回列表；如果已有实质内容，直接返回列表（草稿保留）

## 2. 页面布局

```
┌─────────────────────────────────────────────────────────┐
│ 面包屑: FMEA > DFMEA向导 > DFMEA-2026-001              │
│                                    [保存草稿] [返回列表] │
├──────────────┬──────────────────────────────────────────┤
│  左侧面板     │  右侧内容区                              │
│  (280px固定)  │                                          │
│              │  ┌─ 引导卡片（可折叠）────────────────┐   │
│  结构树       │  │ 📖 第X步：{步骤名}                │   │
│  (Step 2起)  │  │ 目的：...                          │   │
│              │  │ 填写要点：...                      │   │
│  ──────────  │  │ 示例：...                          │   │
│  步骤导航     │  └──────────────────────────────────┘   │
│  ① 5T范围    │                                          │
│  ② 结构分析 ✓│  ┌─ 步骤内容 ─────────────────────────┐   │
│  ③ 功能分析   │  │ （当前步骤的表单/表格）              │   │
│  ④ 失效分析   │  │                                     │   │
│  ⑤ 风险分析   │  └─────────────────────────────────────┘   │
│  ⑥ 优化      │                                          │
│  ⑦ 确认      │  ┌─ 底部导航 ─────────────────────────┐   │
│              │  │        [上一步]    [下一步/完成]      │   │
│              │  └──────────────────────────────────────┘   │
└──────────────┴──────────────────────────────────────────┘
```

**左侧面板两部分：**
1. **结构树** — 从 Step 2 起显示 System/Subsystem/Component 层级，点击节点高亮右侧对应内容。Step 1 时显示提示"结构树将在第二步后出现"
2. **步骤导航** — 竖直 Ant `Steps`，已完成步骤显示 ✓ 可点击跳回修改，当前步骤高亮

**右侧内容区三部分：**
1. **引导卡片** — 每步顶部，可折叠，默认展开。含目的、填写要点、示例。折叠状态持久化到 localStorage key `dfmea_wizard_card_collapsed`，用户手动折叠后切换步骤保持折叠状态
2. **步骤表单** — 从现有 GenerationWizard 迁移的核心内容
3. **底部导航** — 上一步/下一步按钮，最后一步为"完成"

**步骤间自由跳转：** 点击已完成步骤可返回修改，修改后数据立即生效，不丢失后续步骤已填内容。例如在 Step 5 可返回 Step 2 添加零部件，回到 Step 5 时新增零部件出现在对应位置。

### 响应式规则

- **桌面 (≥1024px)：** 左右分栏布局，左侧 280px 固定，右侧内容区自适应
- **平板 (768px–1023px)：** 左侧面板收起为可展开抽屉（Ant `Drawer`），通过汉堡按钮切换，右侧内容区全宽
- **手机 (<768px)：** 不显示结构树面板，步骤导航移至顶部水平滚动 `Steps`（small 尺寸），引导卡片默认折叠，内容区全宽

### 无障碍 (A11y)

- **键盘焦点顺序：** 左侧步骤导航 → 右侧引导卡片折叠按钮 → 引导卡片内容 → 步骤表单字段 → 底部导航按钮。`Tab` 在右侧内容区内流转，`Ctrl+↑/↓` 切换步骤（可选增强）
- **ARIA 属性：** 引导卡片使用 `aria-expanded` 标记折叠状态；步骤导航使用 `aria-current="step"` 标记当前步骤；保存状态按钮使用 `aria-live="polite"` 动态播报保存状态变化
- **保存状态指示：** 保存按钮旁边显示文字状态（"已保存 ✓" / "保存中..." / "未保存 ●"），配合 `aria-live` 确保屏幕阅读器可感知

## 3. 草稿保存机制

**渐进式改造（方案 A）**：复用现有 API（`PUT /fmea/{id}`），后端创建 draft 文档，前端每步切换自动保存，另提供手动"保存草稿"按钮。

### 数据流

```
Modal创建 → POST /fmea/ → draft文档(含初始System节点) → 进入向导页面
每步切换 → 自动 PUT /fmea/{id} graph_data (带 lock_version)
手动保存 → PUT /fmea/{id} graph_data (带 lock_version)
最后完成 → PUT /fmea/{id} graph_data → 跳转编辑器
```

> **注意：** 后端创建 DFMEA 时会自动注入一个初始 System 节点（`{ type: "System", name: "新建系统" }`），向导需在此基础上扩展而非从空 graph_data 开始。

### 向导数据序列化到 graph_data

现有 `FMEADocument.graph_data` 为 `{ nodes: [], edges: [] }` JSONB。`GraphNodeSchema` 定义了严格的节点字段（`id`, `type`, `name`, `severity`, `occurrence`, `detection`, `requirement`, `specification` 等），5T 范围信息（team/timeframe/tool/task/trend）不属于这些字段。

**解决方案：5T 范围数据存入 `graph_data` 根属性 `wizardScope`，不放入 nodes 数组。** 理由：
- 存入 localStorage 无法跨设备恢复草稿（核心需求），也不与文档数据一同持久化
- 存入 nodes 数组（`type: "WizardScope"`）会污染图可视化（GraphCanvas 渲染孤立节点）和统计过滤（所有 `getStructureNodes` / `getFunctionNodes` 等需加 `.filter(n => n.type !== 'WizardScope')`）
- JSONB 允许任意根属性，利用 PostgreSQL JSONB 灵活性在 `graph_data` 根层存储 `wizardScope`

需要的小改动：
- **后端** `GraphDataSchema` 添加 `wizardScope: WizardScopeSchema | None = None` 可选字段
- **前端** `GraphData` 类型添加 `wizardScope?: { team?: string; timeframe?: string; tool?: string; task?: string; trend?: string }`
- 编辑器加载 graph_data 时忽略 `wizardScope`（现有代码只读 `nodes`/`edges`，零影响）

向导数据映射到 graph_data：

| 步骤数据 | 映射方式 |
|---------|---------|
| 5T范围 | `graph_data.wizardScope` 根属性（跨设备可恢复，不污染 nodes） |
| 结构树 | System/Subsystem/Component/Interface 节点 + 对应边（已有字段） |
| 功能 | ProcessWorkElementFunction 节点 + HAS_FUNCTION 边（已有字段） |
| 失效链 | FailureMode/FailureEffect/FailureCause 节点 + 对应边（已有字段） |
| S/O/D值 | 节点的 severity/occurrence/detection 属性（已有字段） |
| 优化措施 | PreventionControl/DetectionControl 节点 + 对应边（已有字段） |

### 乐观锁 & 保存策略

后端使用 `lock_version` 乐观锁（`FMEAUpdate.lock_version` + `SELECT ... FOR UPDATE`）。向导保存必须正确处理并发：

- **每次 PUT 请求携带 `lock_version`**：从上次 GET/PUT 响应中获取，发送 `lock_version` 字段。成功后更新本地 `lock_version`
- **步骤切换自动保存**：静默 PUT，不弹 message，保存按钮短暂显示 ✓
- **手动"保存草稿"**：显式 PUT，按钮显示"保存中..."→"已保存 ✓"，2秒后恢复
- **409 冲突处理**：若 PUT 返回 `lock_version_mismatch` 错误（极罕见，单人操作向导时不应发生），弹提示"数据已被其他会话修改，请刷新页面后重试"，不自动合并
- **防抖策略**：步骤切换和手动保存共用 `useRef` 标记 + 500ms debounce。步骤切换时设置"脏"标记并启动 debounce 计时器，计时器到期后发起 PUT。手动保存立即取消 debounce 并直接发起 PUT。避免短时间内多次切换步骤导致重复请求
- **请求队列化**：PUT 请求串行执行。前一次 PUT 返回并更新本地 `lock_version` 后，才发起下一次 PUT。避免并发 PUT 导致乐观锁冲突。实现：`useRef<Promise>` 追踪进行中的请求，新的 PUT 链接到前一个 Promise 的 `.then()`
- **按钮状态**：PUT 发送期间"下一步"/"完成"按钮显示 loading 状态（Ant `Button` 的 `loading` 属性），防止用户快速连续点击。保存按钮同步显示"保存中..."
- **乐观更新**：前端状态先更新，PUT 异步发出。失败时弹 message 提示"保存失败，请重试"，不回滚前端状态（避免用户正在编辑时数据闪烁）
- **离开页面**：`beforeunload` 事件弹浏览器确认（无法保证 PUT 完成），有脏数据时提示用户先保存
- **完成向导**：最终 PUT 保留所有 graph_data 节点，跳转 `/fmea/{id}` 编辑器，编辑器已有 `draft → in_review` 状态机

## 4. 各步骤内容 & 引导卡片

### Step 1 — 5T范围定义

**引导卡片：**
> 📖 **第一步：5T范围定义**
> **目的：** 明确 DFMEA 分析的边界、团队和关注点，确保后续分析聚焦。
> **填写要点：** 团队应包含设计、工艺、质量等跨职能成员；任务描述要具体到产品/系统层级。
> **示例：** 团队：BMS设计组、工艺工程组；时间范围：2026年Q1-Q3；工具：FMEA工作表；任务：DC-DC转换器DFMEA分析；趋势：过往3款同类产品客户投诉统计

**表单：** 标题、文档编号已在 Modal 中填写，此步骤只保留 5T 字段（团队、时间范围、工具、任务、趋势）

### Step 2 — 结构分析

**引导卡片：**
> 📖 **第二步：结构分析**
> **目的：** 将产品分解为系统→子系统→零部件的层级结构，为功能分析提供基础。
> **填写要点：** 层级不宜超过4层；每个零部件应是可独立分析的物理单元；可添加接口节点表示跨分支的交互。
> **示例：** 系统: BMS → 子系统: BMU / 充电管理 → 零部件: LTC6811 / MOSFET

**表单：** 复用现有结构树编辑，但在左侧面板大区域展示而非 Modal 内小区域

**级联删除：** 删除结构节点时必须级联清理所有下游关联节点。依赖链为 Component → Function → FailureMode → (FailureEffect, FailureCause) → (PreventionControl, DetectionControl)。删除逻辑：
1. 找到被删节点的所有出边，收集目标节点 ID
2. 递归遍历：对每个下游节点，查找仅由被删路径可达的节点（即没有其他入边的节点）
3. 将这些孤立节点及其关联边一并移除
4. 共享控制节点（被多个 FailureCause 引用）不删除，仅删除边

### Step 3 — 功能分析

**引导卡片：**
> 📖 **第三步：功能分析**
> **目的：** 为每个零部件定义其功能、技术要求和规格参数，建立"零部件需要做什么"的清晰描述。
> **填写要点：** 功能描述用"动词+名词"格式（如"采集单体电压"）；技术要求描述期望性能指标；规格参数带公差（如"±2mV"）。
> **示例：** 零部件 LTC6811 → 功能: 采集单体电压 → 要求: 准确采集每个电芯电压 → 规格: 精度±2mV, 采样率≥10Hz

**表单：** 左侧结构树高亮当前零部件，右侧显示对应功能表单

### Step 4 — 失效分析

**引导卡片：**
> 📖 **第四步：失效分析**
> **目的：** 针对每个功能识别失效模式、失效影响和失效原因，形成完整的失效链。
> **填写要点：** 失效模式 = 功能的反面（"采集电压"→"无法采集"/"采集精度不足"）；影响描述对系统的后果而非本身；原因要具体到可措施层面。
> **示例：** 功能"采集单体电压" → 失效模式: 采集精度不足 → 影响: 控制决策偏差 → 原因: 传感器老化/校准漂移

**表单：** 复用智能推荐（dfmeaRules），按零部件/功能分组显示失效链

### Step 5 — 风险分析

**引导卡片：**
> 📖 **第五步：风险分析**
> **目的：** 为每条失效链评估严重度(S)、发生度(O)、探测度(D)，计算措施优先级(AP)。
> **填写要点：** S 评估失效影响的严重程度(1-10)；O 评估失效原因发生的可能性(1-10)；D 评估当前探测措施能发现原因的能力(1-10)；AP 由系统自动计算，无需手动填写。
> **示例：** S=8(严重) + O=4(偶发) + D=3(较难探测) → AP=H(必须优化)

**表单：** 复用现有 S/O/D 表格 + AP 自动计算

### Step 6 — 优化措施

**引导卡片：**
> 📖 **第六步：优化措施**
> **目的：** 对 AP=H 的失效链制定预防和探测措施，降低风险。
> **填写要点：** 预防措施降低发生度(O)；探测措施降低探测度(D)；严重度(S)通常只能通过设计变更降低。
> **示例：** 预防: 传感器冗余布置、降额设计 → 预期 O 从4降到2；探测: 在线实时监测、自诊断功能 → 预期 D 从3降到2

**表单：** 只显示 AP=H 的失效链，复用现有优化卡片

### Step 7 — 确认创建

**引导卡片：**
> 📖 **第七步：确认创建**
> **目的：** 检查所有步骤的数据完整性，确认后进入正式编辑器继续完善。
> **填写要点：** 检查结构是否完整、功能是否覆盖所有零部件、失效链是否有遗漏、S/O/D 是否填写。
> **示例：** 确认后将创建 DFMEA 文档并进入编辑器，可在编辑器中继续添加细节。

**表单：** 汇总统计（结构节点数、功能节点数、失效链数、总节点数、总边数）+ "完成并进入编辑器"按钮

### 步骤完整性校验

当用户回退修改已完成步骤后，后续步骤需标记"待补全"状态：

- **步骤导航图标：** 已完成步骤默认显示 ✓。若回退修改导致后续步骤数据不完整，受影响步骤显示 ⚠（黄色警告图标），提示用户需要补全
- **校验规则：**
  - Step 3（功能分析）待补全：存在 Component 节点没有通过 `HAS_FUNCTION` 边连接 Function 节点
  - Step 4（失效分析）待补全：存在 Function 节点没有通过 `HAS_FAILURE_MODE` 边连接 FailureMode 节点
  - Step 5（风险分析）待补全：存在 FailureMode 节点的 S/O/D 值为 0
- **Step 7 完成限制：** "完成并进入编辑器"按钮在校验不通过时置为 disabled，显示红色提示文字说明哪些步骤需要补全。用户仍可手动保存草稿，但不能完成向导

## 5. 实现要点

### 新增文件
- `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` — 向导独立页面主组件
- `frontend/src/components/dfmea/WizardGuidanceCard.tsx` — 可折叠引导卡片组件
- `frontend/src/components/dfmea/WizardStructureTree.tsx` — 左侧结构树+步骤导航面板

- `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` — 加载文档时检查 `fmea_type === "DFMEA" && status === "draft"`，自动跳转 `/fmea/wizard/{id}`
- `frontend/src/App.tsx` — 新增 `/fmea/wizard/:id` 路由
- `frontend/src/pages/planning/fmea/FMEAListPage.tsx` — DFMEA 创建后跳转向导页面而非打开 Modal
- `frontend/src/locales/zh-CN/dfmea.json` — 新增引导卡片文案
- `frontend/src/locales/en-US/dfmea.json` — 新增引导卡片英文翻译

### 复用模块
- `frontend/src/utils/dfmeaRules.ts` — 智能推荐规则引擎
- `frontend/src/components/dfmea/GenerationWizard.tsx` — 步骤表单逻辑迁移到新页面组件，原 Modal 保留
- `frontend/src/types/index.ts` — GraphNode/GraphEdge 类型

### 后端改动（小）
- `backend/app/schemas/fmea.py` — `GraphDataSchema` 添加 `wizardScope: WizardScopeSchema | None = None` 可选字段，`WizardScopeSchema` 包含 `team/timeframe/tool/task/trend` 五个可选字符串字段
- 现有 `POST /fmea/`（创建 draft 含初始 System 节点）和 `PUT /fmea/{id}`（带 lock_version 乐观锁）无需其他改动