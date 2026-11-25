"""ASGI middleware that translates JSON response messages per Accept-Language."""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.i18n import _CJK, pick_language, request_language, translate_json

# Do not buffer very large payloads (e.g. exports); they pass through unchanged.
_MAX_BODY = 5 * 1024 * 1024


class ResponseTranslationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        lang = pick_language(headers.get("accept-language"))
        if lang is None:
            await self.app(scope, receive, send)
            return
        token = request_language.set(lang)
        try:
            await self._call(scope, receive, send, lang)
        finally:
            request_language.reset(token)

    async def _call(self, scope: Scope, receive: Receive, send: Send, lang: str) -> None:
        start: Message | None = None
        chunks: list[bytes] = []
        passthrough = False

        async def wrapped_send(message: Message) -> None:
            nonlocal start, passthrough
            if message["type"] == "http.response.start":
                ctype = ""
                for k, v in message.get("headers", []):
                    if k.decode("latin-1").lower() == "content-type":
                        ctype = v.decode("latin-1").lower()
                if not ctype.startswith("application/json"):
                    passthrough = True
                    await send(message)
                else:
                    start = message
                return
            if message["type"] != "http.response.body" or passthrough:
                await send(message)
                return
            chunks.append(message.get("body", b""))
            size = sum(len(c) for c in chunks)
            if message.get("more_body", False) and size <= _MAX_BODY:
                return
            body = b"".join(chunks)
            if not message.get("more_body", False):
                body = _translate_body(body, lang)
            assert start is not None
            hdrs = [(k, v) for k, v in start.get("headers", []) if k.decode("latin-1").lower() != "content-length"]
            if not message.get("more_body", False):
                hdrs.append((b"content-length", str(len(body)).encode("latin-1")))
            await send({**start, "headers": hdrs})
            await send({"type": "http.response.body", "body": body, "more_body": message.get("more_body", False)})
            passthrough = True  # stream the rest unchanged

        await self.app(scope, receive, wrapped_send)


def _translate_body(body: bytes, lang: str) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    if not _CJK.search(text):
        return body
    try:
        data = json.loads(text)
    except ValueError:
        return body
    return json.dumps(translate_json(data, lang), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
