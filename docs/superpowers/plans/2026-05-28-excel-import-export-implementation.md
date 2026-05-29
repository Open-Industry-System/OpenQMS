# 批量导入/导出 (Excel) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 OpenQMS 添加 Excel 批量导入/导出能力，先完成供应商 + SPC + IQC 物料的垂直切片，验证后扩展其他模块。

**Architecture:** 共享 Excel 工具层 (`backend/app/utils/excel.py`) 封装 openpyxl 样式/解析/响应构建。各模块 service 层 inline 校验（不做通用 validate_rows）。导入事务统一用 flush/commit/rollback 风格。前端共享 download/upload helper + 可复用 ImportExcelDialog 组件。

**Tech Stack:** openpyxl 3.1.2 (backend), Ant Design Upload.Dragger (frontend), Axios blob download

**Spec:** `docs/superpowers/specs/2026-05-28-excel-import-export-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/utils/__init__.py` | Create | 包初始化 |
| `backend/app/utils/excel.py` | Create | 共享 Excel 工具：create_workbook, parse_upload, coerce_datetime, coerce_int_strict, excel_response, create_template |
| `backend/app/services/spc_service.py` | Modify | 拆分 add_sample_batch → _create_sample_batch_inner, _add_audit_log_no_commit, _reevaluate_alarms_no_commit |
| `backend/app/services/iqc_material_service.py` | Modify | 拆分 create_material → _create_material_inner |
| `backend/app/services/supplier_service.py` | Modify | 新增 export_suppliers_excel, bulk_import_suppliers |
| `backend/app/services/supplier_quality_service.py` | Modify | 迁移 export_quality_dashboard_excel 使用共享工具 |
| `backend/app/api/supplier.py` | Modify | 新增 /export, /import, /import-template 端点 |
| `backend/app/api/spc.py` | Modify | 新增 .../samples/import, .../samples/import-template 端点 |
| `backend/app/api/iqc.py` | Modify | 新增 /materials/import, /materials/import-template 端点 |
| `frontend/src/utils/excel.ts` | Create | downloadExcel, uploadExcel, ImportResult 类型 |
| `frontend/src/components/shared/ImportExcelDialog.tsx` | Create | 可复用导入对话框组件 |
| `frontend/src/pages/supplier/SupplierListPage.tsx` | Modify | 加导出/导入按钮 |
| `frontend/src/pages/spc/SPCDetailPage.tsx` | Modify | 替换禁用 Upload.Dragger 为 ImportExcelDialog |
| `frontend/src/pages/iqc/` | Modify | IQC 物料页面加导入按钮 |

---

### Task 1: 创建共享 Excel 工具模块

**Files:**
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/excel.py`

- [ ] **Step 1: 创建 utils 包**

```bash
touch backend/app/utils/__init__.py
```

- [ ] **Step 2: 创建 excel.py — 导出工具部分**

```python
# backend/app/utils/excel.py
from dataclasses import dataclass, asdict
from datetime import datetime
from io import BytesIO
from typing import Any
import urllib.parse
import zipfile

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Font, Alignment, PatternFill
from fastapi.responses import StreamingResponse

# ─── 常量 ───
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1677FF", end_color="1677FF", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")

MAX_EXPORT_ROWS = 10000
MAX_IMPORT_ROWS = 5000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def create_workbook(sheet_name: str, headers: list[str]) -> tuple[Workbook, Worksheet]:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
    return wb, ws


def append_row(ws: Worksheet, values: list[Any]) -> None:
    ws.append(values)


def auto_width(ws: Worksheet, min_width: int = 10, max_width: int = 40) -> None:
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, max_width)


def workbook_to_bytes(wb: Workbook) -> bytes:
    auto_width(wb.active)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def excel_response(excel_bytes: bytes, filename: str) -> StreamingResponse:
    encoded = urllib.parse.quote(filename)
    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


def create_template(headers: list[str], sheet_name: str, example_row: list[Any] | None = None) -> bytes:
    wb, ws = create_workbook(sheet_name, headers)
    if example_row:
        ws.append(example_row)
    return workbook_to_bytes(wb)
```

- [ ] **Step 3: 创建 excel.py — 导入工具部分（追加到同文件）**

```python
# 追加到 backend/app/utils/excel.py

@dataclass
class ImportError:
    row: int
    field: str
    message: str

@dataclass
class ImportResult:
    imported_count: int
    errors: list["ImportError"]


class ExcelParseError(Exception):
    pass


def parse_upload(
    file_bytes: bytes,
    header_mapping: dict[str, str],
    required_headers: list[str] | None = None,
    sheet_index: int = 0,
) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException
        wb = load_workbook(BytesIO(file_bytes), read_only=True)
    except (zipfile.BadZipFile, OSError, InvalidFileException) as e:
        raise ExcelParseError(f"文件格式无效，仅支持 .xlsx 格式: {e}")

    ws = wb.worksheets[sheet_index]
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))

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

    if required_headers:
        for req in required_headers:
            if req.strip().lower() not in matched_headers:
                raise ExcelParseError(f"缺少必需表头：{req}")

    rows = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        record = {}
        all_none = True
        for col_idx, internal_key in col_map.items():
            value = row[col_idx] if col_idx < len(row) else None
            if value is not None:
                record[internal_key] = value
                all_none = False
        if not all_none:
            rows.append({"_row": row_idx, **record})

    wb.close()
    return rows


def coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, float):
        try:
            from openpyxl.utils.datetime import from_excel
            return from_excel(value)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def coerce_int_strict(value: Any) -> int:
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

- [ ] **Step 4: 验证模块可导入**

