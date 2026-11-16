# backend/app/utils/excel.py
import urllib.parse
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

# ─── 常量 ───
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1677FF", end_color="1677FF", fill_type="solid")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")

MAX_EXPORT_ROWS = 10000
MAX_IMPORT_ROWS = 5000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_ENTRIES = 1000
MAX_ZIP_ENTRY_BYTES = 8 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 32 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 200
MAX_IMPORT_COLUMNS = 256
MAX_IMPORT_CELLS = 250000
MAX_IMPORT_SHEETS = 16


def create_workbook(sheet_name: str, headers: list[str]) -> tuple[Workbook, Worksheet]:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    append_row(ws, headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
    return wb, ws


def append_row(ws: Worksheet, values: list[Any]) -> None:
    ws.append(values)
    # openpyxl infers a leading '=' as a formula. Export business strings literally.
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"


def csv_safe_value(value: Any) -> Any:
    """Neutralize spreadsheet formula prefixes without converting numeric values."""
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


async def read_upload_bounded(file: UploadFile) -> bytes:
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")
    return raw


def auto_width(ws: Worksheet, min_width: int = 10, max_width: int = 40) -> None:
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max(min(max_len + 2, max_width), min_width)


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
        append_row(ws, example_row)
    return workbook_to_bytes(wb)


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


def _validate_archive(file_bytes: bytes) -> None:
    """Budget expansion and worksheet dimensions before openpyxl allocates objects."""
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string, range_boundaries

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ExcelParseError("文件超过 10MB 限制")
    with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or len({i.filename for i in entries}) != len(entries):
            raise ExcelParseError("工作簿 ZIP 条目过多或重复")
        total = 0
        for entry in entries:
            total += entry.file_size
            if (entry.file_size > MAX_ZIP_ENTRY_BYTES or total > MAX_ZIP_TOTAL_BYTES
                    or entry.file_size > MAX_ZIP_COMPRESSION_RATIO * max(1, entry.compress_size)):
                raise ExcelParseError("工作簿解压大小或压缩比超过限制")
        sheets = [e for e in entries if e.filename.startswith("xl/worksheets/") and e.filename.endswith(".xml")]
        if len(sheets) > MAX_IMPORT_SHEETS:
            raise ExcelParseError("工作表数量超过限制")
        cell_count = 0
        for entry in entries:
            if not entry.filename.endswith((".xml", ".rels")):
                continue
            # Bounded by metadata above; reject entity declarations in every XML part.
            xml = archive.read(entry)
            upper = xml.upper().replace(b"\x00", b"")
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ExcelParseError("工作簿不允许 XML 实体声明")
            # Inspect all XML parts: relationship targets can use nonstandard paths.
            rows = 0
            row_cells = 0
            for _, element in ElementTree.iterparse(BytesIO(xml), events=("end",)):
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "dimension":
                    _, _, max_col, max_row = range_boundaries(element.attrib["ref"])
                    if max_col > MAX_IMPORT_COLUMNS or max_row > MAX_IMPORT_ROWS + 1:
                        raise ExcelParseError("工作表行数或列数超过限制")
                elif tag == "row":
                    rows += 1
                    row_cells = 0
                    if rows > MAX_IMPORT_ROWS + 1 or int(element.attrib.get("r", rows)) > MAX_IMPORT_ROWS + 1:
                        raise ExcelParseError("导入行数超过限制")
                elif tag == "c":
                    cell_count += 1
                    row_cells += 1
                    if row_cells > MAX_IMPORT_COLUMNS:
                        raise ExcelParseError("工作表列数超过限制")
                    ref = element.attrib.get("r")
                    if ref:
                        col, row = coordinate_from_string(ref)
                        if column_index_from_string(col) > MAX_IMPORT_COLUMNS or row > MAX_IMPORT_ROWS + 1:
                            raise ExcelParseError("工作表单元格范围超过限制")
                    if cell_count > MAX_IMPORT_CELLS:
                        raise ExcelParseError("工作簿单元格数量超过限制")
                element.clear()


def parse_upload(
    file_bytes: bytes,
    header_mapping: dict[str, str],
    required_headers: list[str] | None = None,
    sheet_index: int = 0,
) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
        from openpyxl.utils.exceptions import InvalidFileException
        _validate_archive(file_bytes)
        wb = load_workbook(BytesIO(file_bytes), read_only=True, keep_links=False)
    except (zipfile.BadZipFile, OSError, InvalidFileException, ElementTree.ParseError, ValueError, KeyError) as e:
        raise ExcelParseError(f"文件格式无效，仅支持 .xlsx 格式: {e}")

    try:
        if sheet_index < 0 or sheet_index >= len(wb.worksheets):
            raise ExcelParseError("工作表不存在")
        ws = wb.worksheets[sheet_index]
        if (ws.max_row or 0) > MAX_IMPORT_ROWS + 1 or (ws.max_column or 0) > MAX_IMPORT_COLUMNS:
            raise ExcelParseError("工作表行数或列数超过限制")
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
            if row_idx > MAX_IMPORT_ROWS + 1:
                raise ExcelParseError("导入行数超过限制")
            record = {}
            all_none = True
            for col_idx, internal_key in col_map.items():
                value = row[col_idx] if col_idx < len(row) else None
                if value is not None:
                    # trim 字符串值，避免 "   " 通过必填校验
                    if isinstance(value, str):
                        value = value.strip()
                    if value is not None and value != "":
                        record[internal_key] = value
                        all_none = False
            if not all_none:
                rows.append({"_row": row_idx, **record})

        return rows
    finally:
        wb.close()


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
