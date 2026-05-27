# DFMEA 双视图编辑器设计规格说明书

**日期**: 2026-05-20  
**状态**: 提案 (Proposal)  
**作者**: Antigravity AI  

---

## 1. 业务背景与设计目标

### 1.1 背景
设计失效模式及影响分析 (DFMEA) 是质量管理系统 (QMS) 的核心组成部分，用于在设计阶段识别和降低产品失效风险。与聚焦工序流的 PFMEA 不同，DFMEA 聚焦于产品的**物理/功能结构（系统树）**与**设计参数/要求**。

### 1.2 设计冲突与解决方案
* **痛点**: 
  1. 现代 QMS 倾向于将产品结构建模为层级树（系统 → 子系统 → 零部件），能极好地展现失效传递路径（方案 A）。
  2. 传统品质工程师和外部客户审计通常更习惯传统 Excel 的平铺大表格（方案 C），且需要支持直接按行录入与对比。
* **解决方案**: 
  **双视图融合模式** —— 默认呈现**“结构树 + 选中节点参数矩阵”**的高效主视图，同时提供**“传统平铺大表格”**一键切换模式。双视图共享同一个底层底层图数据库模型 (Graph Data Model)，实现任意一方修改，双向实时同步。

---

## 2. 系统架构与数据模型

### 2.1 底层图数据结构 (Graph Data Model)
为了保持与现有 PFMEA 数据模型的高度一致且无需修改 PostgreSQL schema，DFMEA 的文档数据将继续以 JSONB 格式存储在 `fmea_documents.graph_data` 中，其数据结构为典型的点边图模式 `{"nodes": [], "edges": []}`。

为了完美适配 **AIAG-VDA FMEA 第五版 (2019) 的七步法**，DFMEA 图数据模型采用以“关注要素 (Focus Element)”为核心的相对级联关系，构建出符合标准的“结构-功能-失效-控制”的完整拓扑网络。

#### 节点定义 (Nodes)
* **System (系统) / Subsystem (子系统) / Component (零部件) (结构要素)**:
  `{ "id": "sys_1", "type": "System", "name": "转向系统" }`
  `{ "id": "sub_1", "type": "Subsystem", "name": "转向柱组合" }`
  `{ "id": "comp_1", "type": "Component", "name": "滚动轴承" }`
  > [!NOTE]
  > 在分析中，结构要素节点会根据分析层级被自动映射为**“上一较高级别 (Higher Level)”**、**“关注要素 (Focus Element)”**和**“下一较低级别 (Lower Level)”**。
* **Function (功能及要求)**:
  `{ "id": "fun_1", "type": "Function", "name": "传输旋转运动并承受径向载荷", "requirement": "扭矩传递率 >= 98%, 径向载荷阻抗 >= 15kN" }`
  > [!NOTE]
  > Function 节点同时承载功能描述和其对应的技术要求，对应 FMEA 中的“功能与要求”。
* **Characteristic (设计/特性)**:
  `{ “id”: “char_1”, “type”: “Characteristic”, “name”: “工作游隙”, “specification”: “5~15μm” }`
  > [!NOTE]
  > 代表较低级别的设计或材料特性，如尺寸、公差、硬度等，对应”下一较低级别功能及要求或特性”。
* **DesignParameter (设计参数)**:
  `{ “id”: “dp_1”, “type”: “DesignParameter”, “name”: “工作游隙”, “nominal_value”: 10.0, “unit”: “μm”, “tolerance_upper”: 15, “tolerance_lower”: 5, “specification”: “5~15μm” }`
* **Interface (接口)**:
  `{ “id”: “if_1”, “type”: “Interface”, “name”: “电气接口-连接器”, “interface_type”: “electrical” }`
  > [!NOTE]
  > interface_type 可选值: “mechanical”(机械), “electrical”(电气), “hydraulic”(液压), “software”(软件), “thermal”(热).
* **DVPTask (设计验证任务)**:
  `{ “id”: “dvp_1”, “type”: “DVPTask”, “name”: “轴承台架耐久测试”, “test_method”: “GB/T XXX”, “result”: “pass/fail/pending”, “detection_contribution”: 2 }`
  > [!NOTE]
  > DVP 验证任务节点关联至 DetectionControl 或 FailureMode，验证结果反馈更新探测度(D)评分。
