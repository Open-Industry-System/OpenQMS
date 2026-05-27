# 产品线选择器设计文档

**日期**: 2026-05-24  
**状态**: 待实现  
**模块**: 产品线选择器（Product Line Selector）

---

## 目标

实现多产品线切换与数据隔离，支持全局选择器统一过滤所有模块数据。

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 架构方案 | 后端 `product_lines` 表 + 前端全局选择器 | 产品线为一等实体，需可管理 |
| 过滤范围 | 所有模块统一过滤 | 一致性体验 |
| "全部"选项 | 支持 | 跨产品线概览场景（仪表盘） |
| 列名统一 | 不改 | 避免大规模迁移，现有列名保持原样 |

---

## 数据层

### product_lines 表

```sql
CREATE TABLE product_lines (
    code       VARCHAR(20) PRIMARY KEY,   -- 如 DC-DC-100
    name       VARCHAR(100) NOT NULL,     -- 如 "DC-DC 100W 电源模块"
    is_active  BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### Seed 数据

| code | name |
|------|------|
| DC-DC-100 | DC-DC 100W 电源模块 |
| PCB-SMT-200 | PCB SMT 200 贴片线 |

### 现有模型不动

| 模型 | 列名 | 保持 |
|------|------|------|
| FMEA | `product_line_code` | 不改 |
| CAPA | `product_line_code` | 不改 |
| ControlPlan | `product_line_code` | 不改 |
| SpecialCharacteristic | `product_line_code` | 不改 |
| InspectionCharacteristic | `product_line` | 不改 |
| QualityGoal | `product_line` | 不改 |

---

## API 层

### 新增端点

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/product-lines` | 列表（?is_active=true） | 所有登录用户 |
| POST | `/product-lines` | 创建产品线 | admin |
| PUT | `/product-lines/{code}` | 更新名称/状态 | admin |
| DELETE | `/product-lines/{code}` | 软删除（is_active=false） | admin |

### Schema

```python
class ProductLineCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)

class ProductLineUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None

class ProductLineResponse(BaseModel):
    code: str
    name: str
    is_active: bool
    created_at: datetime
```

> **注意**: `product_lines.code` 是唯一的主键名称。`QMS_PRD.md` 草案中引用的 `pl_code` 不适用于本实现，以 `code` 为准。现有业务表（fmea_documents 等）的 `product_line_code` 列不建立数据库级外键约束，采用松散耦合设计。

### Service 层校验

由于业务表不设 FK 约束，所有涉及写入 `product_line_code` / `product_line` 的 service 方法（FMEA 创建/更新、CAPA 创建/更新、ControlPlan 创建等）必须调用 `product_line_service.validate_product_line(code)` 校验该产品线存在且 `is_active = true`，否则抛出 `ValueError("产品线不存在或已停用")`。

**删除安全检查**：软删除产品线（`is_active=false`）前，必须检查该产品线是否被以下业务表引用。若存在活跃引用则拒绝删除，返回引用表清单：
- `fmea_documents.product_line_code`（status != 'archived'）
- `capa_eightd.product_line_code`（status != 'closed'）
- `control_plans.product_line_code`（status != 'archived'）
- `inspection_characteristics.product_line`（is_active = true）
- `special_characteristics.product_line_code`（status = 'active'）
- `quality_goals.product_line_code`（status = 'active'）
- `suppliers`（通过 IqcInspection 间接关联）

### 现有端点改造

以下 list 端点新增 `product_line: str | None = Query(None)` 参数，service 层加 `.where()` 过滤：

| 端点 | 模型列 |
|------|--------|
| `GET /fmea-documents` | `FMEA.product_line_code` |
| `GET /capa` | `CAPA.product_line_code` |
| `GET /control-plans` | `ControlPlan.product_line_code` |
| `GET /dashboard/kpi` | 各表 `product_line_code` / `product_line` |
| `GET /audits` | `AuditProgram.product_line_code` / `AuditPlan.product_line_code` |
| `GET /management-reviews` | `ManagementReview.product_line_code` |

已有 `product_line` 参数的端点（`GET /quality-goals`、`GET /inspection-characteristics`、`GET /special-characteristics`、`GET /special-characteristics/matrix`）无需改造，前端改为从全局 store 取值传入即可。

---

## 前端层

### Zustand Store

新建 `store/productLineStore.ts`：

```ts
interface ProductLineState {
  productLines: ProductLine[];
  selected: string | null;       // null = 全部
  setSelected: (code: string | null) => void;
  load: () => Promise<void>;
}
```

- `selected` 同步写入 localStorage key `openqms_product_line`
- 初始化从 localStorage 恢复，默认 null
- `load()` 调用 `GET /product-lines` 填充列表

### AppLayout 全局选择器

Header 右侧新增 `<Select>` 组件：

```
[全部产品线 ▾]   ← 默认
[DC-DC-100 ▾]
[PCB-SMT-200 ▾]
```

- 选项来自 store.productLines
- 第一项 value=null，label="全部产品线"
- onChange 调用 store.setSelected
- Select 样式：`style={{ width: 200 }}`，`bordered={false}`

### 各模块适配

所有列表页将 `productLineStore.selected` 作为 `useEffect` 依赖项，切换产品线后自动重新请求数据，无需手动刷新。

| 页面 | 改动 |
|------|------|
| FMEAListPage | 从 store 取 selected，拼入 API 请求参数，selected 变化自动 refetch |
| CAPAListPage | 同上 |
| ControlPlanListPage | 同上（新增 product_line 参数） |
| DashboardPage | KPI 请求带 productLine 参数 |
| SPCListPage | 改为从 store 取值替代页面内 state |
| SCMatrixPage | 改为从 store 取值替代页面内 state |
| QualityGoalListPage | 改为从 store 取值替代页面内 state |

Dashboard 特殊处理：selected=null 时显示全局汇总，选择具体产品线时只统计该线数据。

### 新建文档时的产品线默认值

- 全局选择了具体产品线（如 `DC-DC-100`）：新建弹窗中产品线字段预填该值
- 全局选择"全部产品线"（null）：产品线字段留空，强制用户手动选择一条有效产品线后才能提交

---

## 不做的事

- 不迁移现有列名（product_line_code / product_line 保持原样）
- 不为 audit_logs 表加 product_line 列（Phase 2 考虑）
- 不做产品线级别的权限隔离（RBAC 仍为全局角色）
- 不建数据库外键约束（松散耦合，service 层校验代替）

---

## 验收标准

1. product_lines 表可 CRUD（admin 权限），code 带正则校验
2. AppLayout header 显示全局产品线选择器
3. 切换产品线后，FMEA/CAPA/ControlPlan/SPC/SC/QualityGoal/Dashboard 列表数据自动刷新过滤
4. 选择"全部"显示所有产品线数据
5. 选择持久化到 localStorage，刷新页面后恢复
6. Service 层对 product_line 写入做存在性校验
7. 新建文档时产品线字段按全局选择预填或强制选择
8. TypeScript 编译通过，Python 语法检查通过
