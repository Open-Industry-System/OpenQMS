"""Content-safe HTTP boundary for scan-gated task attachments."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import AsyncIterator
from typing import Final
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.core.deps import RequestScope, get_request_scope
from app.database import get_db
from app.schemas.agent_attachment import AttachmentAvailability, AttachmentList, AttachmentOut
from app.services.agent_runtime import task_attachments, task_service


_MAX_PART_HEADERS: Final = 16 * 1024
_BOUNDARY_RE: Final = re.compile(
    r'^\s*multipart/form-data\s*;\s*boundary=(?:"([^"]+)"|([^;\s]+))\s*$', re.IGNORECASE,
)
_BOUNDARY_BYTES_RE: Final = re.compile(br"[0-9A-Za-z'()+_,./:=?-]{1,70}\Z")
_FILE_DISPOSITION_RE: Final = re.compile(
    br'form-data;\s*name="file"(?:;\s*filename="(?P<filename>(?:[^"\\\r\n]|\\.)*)")?\Z', re.IGNORECASE,
)
_ALLOWED_EXTENSIONS: Final = frozenset({"pdf", "png", "jpg", "jpeg", "txt", "csv", "docx", "xlsx"})


class _EmptyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MultipartInputInvalid(task_attachments.AttachmentInputLimitError):
    """Uses Task 3's safe terminal cleanup while retaining a distinct HTTP code."""


