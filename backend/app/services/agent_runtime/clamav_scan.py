"""Strict, fail-closed ClamAV zINSTREAM client for private attachments."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScanResult:
    outcome: Literal["clean", "found", "unavailable"]
    scanner_version: str | None
    failure_code: str | None


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
            writer.write(b"zVERSIONCOMMANDS\0")
            await writer.drain()
            version = await _read_frame(stream_reader)

            writer.write(b"zINSTREAM\0")
            async for chunk in reader:
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
                return ScanResult(outcome, _version(version), None)
            return ScanResult("unavailable", None, "scanner_unavailable")
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError, TypeError, OverflowError):
        return ScanResult("unavailable", None, "scanner_unavailable")
    finally:
        if writer is not None:
            writer.close()


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    reply = await reader.readuntil(b"\0")
    if not reply.endswith(b"\0"):
        raise ValueError("scanner reply is not framed")
    return reply[:-1]


async def _read_final_reply(reader: asyncio.StreamReader) -> bytes:
    reply = await _read_frame(reader)
    if await reader.read(1):
        raise ValueError("scanner reply is not a single frame")
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
    if not reply or len(reply) > 255:
        raise ValueError("scanner version reply is invalid")
    return reply.decode("ascii")
