"""Strict, fail-closed ClamAV newline-INSTREAM client for private attachments."""
from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal


_VERSION_REPLY = re.compile(rb"ClamAV [0-9]+(?:\.[0-9]+)+/[0-9]+(?:/[^\r\n\0]{1,200})?")
_COMMANDS_REPLY = re.compile(rb"COMMANDS: [A-Z][A-Z_]*(?: [A-Z][A-Z_]*){0,255}")


@dataclass(frozen=True)
class ScanResult:
    outcome: Literal["clean", "found", "unavailable"]
    scanner_version: str | None
    failure_code: str | None


class _ReaderValueError(Exception):
    """Separates caller stream validation from scanner protocol failures."""


async def _reader_chunks(reader: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    try:
        async for chunk in reader:
            yield chunk
    except ValueError as exc:
        raise _ReaderValueError from exc


async def scan_stream(
    reader: AsyncIterator[bytes], *, host: str, port: int, timeout_seconds: int
) -> ScanResult:
    """Scan a byte stream over one bounded, strict ClamAV exchange."""
    if not host or not 0 < port <= 65535 or not 0 < timeout_seconds <= 60:
        return ScanResult("unavailable", None, "scanner_unavailable")

    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            stream_reader, writer = await asyncio.open_connection(host, port)
            writer.write(b"nVERSIONCOMMANDS\n")
            await writer.drain()
            version = await _version_commands(stream_reader)

            writer.write(b"nINSTREAM\n")
            async for chunk in _reader_chunks(reader):
                if not isinstance(chunk, bytes):
                    raise ValueError("scanner stream must contain bytes")
                if not chunk:
                    continue
                writer.write(len(chunk).to_bytes(4, "big") + chunk)
                await writer.drain()
            writer.write((0).to_bytes(4, "big"))
            await writer.drain()

            reply = await _read_final_reply(stream_reader)
            outcome = _parse_outcome(reply)
            if outcome is not None:
                return ScanResult(outcome, version, None)
            return ScanResult("unavailable", None, "scanner_unavailable")
    except _ReaderValueError as exc:
        raise exc.__cause__ from None
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError, TypeError, OverflowError):
        return ScanResult("unavailable", None, "scanner_unavailable")
    finally:
        if writer is not None:
            writer.close()


async def _read_line(reader: asyncio.StreamReader) -> bytes:
    reply = await reader.readuntil(b"\n")
    if len(reply) > 4096 or not reply.endswith(b"\n"):
        raise ValueError("scanner reply is not newline framed")
    return reply[:-1]


async def _read_final_reply(reader: asyncio.StreamReader) -> bytes:
    reply = await _read_line(reader)
    if bytes(reader._buffer).strip():
        raise ValueError("scanner reply has trailing data")
    return reply


def _parse_outcome(reply: bytes) -> Literal["clean", "found"] | None:
    if not reply.startswith(b"stream: "):
        return None
    payload = reply.removeprefix(b"stream: ")
    if not payload.isascii() or any(value < 0x20 or value > 0x7E for value in payload):
        return None
    if payload == b"OK":
        return "clean"
    if payload.endswith(b" FOUND") and payload[:-6]:
        return "found"
    if payload.endswith(b" ERROR") and payload[:-6]:
        return None
    return None


def _version(reply: bytes) -> str:
    if len(reply) > 255 or _VERSION_REPLY.fullmatch(reply) is None:
        raise ValueError("scanner version reply is invalid")
    return reply.decode("ascii")


def _commands(reply: bytes) -> None:
    if len(reply) > 4096 or _COMMANDS_REPLY.fullmatch(reply) is None:
        raise ValueError("scanner commands reply is invalid")
    if b"INSTREAM" not in reply.removeprefix(b"COMMANDS: ").split(b" "):
        raise ValueError("scanner does not support instream")


async def _version_commands(reader: asyncio.StreamReader) -> str:
    reply = await _read_line(reader)
    delimiter = b"| COMMANDS: "
    if delimiter in reply:
        version_reply, commands = reply.split(delimiter, 1)
        version = _version(version_reply)
        _commands(b"COMMANDS: " + commands)
        return version
    version = _version(reply)
    _commands(await _read_line(reader))
    return version
