# 批量导入/导出 (Excel) 设计规格 v4

**日期**: 2026-05-28
**优先级**: Phase 2 P2
**状态**: 待实施

---

## 1. 概述

为 OpenQMS 各模块添加 Excel 导入/导出能力。采用垂直切片策略：先完成共享工具 + 供应商导入导出 + SPC 样本导入的完整链路，验证后扩展至 FMEA/CP/CAPA/IQC。

### 现有基础

- `openpyxl==3.1.2` 已在 requirements.txt
- 供应商质量看板已有 Excel 导出：`supplier_quality_service.py:356-402`
- SPC 详情页已有 Upload.Dragger 占位（已禁用）：`SPCDetailPage.tsx:801-814`
- 前端已有 blob 下载模式：`supplier.ts:143-160`

### 全局约束

| 约束 | 值 | 原因 |
|------|-----|------|
| 上传文件大小限制 | 10 MB | openpyxl 全量加载，防范 OOM |
| 单次导出最大行数 | 10000 | 隐性限制在 service 层 |
| 单次导入最大行数 | 5000 | 隐性限制在 service 层 |
| 前端下载/上传超时 | 60 秒 | 覆盖 axios 默认 10 秒 |
| 日期解析容错 | datetime / float / str 均处理 | Excel 日期格式不稳定 |

---

## 2. Excel 合约

导出与导入使用不同字段集。内部字段名必须与 model/schema 字段名一致。

### 2.1 导出合约

#### 供应商列表 `GET /suppliers/export`

筛选参数：`status`, `grade`, `search`（与 `list_suppliers` 服务签名一致，无 product_line_code）

| 中文表头 | 内部字段 (Supplier model) |
|---------|---------|
| 供应商编号 | supplier_no |
| 名称 | name |
| 简称 | short_name |
| 联系人 | contact_name |
| 电话 | contact_phone |
| 邮箱 | contact_email |
| 地址 | address |
| 供货范围 | product_scope |
| 状态 | status |
| 创建时间 | created_at |

#### FMEA `GET /fmea/{fmea_id}/export`（扩展模块）

单文档导出，展开 graph_data JSONB 为 AIAG 格式。后端需移植 `frontend/src/utils/fmeaTable.ts` 的行展开算法。

graph_data 中的节点类型（以 `fmeaTable.ts` 的 `functionTypes` 和实际 graph 结构为准）：
- **PFMEA**: ProcessItem, ProcessStep, ProcessWorkElement, ProcessItemFunction, ProcessStepFunction, ProcessWorkElementFunction, FailureMode, FailureEffect, FailureCause, PreventionControl, DetectionControl, RecommendedAction
- **DFMEA**: System, Subsystem, Component, FailureMode, FailureEffect, FailureCause, PreventionControl, DetectionControl, RecommendedAction

注：DFMEA 当前行展开算法不包含 DesignParameter / Interface 类型；PFMEA 需包含 ProcessItemFunction / ProcessStepFunction。

实现时需先移植 fmeaTable.ts 的 graph→rows 转换逻辑到 Python。

#### 控制计划 `GET /control-plans/{cp_id}/export`（扩展模块）

单文档导出，每行一个 ControlPlanItem。

| 中文表头 | 内部字段 (ControlPlanItemBase) |
|---------|------|
| 工序编号 | step_no |
| 过程名称 | process_name |
| 设备 | equipment |
| 特性编号 | characteristic_no |
| 产品特性 | product_characteristic |
| 过程特性 | process_characteristic |
| 特殊特性 | special_class |
| 规格/公差 | specification_tolerance |
| 评价方法 | evaluation_method |
| 样本量 | sample_size |
| 频率 | sample_frequency |
| 控制方法 | control_method |
| 反应计划 | reaction_plan |

#### CAPA/8D `GET /capa/{report_id}/export`（扩展模块）

| 中文表头 | 内部字段 (CAPAResponse) |
|---------|------|
| 报告编号 | document_no |
| 标题 | title |
| 严重度 | severity |
| 状态 | status |
| D1 团队 | d1_team |
| D2 问题描述 | d2_description |
| D3 临时措施 | d3_interim |
| D4 根本原因 | d4_root_cause |
| D5 纠正措施 | d5_correction |
| D6 实施验证 | d6_verification |
| D7 预防措施 | d7_prevention |
| D8 闭环 | d8_closure |
| 创建时间 | created_at |

