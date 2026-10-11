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
    reply: bytes = b"stream: OK\n"
    version_reply: bytes = b"ClamAV 1.4.2/12345\nCOMMANDS: INSTREAM VERSIONCOMMANDS\n"
    frames: list[bytes] = field(default_factory=list)
    version_command: bytes | None = None
    hold_open_after_reply: bool = False
    _server: asyncio.AbstractServer | None = None

    @property
    def address(self):
        assert self._server is not None
        host, port = self._server.sockets[0].getsockname()[:2]
        return {"host": host, "port": port, "timeout_seconds": 1}

    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        command = await reader.readuntil(b"\n")
        if command == b"nVERSIONCOMMANDS\n":
            self.version_command = command
            writer.write(self.version_reply)
            await writer.drain()
            await reader.read()
            return
        assert command == b"nINSTREAM\n"
        while True:
            size = int.from_bytes(await reader.readexactly(4), "big")
            if size == 0:
                self.frames.append(b"")
                break
            self.frames.append(await reader.readexactly(size))
        writer.write(self.reply)
        await writer.drain()
        if self.hold_open_after_reply:
            await reader.read()
            return
        writer.close()
        await writer.wait_closed()


@asynccontextmanager
async def strict_clamd_server(reply: bytes = b"stream: OK\n", *, hold_open_after_reply: bool = False):
    clamd = StrictClamd(reply=reply, hold_open_after_reply=hold_open_after_reply)
    clamd._server = await asyncio.start_server(clamd.handler, "127.0.0.1", 0)
    try:
        yield clamd
    finally:
        clamd._server.close()
        await clamd._server.wait_closed()


@pytest.mark.asyncio
async def test_scan_stream_sends_newline_instream_and_zero_terminator():
    async with strict_clamd_server() as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"abc"]), **strict_clamd.address)

    assert result.outcome == "clean"
    assert result.scanner_version == "ClamAV 1.4.2/12345"
    assert result.failure_code is None
    assert strict_clamd.version_command == b"nVERSIONCOMMANDS\n"
    assert strict_clamd.frames == [b"abc", b""]


@pytest.mark.asyncio
async def test_scan_stream_accepts_valid_result_when_daemon_keeps_socket_open():
    async with strict_clamd_server(hold_open_after_reply=True) as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"abc"]), **strict_clamd.address)

    assert result.outcome == "clean"
    assert result.scanner_version == "ClamAV 1.4.2/12345"
    assert strict_clamd.frames == [b"abc", b""]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version_reply", "expected_version"),
    (
        (b"ClamAV 1.4.2/12345\nCOMMANDS: INSTREAM VERSIONCOMMANDS\n", "ClamAV 1.4.2/12345"),
        (b"ClamAV 1.4.2/12345\nCOMMANDS: VERSIONCOMMANDS INSTREAM\n", "ClamAV 1.4.2/12345"),
        (
            b"ClamAV 1.4.3/28150/Sun Oct 11 06:26:01 2026| COMMANDS: VERSIONCOMMANDS INSTREAM\n",
            "ClamAV 1.4.3/28150/Sun Oct 11 06:26:01 2026",
        ),
    ),
)
async def test_scan_stream_accepts_newline_versioncommands_record(version_reply, expected_version):
    async with strict_clamd_server() as strict_clamd:
        strict_clamd.version_reply = version_reply
        result = await scan_module().scan_stream(chunks([b"abc"]), **strict_clamd.address)

    assert result.outcome == "clean"
    assert result.scanner_version == expected_version
    assert strict_clamd.frames == [b"abc", b""]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "version_reply",
    [b"anything\n", b"stream: ERROR\n", b"ClamAV 1.4.2/12345\nextra\n"],
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
    [b"stream: Heuristics.Limits.Exceeded FOUND\n", b"stream: Encrypted.Doc FOUND\n"],
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
    [b"stream: ERROR\n", b"stream: OK\nextra", b"unexpected: CLEAN\n"],
)
async def test_scan_stream_maps_error_or_malformed_reply_to_unavailable(reply):
    async with strict_clamd_server(reply) as strict_clamd:
        result = await scan_module().scan_stream(chunks([b"x"]), **strict_clamd.address)

    assert result.outcome == "unavailable"
    assert result.scanner_version is None
    assert result.failure_code is not None


@pytest.mark.asyncio
async def test_scan_stream_propagates_input_limit_from_reader():
    from app.services.agent_runtime.task_attachments import AttachmentInputLimitError

    async def limited_reader():
        raise AttachmentInputLimitError("input limit")
        yield b""

    async with strict_clamd_server() as strict_clamd:
        with pytest.raises(AttachmentInputLimitError):
            await scan_module().scan_stream(limited_reader(), **strict_clamd.address)