```bash
cd backend && python -c "from app.utils.excel import create_workbook, parse_upload, coerce_datetime, coerce_int_strict, excel_response, create_template, ExcelParseError, ImportError, ImportResult, MAX_IMPORT_ROWS, MAX_UPLOAD_BYTES; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: 验证 coerce_int_strict 严格性**

```bash
cd backend && python -c "
from app.utils.excel import coerce_int_strict
assert coerce_int_strict(3) == 3
assert coerce_int_strict(3.0) == 3
assert coerce_int_strict('3') == 3
try:
    coerce_int_strict(1.5)
    print('FAIL: should have raised')
except ValueError as e:
    assert '小数' in str(e)
    print('OK: 1.5 rejected')
"
```

Expected: `OK: 1.5 rejected`

- [ ] **Step 6: 提交**

```bash
git add backend/app/utils/__init__.py backend/app/utils/excel.py
git commit -m "feat(excel): add shared Excel import/export utilities"
```

---

### Task 2: SPC 服务重构 — 拆分 add_sample_batch

**Files:**
- Modify: `backend/app/services/spc_service.py:25-415`

- [ ] **Step 1: 新增 _add_audit_log_no_commit**

在 `_create_audit_log` 函数（line 25）之前添加：

```python
async def _add_audit_log_no_commit(
    db: AsyncSession, user_id: uuid.UUID, action: str, table_name: str,
    record_id: uuid.UUID, changed_fields: dict | None = None
) -> None:
    """db.add(AuditLog) + db.flush()，不 commit。"""
    db.add(AuditLog(
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields or {},
        operated_by=user_id,
    ))
    await db.flush()
```

- [ ] **Step 2: 修改 _create_audit_log 复用 _add_audit_log_no_commit**

将 `_create_audit_log`（line 25-36）改为：

```python
async def _create_audit_log(
    db: AsyncSession, user_id: uuid.UUID, action: str, table_name: str,
    record_id: uuid.UUID, changed_fields: dict | None = None
) -> None:
    await _add_audit_log_no_commit(db, user_id, action, table_name, record_id, changed_fields)
    await db.commit()
```

- [ ] **Step 3: 新增 _create_sample_batch_inner**

在 `add_sample_batch` 函数（line 358）之前添加。逻辑从 add_sample_batch 的 line 362-400 搬入，AuditLog 改用 `_add_audit_log_no_commit`，最后 flush 而非 commit，不调用 _reevaluate_alarms：

```python
async def _create_sample_batch_inner(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID, data: dict
) -> SampleBatch:
    """创建 SampleBatch + SampleValues + AuditLog，flush 但不 commit。"""
    ic = await get_inspection_characteristic(db, ic_id)
    if not ic:
        raise ValueError("Inspection characteristic not found")

    inspected_count = None
    defect_count = None
    attribute_charts = {"p", "np", "c", "u"}

    if ic.chart_type in attribute_charts:
        inspected_count = data.get("inspected_count")
        defect_count = data.get("defect_count")
        if inspected_count is None or defect_count is None:
            raise ValueError(f"计数值图（{ic.chart_type}）必须提供 inspected_count 和 defect_count")
        if defect_count > inspected_count:
            raise ValueError("defect_count 不能超过 inspected_count")
        values = []
    else:
        values = data.get("values")
        if not values:
            raise ValueError("Values cannot be empty")
        if ic.chart_type == "xbar_r" and len(values) != ic.subgroup_size:
            raise ValueError(f"Expected {ic.subgroup_size} values for xbar_r, got {len(values)}")
        if ic.chart_type == "imr" and len(values) != 1:
            raise ValueError(f"Expected 1 value for imr, got {len(values)}")

    sampled_at = data["sampled_at"]
    if isinstance(sampled_at, str):
        sampled_at = datetime.fromisoformat(sampled_at.replace("Z", "+00:00"))

    batch = SampleBatch(
        ic_id=ic_id,
        batch_no=data["batch_no"],
        sampled_at=sampled_at,
        subgroup_size=len(values),
        inspected_count=inspected_count,
        defect_count=defect_count,
    )
    db.add(batch)
    await db.flush()

    for i, val in enumerate(values):
        db.add(SampleValue(batch_id=batch.batch_id, sequence_no=i + 1, value=val))

    await _add_audit_log_no_commit(
        db, user_id, "CREATE", "sample_batches", batch.batch_id,
        {"ic_id": str(ic_id), "batch_no": data["batch_no"], "count": len(values)}
    )
    return batch
```

- [ ] **Step 4: 修改 add_sample_batch 复用 _create_sample_batch_inner**

将 `add_sample_batch`（line 358-415）改为：

```python
async def add_sample_batch(
    db: AsyncSession, user_id: uuid.UUID, ic_id: uuid.UUID, data: dict
) -> SampleBatch:
    batch = await _create_sample_batch_inner(db, user_id, ic_id, data)
    await db.commit()
    await db.refresh(batch)
    ic = await get_inspection_characteristic(db, ic_id)
    if ic:
        await _reevaluate_alarms(db, ic)
    return batch
```

- [ ] **Step 5: 新增 _reevaluate_alarms_no_commit**

在 `_reevaluate_alarms` 函数（line ~508）之前添加。从现有 `_reevaluate_alarms`（line ~508-573）复制计算逻辑，做两处修改：

```python
async def _reevaluate_alarms_no_commit(db: AsyncSession, ic: InspectionCharacteristic) -> None:
    """计算告警 + 生成 SPCAlarm 记录 + db.flush()，不 commit。
    批量导入只创建 SPCAlarm，不自动创建 CAPA。"""
    # 步骤：读取现有 _reevaluate_alarms (line ~508-573) 完整代码
    # 复制到此函数，做两处修改：
    # (1) 将最后的 await db.commit() (line 573) 改为 await db.flush()
    # (2) 删除 CAPA 创建块：找到 if alarm["severity"] == "critical": 块
    #     （line ~560-571），该块创建 CAPAEightD 并设置 spc_alarm.linked_capa_id，
    #     整个 if 块删除
