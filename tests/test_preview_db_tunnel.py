import asyncio
import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('db_tunnel', ROOT / 'scripts/oracle-preview-db-tunnel.py')
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_binary_forwarding_preserves_server_first_bytes_and_client_half_close(capsys):
    tunnel = module()

    async def exercise():
        payload = bytes(range(256)) * 4096

        async def database(reader, writer):
            writer.write(b'PG-hello')
            await writer.drain()
            received = await reader.read()
            writer.write(hashlib.sha256(received).digest())
            await writer.drain()
            await tunnel.close(writer)

        upstream = await asyncio.start_server(database, '127.0.0.1', 0)
        port = upstream.sockets[0].getsockname()[1]
        handler = tunnel.Tunnel()
        proxy = await asyncio.start_server(handler.handle, '127.0.0.1', 0)
        async def connect():
            return await asyncio.open_connection('127.0.0.1', port)
        try:
            with patch.object(tunnel, 'connect_database', side_effect=connect):
                reader, writer = await asyncio.open_connection('127.0.0.1', proxy.sockets[0].getsockname()[1])
                assert await asyncio.wait_for(reader.readexactly(8), 2) == b'PG-hello'
                writer.write(payload)
                await writer.drain()
                writer.write_eof()
                assert await asyncio.wait_for(reader.read(), 2) == hashlib.sha256(payload).digest()
                await tunnel.close(writer)
                for _ in range(100):
                    if handler.active == 0:
                        break
                    await asyncio.sleep(0.01)
                assert handler.active == 0
        finally:
            proxy.close()
            upstream.close()
            await proxy.wait_closed()
            await upstream.wait_closed()

    asyncio.run(exercise())
    assert capsys.readouterr().out == ''


def test_connection_failure_closes_client_and_releases_slot():
    tunnel = module()

    async def exercise():
        handler = tunnel.Tunnel()
        server = await asyncio.start_server(handler.handle, '127.0.0.1', 0)
        try:
            with patch.object(tunnel, 'connect_database', new=AsyncMock(side_effect=ConnectionRefusedError)):
                reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
                assert await asyncio.wait_for(reader.read(), 2) == b''
                await tunnel.close(writer)
                for _ in range(100):
                    if handler.active == 0:
                        break
                    await asyncio.sleep(0.01)
                assert handler.active == 0
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_capacity_rejects_extra_clients_without_opening_database():
    tunnel = module()

    async def exercise():
        handler = tunnel.Tunnel()
        handler.active = tunnel.MAX_CONNECTIONS
        server = await asyncio.start_server(handler.handle, '127.0.0.1', 0)
        try:
            with patch.object(tunnel, 'connect_database', new=AsyncMock()) as connect:
                reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
                assert await asyncio.wait_for(reader.read(), 2) == b''
                await tunnel.close(writer)
                connect.assert_not_called()
                assert handler.active == tunnel.MAX_CONNECTIONS
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_database_target_is_fixed_and_connection_timeout_is_bounded():
    tunnel = module()
    connect = AsyncMock(return_value=(None, None))
    with patch.object(tunnel.asyncio, 'open_connection', new=connect):
        assert asyncio.run(tunnel.connect_database()) == (None, None)
    connect.assert_awaited_once_with('db', 5432, limit=65536)
