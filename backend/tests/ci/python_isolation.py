"""Test-only isolation for supported Python entry points (not an OS sandbox)."""
import os
import sys

PURE_FLAG = 'OPENQMS_CI_PURE'


def disable_implicit_dotenv():
    """Default Settings to no dotenv; preserve explicit _env_file test fixtures."""
    from pydantic_settings import BaseSettings

    if getattr(BaseSettings.__init__, '_openqms_no_dotenv', False):
        return
    original = BaseSettings.__init__

    def isolated_init(self, *args, **kwargs):
        kwargs.setdefault('_env_file', None)
        original(self, *args, **kwargs)

    isolated_init._openqms_no_dotenv = True
    BaseSettings.__init__ = isolated_init


def is_pure():
    return os.environ.get(PURE_FLAG) == '1'


def install_pure_guard():
    """Reject Python socket operations before any application imports."""
    def reject_network(event, args):
        if event in {
            'socket.connect', 'socket.getaddrinfo', 'socket.sendto', 'socket.sendmsg',
            # gethostbyname_ex shares the gethostbyname audit event.
            'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.bind',
        }:
            raise RuntimeError('pure_test_network_forbidden')

    sys.addaudithook(reject_network)
    # libpq's C sockets do not emit Python socket audit events. These are the
    # project's supported psycopg entrypoints, not a general native-code sandbox.
    import psycopg

    def reject_database(*args, **kwargs):
        raise RuntimeError('pure_test_database_forbidden')

    async def reject_async_database(*args, **kwargs):
        raise RuntimeError('pure_test_database_forbidden')

    psycopg.connect = reject_database
    psycopg.Connection.connect = classmethod(reject_database)
    psycopg.AsyncConnection.connect = classmethod(reject_async_database)


def bootstrap():
    if is_pure():
        # Keep both initial and nested pytest.main calls independent of ambient
        # installed entry-point plugins; explicitly retain the project's asyncio.
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        os.environ['PYTEST_PLUGINS'] = 'pytest_asyncio.plugin'
        install_pure_guard()
    disable_implicit_dotenv()