```

**注意**：此步骤需要实际读取 `_reevaluate_alarms` 的完整代码并复制，不是伪代码。

- [ ] **Step 6: 验证现有功能未被破坏**

```bash
cd backend && python -c "from app.services.spc_service import add_sample_batch, _create_sample_batch_inner, _reevaluate_alarms_no_commit, _add_audit_log_no_commit; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/spc_service.py
git commit -m "refactor(spc): split add_sample_batch into no-commit inner helpers"
```

---

### Task 3: IQC 物料服务重构 — 拆分 create_material

**Files:**
- Modify: `backend/app/services/iqc_material_service.py:45-85`

- [ ] **Step 1: 新增 _create_material_inner**

在 `create_material` 函数（line 45）之前添加：

```python
async def _create_material_inner(
    db: AsyncSession,
    part_no: str,
    part_name: str,
    part_spec: str | None = None,
    material_type: str = "raw",
    default_aql: float | None = None,
    default_inspection_level: str | None = None,
    unit: str | None = None,
    product_line_code: str = "DC-DC-100",
    user_id: uuid.UUID | None = None,
) -> IqcMaterial:
    """创建 IqcMaterial + AuditLog，flush 但不 commit。"""
    material = IqcMaterial(
        part_no=part_no,
        part_name=part_name,
        part_spec=part_spec,
        material_type=material_type,
        default_aql=default_aql,
        default_inspection_level=default_inspection_level,
        unit=unit,
        product_line_code=product_line_code,
        created_by=user_id,
    )
    db.add(material)
    await db.flush()  # 先 flush 获取 material_id

    if user_id:
        db.add(AuditLog(
            table_name="iqc_materials",
            record_id=material.material_id,
            action="CREATE",
            changed_fields={"part_no": part_no, "part_name": part_name},
            operated_by=user_id,
        ))

    return material
