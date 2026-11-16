"""Pure regression tests for spreadsheet input and output boundaries."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from unittest.mock import patch

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook, load_workbook
from app.utils import excel


def workbook(rows):
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def test_xlsx_export_preserves_strings_as_text_and_numeric_types():
    payload = '=HYPERLINK("https://attacker.invalid","click")'
    wb, ws = excel.create_workbook("export", [payload])
    excel.append_row(ws, [payload, "+cmd", "-2", "@SUM(A1)", -2, 3.5])
    loaded = load_workbook(BytesIO(excel.workbook_to_bytes(wb)))
    assert loaded.active.cell(1, 1).data_type == "s"
    assert loaded.active.cell(2, 1).value == payload
    assert loaded.active.cell(2, 1).data_type == "s"
    assert loaded.active.cell(2, 5).value == -2
    assert loaded.active.cell(2, 5).data_type == "n"


@pytest.mark.parametrize("text", ['=1+1', '+cmd', '-cmd', '@SUM(A1)', '\t=1', '\r=1', '  =1', '\n=1'])
def test_csv_formula_prefixes_are_literal(text):
    assert excel.csv_safe_value(text) == "'" + text


def test_csv_normal_values_keep_types():
    assert excel.csv_safe_value(-2) == -2
    assert excel.csv_safe_value(3.5) == 3.5
    assert excel.csv_safe_value("supplier") == "supplier"


@pytest.mark.asyncio
async def test_upload_read_is_bounded_before_allocating_full_part(monkeypatch):
    monkeypatch.setattr(excel, "MAX_UPLOAD_BYTES", 16)
    upload = UploadFile(BytesIO(b"x" * 100))
    with pytest.raises(HTTPException) as exc:
        await excel.read_upload_bounded(upload)
    assert exc.value.status_code == 413
    assert upload.file.tell() == 17


def test_parser_rejects_bytes_limit_before_openpyxl(monkeypatch):
    monkeypatch.setattr(excel, "MAX_UPLOAD_BYTES", 4)
    with patch("openpyxl.load_workbook") as loader:
        with pytest.raises(excel.ExcelParseError):
            excel.parse_upload(b"x" * 5, {"name": "name"})
        loader.assert_not_called()


@pytest.mark.parametrize("budget,value", [("MAX_ZIP_ENTRIES", 1), ("MAX_ZIP_ENTRY_BYTES", 10), ("MAX_ZIP_TOTAL_BYTES", 10), ("MAX_ZIP_COMPRESSION_RATIO", 1)])
def test_archive_budgets_precede_workbook_parser(monkeypatch, budget, value):
    raw = workbook([["name"], ["supplier"]])
    monkeypatch.setattr(excel, budget, value, raising=False)
    with patch("openpyxl.load_workbook") as loader:
        with pytest.raises(excel.ExcelParseError):
            excel.parse_upload(raw, {"name": "name"})
        loader.assert_not_called()


def test_parser_stops_at_physical_row_budget(monkeypatch):
    raw = workbook([["name"], [None], [None], ["supplier"]])
    monkeypatch.setattr(excel, "MAX_IMPORT_ROWS", 2)
    with pytest.raises(excel.ExcelParseError):
        excel.parse_upload(raw, {"name": "name"})


def test_parser_rejects_sparse_wide_dimensions_before_openpyxl():
    raw = workbook([["name"]])
    out = BytesIO()
    with ZipFile(BytesIO(raw)) as original, ZipFile(out, "w", ZIP_DEFLATED) as target:
        for item in original.infolist():
            data = original.read(item)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data.replace(b'A1:A1', b'A1:XFD1048576')
            target.writestr(item.filename, data)
    with patch("openpyxl.load_workbook") as loader:
        with pytest.raises(excel.ExcelParseError):
            excel.parse_upload(out.getvalue(), {"name": "name"})
        loader.assert_not_called()


def test_normal_import_still_reads_values():
    assert excel.parse_upload(workbook([["name"], [" supplier "]]), {"name": "name"}) == [{"_row": 2, "name": "supplier"}]


def replace_sheet(raw, content):
    output = BytesIO()
    with ZipFile(BytesIO(raw)) as original, ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for item in original.infolist():
            target.writestr(item.filename, content if item.filename == 'xl/worksheets/sheet1.xml' else original.read(item))
    return output.getvalue()


def test_implicit_cells_cannot_bypass_column_budget(monkeypatch):
    monkeypatch.setattr(excel, 'MAX_IMPORT_COLUMNS', 2)
    xml = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c/><c/><c/></row></sheetData></worksheet>'
    with patch('openpyxl.load_workbook') as loader:
        with pytest.raises(excel.ExcelParseError):
            excel.parse_upload(replace_sheet(workbook([['name']]), xml), {'name': 'name'})
        loader.assert_not_called()


def test_utf16_entity_declarations_are_rejected_before_openpyxl():
    xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE worksheet [<!ENTITY x "text">]><worksheet>&x;</worksheet>'.encode('utf-16')
    with patch('openpyxl.load_workbook') as loader:
        with pytest.raises(excel.ExcelParseError):
            excel.parse_upload(replace_sheet(workbook([['name']]), xml), {'name': 'name'})
        loader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['excel', 'csv'])
async def test_heatmap_export_neutralizes_all_text_fields(monkeypatch, format):
    import csv
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services.supply_chain_risk_map import service
    payload = '=HYPERLINK("https://attacker.invalid","click")'
    heatmap = SimpleNamespace(columns=[SimpleNamespace(label=payload)], rows=[SimpleNamespace(
        supplier_name=payload, cells=[SimpleNamespace(value=-2.5, source=payload)]
    )])
    monkeypatch.setattr(service, 'get_heatmap_data', AsyncMock(return_value=heatmap))
    response = await service.export_heatmap(None, None, '2026-11', format)
    chunks = [chunk async for chunk in response.body_iterator]
    if format == 'excel':
        sheet = load_workbook(BytesIO(b''.join(chunks))).active
        assert sheet['A2'].value == payload
        assert sheet['A2'].data_type == 's'
        assert sheet['B2'].value == -2.5
        assert sheet['D2'].data_type == 's'
        assert sheet['B1'].data_type == 's'
    else:
        rows = list(csv.reader(''.join(chunks).splitlines()))
        assert rows[0][1] == "'" + payload
        assert rows[1] == ["'" + payload, '-2.5', '', "'" + payload]