#### IQC 检验记录 `GET /iqc/inspections/export`（扩展模块）

筛选参数：`status`, `inspection_result`, `supplier_id`, `date_from`, `date_to`, `product_line_code`（与 `list_inspections` 签名一致）

| 中文表头 | 内部字段 (IqcInspection model) | 备注 |
|---------|------|------|
| 检验单号 | inspection_no | |
| 物料号 | part_no | |
| 物料名称 | part_name | |
| 供应商编号 | supplier_id | UUID，导出时 join Supplier 取 supplier_no |
| 批次号 | lot_no | 不是 batch_no |
| 批量 | lot_qty | 不是 batch_size |
| 检验结果 | inspection_result | 不是 result |
| 缺陷数 | defect_qty | |
| 检验日期 | inspection_date | |
| 检验员 | inspected_by | UUID，导出时 join User 取 display_name |
| 创建时间 | created_at | |

### 2.2 导入合约

#### 供应商 `POST /suppliers/import`

| 中文表头 | 内部字段 | 必填 | 唯一性 |
|---------|---------|------|--------|
| 名称* | name | 是 | 批内 + DB (Supplier.name) |
| 简称* | short_name | 是 | 批内 + DB (Supplier.short_name) |
| 联系人 | contact_name | 否 | - |
| 电话 | contact_phone | 否 | - |
| 邮箱 | contact_email | 否 | - |
| 地址 | address | 否 | - |
| 供货范围 | product_scope | 否 | - |

自动处理：supplier_no (`SUP-{year}-{seq}`)，status="pending_review"，created_by=当前用户，AuditLog。

#### IQC 物料 `POST /iqc/materials/import`

| 中文表头 | 内部字段 | 必填 | 唯一性 |
|---------|---------|------|--------|
| 物料号* | part_no | 是 | 批内 + DB (IqcMaterial.part_no) |
| 名称* | part_name | 是 | - |
| 规格 | part_spec | 否 | - |
| 类型 | material_type | 否 | - |
| 默认AQL | default_aql | 否 | - |
| 检验水平 | default_inspection_level | 否 | - |
| 单位 | unit | 否 | - |
| 产品线 | product_line_code | 否 | - |

自动处理：created_by=当前用户，product_line_code 默认当前选择，AuditLog。

#### SPC 样本 `POST /spc/inspection-characteristics/{ic_id}/samples/import`

**变量图** (xbar_r, imr):

| 中文表头 | 内部字段 (解析后) | 必填 | 唯一性 |
|---------|---------|------|--------|
| 批次号* | batch_no | 是 | 批内 + DB (SampleBatch WHERE ic_id) |
| 采样时间* | sampled_at | 是 | - |
| 样本值1 | value_1 | 是 | 缺失则精确报 "样本值1" |
| 样本值2 | value_2 | 是 | 缺失则精确报 "样本值2" |
| ... | ... | ... | - |

**计数值图** (p, np, c, u):

| 中文表头 | 内部字段 (解析后) | 必填 | 唯一性 |
|---------|---------|------|--------|
| 批次号* | batch_no | 是 | 批内 + DB (SampleBatch WHERE ic_id) |
| 采样时间* | sampled_at | 是 | - |
| 检验数 | inspected_count | 是 | - |
| 缺陷数 | defect_count | 是 | - |

注意：
- 模板列数由 `InspectionCharacteristic.subgroup_size` 和 `chart_type` 动态决定。
- 解析后保留 `value_1`, `value_2`, ... 原始键到 service 校验层，不提前合并为 `values[]`。service 校验通过后再组装 `values`。
- 最终转换为 `_create_sample_batch_inner` 期望的 `data` 格式：`{batch_no, sampled_at, values: [...]}` 或 `{batch_no, sampled_at, inspected_count, defect_count}`。

---

## 3. 共享 Excel 工具

**新建 `backend/app/utils/excel.py`**