```

- [ ] **Step 2: 修改 create_material 复用 _create_material_inner**

将 `create_material`（line 45-85）改为：

```python
async def create_material(
    db: AsyncSession,
    part_no: str,
    part_name: str,
    part_spec: str | None = None,
    material_type: str = "raw",
    default_aql: float | None = None,
    default_inspection_level: str | None = None,
    unit: str | None = None,
    product_line_code: str = "DC-DC-100",
    user_id: uuid.UUID | None = None,
) -> IqcMaterial:
    material = await _create_material_inner(
        db, part_no, part_name, part_spec, material_type,
        default_aql, default_inspection_level, unit, product_line_code, user_id,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(f"物料号 '{part_no}' 已存在")
    return material
```

- [ ] **Step 3: 验证**

```bash
cd backend && python -c "from app.services.iqc_material_service import create_material, _create_material_inner; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/iqc_material_service.py
git commit -m "refactor(iqc): split create_material into no-commit inner helper"
```

---

### Task 4: 供应商导出

**Files:**
- Modify: `backend/app/services/supplier_service.py`
- Modify: `backend/app/api/supplier.py`

- [ ] **Step 1: 添加 export_suppliers_excel 到 service**

在 `backend/app/services/supplier_service.py` 的 `list_suppliers` 函数之后添加：

```python
async def export_suppliers_excel(
    db: AsyncSession,
    status: str | None = None,
    grade: str | None = None,
    search: str | None = None,
) -> bytes:
    from app.utils.excel import create_workbook, append_row, workbook_to_bytes, MAX_EXPORT_ROWS
    items, _ = await list_suppliers(db, page=1, page_size=MAX_EXPORT_ROWS, status=status, grade=grade, search=search)
    headers = ["供应商编号", "名称", "简称", "联系人", "电话", "邮箱", "地址", "供货范围", "状态", "创建时间"]
    wb, ws = create_workbook("供应商", headers)
    for s in items:
        append_row(ws, [
            s.supplier_no, s.name, s.short_name,
            s.contact_name or "", s.contact_phone or "", s.contact_email or "",
            s.address or "", s.product_scope or "",
            s.status, s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
        ])
    return workbook_to_bytes(wb)
```

- [ ] **Step 2: 添加导出端点到 API**

在 `backend/app/api/supplier.py` 的 `# Stats MUST be before "/{supplier_id}"` 注释之前（line 18 之前）添加：

```python
# Export MUST be before "/{supplier_id}"
@router.get("/export")
async def export_suppliers(
    status: str | None = Query(None),
    grade: str | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    excel_bytes = await supplier_service.export_suppliers_excel(db, status, grade, search)
    return excel_response(excel_bytes, f"suppliers_{date_type.today().strftime('%Y%m%d')}.xlsx")
```

在文件顶部 import 区添加：

```python
from app.utils.excel import excel_response
```

- [ ] **Step 3: 验证语法**

```bash
cd backend && python -c "from app.api.supplier import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/supplier_service.py backend/app/api/supplier.py
git commit -m "feat(supplier): add Excel export endpoint"
```

---

### Task 5: 供应商导入

**Files:**
- Modify: `backend/app/services/supplier_service.py`
- Modify: `backend/app/api/supplier.py`

- [ ] **Step 1: 添加 bulk_import_suppliers 到 service**

在 `backend/app/services/supplier_service.py` 的 `export_suppliers_excel` 之后添加：

```python
async def bulk_import_suppliers(
    db: AsyncSession,
    rows: list[dict],
    user_id: uuid.UUID,
) -> "ImportResult":
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    # 预检查 DB 已存在
    existing_names: set[str] = set()
    existing_short: set[str] = set()
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
                existing_short.add(short)

    # 逐行校验
    errors = []
    seen_names: set[str] = set()
    seen_short: set[str] = set()
    validated = []
    for row in rows:
        row_no = row.pop("_row")
        errs = []
        if not row.get("name"):
            errs.append(ExcelImportError(row_no, "name", "名称为必填项"))
        if not row.get("short_name"):
            errs.append(ExcelImportError(row_no, "short_name", "简称为必填项"))
        name = row.get("name")
        short = row.get("short_name")
        if name and name in seen_names:
            errs.append(ExcelImportError(row_no, "name", f"批次内重复: {name}"))
        if short and short in seen_short:
            errs.append(ExcelImportError(row_no, "short_name", f"批次内重复: {short}"))
        if name and name in existing_names:
            errs.append(ExcelImportError(row_no, "name", f"数据库已存在: {name}"))
        if short and short in existing_short:
            errs.append(ExcelImportError(row_no, "short_name", f"数据库已存在: {short}"))
        if errs:
            errors.extend(errs)
        else:
            seen_names.add(name)
            seen_short.add(short)
            validated.append((row_no, row))

    if errors:
        return ImportResult(0, errors)

    # 批量创建
    created = []
    try:
        from datetime import datetime as dt
        for row_no, row in validated:
            supplier_no = await _generate_supplier_no(db, dt.now().year)
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
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入冲突，请重试")])
    return ImportResult(len(created), [])
```

- [ ] **Step 2: 添加导入端点到 API**

在 `backend/app/api/supplier.py` 的导出端点之后、`# Stats MUST be before` 之前添加：

```python
# Import MUST be before "/{supplier_id}"
@router.post("/import")
async def import_suppliers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    header_mapping = {
        "名称*": "name", "简称*": "short_name",
        "联系人": "contact_name", "电话": "contact_phone",
        "邮箱": "contact_email", "地址": "address",
        "供货范围": "product_scope",
    }
    try:
        rows = parse_upload(raw, header_mapping, required_headers=["名称*", "简称*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})

    result = await supplier_service.bulk_import_suppliers(db, rows, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}
```

在文件顶部 import 区添加：

```python
from fastapi import UploadFile, File
```

- [ ] **Step 3: 添加导入模板端点**

在导入端点之后添加：

```python
# Import template MUST be before "/{supplier_id}"
@router.get("/import-template")
async def download_supplier_import_template():
    headers = ["名称*", "简称*", "联系人", "电话", "邮箱", "地址", "供货范围"]
    example = ["示例供应商", "示例", "张三", "13800138000", "test@example.com", "上海市", "电子元器件"]
    from app.utils.excel import create_template
    template_bytes = create_template(headers, "供应商导入模板", example)
    return excel_response(template_bytes, "supplier_import_template.xlsx")
```

- [ ] **Step 4: 验证语法**

```bash
cd backend && python -c "from app.api.supplier import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/supplier_service.py backend/app/api/supplier.py
git commit -m "feat(supplier): add Excel import endpoints with validation"
```

---

### Task 6: SPC 样本导入

**Files:**
- Modify: `backend/app/services/spc_service.py`
- Modify: `backend/app/api/spc.py`

- [ ] **Step 1: 添加 bulk_import_samples 到 service**

在 `backend/app/services/spc_service.py` 的 `_reevaluate_alarms_no_commit` 之后添加：

```python
async def bulk_import_samples(
    db: AsyncSession,
    ic: InspectionCharacteristic,
    rows: list[dict],
    user_id: uuid.UUID,
) -> "ImportResult":
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS
    from app.utils.excel import coerce_datetime, coerce_int_strict

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    # 预检查 DB 已存在的 batch_no
    result = await db.execute(
        select(SampleBatch.batch_no).where(SampleBatch.ic_id == ic.ic_id)
    )
    existing_batch_nos = {bn for (bn,) in result.all()}

    errors = []
    seen = set()
    validated = []
    attribute_charts = {"p", "np", "c", "u"}

    for row in rows:
        row_no = row.pop("_row")
        errs = []

        if not row.get("batch_no"):
            errs.append(ExcelImportError(row_no, "batch_no", "批次号为必填项"))
        if not row.get("sampled_at"):
            errs.append(ExcelImportError(row_no, "sampled_at", "采样时间为必填项"))

        sampled_at = coerce_datetime(row.get("sampled_at"))
        if sampled_at is None and row.get("sampled_at"):
            errs.append(ExcelImportError(row_no, "sampled_at", "日期格式无效"))
        elif sampled_at:
            row["sampled_at"] = sampled_at

        batch_no = row.get("batch_no")
        if batch_no:
            if batch_no in seen:
                errs.append(ExcelImportError(row_no, "batch_no", f"批次内重复: {batch_no}"))
            if batch_no in existing_batch_nos:
                errs.append(ExcelImportError(row_no, "batch_no", f"数据库已存在: {batch_no}"))
            seen.add(batch_no)

        if ic.chart_type in attribute_charts:
            ic_val = row.get("inspected_count")
            if ic_val is None:
                errs.append(ExcelImportError(row_no, "inspected_count", "计数值图需要检验数"))
            else:
                try:
                    ic_int = coerce_int_strict(ic_val)
                    if ic_int < 0:
                        errs.append(ExcelImportError(row_no, "inspected_count", "检验数必须为非负整数"))
                    else:
                        row["inspected_count"] = ic_int
                except (ValueError, TypeError):
                    errs.append(ExcelImportError(row_no, "inspected_count", "检验数必须为整数（不能为小数）"))

            dc_val = row.get("defect_count")
            if dc_val is None:
                errs.append(ExcelImportError(row_no, "defect_count", "计数值图需要缺陷数"))
            else:
                try:
                    dc_int = coerce_int_strict(dc_val)
                    if dc_int < 0:
                        errs.append(ExcelImportError(row_no, "defect_count", "缺陷数必须为非负整数"))
                    elif "inspected_count" in row and dc_int > row["inspected_count"]:
                        errs.append(ExcelImportError(row_no, "defect_count", "缺陷数不能超过检验数"))
                    else:
                        row["defect_count"] = dc_int
                except (ValueError, TypeError):
                    errs.append(ExcelImportError(row_no, "defect_count", "缺陷数必须为整数（不能为小数）"))
        else:
            values = []
            for i in range(1, ic.subgroup_size + 1):
                key = f"value_{i}"
                val = row.get(key)
                if val is None:
                    errs.append(ExcelImportError(row_no, key, f"样本值{i}为必填项"))
                else:
                    try:
                        values.append(float(val))
                    except (ValueError, TypeError):
                        errs.append(ExcelImportError(row_no, key, f"样本值{i}必须为数字"))
            if not errs:
                row["_values"] = values

        if errs:
            errors.extend(errs)
        else:
            validated.append(row)

    if errors:
        return ImportResult(0, errors)

    created = []
    try:
        for row in validated:
            data = {"batch_no": row["batch_no"], "sampled_at": row["sampled_at"]}
            if ic.chart_type in attribute_charts:
                data["inspected_count"] = row["inspected_count"]
                data["defect_count"] = row["defect_count"]
                data["values"] = []
            else:
                data["values"] = row.pop("_values")
            batch = await _create_sample_batch_inner(db, user_id, ic.ic_id, data)
            created.append(batch)

        await _reevaluate_alarms_no_commit(db, ic)
        await db.commit()
    except Exception:
        await db.rollback()
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入失败，请重试")])

    return ImportResult(len(created), [])
```

- [ ] **Step 2: 添加导入端点到 API**

在 `backend/app/api/spc.py` 中，导入端点放在 `POST .../samples`（line 111）之后（line 135 附近）：

```python
@router.post("/inspection-characteristics/{ic_id}/samples/import")
async def import_samples(
    ic_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError, MAX_UPLOAD_BYTES
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="inspection characteristic not found")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

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

    result = await spc_service.bulk_import_samples(db, ic, rows, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}
```

在文件顶部 import 区添加：

```python
from fastapi import UploadFile, File
```

- [ ] **Step 3: 添加导入模板端点**

**注意**：需要在文件顶部 import 区添加 `from app.utils.excel import excel_response`（如果尚未添加）。

```python
@router.get("/inspection-characteristics/{ic_id}/samples/import-template")
async def download_sample_import_template(
    ic_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.utils.excel import create_template, excel_response

    ic = await spc_service.get_inspection_characteristic(db, ic_id)
    if not ic:
        raise HTTPException(status_code=404, detail="inspection characteristic not found")

    if ic.chart_type in ("p", "np", "c", "u"):
        headers = ["批次号*", "采样时间*", "检验数", "缺陷数"]
        example = ["B001", "2026-05-28 10:00", "100", "3"]
    else:
        headers = ["批次号*", "采样时间*"] + [f"样本值{i}" for i in range(1, ic.subgroup_size + 1)]
        example = ["B001", "2026-05-28 10:00"] + ["10.5"] * ic.subgroup_size

    template_bytes = create_template(headers, "样本导入模板", example)
    filename = f"spc_samples_{ic.chart_type}_template.xlsx"
    return excel_response(template_bytes, filename)
```

- [ ] **Step 4: 验证语法**

```bash
cd backend && python -c "from app.api.spc import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/spc_service.py backend/app/api/spc.py
git commit -m "feat(spc): add Excel import endpoints with validation and alarm reevaluation"
```

---

### Task 7: IQC 物料导入

**Files:**
- Modify: `backend/app/services/iqc_material_service.py`
- Modify: `backend/app/api/iqc.py`

- [ ] **Step 1: 添加 bulk_import_materials 到 service**

在 `backend/app/services/iqc_material_service.py` 的 `_create_material_inner` 之后添加：

```python
async def bulk_import_materials(
    db: AsyncSession,
    rows: list[dict],
    product_line_code: str,
    user_id: uuid.UUID,
) -> "ImportResult":
    from app.utils.excel import ImportError as ExcelImportError, ImportResult, MAX_IMPORT_ROWS

    if len(rows) > MAX_IMPORT_ROWS:
        return ImportResult(0, [ExcelImportError(0, "", f"导入行数超过上限 {MAX_IMPORT_ROWS}")])

    # 预检查 DB 已存在的 part_no
    existing: set[str] = set()
    for row in rows:
        pn = row.get("part_no")
        if pn:
            r = await db.execute(select(IqcMaterial.material_id).where(IqcMaterial.part_no == pn))
            if r.scalar_one_or_none():
                existing.add(pn)

    errors = []
    seen = set()
    validated = []
    for row in rows:
        row_no = row.pop("_row")
        errs = []
        if not row.get("part_no"):
            errs.append(ExcelImportError(row_no, "part_no", "物料号为必填项"))
        if not row.get("part_name"):
            errs.append(ExcelImportError(row_no, "part_name", "名称为必填项"))
        pn = row.get("part_no")
        if pn:
            if pn in seen:
                errs.append(ExcelImportError(row_no, "part_no", f"批次内重复: {pn}"))
            if pn in existing:
                errs.append(ExcelImportError(row_no, "part_no", f"数据库已存在: {pn}"))
            seen.add(pn)
        # default_aql 类型校验（在校验阶段做，避免创建阶段 ValueError）
        if row.get("default_aql") is not None:
            try:
                float(row["default_aql"])
            except (ValueError, TypeError):
                errs.append(ExcelImportError(row_no, "default_aql", "默认AQL必须为数字"))
        if errs:
            errors.extend(errs)
        else:
            validated.append((row_no, row))

    if errors:
        return ImportResult(0, errors)

    created = []
    try:
        for row_no, row in validated:
            material = await _create_material_inner(
                db,
                part_no=row["part_no"],
                part_name=row["part_name"],
                part_spec=row.get("part_spec"),
                material_type=row.get("material_type", "raw"),
                default_aql=float(row["default_aql"]) if row.get("default_aql") is not None else None,
                default_inspection_level=row.get("default_inspection_level"),
                unit=row.get("unit"),
                product_line_code=row.get("product_line_code", product_line_code),
                user_id=user_id,
            )
            created.append(material)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return ImportResult(0, [ExcelImportError(0, "", "数据库写入冲突，请重试")])
    return ImportResult(len(created), [])
```

- [ ] **Step 2: 添加导入端点到 API**

在 `backend/app/api/iqc.py` 中，导入端点放在 `POST /materials`（line 34）之后、`GET /materials/{material_id}`（line 58）之前（line 56 附近）。

**注意**：需要在文件顶部 import 区添加 `from fastapi import UploadFile, File`（现有 import 在 line 2）。

```python
@router.post("/materials/import")
async def import_materials(
    file: UploadFile = File(...),
    product_line_code: str = Query("DC-DC-100"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    from app.utils.excel import parse_upload, ExcelParseError, ImportError as ExcelImportError, MAX_UPLOAD_BYTES
    from dataclasses import asdict
    from fastapi.responses import JSONResponse

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    header_mapping = {
        "物料号*": "part_no", "名称*": "part_name", "规格": "part_spec",
        "类型": "material_type", "默认AQL": "default_aql", "检验水平": "default_inspection_level",
        "单位": "unit", "产品线": "product_line_code",
    }
    try:
        rows = parse_upload(raw, header_mapping, required_headers=["物料号*", "名称*"])
    except ExcelParseError as e:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [{"row": 0, "field": "", "message": str(e)}]})

    result = await iqc_material_service.bulk_import_materials(db, rows, product_line_code, user.user_id)
    if result.errors:
        return JSONResponse(status_code=422, content={"imported_count": 0, "errors": [asdict(e) for e in result.errors]})
    return {"imported_count": result.imported_count, "errors": []}
```

- [ ] **Step 3: 添加导入模板端点**

**注意**：需要在文件顶部 import 区添加 `from app.utils.excel import excel_response`（如果尚未添加）。

```python
@router.get("/materials/import-template")
async def download_material_import_template():
    from app.utils.excel import create_template, excel_response
    headers = ["物料号*", "名称*", "规格", "类型", "默认AQL", "检验水平", "单位", "产品线"]
    example = ["PN-001", "示例物料", "10x20mm", "raw", "0.65", "II", "pcs", "DC-DC-100"]
    template_bytes = create_template(headers, "物料导入模板", example)
    return excel_response(template_bytes, "iqc_material_import_template.xlsx")
```

- [ ] **Step 4: 验证语法**

```bash
cd backend && python -c "from app.api.iqc import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/iqc_material_service.py backend/app/api/iqc.py
git commit -m "feat(iqc): add Excel import endpoints for materials"
```

---

### Task 8: 迁移现有供应商质量导出到共享工具

**Files:**
- Modify: `backend/app/services/supplier_quality_service.py:356-402`

- [ ] **Step 1: 修改 export_quality_dashboard_excel 使用共享工具**

将 `supplier_quality_service.py` 的 `export_quality_dashboard_excel` 函数（line 356-402）中的 openpyxl 直接调用替换为共享工具：

```python
async def export_quality_dashboard_excel(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    product_line_code: Optional[str] = None,
) -> bytes:
    from app.utils.excel import create_workbook, append_row, workbook_to_bytes

    dashboard_data = await get_quality_dashboard(db, start_date, end_date, product_line_code)

    headers = ["排名", "供应商编号", "供应商名称", "评级", "PPM", "批次合格率", "交付准时率", "开放SCAR"]
    wb, ws = create_workbook("供应商质量排名", headers)

    for idx, item in enumerate(dashboard_data["ranking"], 1):
        append_row(ws, [
            idx,
            item["supplier_no"],
            item["name"],
            item["grade"],
            round(item["ppm"], 2),
            f"{item['batch_acceptance_rate'] * 100:.2f}%",
            f"{item['delivery_rate'] * 100:.2f}%",
            item["open_scar_count"],
        ])

    ws2 = wb.create_sheet("PPM月度趋势")
    ws2.append(["月份", "PPM"])
    for point in dashboard_data["ppm_trend"]:
        ws2.append([point["month"], round(point["ppm"], 2)])

    return workbook_to_bytes(wb)
```

- [ ] **Step 2: 验证语法**

```bash
cd backend && python -c "from app.services.supplier_quality_service import export_quality_dashboard_excel; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/supplier_quality_service.py
git commit -m "refactor(supplier-quality): migrate Excel export to shared utilities"
```

---

### Task 9: 前端共享 Excel 工具

**Files:**
- Create: `frontend/src/utils/excel.ts`

- [ ] **Step 1: 创建 excel.ts**

```typescript
import client from "../api/client";

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
  params: Record<string, string | undefined> = {},
  filename: string,
  timeoutMs: number = 60000,
): Promise<void> {
  const resp = await client.get(url, {
    params,
    responseType: "blob",
    timeout: timeoutMs,
  });
  const blob = new Blob([resp.data]);
  const urlObj = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = urlObj;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(urlObj);
}

export async function uploadExcel(
  url: string,
  file: File,
  params: Record<string, string> = {},
  timeoutMs: number = 60000,
): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const resp = await client.post(url, formData, {
      params,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: timeoutMs,
    });
    return resp.data as ImportResult;
  } catch (err: any) {
    if (err.response?.status === 422) {
      return err.response.data as ImportResult;
    }
    throw err;
  }
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit src/utils/excel.ts 2>&1 || true
```

Expected: 无报错（或仅依赖报错，不影响类型正确性）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/utils/excel.ts
git commit -m "feat(frontend): add shared Excel download/upload utilities"
```

---

### Task 10: 前端导入对话框组件

**Files:**
- Create: `frontend/src/components/shared/ImportExcelDialog.tsx`

- [ ] **Step 1: 创建 ImportExcelDialog 组件**

```tsx
import React, { useState } from "react";
import { Modal, Upload, Button, Table, message, Space, Typography } from "antd";
import { InboxOutlined, DownloadOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload";
import type { ImportResult, ImportRowError } from "../../utils/excel";

const { Dragger } = Upload;
const { Link } = Typography;

interface ImportExcelDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (count: number) => void;
  importFn: (file: File) => Promise<ImportResult>;
  templateDownloadFn?: () => Promise<void>;
  hint?: string;
  title?: string;
}

export default function ImportExcelDialog({
  open,
  onClose,
  onImported,
  importFn,
  templateDownloadFn,
  hint,
  title = "批量导入",
}: ImportExcelDialogProps) {
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<ImportRowError[]>([]);
  const [fileList, setFileList] = useState<UploadFile[]>([]);

  const handleUpload = async (file: File) => {
    setLoading(true);
    setErrors([]);
    try {
      const result: ImportResult = await importFn(file);
      if (result.errors && result.errors.length > 0) {
        setErrors(result.errors);
      } else {
        message.success(`成功导入 ${result.imported_count} 条记录`);
        onImported(result.imported_count);
        handleClose();
      }
    } catch {
      message.error("导入失败，请检查文件格式");
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setErrors([]);
    setFileList([]);
    onClose();
  };

  const handleDownloadTemplate = async () => {
    if (templateDownloadFn) {
      await templateDownloadFn();
    }
  };

  const errorColumns = [
    { title: "行号", dataIndex: "row", key: "row", width: 80 },
    { title: "字段", dataIndex: "field", key: "field", width: 120 },
    { title: "错误信息", dataIndex: "message", key: "message" },
  ];

  return (
    <Modal
      title={title}
      open={open}
      onCancel={handleClose}
      footer={null}
      width={600}
      destroyOnClose
    >
      {errors.length > 0 ? (
        <>
          <Table
            dataSource={errors.map((e, i) => ({ ...e, key: i }))}
            columns={errorColumns}
            size="small"
            pagination={{ pageSize: 10 }}
            style={{ marginBottom: 16 }}
          />
          <Space>
            <Button onClick={() => { setErrors([]); setFileList([]); }}>重新选择文件</Button>
            <Button onClick={handleClose}>取消</Button>
          </Space>
        </>
      ) : (
        <>
          <Dragger
            accept=".xlsx"
            fileList={fileList}
            beforeUpload={(file) => {
              if (file.size > 10 * 1024 * 1024) {
                message.error("文件超过 10MB 限制");
                return Upload.LIST_IGNORE;
              }
              handleUpload(file);
              return false;
            }}
            onChange={({ fileList: newList }) => setFileList(newList)}
            disabled={loading}
            maxCount={1}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽 .xlsx 文件到此区域上传</p>
            {hint && <p className="ant-upload-hint">{hint}</p>}
          </Dragger>
          <div style={{ marginTop: 12, textAlign: "center" }}>
            <Link onClick={handleDownloadTemplate}>
              <DownloadOutlined /> 下载导入模板
            </Link>
          </div>
        </>
      )}
    </Modal>
  );
}
```

- [ ] **Step 2: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: 无 TypeScript 错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/shared/ImportExcelDialog.tsx
git commit -m "feat(frontend): add reusable ImportExcelDialog component"
```

---

### Task 11: 供应商页面接入导出/导入

**Files:**
- Modify: `frontend/src/pages/supplier/SupplierListPage.tsx`
- Modify: `frontend/src/api/supplier.ts`

- [ ] **Step 1: 添加 API 函数到 supplier.ts**

在 `frontend/src/api/supplier.ts` 末尾追加：

```typescript
import { downloadExcel, uploadExcel, type ImportResult } from "../utils/excel";

export async function exportSuppliers(params?: Record<string, string | undefined>): Promise<void> {
  await downloadExcel("/suppliers/export", params || {}, `suppliers_${new Date().toISOString().split("T")[0]}.xlsx`);
}

export async function downloadSupplierImportTemplate(): Promise<void> {
  await downloadExcel("/suppliers/import-template", {}, "supplier_import_template.xlsx");
}

export async function importSuppliers(file: File): Promise<ImportResult> {
  return uploadExcel("/suppliers/import", file);
}
```

- [ ] **Step 2: 在 SupplierListPage 添加导出/导入按钮**

在 `SupplierListPage.tsx` 的工具栏区域（现有搜索和筛选按钮附近）添加：

```tsx
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { exportSuppliers, importSuppliers, downloadSupplierImportTemplate } from "../../api/supplier";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";

// 在组件 state 中添加：
const [importOpen, setImportOpen] = useState(false);

// 在工具栏 JSX 中添加按钮：
<Button icon={<DownloadOutlined />} onClick={() => exportSuppliers({
  search: filterName || undefined,
  status: filterStatus,
})}>
  导出
</Button>
<Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
  导入
</Button>

// 在组件末尾添加对话框：
<ImportExcelDialog
  open={importOpen}
  onClose={() => setImportOpen(false)}
  onImported={() => fetchSuppliers()}
  importFn={(file) => importSuppliers(file)}
  templateDownloadFn={downloadSupplierImportTemplate}
  hint="每行包含: 名称*, 简称*, 联系人, 电话, 邮箱, 地址, 供货范围"
/>
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: 无 TypeScript 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/supplier.ts frontend/src/pages/supplier/SupplierListPage.tsx
git commit -m "feat(supplier): add export/import buttons to supplier list page"
```

---

### Task 12: SPC 页面接入导入

**Files:**
- Modify: `frontend/src/pages/spc/SPCDetailPage.tsx`
- Modify: `frontend/src/api/spc.ts`

- [ ] **Step 1: 添加 API 函数到 spc.ts**

在 `frontend/src/api/spc.ts` 末尾追加：

```typescript
import { downloadExcel, uploadExcel, type ImportResult } from "../utils/excel";

export async function downloadSampleImportTemplate(icId: string): Promise<void> {
  await downloadExcel(`/spc/inspection-characteristics/${icId}/samples/import-template`, {}, `spc_samples_template.xlsx`);
}

export async function importSamples(icId: string, file: File): Promise<ImportResult> {
  return uploadExcel(`/spc/inspection-characteristics/${icId}/samples/import`, file);
}
```

- [ ] **Step 2: 替换 SPCDetailPage 中禁用的 Upload.Dragger**

找到 `SPCDetailPage.tsx` 中 `key: "batch"` tab 的 children（line ~801-814），替换禁用的 Upload.Dragger 为：

```tsx
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";
import { importSamples, downloadSampleImportTemplate } from "../../api/spc";

// 替换原有 Upload.Dragger 占位为：
// 注意：useState 必须加在组件顶层，与其他 useState 放一起，不能放进 tab children/JSX 分支里
const [importOpen, setImportOpen] = useState(false);

// 在 "批量导入" tab 的 children 中：
<>
  <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
    上传 Excel 批量导入
  </Button>
  <ImportExcelDialog
    open={importOpen}
    onClose={() => setImportOpen(false)}
    onImported={() => fetchAll()}
    importFn={(file) => importSamples(id!, file)}
    templateDownloadFn={() => downloadSampleImportTemplate(id!)}
    hint={ic?.chart_type === "xbar_r" || ic?.chart_type === "imr"
      ? `每行: 批次号*, 采样时间*, 样本值1${ic?.chart_type === "xbar_r" ? ", 样本值2, ..." : ""}`
      : "每行: 批次号*, 采样时间*, 检验数, 缺陷数"}
  />
</>
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: 无 TypeScript 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/spc.ts frontend/src/pages/spc/SPCDetailPage.tsx
git commit -m "feat(spc): wire up ImportExcelDialog replacing disabled Upload.Dragger"
```

---

### Task 13: IQC 物料页面接入导入

**Files:**
- Modify: `frontend/src/api/iqc.ts`
- Modify: `frontend/src/pages/iqc/` (物料列表页面)

- [ ] **Step 1: 添加 API 函数到 iqc.ts**

在 `frontend/src/api/iqc.ts` 末尾追加：

```typescript
import { downloadExcel, uploadExcel, type ImportResult } from "../utils/excel";

export async function downloadMaterialImportTemplate(): Promise<void> {
  await downloadExcel("/iqc/materials/import-template", {}, "iqc_material_import_template.xlsx");
}

export async function importMaterials(file: File, productLineCode?: string): Promise<ImportResult> {
  return uploadExcel("/iqc/materials/import", file, productLineCode ? { product_line_code: productLineCode } : {});
}
```

- [ ] **Step 2: 在 IQC 物料列表页面添加导入按钮**

在 IQC 物料列表页面的工具栏添加导入按钮和 ImportExcelDialog：

```tsx
import { UploadOutlined } from "@ant-design/icons";
import ImportExcelDialog from "../../components/shared/ImportExcelDialog";
import { importMaterials, downloadMaterialImportTemplate } from "../../api/iqc";

const [importOpen, setImportOpen] = useState(false);

<Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
  导入物料
</Button>

<ImportExcelDialog
  open={importOpen}
  onClose={() => setImportOpen(false)}
  onImported={() => fetchMaterials()}
  importFn={(file) => importMaterials(file)}
  templateDownloadFn={downloadMaterialImportTemplate}
  hint="每行: 物料号*, 名称*, 规格, 类型, 默认AQL, 检验水平, 单位, 产品线"
/>
```

- [ ] **Step 3: 验证编译**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: 无 TypeScript 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/iqc.ts frontend/src/pages/iqc/
git commit -m "feat(iqc): add material import button and dialog to IQC materials page"
```

---

### Task 14: 端到端验证

- [ ] **Step 1: 后端完整构建验证**

```bash
cd backend && python -c "
from app.utils.excel import *
from app.api.supplier import router as sr
from app.api.spc import router as sp
from app.api.iqc import router as ir
print('All backend imports OK')
"
```

Expected: `All backend imports OK`

- [ ] **Step 2: 前端完整构建**

```bash
cd frontend && npm run build
```

Expected: 成功，无 TypeScript 错误

- [ ] **Step 3: API 手动测试（需要后端运行）**

```bash
# 导出供应商
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/export -o suppliers.xlsx

# 下载导入模板
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/import-template -o template.xlsx

# 导入（填写模板后）
curl -F "file=@filled.xlsx" -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/suppliers/import
```

- [ ] **Step 4: 浏览器手动测试**

1. 打开供应商列表页 → 点击"导出" → 验证下载 .xlsx
2. 点击"导入" → 上传 .xlsx → 验证成功/错误提示
3. 打开 SPC 详情页 → "批量导入" tab → 上传样本数据 → 验证图表更新
4. 打开 IQC 物料页 → 点击"导入物料" → 验证模板下载和导入流程

- [ ] **Step 5: 验收点检查**

1. 上传含 `inspected_count = 1.5` 的 SPC 文件 → 应报 "必须为整数（不能为小数）"
2. 上传缺少 "批次号*" 的 SPC 文件 → 应报 "缺少必需表头：批次号*"
3. SPC 批量导入后检查 → 只有 SPCAlarm，无自动 CAPA
