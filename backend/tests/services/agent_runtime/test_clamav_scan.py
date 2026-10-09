"""Strict wire-contract tests for the private attachment ClamAV client."""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import pytest


def scan_module():
    try:
        from app.services.agent_runtime import clamav_scan
    except ImportError:
        pytest.fail("ClamAV scanner is not implemented")
    return clamav_scan


async def chunks(values: list[bytes]) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@dataclass
class StrictClamd:
    reply: bytes = b"stream: OK\0"
    version_reply: bytes = b"ClamAV 1.4.2/12345\0"
    frames: list[bytes] = field(default_factory=list)
    version_command: bytes | None = None
    _server: asyncio.AbstractServer | None = None

    @property
    def address(self):
        assert self._server is not None
        host, port = self._server.sockets[0].getsockname()[:2]
        return {"host": host, "port": port, "timeout_seconds": 60}

    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.version_command = await reader.readuntil(b"\0")
        writer.write(self.version_reply)
        await writer.drain()
        try:
            command = await reader.readuntil(b"\0")
        except asyncio.IncompleteReadError:
            return
        assert command == b"zINSTREAM\0"
        while True:
            size = int.from_bytes(await reader.readexactly(4), "big")
            if size == 0:
                self.frames.append(b"")
                break
            self.frames.append(await reader.readexactly(size))
        writer.write(self.reply)
        await writer.drain()
        writer.close()
        await writer.wait_closed()


@asynccontextmanager
async def strict_clamd_server(reply: bytes = b"stream: OK\0"):
    clamd = StrictClamd(reply=reply)
    clamd._server = await asyncio.start_server(clamd.handler, "127.0.0.1", 0)
    try:
        yield clamd
    finally:
        clamd._server.close()
        await clamd._server.wait_closed()


@pytest.mark.asyncio
async def test_scan_stream_sends_zinstream_and_zero_terminator():
    async with strict_clamd_server() as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"abc"]), **strict_clamd.address)

    assert result.outcome == "clean"
    assert result.scanner_version == "ClamAV 1.4.2/12345"
    assert result.failure_code is None
    assert strict_clamd.version_command == b"zVERSIONCOMMANDS\0"
    assert strict_clamd.frames == [b"abc", b""]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version_reply",
    [b"anything\0", b"stream: ERROR\0", b"ClamAV 1.4.2/12345\0extra\0"],
)
async def test_scan_stream_rejects_invalid_version_negotiation(version_reply):
    async with strict_clamd_server() as strict_clamd:
        strict_clamd.version_reply = version_reply
        result = await scan_module().scan_stream(chunks([b"x"]), **strict_clamd.address)

    assert result.outcome == "unavailable"
    assert result.scanner_version is None
    assert result.failure_code == "scanner_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [b"stream: Heuristics.Limits.Exceeded FOUND\0", b"stream: Encrypted.Doc FOUND\0"],
)
async def test_scan_stream_rejects_all_found_replies(reply):
    async with strict_clamd_server(reply) as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"x"]), **strict_clamd.address)

    assert result.outcome == "found"
    assert result.scanner_version == "ClamAV 1.4.2/12345"
    assert result.failure_code is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [b"stream: ERROR\0", b"stream: OK\0extra", b"unexpected: CLEAN\0"],
)
async def test_scan_stream_maps_error_or_malformed_reply_to_unavailable(reply):
    async with strict_clamd_server(reply) as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"x"]), **strict_clamd.address)

    assert result.outcome == "unavailable"
    assert result.scanner_version is None
    assert result.failure_code is not None
