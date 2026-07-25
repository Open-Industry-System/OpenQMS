"""PPT 响应助手（镜像 utils/excel.py 的 excel_response）。"""
import urllib.parse
from io import BytesIO

from fastapi.responses import StreamingResponse


def pptx_response(pptx_bytes: bytes, filename: str, headers: dict | None = None) -> StreamingResponse:
    encoded = urllib.parse.quote(filename)
    return StreamingResponse(
        BytesIO(pptx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}", **(headers or {})},
    )
