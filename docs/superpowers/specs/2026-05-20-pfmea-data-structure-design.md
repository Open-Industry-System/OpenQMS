# PFMEA 七步法数据结构优化设计规格说明书

**日期**: 2026-05-20  
**状态**: 已评审通过 (Approved)  
**作者**: Antigravity AI  

---

## 1. 业务背景与设计目标

### 1.1 背景
过程失效模式及影响分析 (PFMEA) 是质量管理系统 (QMS) 中用于识别、评估和规避制造、装配与物流工序中潜在质量风险的核心工具。新版 AIAG-VDA FMEA (2019) 标准引入了严谨的**「七步法」**分析方法，将传统的二维平铺表格升级为了高度关联的“结构-功能-失效-控制”拓扑链条。

### 1.2 设计冲突与方案选择
* **痛点**: 
  传统的 PFMEA 往往使用单一的通用节点（如 `Process`, `Function`, `ControlMeasure`）进行简单关联。这种结构在面对新版七步法的“三级过程分解”（过程项目-过程步骤-过程作业要素）和“三级功能与特性分解”时，无法提供明确的类型强契约约束。在大表格平铺展示时，也由于节点层级模糊极易产生行合并错乱和数据丢失。
* **解决方案**: 
  **方案 A（完全规范化对称模式）**。引入专用的 PFMEA 结构、功能与风险节点类型，与已有的 DFMEA 编辑器规范保持完美对称与统一。所有新增属性以可选字段形式扩展至已有的图谱 Schema 中，既实现了极佳的七步法理论还原度，又保持了数据库层的完美向下兼容。

---

## 2. 拓扑模型与图数据结构 (Graph Data Model)

底层数据继续存储于 `fmea_documents.graph_data` 中，其基本数据格式为 `{ "nodes": [], "edges": [] }`。

### 2.1 节点类型规范 (Nodes)

#### A. 过程结构分析节点 (Step 2 - 结构分析)
* **ProcessItem (过程项目 / 过程名称)**: 级别最高的整合层级（如生产线、装配线名称）。
  `{ "id": "pi_1", "type": "ProcessItem", "name": "SMT焊接生产线" }`
* **ProcessStep (过程步骤 / 工位工序)**: 具体的工位或操作工序，承载工序号。
  `{ "id": "ps_1", "type": "ProcessStep", "name": "SMT元器件贴装", "process_number": "OP10", "external_process_ref": null }`
  > [!NOTE]
  > `external_process_ref` 为外部生产系统工艺路线映射主键，用于SPC数据采集的物理映射。
* **ProcessWorkElement (过程作业要素 / 4M1E)**: 影响工步的最低层要素（人、机、料、环等）。
  `{ "id": "we_1", "type": "ProcessWorkElement", "name": "高速贴片机", "classification": "Machine" }`
  > [!NOTE]
  > `classification` 可选值: `"Man"` (人), `"Machine"` (机), `"Material"` (料), `"Environment"` (环)。该字段仅用于 4M 分类。特殊特性 (CC/SC) 应设置在 ProcessStepFunction（产品特性）或 ProcessWorkElementFunction（过程特性）上。

#### B. 过程功能与特性节点 (Step 3 - 功能分析)
* **ProcessItemFunction (过程项目功能)**: 过程项目在企业内部、发运直接客户或最终用户层面的期望效果。
  `{ "id": "pif_1", "type": "ProcessItemFunction", "name": "完成电路板SMT焊接与元器件组装" }`
* **ProcessStepFunction (过程步骤功能 / 产品特性)**: 该工步的预期功能以及在此产生的”产品特性”。
  `{ “id”: “psf_1”, “type”: “ProcessStepFunction”, “name”: “准确贴装电子元器件”, “specification”: “元器件贴装偏移度 <= 0.05mm”, “special_characteristic_class”: null }`
* **ProcessWorkElementFunction (作业要素功能 / 过程特性)**: 作业要素对工步功能的贡献以及需控制的”过程特性”（工艺参数）。
  `{ “id”: “wef_1”, “type”: “ProcessWorkElementFunction”, “name”: “设备提供适宜且稳定的贴装压力”, “requirement”: “贴装压力 3.0±0.5N”, “special_characteristic_class”: null }`

