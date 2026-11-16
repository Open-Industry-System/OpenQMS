"""Bound Excel import request bodies before multipart files are spooled."""
import re

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.excel import MAX_UPLOAD_BYTES


MAX_IMPORT_BODY_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
_IMPORT_PATH = re.compile(
    r"(?:/api/suppliers/import|/api/iqc/materials/import|"
    r"/api/spc/inspection-characteristics/[^/]+/samples/import)/?\Z"
)


class ImportBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_IMPORT_BODY_BYTES):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope["method"] != "POST"
                or not _IMPORT_PATH.fullmatch(scope["path"])):
            await self.app(scope, receive, send)
            return

        rejection = JSONResponse({"detail": "IMPORT_BODY_LIMIT"}, status_code=413)
        lengths = [value for key, value in scope["headers"] if key.lower() == b"content-length"]
        if lengths and (len(lengths) != 1 or not lengths[0].isdigit()
                or len(lengths[0]) > 20 or int(lengths[0]) > self.max_body_bytes):
            await rejection(scope, receive, send)
            return

        received = 0
        exceeded = False
        started = False
        rejection_sent = False

        async def bounded_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    exceeded = True
                    # Starlette's multipart parser closes all partial spooled
                    # files for this exception; raising HTTPException would leak
                    # those files on the dependency-body parsing error path.
                    raise MultiPartException("import request body limit exceeded")
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started, rejection_sent
            if rejection_sent:
                return
            if exceeded and not started:
                started = rejection_sent = True
                # Request.form maps MultiPartException to 400. Preserve its
                # spool cleanup while returning the correct fixed 413 response.
                await rejection(scope, receive, send)
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except Exception:
            if not exceeded or started:
                raise
            await rejection(scope, receive, send)