* **FailureEffect (FE - 潜在失效影响)**:
  `{ "id": "fe_1", "type": "FailureEffect", "name": "方向盘异常振动与手感不良", "severity": 6 }`
  > [!IMPORTANT]
  > 严重度 (Severity, S) 直接决定了失效影响的后果级别，因此 `severity` 属性保存在 `FailureEffect` 节点上，评分为 1-10。
* **FailureMode (FM - 潜在失效模式)**:
  `{ "id": "fm_1", "type": "FailureMode", "name": "轴承内部游隙过大异响" }`
  > [!NOTE]
  > 对应关注要素的功能失效。
* **FailureCause (FC - 潜在失效起因)**:
  `{ "id": "fc_1", "type": "FailureCause", "name": "内部滚珠尺寸公差偏大", "occurrence": 3 }`
  > [!IMPORTANT]
  > 频度 (Occurrence, O) 决定了失效起因发生的预测等级，在采取现行预防措施后进行评估，因此 `occurrence` 属性保存在 `FailureCause` 节点上，评分为 1-10。
* **PreventionControl (PC - 现行设计控制-预防措施)**:
  `{ "id": "pc_1", "type": "PreventionControl", "name": "设计公差仿真分析" }`
* **DetectionControl (DC - 现行设计控制-探测措施)**:
  `{ "id": "dc_1", "type": "DetectionControl", "name": "噪音/振动台架测试", "detection": 4 }`
  > [!IMPORTANT]
  > 探测度 (Detection, D) 决定了设计发布前探测到失效起因或模式的能力，因此 `detection` 属性保存在 `DetectionControl` 节点上，评分为 1-10。
* **RecommendedAction (优化/建议措施)**:
  `{ "id": "opt_1", "type": "RecommendedAction", "name": "优化滚珠公差带设计，增加CAE公差配合分析", "responsible": "张工", "due_date": "2026-06-30", "status": "open", "action_taken": "", "completion_date": "", "revised_severity": 0, "revised_occurrence": 0, "revised_detection": 0, "revised_ap": "" }`

#### 边定义 (Edges)
* `HAS_SUBSYSTEM`: System ➔ Subsystem (系统包含子系统)
* `HAS_COMPONENT`: Subsystem ➔ Component (子系统包含零部件)
* `HAS_FUNCTION`: System/Subsystem/Component ➔ Function (结构要素包含其功能与要求)
* `HAS_CHARACTERISTIC`: Component ➔ Characteristic (零部件包含设计特性)
* `HAS_DESIGN_PARAMETER`: Component ➔ DesignParameter (零部件包含设计参数)
* `HAS_INTERFACE`: Component ➔ Interface (零部件包含接口)
* `HAS_FAILURE_MODE`: Function ➔ FailureMode (功能存在潜在失效模式)
* `EFFECT_OF`: FailureMode ➔ FailureEffect (失效模式产生上一级功能层面的失效影响)
* `CAUSE_OF`: FailureCause ➔ FailureMode (下一较低层级的失效起因导致关注要素的失效模式)
* `PREVENTED_BY`: FailureCause ➔ PreventionControl (失效起因由现行预防措施规避)
* `DETECTED_BY`: FailureCause/FailureMode ➔ DetectionControl (失效起因/失效模式由现行探测措施探测)
* `OPTIMIZED_BY`: FailureCause ➔ RecommendedAction (失效起因对应优化建议措施)
* `VALIDATED_BY`: FailureMode/DetectionControl ➔ DVPTask (设计验证任务关联)

---

## 3. API 接口设计

无需设计新的 API，通过直接复用并兼容现有的 `/api/fmea` 端点：

* **创建 FMEA**: `POST /api/fmea`  
  支持传入 `fmea_type="DFMEA"`。
  
* **更新 FMEA**: `PUT /api/fmea/{fmea_id}`  
  传入 `{ "title": "...", "graph_data": { "nodes": [...], "edges": [...] } }`。
  
* **获取 FMEA 详情**: `GET /api/fmea/{fmea_id}`  
  返回完整文档信息以及 `graph_data`。

> [!NOTE]
> 在后端 `fmea_service.py` 的 `create_fmea` 服务中，当 `fmea_type` 为 `DFMEA` 时，我们将为其初始化一个基础模版结构（一个空的 System 节点），方便前端直接渲染。

---

## 4. 前端界面设计与双视图实现