class ContentSafeAttachmentRoute(APIRoute):
    """Suppress framework validation payloads without consuming attachment bodies."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "ATTACHMENT_INPUT_INVALID"})

        return guarded


def _multipart_boundary(content_type: str | None) -> bytes:
    match = _BOUNDARY_RE.fullmatch(content_type or "")
    if match is None:
        raise MultipartInputInvalid("invalid multipart content type")
    try:
        boundary = (match.group(1) or match.group(2)).encode("ascii")
    except UnicodeEncodeError as exc:
        raise MultipartInputInvalid("invalid multipart boundary") from exc
    if _BOUNDARY_BYTES_RE.fullmatch(boundary) is None:
        raise MultipartInputInvalid("invalid multipart boundary")
    return boundary


class AttachmentTypeRejected(task_attachments.AttachmentInputRejected):
    """The client name is absent, unsafe, or outside the controlled allowlist."""


def _attachment_metadata(
    raw_filename: bytes,
    raw_content_type: bytes | None,
) -> task_attachments.AttachmentUploadMetadata:
    try:
        filename = re.sub(br"\\(.)", rb"\1", raw_filename).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MultipartInputInvalid("invalid attachment filename") from exc
    filename = unicodedata.normalize("NFC", filename)
    if (
        not filename
        or len(filename) > 255
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        raise MultipartInputInvalid("invalid attachment filename")
    stem, separator, extension = filename.rpartition(".")
    if not separator or not stem or not extension or extension.casefold() not in _ALLOWED_EXTENSIONS:
        raise AttachmentTypeRejected("attachment extension is rejected")
    if raw_content_type is None:
        declared_content_type = None
    else:
        try:
            declared_content_type = raw_content_type.decode("ascii")
        except UnicodeDecodeError as exc:
            raise MultipartInputInvalid("invalid attachment content type") from exc
        if len(declared_content_type) > 255:
            raise MultipartInputInvalid("invalid attachment content type")
    return task_attachments.AttachmentUploadMetadata(
        display_name=filename,
        extension=extension.casefold(),
        declared_content_type=declared_content_type,
    )


def _validate_part_headers(raw_headers: bytes) -> task_attachments.AttachmentUploadMetadata:
    fields: dict[bytes, bytes] = {}
    for line in raw_headers.split(b"\r\n"):
        if not line or b":" not in line:
            raise MultipartInputInvalid("invalid multipart headers")
        name, value = line.split(b":", 1)
        name = name.strip().lower()
        value = value.strip()
        if name in fields or name not in {b"content-disposition", b"content-type"}:
            raise MultipartInputInvalid("invalid multipart headers")
        if any(byte < 32 or byte == 127 for byte in value):
            raise MultipartInputInvalid("invalid multipart headers")
        fields[name] = value
    disposition = fields.get(b"content-disposition")
    match = _FILE_DISPOSITION_RE.fullmatch(disposition or b"")
    if match is None:
        raise MultipartInputInvalid("invalid multipart file part")
    raw_filename = match.group("filename")
    if raw_filename is None:
        raise AttachmentTypeRejected("attachment filename is required")
    return _attachment_metadata(raw_filename, fields.get(b"content-type"))


async def _file_part_chunks(
    stream: AsyncIterator[bytes],
    boundary: bytes,
    metadata: task_attachments.AttachmentUploadMetadata,
) -> AsyncIterator[bytes]:
    """Yield exactly one form-data file payload without buffering the payload."""
    opening = b"--" + boundary + b"\r\n"
    delimiter = b"\r\n--" + boundary
    header_buffer = bytearray()
    body_buffer: bytearray | None = None
    complete = False

    async for chunk in stream:
        if not isinstance(chunk, bytes):
            raise MultipartInputInvalid("invalid multipart stream")
        if complete:
            if chunk:
                raise MultipartInputInvalid("unexpected multipart data")
            continue
        started_body = False
        if body_buffer is None:
            header_buffer.extend(chunk)
            opening_prefix = min(len(header_buffer), len(opening))
            if header_buffer[:opening_prefix] != opening[:opening_prefix]:
                raise MultipartInputInvalid("invalid multipart opening boundary")
            if len(header_buffer) < len(opening):
                continue
            headers_start = len(opening)
            headers_end = header_buffer.find(b"\r\n\r\n", headers_start)
            if headers_end < 0:
                if len(header_buffer) - headers_start > _MAX_PART_HEADERS:
                    raise MultipartInputInvalid("multipart headers too large")
                continue
            if headers_end - headers_start > _MAX_PART_HEADERS:
                raise MultipartInputInvalid("multipart headers too large")
            parsed_metadata = _validate_part_headers(bytes(header_buffer[headers_start:headers_end]))
            metadata.display_name = parsed_metadata.display_name
            metadata.extension = parsed_metadata.extension
            metadata.declared_content_type = parsed_metadata.declared_content_type
            del header_buffer[:headers_end + 4]
            body_buffer = header_buffer
            started_body = True

        if not started_body:
            body_buffer.extend(chunk)
        while not complete:
            marker_at = body_buffer.find(delimiter)
            if marker_at < 0:
                keep = len(delimiter) + 4
                if len(body_buffer) > keep:
                    safe_size = len(body_buffer) - keep
                    yield bytes(body_buffer[:safe_size])
                    del body_buffer[:safe_size]
                break
            marker_end = marker_at + len(delimiter)
            if len(body_buffer) < marker_end + 2:
                if marker_at:
                    yield bytes(body_buffer[:marker_at])
                    del body_buffer[:marker_at]
                break
            if marker_at:
                yield bytes(body_buffer[:marker_at])
                del body_buffer[:marker_at]
                marker_end = len(delimiter)
            suffix = body_buffer[marker_end:marker_end + 2]
            if suffix == b"\r\n":
                raise MultipartInputInvalid("multiple multipart parts are not allowed")
            if suffix != b"--":
                raise MultipartInputInvalid("invalid multipart closing boundary")
            if len(body_buffer) < marker_end + 4:
                break
            if body_buffer[marker_end + 2:marker_end + 4] != b"\r\n":
                raise MultipartInputInvalid("invalid multipart closing boundary")
            del body_buffer[:marker_end + 4]
            if body_buffer:
                raise MultipartInputInvalid("unexpected multipart data")
            complete = True

    if body_buffer is None or not complete:
        raise MultipartInputInvalid("incomplete multipart input")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, AttachmentTypeRejected):
        return HTTPException(status_code=422, detail="ATTACHMENT_TYPE_REJECTED")
    if isinstance(exc, MultipartInputInvalid):
        return HTTPException(status_code=422, detail="ATTACHMENT_INPUT_INVALID")
    if isinstance(exc, task_attachments.AttachmentInputLimitError):
        return HTTPException(status_code=413, detail="ATTACHMENT_INPUT_LIMIT")
    if isinstance(exc, task_attachments.AttachmentSourceChanged | task_attachments.AttachmentTaskStateError):
        return HTTPException(status_code=409, detail="ATTACHMENT_SOURCE_CHANGED")
    if isinstance(exc, task_attachments.AttachmentCapacityError):
        return HTTPException(status_code=503, detail="ATTACHMENT_CAPACITY_BUSY")
    if isinstance(exc, (PermissionError, LookupError)):
        return HTTPException(status_code=404, detail="Not Found")
    return HTTPException(status_code=500, detail="ATTACHMENT_UNAVAILABLE")


def _upload_result(view: task_attachments.AttachmentView) -> AttachmentView:
    if view.status == "available":
        return view
    if view.status == "rejected_malware":
        raise HTTPException(status_code=422, detail="ATTACHMENT_MALWARE_REJECTED")
    if view.status == "rejected_scanner":
        raise HTTPException(status_code=503, detail="ATTACHMENT_SCANNER_UNAVAILABLE")
    raise HTTPException(status_code=500, detail="ATTACHMENT_UNAVAILABLE")


def require_attachments() -> None:
    if not settings.AGENT_TASK_ATTACHMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(
    prefix="/api/agent/tasks/{task_id}/attachments",
    tags=["agent-task-attachments"],
    route_class=ContentSafeAttachmentRoute,
    dependencies=[Depends(require_attachments)],
)


@router.get("/availability", response_model=AttachmentAvailability)
async def availability(
    task_id: UUID,
    query: _EmptyQuery = Query(),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    try:
        await task_service.get_task_for_view(db, scope, task_id)
        return {"enabled": True}
    except (PermissionError, LookupError, ValueError, RuntimeError) as exc:
        raise _error(exc) from None


@router.post("", response_model=AttachmentOut)
async def upload(
    task_id: UUID,
    request: Request,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    try:
        async with await task_attachments.reserve_upload(db, scope, task_id) as reservation:
            boundary = _multipart_boundary(request.headers.get("content-type"))
            metadata = task_attachments.AttachmentUploadMetadata()
            view = await task_attachments.receive_and_scan(
                reservation,
                _file_part_chunks(request.stream(), boundary, metadata),
                metadata,
            )
        return _upload_result(view)
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(exc) from None


@router.get("", response_model=AttachmentList)
async def list_attachments(
    task_id: UUID,
    query: _EmptyQuery = Query(),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    try:
        return {"items": await task_attachments.list_for_view(db, scope, task_id)}
    except (PermissionError, LookupError, ValueError, RuntimeError) as exc:
        raise _error(exc) from None


@router.get("/{attachment_id}/download")
async def download(
    task_id: UUID,
    attachment_id: UUID,
    query: _EmptyQuery = Query(),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    try:
        handle = await task_attachments.open_download(db, scope, task_id, attachment_id)
    except (PermissionError, LookupError, ValueError, RuntimeError) as exc:
        raise _error(exc) from None

    def body():
        try:
            while chunk := handle.stream.read(64 * 1024):
                yield chunk
        finally:
            handle.stream.close()

    return StreamingResponse(body(), headers=handle.headers)


@router.delete("/{attachment_id}", status_code=204)
async def delete(
    task_id: UUID,
    attachment_id: UUID,
    query: _EmptyQuery = Query(),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    try:
        await task_attachments.purge_for_owner(db, scope, task_id, attachment_id)
    except (PermissionError, LookupError, ValueError, OSError, RuntimeError) as exc:
        raise _error(exc) from None
    return Response(status_code=204)
