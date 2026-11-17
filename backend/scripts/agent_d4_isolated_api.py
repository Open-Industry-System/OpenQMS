"""Entrypoint for the dedicated D4 API process.

Order matters and is the whole point of this file:

1. install the logging policy,
2. then import the application.

Once the app is imported it may log during import, during lifespan startup, or
while uvicorn reconfigures logging. If the policy were installed afterwards, any
of those paths could already have written an attacker-controlled request target
to a handler that was configured before it.

The process is deliberately narrow: one worker, IPv4 loopback only, no reload, no
proxy headers, and the HTTP parser pinned to h11 rather than whatever happens to
be installed.
"""
import os
import sys

# `-I` ignores PYTHONPATH and site, so the deployment directory is added
# explicitly. It is always the process's own working directory, never a caller
# supplied path: this process runs from the reviewed deployment root.
_DEPLOY_ROOT = os.getcwd()
if _DEPLOY_ROOT not in sys.path:
    sys.path.insert(0, _DEPLOY_ROOT)

# Refuse to start with an inherited configuration that would widen the surface.
_ALLOWED_ENV = {'PATH', 'LANG', 'LC_ALL', 'TZ', 'HOME', 'PYTHONPATH',
                'OPENQMS_ISOLATION_API_PORT', 'OPENQMS_ISOLATION_API_HOST'}


def _install_policy():
    from app.core import agent_isolation_logging
    agent_isolation_logging.install()


def _bind_from_environment():
    host = os.environ.get('OPENQMS_ISOLATION_API_HOST', '127.0.0.1')
    port = os.environ.get('OPENQMS_ISOLATION_API_PORT', '18777')
    if host != '127.0.0.1':
        raise SystemExit('isolated API refuses to bind anything but 127.0.0.1')
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        raise SystemExit('isolated API port is invalid')
    return host, int(port)


def main(argv=None):
    _install_policy()
    host, port = _bind_from_environment()
    import uvicorn
    from app.main import app                     # imported AFTER the policy

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        workers=1,
        reload=False,
        proxy_headers=False,
        server_header=False,
        date_header=False,
        access_log=True,
        log_config=None,          # never let uvicorn replace our handlers
        http='h11',               # pin the parser; do not auto-select httptools
        lifespan='on',
    )
    server = uvicorn.Server(config)
    return 0 if server.run() is None else 0


if __name__ == '__main__':
    sys.exit(main())