### 3.1 导出工具

```python
# 样式常量（复用现有 supplier_quality_service.py 的蓝底白字风格）
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1677FF", end_color="1677FF", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")

MAX_EXPORT_ROWS = 10000

def create_workbook(sheet_name: str, headers: list[str]) -> tuple[Workbook, Worksheet]:
    """创建带样式表头的工作簿"""

def append_row(ws: Worksheet, values: list[Any]) -> None:
    """追加数据行"""

def auto_width(ws: Worksheet, min_width=10, max_width=40) -> None:
    """自动列宽"""

def workbook_to_bytes(wb: Workbook) -> bytes:
    """auto_width + 序列化为 bytes"""

def excel_response(excel_bytes: bytes, filename: str) -> StreamingResponse:
    """构建 FastAPI StreamingResponse，RFC 5987 编码中文文件名"""
```

### 3.2 导入工具

```python
from datetime import datetime

MAX_IMPORT_ROWS = 5000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

@dataclass
class ImportError:
    row: int       # Excel 行号（从 2 开始）
    field: str     # 内部字段名
    message: str

@dataclass
class ImportResult:
    imported_count: int
    errors: list[ImportError]

def create_template(headers: list[str], sheet_name: str, example_row: list[Any] | None = None) -> bytes:
    """生成导入模板（空数据 + 可选示例行）"""

class ExcelParseError(Exception):
    """解析失败时抛出，API 层捕获后返回 422。"""
    pass

def parse_upload(
    file_bytes: bytes,
    header_mapping: dict[str, str],  # {"中文表头": "内部字段名"}
    required_headers: list[str] | None = None,
    sheet_index: int = 0,
) -> list[dict[str, Any]]:
    """解析 Excel 为字典列表，键为内部字段名。
    - 容错：表头大小写不敏感、去除首尾空白
    - 空行处理：所有解析值均为 None 的行直接剔除，不进入 service 层
    - 每行添加 _row 键标记原始行号
    - 必需表头检查：required_headers 中列出的表头必须在文件中找到
    """
    try:
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(file_bytes), read_only=True)
    except (zipfile.BadZipFile, openpyxl.utils.exceptions.InvalidFileException):
        raise ExcelParseError("文件格式无效，仅支持 .xlsx 格式")

    ws = wb.worksheets[sheet_index]
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))

    # 建立列索引（大小写不敏感、去除空白）+ 记录匹配到的表头
    col_map: dict[int, str] = {}
    matched_headers: set[str] = set()
    for col_idx, header in enumerate(header_row):
        if header:
            header_clean = str(header).strip().lower()
            for cn_header, internal_key in header_mapping.items():
                if cn_header.strip().lower() == header_clean:
                    col_map[col_idx] = internal_key
                    matched_headers.add(cn_header.strip().lower())
                    break

    # 必需表头检查
    if required_headers:
        for req in required_headers:
            if req.strip().lower() not in matched_headers:
                raise ExcelParseError(f"缺少必需表头：{req}")

    # ... 解析数据行 ...

def coerce_datetime(value: Any) -> datetime | None:
    """Excel 日期容错解析：
    - datetime 对象 → 直接返回
    - float → 用 openpyxl.utils.from_excel 转换（Excel 序列号日期）
    - str → 尝试 ISO / 常见中文日期格式解析
    - 失败 → 返回 None
    """

def coerce_int_strict(value: Any) -> int:
    """严格整数转换：拒绝 1.5 等非整数值。
    - float: 必须 value.is_integer()，否则 raise ValueError
    - str: 必须可解析为整数（允许前导空格，不允许小数点），否则 raise ValueError
    - int: 直接返回
    """
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"必须为整数，不能为小数: {value}")
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s or '.' in s or not s.lstrip('-').isdigit():
            raise ValueError(f"必须为整数: {value}")
        return int(s)
    raise ValueError(f"无法转换为整数: {value}")
```

**不做**通用 validate_rows。各模块在 service 层 inline 做校验（必填、批内唯一、DB 唯一、类型转换），因每个模块的校验逻辑差异较大（自动编号、FK 解析、chart_type 决定字段），强行抽象反而增加复杂度。

