"""Pure ASGI regressions for pre-parser Excel import body limits."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, File, UploadFile
from starlette import formparsers


PATHS = ["/api/suppliers/import", "/api/iqc/materials/import",
    "/api/spc/inspection-characteristics/5b032ecd-41ce-4914-a3d4-443ccf01cbe0/samples/import"]


async def request(app, path, chunks, *, headers=()):
    messages = []
    consumed = []
    iterator = iter(chunks)
    async def receive():
        try:
            chunk = next(iterator)
        except StopIteration:
            return {"type": "http.disconnect"}
        consumed.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": len(consumed) < len(chunks)}
    async def send(message):
        messages.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "method": "POST", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "server": ("test", 80), "client": ("test", 1), "headers": list(headers)}
    await app(scope, receive, send)
    return messages, consumed


def middleware(app, limit):
    from app.core.import_body_limit import ImportBodyLimitMiddleware
    return ImportBodyLimitMiddleware(app, max_body_bytes=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", PATHS)
async def test_declared_oversize_is_rejected_before_body_or_downstream(path):
    async def downstream(*_args):
        pytest.fail("oversize request reached downstream")
    messages, consumed = await request(middleware(downstream, 8), path, [b"unused"], headers=[(b"content-length", b"9")])
    assert consumed == []
    assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [413]


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [None, b"1"])
async def test_chunked_or_false_length_upload_stops_before_spooling_entire_body(monkeypatch, declared):
    app = FastAPI()
    reached = []
    @app.post(PATHS[0])
    async def upload(file: UploadFile = File(...)):
        reached.append(True)
        return {"size": len(await file.read())}
    files = []
    original = formparsers.SpooledTemporaryFile
    def observe_spool(*args, **kwargs):
        file = original(*args, **kwargs)
        files.append(file)
        return file
    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", observe_spool)
    prefix = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="file.xlsx"\r\n\r\n'
    headers = [(b"content-type", b"multipart/form-data; boundary=boundary")]
    if declared is not None:
        headers.append((b"content-length", declared))
    messages, consumed = await request(middleware(app, len(prefix) + 16), PATHS[0], [prefix, b"a" * 8, b"b" * 32, b"never-read" * 1000], headers=headers)
    assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [413]
    assert len(consumed) == 3
    assert reached == []
    assert files and all(file.closed for file in files)
    body = b"".join(m.get("body", b"") for m in messages)
    assert json.loads(body)["detail"] == "IMPORT_BODY_LIMIT"


@pytest.mark.asyncio
async def test_unrelated_routes_keep_their_existing_body_policy():
    async def downstream(scope, receive, send):
        assert len((await receive())["body"]) == 100
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    messages, _ = await request(middleware(downstream, 8), "/api/other", [b"x" * 100], headers=[(b"content-length", b"100")])
    assert messages[0]["status"] == 200


def test_main_registers_pre_parser_import_guard():
    from app.main import app
    assert "ImportBodyLimitMiddleware" in {entry.cls.__name__ for entry in app.user_middleware}


@pytest.mark.parametrize("filename", ["Caddyfile", "preview-Caddyfile", "production-edge-Caddyfile"])
def test_caddy_import_routes_have_request_body_budget(filename):
    config = (Path(__file__).resolve().parents[3] / "deploy" / filename).read_text()
    assert "request_body @excel_imports" in config
    assert "max_size 10551296" in config
    assert "/api/suppliers/import" in config and "/api/iqc/materials/import" in config
    assert "/api/spc/inspection-characteristics/*/samples/import" in config


@pytest.mark.asyncio
async def test_valid_bounded_multipart_upload_reaches_endpoint():
    app = FastAPI()
    @app.post(PATHS[0])
    async def upload(file: UploadFile = File(...)):
        return {"size": len(await file.read())}
    content = (b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="safe.xlsx"\r\n\r\n'
        b'clean\r\n--boundary--\r\n')
    messages, consumed = await request(middleware(app, len(content)), PATHS[0], [content],
        headers=[(b"content-type", b"multipart/form-data; boundary=boundary")])
    assert messages[0]["status"] == 200
    assert json.loads(messages[1]["body"]) == {"size": 5}
    assert consumed == [len(content)]