DFMEA 编辑器组件 `DFMEAEditorPage.tsx` 将设计为一个大容器结构，其中包含视图状态 `viewMode: 'tree' | 'spreadsheet'`：

### 4.1 主视图 A (结构树 + 设计矩阵)
* **左侧面板（系统树）**: 
  - 依据 `HAS_SUBSYSTEM` 和 `HAS_COMPONENT` 边递归渲染 `System -> Subsystem -> Component` 节点层级拓扑关系。
  - 提供快速增加/删除节点、重命名节点的右键菜单或悬浮工具条。
  - 当选中某个节点时，它被定义为当前的**“关注要素 (Focus Element)”**，其父级自动识别为**“上一较高级别 (Higher Level)”**，其子级/特性自动识别为**“下一较低级别 (Lower Level)”**。
* **右侧面板（设计矩阵）**: 
  - 根据选中的关注要素节点过滤展示其直接挂载的 `Function`（关注要素功能与要求）及其相关的 `FailureMode`，以及级联形成的完整 FMEA 数据链（FE ➔ FM ➔ FC ➔ PC/DC ➔ AP）。
  - 提供便捷的可视化编辑卡片，用于直接编辑功能要求、失效模式、失效后果（严重度 S）、失效起因（频度 O）、当前预防控制（PC）与当前探测控制（DC，探测度 D）。

### 4.2 传统平铺视图 C (Excel 矩阵)
* **大平铺表格**:
  - 全屏宽度渲染，支持横向滚动，完美对接 VDA-AIAG 5th Edition 官方模板。
  - 列定义（共 25 列，体现标准的 7 步法全流程）：
    1. **结构分析 (Step 2)**: `上一较高级别` | `关注要素` | `下一较低级别或特性类型`
    2. **功能分析 (Step 3)**: `上一较高级别功能及要求` | `关注要素功能及要求` | `下一较低级别功能及要求或特性`
    3. **失效分析 (Step 4)**: `潜在失效影响 (FE)` | `潜在失效模式 (FM)` | `潜在失效起因 (FC)`
    4. **风险分析 (Step 5)**: `严重度 (S)` | `现行预防控制 (PC)` | `频度 (O)` | `现行探测控制 (DC)` | `探测度 (D)` | `RPN` | `措施优先级 (AP)`
    5. **优化 (Step 6)**: `建议措施` | `责任人` | `计划完成日期` | `采取的措施及生效日期` | `修改后的 S` | `修改后的 O` | `修改后的 D` | `修改后的 RPN` | `修改后的 AP`
  - **rowSpan 动态合并**: 使用 `rowSpan` 合并相同父层级的单元格（例如同一个系统合并展示其下的所有子系统和零部件，以及相同功能下的多个失效模式）。
  - **实时联动计算**:
    - $RPN = S \times O \times D$。
    - **措施优先级 (AP)**: 依据 AIAG-VDA 第五版附录 C1.5 表格，根据 S、O、D 的评分组合自动实时计算出 AP 等级（**高 H**、**中 M**、**低 L**），并以醒目的高对比度标签（如红色高亮 H，黄色 M，绿色 L）渲染，无需手动填写。
  - 所有单元格在点击时激活为编辑态（Input/Select/NumberInput），失焦时自动同步并触发防抖保存。

### 4.3 视图间状态同步逻辑
由于两个视图绑定的是同一个 React 状态 `nodes` 和 `edges`，因此：
- 只要修改了 `nodes` 列表或 `edges` 列表，两个视图都会触发重绘。
- 在“平铺表格视图”下新增一行，会自动在 Graph 模型中生成相应的子系统或零部件节点，并通过 `edges` 将它们与父级关联。
- 提供输入防抖（Debounce）保存机制，在用户停止输入 500ms 后自动同步至后端。

---

## 5. 验证与测试计划

### 5.1 自动化测试
* 单元测试: 测试图谱解析器（如 `flattenGraphToTable` 和 `tableToFlattenedNodes`）的边界情况。
* 接口测试: 确保 `fmea_type="DFMEA"` 能够正确写入审计日志，并且防抖保存能够正确调用 `PUT` 请求。

### 5.2 手动测试
* 部署到本地测试环境，在结构树视图和传统平铺大表格之间快速切换。
* 验证数据流双向保存：在结构树中新增的零部件，能够在平铺视图中显示；在平铺视图中新增一行，能在左侧结构树中自动生成节点。