### 3.3 迁移现有导出

修改 `supplier_quality_service.export_quality_dashboard_excel`（line 356-402）使用 `create_workbook` / `append_row` / `workbook_to_bytes`，避免新旧两套 Excel 风格并存。

---

## 4. 前置重构

所有前置重构的目标：让批量导入可以在单次 commit 内完成，中间步骤只 flush 不 commit。

### 4.1 SPC: 拆分 add_sample_batch 和 _create_audit_log

**文件**: `backend/app/services/spc_service.py`

**问题链**：
- `add_sample_batch` (line 358) 内部 `db.commit()` (line 405)
- `_create_audit_log` (line 25) 内部 `db.commit()` (line 36)
- `_reevaluate_alarms` (line ~508) 内部 `db.commit()` (line 573)

任何一个在批量导入中被调用都会破坏"全有或全无"语义。

**拆分方案**：

```python
# 新增：无 commit 版本的 audit log
async def _add_audit_log_no_commit(
    db, user_id, action, table_name, record_id, changed_fields=None
) -> None:
    """db.add(AuditLog) + db.flush()，不 commit。"""
    db.add(AuditLog(...))
    await db.flush()

# 修改现有函数，复用 no_commit 版本
async def _create_audit_log(db, user_id, action, table_name, record_id, changed_fields=None):
    await _add_audit_log_no_commit(db, user_id, action, table_name, record_id, changed_fields)
    await db.commit()  # 保持向后兼容

# 新增：无 commit 版本的 sample batch 创建
async def _create_sample_batch_inner(db, user_id, ic_id, data) -> SampleBatch:
    """创建 SampleBatch + SampleValues + AuditLog，flush 但不 commit。"""
    # 现有 add_sample_batch 的 line 362-400 逻辑搬入
    # AuditLog 改用 _add_audit_log_no_commit
    # 不调用 _reevaluate_alarms

# 新增：无 commit 版本的告警重算
async def _reevaluate_alarms_no_commit(db, ic) -> None:
    """计算告警 + 生成 SPCAlarm 记录 + db.flush()，不 commit。
    与 _create_sample_batch_inner 在同一事务中调用，保证样本和告警全有或全无。
    批量导入只创建 SPCAlarm，不自动创建 CAPA。"""
    # 现有 _reevaluate_alarms 的计算逻辑搬入
    # 改 flush 而非 commit

# 修改现有函数，复用 inner 版本
async def add_sample_batch(db, user_id, ic_id, data) -> SampleBatch:
    """单条新增（保持向后兼容）"""
    batch = await _create_sample_batch_inner(db, user_id, ic_id, data)
    await db.commit()
    await db.refresh(batch)
    await _reevaluate_alarms(db, await get_inspection_characteristic(db, ic_id))
    return batch
```

### 4.2 IQC 物料: 拆分 create_material

**文件**: `backend/app/services/iqc_material_service.py`

现有 `create_material` (line 45) 内部 `db.commit()` (line 81)。

```python
async def _create_material_inner(db, part_no, part_name, ..., user_id) -> IqcMaterial:
    """创建 IqcMaterial + AuditLog，flush 但不 commit。"""
    # 现有 create_material 的 line 57-77 逻辑搬入
    # 改为 flush 而非 commit
    # AuditLog 也只 add + flush

async def create_material(db, part_no, part_name, ..., user_id) -> IqcMaterial:
    """单条新增（保持向后兼容）"""
    material = await _create_material_inner(db, part_no, part_name, ..., user_id)
    await db.commit()
    return material
```

---

## 5. 后端端点

### 路由顺序约束

所有静态路由（`/export`, `/import`, `/import-template`）必须放在 `/{id}` 动态路由之前，参照现有 `# Stats MUST be before "/{supplier_id}"` 注释模式（supplier.py line 18）。

### 5.1 供应商

**文件**: `backend/app/api/supplier.py`, `backend/app/services/supplier_service.py`

```
GET  /suppliers/export                → StreamingResponse (.xlsx)
POST /suppliers/import                → { imported_count, errors } 或 422
GET  /suppliers/import-template       → StreamingResponse (.xlsx)
```

