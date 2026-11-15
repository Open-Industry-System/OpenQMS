#!/usr/bin/env python3
"""Bounded byte forwarding to this stack's private database. No credentials or logs."""
import asyncio
from contextlib import suppress

BUFFER_SIZE = 65536
MAX_CONNECTIONS = 8


async def close(writer):
    writer.close()
    with suppress(OSError, asyncio.TimeoutError):
        await asyncio.wait_for(writer.wait_closed(), 2)


async def connect_database():
    return await asyncio.wait_for(
        asyncio.open_connection('db', 5432, limit=BUFFER_SIZE), 10)


async def copy(source, destination):
    while data := await source.read(BUFFER_SIZE):
        destination.write(data)
        await destination.drain()
    if destination.can_write_eof():
        destination.write_eof()
        await destination.drain()


class Tunnel:
    def __init__(self):
        self.active = 0

    async def handle(self, reader, writer):
        if self.active >= MAX_CONNECTIONS:
            await close(writer)
            return
        self.active += 1
        upstream = None
        try:
            remote_reader, upstream = await connect_database()
            await asyncio.wait_for(asyncio.gather(
                copy(reader, upstream), copy(remote_reader, writer)), 60)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            if upstream is not None:
                await close(upstream)
            await close(writer)
            self.active -= 1


async def main():
    server = await asyncio.start_server(
        Tunnel().handle, '0.0.0.0', 5432, limit=BUFFER_SIZE,
        backlog=MAX_CONNECTIONS)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
