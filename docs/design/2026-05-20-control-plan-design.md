# 控制计划编辑器设计规格

**日期**: 2026-05-20  
**关联功能**: ROADMAP M3-M4 P0 - 控制计划编辑器 + FMEA 联动  
**架构方案**: 独立数据表（A）+ 引用关联变更提示（方法2）

---

## 1. 数据模型与表结构

### 1.1 `control_plans`（头表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `cp_id` | UUID PK | 控制计划ID |
| `document_no` | str(50), unique | 编号，如 `CP-2026-001` |
| `title` | str(200) | 标题 |
| `fmea_ref_id` | UUID FK → fmea_documents, nullable | **仅关联 PFMEA**，不关联 DFMEA |
| `product_line_code` | str(20) | 产品线，默认 `DC-DC-100` |
| `status` | str(20) | `draft` / `review` / `approved` |
| `version` | int | 版本号，默认 1 |
| `phase` | str(20) | 阶段：`sample`(样件) / `trial`(试生产) / `production`(生产) |
| `part_no` | str(100) | 零件编号 |
| `part_name` | str(200) | 零件名称/描述 |
| `contact_info` | str(200) | 主要联系人/电话 |
| `drawing_rev` | str(100) | 图纸版本/日期 |
| `org_factory` | str(200) | 组织/工厂 |
| `core_group` | str(200) | 核心小组 |
| `created_by` / `updated_by` / `approved_by` | UUID FK | 审计字段 |
| `created_at` / `updated_at` / `approved_at` | datetime | 审计字段 |

### 1.2 `control_plan_items`（行表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `item_id` | UUID PK | 行ID |
| `cp_id` | UUID FK | 所属控制计划 |
| `step_no` | str(50) | 零件/过程编号，如 `OP30` |
| `process_name` | str(200) | 过程名称/操作描述 |
| `equipment` | str(200) | 制造用机器、装置、夹具、工具 |
| `characteristic_no` | str(50) | 特性编号 |
| `product_characteristic` | str(200) | 产品特性 |
| `process_characteristic` | str(200) | 过程特性 |
| `special_class` | str(20) | 特殊特性分类：`CC` / `SC` / `无` |
| `specification_tolerance` | str(200) | 产品/过程/规格/公差 |
| `evaluation_method` | str(200) | 评价/测量技术 |
| `sample_size` | str(50) | 样本大小 |
| `sample_frequency` | str(50) | 样本频次 |
| `control_method` | str(200) | 控制方法 |
| `reaction_plan` | str(200) | 反应计划/纠正措施 |
| `source_fmea_node_id` | str(100), nullable | 来源 PFMEA 节点ID（方法2核心） |
| `sort_order` | int | 排序 |

---

## 2. 后端架构与关键业务逻辑

### 2.1 文件结构

```
backend/app/
  models/control_plan.py      → ControlPlan, ControlPlanItem
  schemas/control_plan.py     → Pydantic schemas
  services/control_plan_service.py → 业务逻辑
  api/control_plan.py         → FastAPI 路由
```

### 2.2 Service 层核心方法

**`create_control_plan()`**
- 创建头表，自动生成编号 `CP-2026-XXX`
- 初始状态为 `draft`

**`import_from_fmea(cp_id, fmea_id, step_filter?)`**
1. 校验目标 FMEA 存在且 `fmea_type == "PFMEA"`，否则抛 `ValueError`
2. 遍历 PFMEA `graph_data.nodes`，筛选 `type == "ProcessStep"` 的节点
3. 对每个 ProcessStep：
   - `node.process_number` → `step_no`
   - `node.name` → `process_name`
   - 查找该 ProcessStep 下游的 `ProcessWorkElement` 节点
   - `workElement.name` → `process_characteristic`
   - `workElement.classification` → `special_class`
   - `node.specification` → `specification_tolerance`
   - `node.id` → `source_fmea_node_id`
4. 生成 `ControlPlanItem` 行，按 `process_number` 排序
5. 手动创建 AuditLog

**`check_stale_items(cp_id)`**
1. 查询控制计划关联的 PFMEA `graph_data`
2. 对每个 `source_fmea_node_id` 非空的行：
   - 在 PFMEA graph 中查找对应节点
   - 比较节点当前 `name` / `process_number` 与行的 `process_name` / `step_no`
   - 若 PFMEA 中节点不存在 → 标记为 `source_deleted`
   - 若字段不一致 → 标记为 `modified`，记录差异字段
3. 返回不一致项列表，供前端显示变更提示

**`update_control_plan()`**
- 标准 CRUD，同步更新 `updated_at`
- `approved` 状态下禁止编辑

**`approve_control_plan()`**
- 仅 `admin` / `manager` 可执行
- 状态从 `draft` 变为 `approved`，记录 `approved_by` / `approved_at`
- 手动创建 AuditLog