权限：导出 = get_current_user，导入 = require_engineer_or_admin

**导入事务处理**：沿用项目现有 flush/commit/rollback 风格，不用 `async with db.begin()`：

```python
async def bulk_import_suppliers(db, rows, user_id) -> ImportResult:
    # 0. 检查行数上限
    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    # 1. 预检查 DB 已存在（SELECT 在 autobegin 内）
    existing_names = set()
    existing_short_names = set()
    for row in rows:
        name = row.get("name")
        short = row.get("short_name")
        if name:
            r = await db.execute(select(Supplier.supplier_id).where(Supplier.name == name))
            if r.scalar_one_or_none():
                existing_names.add(name)
        if short:
            r = await db.execute(select(Supplier.supplier_id).where(Supplier.short_name == short))
            if r.scalar_one_or_none():
                existing_short_names.add(short)

    # 2. 逐行校验：必填、批内重复、DB 重复
    errors = []
    seen_names, seen_short = set(), set()
    validated = []
    for row in rows:
        row_no = row.pop("_row")
        errs = _validate_supplier_row(row, row_no, seen_names, seen_short, existing_names, existing_short_names)
        if errs:
            errors.extend(errs)
        else:
            seen_names.add(row["name"])
            seen_short.add(row["short_name"])
            validated.append((row_no, row))

    if errors:
        return ImportResult(0, errors)

    # 3. 批量创建（单事务：flush 逐条 + 最终一次 commit）
    created = []
    try:
        for row_no, row in validated:
            supplier_no = await _generate_supplier_no(db, datetime.now().year)
            supplier = Supplier(
                supplier_no=supplier_no, name=row["name"], short_name=row["short_name"],
                contact_name=row.get("contact_name"), contact_phone=row.get("contact_phone"),
                contact_email=row.get("contact_email"), address=row.get("address"),
                product_scope=row.get("product_scope"), status="pending_review", created_by=user_id,
            )
            db.add(supplier)
            await db.flush()
            db.add(AuditLog(
                table_name="suppliers", record_id=supplier.supplier_id,
                action="CREATE", changed_fields={"supplier_no": supplier_no, "name": row["name"]},
                operated_by=user_id,
            ))
            created.append(supplier)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return ImportResult(0, [ImportError(0, "", "数据库写入冲突，请重试")])
    return ImportResult(len(created), [])
```

### 5.2 SPC 样本

**文件**: `backend/app/api/spc.py`, `backend/app/services/spc_service.py`

```
POST /spc/inspection-characteristics/{ic_id}/samples/import        → { imported_count, errors } 或 422
GET  /spc/inspection-characteristics/{ic_id}/samples/import-template → StreamingResponse (.xlsx)
```

权限：require_engineer_or_admin

**API 端点实现**：

```python
@router.post("/inspection-characteristics/{ic_id}/samples/import")
async def import_samples(ic_id, file: UploadFile = File(...), db=..., user=Depends(require_engineer_or_admin)):
    ic = await spc_service.get_inspection_characteristic(db, ic_id)  # get_inspection_characteristic，不是 get_ic
    if not ic:
        raise HTTPException(404)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件超过 10MB 限制")

    # 根据 chart_type 构建 header_mapping
    if ic.chart_type in ("p", "np", "c", "u"):
        header_mapping = {"批次号*": "batch_no", "采样时间*": "sampled_at", "检验数": "inspected_count", "缺陷数": "defect_count"}
    else:
        header_mapping = {"批次号*": "batch_no", "采样时间*": "sampled_at"}
        for i in range(1, ic.subgroup_size + 1):
            header_mapping[f"样本值{i}"] = f"value_{i}"

    try:
        rows = parse_upload(raw, header_mapping, required_headers=["批次号*", "采样时间*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})
    # 不在此处合并 value_i → values[]，保留原始键到 service 校验

    result = await spc_service.bulk_import_samples(db, ic, rows, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}
```

**Service 层**：