#### C. 潜在失效分析节点 (Step 4 - 失效分析)
* **FailureEffect (FE - 潜在失效影响)**: 失效模式在不同层面导致的后果，承载严重度。
  `{ "id": "fe_1", "type": "FailureEffect", "name": "电控板功能丧失，导致整车无法启动报警", "severity": 8, "severity_plant": 4, "severity_customer": 8, "severity_user": 8 }`
  > [!IMPORTANT]
  > PFMEA 特有三段式严重度评分属性：`severity_plant` (本厂影响严重度)、`severity_customer` (直接客户/下级工厂影响严重度)、`severity_user` (最终用户影响严重度)。最终的 `severity` 取三者中的最大值。
* **FailureMode (FM - 潜在失效模式)**: 过程步骤功能（产品特性）不符合要求时的表现。
  `{ "id": "fm_1", "type": "FailureMode", "name": "元器件贴装偏移" }`
* **FailureCause (FC - 潜在失效起因)**: 作业要素不满足过程特性（工艺参数超差或失效）的表现，承载频度。
  `{ "id": "fc_1", "type": "FailureCause", "name": "贴装吸嘴磨损导致压力设定偏小", "occurrence": 4 }`

#### D. 风险与控制节点 (Step 5 - 风险分析)
* **PreventionControl (PC - 现行预防控制)**: 旨在减少失效起因发生频度的预防措施。
  `{ "id": "pc_1", "type": "PreventionControl", "name": "开机吸嘴压力自动零点校准与设备预防性维护" }`
* **DetectionControl (DC - 现行探测控制)**: 旨在释放前通过自动或手动方式探测到失效起因或失效模式的措施，承载探测度。
  `{ "id": "dc_1", "type": "DetectionControl", "name": "贴装后在线 3D-AOI 光学检测仪", "detection": 3 }`

#### E. 优化与改进措施节点 (Step 6 - 优化)
* **RecommendedAction (建议优化措施)**: 针对失效起因或模式的改进任务，包含完整的跟进和重评属性。
  `{ "id": "ra_1", "type": "RecommendedAction", "name": "引入吸嘴压力闭环传感器进行实时监测与自适应补偿", "responsible": "张工", "due_date": "2026-06-15", "status": "open", "action_taken": "", "completion_date": "", "revised_severity": 0, "revised_occurrence": 0, "revised_detection": 0, "revised_ap": "" }`

---

### 2.2 关系类型规范 (Edges)

* **结构拓扑层级边**:
  - `HAS_PROCESS_STEP`: ProcessItem ➔ ProcessStep (项目包含工序)
  - `HAS_WORK_ELEMENT`: ProcessStep ➔ ProcessWorkElement (工序包含 4M 要素)
* **结构-功能关联边**:
  - `HAS_FUNCTION`: 结构节点 ➔ 对应功能节点
* **功能层级映射边**:
  - `FUNCTION_MAPPED_TO`: 过程项目功能 ➔ 过程步骤功能 ➔ 作业要素功能 (上级功能与下级实现的依赖链)
* **失效链传递边**:
  - `HAS_FAILURE_MODE`: 过程步骤功能 ➔ 失效模式 (特性不满足产生失效模式)
  - `EFFECT_OF`: 失效模式 ➔ 失效影响 (FM 到 FE 的级联影响)
  - `CAUSE_OF`: 失效起因 ➔ 失效模式 (FC 导致 FM 的起因链)
* **风险控制与优化关联边**:
  - `PREVENTED_BY`: 失效起因 ➔ 现行预防措施
  - `DETECTED_BY`: 失效起因 / 失效模式 ➔ 现行探测措施
  - `OPTIMIZED_BY`: 失效起因 ➔ 建议优化措施

---

## 3. 后端 API 与 Pydantic Schema 设计