### 2.3 API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/control-plans` | 创建控制计划 |
| GET | `/api/control-plans` | 列表（分页） |
| GET | `/api/control-plans/{id}` | 详情（含 items） |
| PUT | `/api/control-plans/{id}` | 更新 |
| DELETE | `/api/control-plans/{id}` | 删除 |
| POST | `/api/control-plans/{id}/import-from-fmea` | 从 PFMEA 导入 |
| GET | `/api/control-plans/{id}/stale-check` | 变更检测 |

---

## 3. 前端架构与页面设计

### 3.1 文件结构

```
frontend/src/
  types/index.ts                          → 新增 ControlPlan / ControlPlanItem 接口
  api/controlPlan.ts                      → API 函数
  pages/control-plan/
    ControlPlanListPage.tsx               → 列表页
    ControlPlanEditorPage.tsx             → 编辑页
  components/control-plan/
    ImportFromFMEAModal.tsx               → 从 PFMEA 导入对话框
```

### 3.2 类型定义

```typescript
interface ControlPlan {
  cp_id: string;
  document_no: string;
  title: string;
  fmea_ref_id: string | null;
  product_line_code: string;
  status: string;
  version: number;
  phase: string;           // sample / trial / production
  part_no: string;
  part_name: string;
  contact_info: string;
  drawing_rev: string;
  org_factory: string;
  core_group: string;
  items: ControlPlanItem[];
  // ...审计字段
}

interface ControlPlanItem {
  item_id: string;
  step_no: string;
  process_name: string;
  equipment: string;
  characteristic_no: string;
  product_characteristic: string;
  process_characteristic: string;
  special_class: string;
  specification_tolerance: string;
  evaluation_method: string;
  sample_size: string;
  sample_frequency: string;
  control_method: string;
  reaction_plan: string;
  source_fmea_node_id: string | null;
  sort_order: number;
}
```

### 3.3 编辑页布局

**顶部表头信息卡片**（两列 Ant Design Card）：
- 左上：零件编号（Input）、零件名称（Input）、联系人（Input）、核心小组（Input）
- 右上：组织/工厂（Input）、图纸版本（Input）、阶段选择（Select：样件/试生产/生产）、关联 PFMEA（只读显示）

**操作按钮栏**：
- 保存（Button）
- 从 PFMEA 导入（Button，弹出 ImportFromFMEAModal）
- 检查 PFMEA 变更（Button，调用 stale-check）
- 批准（Button，仅 admin/manager 可见）

**主体表格**（13 列，横向滚动）：

使用 Ant Design Table 的 `columns` + `children` 实现分组表头：

| 大类 | 子列 |
|------|------|
| — | 零件/过程编号 |
| — | 过程名称/操作描述 |
| — | 设备/工装/夹具 |
| **特性** | 特性编号、产品特性、过程特性 |
| — | 特殊特性分类 |
| — | 产品/过程/规格/公差 |
| **方法** | 评价/测量技术 |
| **样本** | 样本大小、样本频次 |
| — | 控制方法 |
| — | 反应计划 |

行内编辑：每行使用 `Input` + `Select`（`special_class` 用 Select：`CC`/`SC`/`无`），失焦保存。底部可新增空白行，支持删除行。

### 3.4 导入对话框

- 选择 PFMEA（Select，仅显示已批准的 PFMEA 列表）
- 选中后预览该 PFMEA 的 ProcessStep 列表（Table + 勾选框）
- 确认后调用 `importFromFMEA()`，成功刷新表格

### 3.5 变更提示

调用 `checkStaleItems()` 后，若返回不一致项，在页面顶部显示 Ant Design `Alert`：
> "关联的 PFMEA 已发生变更，以下行可能已过期：[列出 step_no]，建议重新导入或手动核对。"

---

## 4. 权限与错误处理

### 4.1 权限控制

| 角色 | 能力 |
|------|------|
| `viewer` | 只读，表格禁用编辑，无操作按钮 |
| `quality_engineer` | 创建/编辑控制计划、执行 PFMEA 导入、检查变更 |
| `manager` / `admin` | 额外拥有批准控制计划权限 |

### 4.2 错误处理

| 场景 | 行为 |
|------|------|
| 从非 PFMEA 导入 | `400 Bad Request`，消息："仅支持从 PFMEA 导入" |
| 关联 PFMEA 已删除 | `stale-check` 返回 `source_deleted` 标记 |
| `approved` 状态编辑 | `400 Bad Request`，消息："已批准的控制计划不可编辑" |
| 无权限操作 | `403 Forbidden` |

---

## 5. 联动机制

### 5.1 PFMEA → 控制计划导入

- 单向导入：PFMEA ProcessStep 节点 → 控制计划行
- 保留引用：`source_fmea_node_id` 记录来源节点 ID
- 可多次执行：增量添加，不覆盖已有行

### 5.2 变更检测

- 通过 `source_fmea_node_id` 追踪 PFMEA 节点变更
- 比较字段：`name`（→ `process_name`）、`process_number`（→ `step_no`）
- 前端展示 Alert 提示，由用户决定是否重新导入
- 不自动同步：控制计划可独立演进