```python
async def bulk_import_samples(db, ic, rows, user_id) -> ImportResult:
    # 0. 行数检查
    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ImportError(0, "", f"...")])

    # 1. 预检查 DB 已存在的 (ic_id, batch_no) 组合
    result = await db.execute(
        select(SampleBatch.batch_no).where(SampleBatch.ic_id == ic.ic_id)
    )
    existing_batch_nos = {bn for (bn,) in result.all()}

    # 2. 逐行校验（保留 value_1, value_2... 原始键，缺失时精确报错）
    errors = []
    seen = set()
    validated = []
    for row in rows:
        row_no = row.pop("_row")
        errs = []

        # 必填
        if not row.get("batch_no"):
            errs.append(ImportError(row_no, "batch_no", "批次号为必填项"))
        if not row.get("sampled_at"):
            errs.append(ImportError(row_no, "sampled_at", "采样时间为必填项"))

        # sampled_at 日期解析
        sampled_at = coerce_datetime(row.get("sampled_at"))
        if sampled_at is None:
            errs.append(ImportError(row_no, "sampled_at", "日期格式无效"))
        else:
            row["sampled_at"] = sampled_at

        batch_no = row.get("batch_no")
        if batch_no:
            # 批内重复
            if batch_no in seen:
                errs.append(ImportError(row_no, "batch_no", f"批次内重复: {batch_no}"))
            # DB 重复
            if batch_no in existing_batch_nos:
                errs.append(ImportError(row_no, "batch_no", f"数据库已存在: {batch_no}"))
            seen.add(batch_no)

        # chart_type 校验 + 数值转换（在校验阶段做，失败报精确错误）
        if ic.chart_type in ("p", "np", "c", "u"):
            # inspected_count: 必须为整数、非负（拒绝 1.5 等小数）
            ic_val = row.get("inspected_count")
            if ic_val is None:
                errs.append(ImportError(row_no, "inspected_count", "计数值图需要检验数"))
            else:
                try:
                    ic_int = coerce_int_strict(ic_val)
                    if ic_int < 0:
                        errs.append(ImportError(row_no, "inspected_count", "检验数必须为非负整数"))
                    else:
                        row["inspected_count"] = ic_int
                except (ValueError, TypeError):
                    errs.append(ImportError(row_no, "inspected_count", "检验数必须为整数（不能为小数）"))

            # defect_count: 必须为整数、非负、<= inspected_count
            dc_val = row.get("defect_count")
            if dc_val is None:
                errs.append(ImportError(row_no, "defect_count", "计数值图需要缺陷数"))
            else:
                try:
                    dc_int = coerce_int_strict(dc_val)
                    if dc_int < 0:
                        errs.append(ImportError(row_no, "defect_count", "缺陷数必须为非负整数"))
                    elif "inspected_count" in row and dc_int > row["inspected_count"]:
                        errs.append(ImportError(row_no, "defect_count", "缺陷数不能超过检验数"))
                    else:
                        row["defect_count"] = dc_int
                except (ValueError, TypeError):
                    errs.append(ImportError(row_no, "defect_count", "缺陷数必须为整数（不能为小数）"))
        else:
            # 逐个检查 value_i：非空 + 可转为 float
            values = []
            for i in range(1, ic.subgroup_size + 1):
                key = f"value_{i}"
                val = row.get(key)
                if val is None:
                    errs.append(ImportError(row_no, key, f"样本值{i}为必填项"))
                else:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        errs.append(ImportError(row_no, key, f"样本值{i}必须为数字"))
            if not errs:
                row["_values"] = values  # 临时缓存，校验通过后使用

        if errs:
            errors.extend(errs)
        else:
            validated.append(row)

    if errors:
        return ImportResult(0, errors)

    # 3. 批量创建（同一事务：inner 创建 + 告警重算 + 一次 commit）
    created = []
    try:
        for row in validated:
            data = {"batch_no": row["batch_no"], "sampled_at": row["sampled_at"]}
            if ic.chart_type in ("p", "np", "c", "u"):
                data["inspected_count"] = row["inspected_count"]
                data["defect_count"] = row["defect_count"]
                data["values"] = []
            else:
                data["values"] = row.pop("_values")

            batch = await _create_sample_batch_inner(db, user_id, ic.ic_id, data)
            created.append(batch)

        # 告警重算纳入同一事务
        await _reevaluate_alarms_no_commit(db, ic)

        await db.commit()
    except Exception:
        await db.rollback()
        return ImportResult(0, [ImportError(0, "", "数据库写入失败，请重试")])

    return ImportResult(len(created), [])
```