### 3.1 扩展的节点 Schema 定义 (`backend/app/schemas/fmea.py`)
```python
from pydantic import BaseModel, Field

class GraphNodeSchema(BaseModel):
    id: str
    type: str  # 节点类型，如 ProcessItem, ProcessStep, ProcessWorkElement 等
    name: str  # 展示名称
    
    # 结构分析层级属性 (Step 2)
    process_number: str | None = None  # 仅用于 ProcessStep 的工序号，如 "OP30"
    classification: str | None = None  # 用于 ProcessWorkElement 的 4M 类型（Man/Machine/Material/Environment）或特性分类 (CC/SC)
    
    # 功能分析与要求属性 (Step 3)
    requirement: str | None = None     # 期望功能描述/技术要求
    specification: str | None = None   # 产品特性参数公差规格
    
    # 风险分析属性 (Step 4 & 5)
    severity: int = Field(default=0, ge=0, le=10)            # 综合严重度 (1-10)
    severity_plant: int | None = Field(default=None, ge=0, le=10)     # 本厂影响严重度 (1-10)
    severity_customer: int | None = Field(default=None, ge=0, le=10)  # 直接客户/下级工厂影响严重度 (1-10)
    severity_user: int | None = Field(default=None, ge=0, le=10)      # 最终用户影响严重度 (1-10)
    
    occurrence: int = Field(default=0, ge=0, le=10)          # 频度 (1-10)
    detection: int = Field(default=0, ge=0, le=10)           # 探测度 (1-10)
    
    # 优化措施跟进属性 (Step 6)
    responsible: str | None = None      # 措施责任人
    due_date: str | None = None         # 计划完成日期
    status: str | None = None           # 措施状态 (如 open / closed / in_progress)
    action_taken: str | None = None     # 实际采取的措施描述
    completion_date: str | None = None  # 实际完成日期
    
    revised_severity: int = Field(default=0, ge=0, le=10)    # 改进后严重度 (1-10)
    revised_occurrence: int = Field(default=0, ge=0, le=10)  # 改进后频度 (1-10)
    revised_detection: int = Field(default=0, ge=0, le=10)   # 改进后探测度 (1-10)
    revised_ap: str | None = None                            # 改进后的措施优先级 (H / M / L)
```

---

## 4. 前端 TypeScript 接口设计

### 4.1 `GraphNode` 接口定义 (`frontend/src/types/index.ts`)
```typescript
export interface GraphNode {
  id: string;
  type: string;  // 节点类型：ProcessItem, ProcessStep, ProcessWorkElement 等
  name: string;  // 展示名称
  
  // 结构分析相关属性
  process_number?: string;   // 过程步骤工序号，如 "OP30"
  classification?: string;   // 作业要素的 4M 类别 (Man/Machine等) 或特殊特性分类 (CC/SC)
  
  // 功能分析与技术要求
  requirement?: string;      // 技术要求
  specification?: string;    // 产品特性公差参数
  
  // 风险评估数值
  severity: number;          // 综合严重度 (1-10)
  severity_plant?: number;   // 本厂影响严重度
  severity_customer?: number;// 直接客户/下级工厂影响严重度
  severity_user?: number;    // 最终用户影响严重度
  
  occurrence: number;        // 发生频度 (1-10)
  detection: number;         // 探测度 (1-10)
  
  // 建议优化与改进措施
  responsible?: string;      // 责任人
  due_date?: string;         // 计划完成日期
  status?: string;           // 状态
  action_taken?: string;     // 实际采取的措施描述
  completion_date?: string;  // 实际完成日期
  
  revised_severity?: number; // 改进后严重度
  revised_occurrence?: number;// 改进后频度
  revised_detection?: number; // 改进后探测度
  revised_ap?: string;       // 改进后措施优先级 (H / M / L)
}
```

---

## 5. 后端模板初始化与 Seed 演示数据设计

### 5.1 FMEA 创建模板初始化
当调用 `create_fmea` 创建文档时，自动基于 `fmea_type` 写入拓扑的基准节点（起点）：
* `PFMEA`: 自动初始化一个 ID 随机的 `ProcessItem` (新建过程项目) 节点。
* `DFMEA`: 自动初始化一个 ID 随机的 `System` (新建系统) 节点。

### 5.2 优化后的 SMT 演示数据 (Seed)
更新后的 SMT 贴装 PFMEA 数据包含了一条完整的符合新版标准的数据链路，作为开发测试与用户操作的最佳范例。

---

## 6. 验证与测试计划

### 6.1 单元测试与 Schema 校验
* **测试用例 1**: 创建全新的 PFMEA，验证接口返回的 `graph_data` 中是否包含默认初始化的单个 `ProcessItem` 节点。
* **测试用例 2**: 提交并存储带有 `severity_plant`, `severity_customer`, `severity_user` 等新字段的 PFMEA 节点数据，确保后端正确反序列化并通过 Pydantic 校验保存。
* **测试用例 3**: 验证更新带有空字符或不含新字段的旧节点时，系统能够保持完美的向下兼容，不触发 Schema 报错。

### 6.2 手动集成测试
* 本地部署测试环境，验证 SMT 工序演示数据（Seed 数据）加载和获取过程是否完好无损。