### 5.3 IQC 物料

**文件**: `backend/app/api/iqc.py`, `backend/app/services/iqc_material_service.py`

```
POST /iqc/materials/import          → { imported_count, errors } 或 422
GET  /iqc/materials/import-template  → StreamingResponse (.xlsx)
```

调用 `_create_material_inner` 逐条创建，最后一次 commit。

---

## 6. 前端

### 6.1 共享工具 `frontend/src/utils/excel.ts`

```typescript
export interface ImportRowError {
  row: number;
  field: string;
  message: string;
}

export interface ImportResult {
  imported_count: number;
  errors: ImportRowError[];
}

export async function downloadExcel(
  url: string,
  params: Record<string, string | undefined>,
  filename: string,
  timeoutMs: number = 60000,  // 覆盖默认 10 秒
): Promise<void> {
  // client.get with responseType: "blob", timeout: timeoutMs
  // blob URL + programmatic <a> click
}

export async function uploadExcel(
  url: string,
  file: File,
  params: Record<string, string>,
  timeoutMs: number = 60000,
): Promise<ImportResult> {
  // FormData + client.post with multipart/form-data
  // catch 422 → return err.response.data as ImportResult
  // catch 其他 → throw（由调用方处理）
}
```

### 6.2 导入对话框 `frontend/src/components/shared/ImportExcelDialog.tsx`

Props: `open, onClose, onImported(count), importFn(file), templateUrl, templateFilename, hint?, title?`

功能：
1. Upload.Dragger 选择文件，accept=".xlsx"，限制 10MB（前后端都只支持 .xlsx，openpyxl 不支持 .xls）
2. 调用 importFn
3. 成功：message.success，调用 onImported
4. 422：对话框内显示错误表格（行号 | 字段 | 错误），不关闭
5. 底部"下载导入模板"链接

### 6.3 页面接入

| 页面 | 修改 |
|------|------|
| SupplierListPage.tsx | 工具栏加"导出"和"导入"按钮 |
| SPCDetailPage.tsx | 替换 line ~801-814 的禁用 Upload.Dragger 为 ImportExcelDialog |
| IQC 物料页面 | 加"导入物料"按钮 |

---

## 7. 扩展模块（垂直切片验证后）

按相同模式添加导出端点。FMEA 导出需先移植 `fmeaTable.ts` 的 graph→rows 展开算法到 Python。

- `GET /fmea/{fmea_id}/export` — graph_data → AIAG 展开表
- `GET /control-plans/{cp_id}/export` — ControlPlanItem 行
- `GET /capa/{report_id}/export` — 8D 报告
- `GET /iqc/inspections/export` — 检验记录列表（注意 join Supplier/User 取可读名称）

---

## 8. 验证

1. **后端**：`cd backend && python -c "from app.utils.excel import create_workbook, parse_upload; print('OK')"`
2. **API 测试**（需完整 URL）：
   - 导出：`curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/export -o suppliers.xlsx`
   - 模板：`curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/import-template -o template.xlsx`
   - 导入：填写模板后 `curl -F "file=@filled.xlsx" -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/import`
3. **前端**：`cd frontend && npm run build` 通过 tsc 检查
4. **浏览器**：下载导出文件、上传导入文件、验证错误提示

### 8.1 实现阶段验收点（3/4/5 号反馈）

1. **整数校验严格性**：上传含 1.5 的 inspected_count / defect_count，应报 "必须为整数" 而非静默截断
2. **批量 SPC CAPA 策略**：`"_reevaluate_alarms_no_commit"` 只创建 SPCAlarm，不自动创建 CAPA
3. **必需表头缺失**：上传缺少 "批次号*" 的模板，API 应返回 `{"imported_count": 0, "errors": [{"row": 0, "field": "", "message": "缺少必需表头：批次号*"}]}`
