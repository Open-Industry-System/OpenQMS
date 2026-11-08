"""Local trial ingress is a real-peer check, never a proxy identity assertion."""
from starlette.requests import Request

from app.services.agent_runtime.routes import RUNTIME_PATHS


def is_local_trial_path(path: str) -> bool:
    return path in RUNTIME_PATHS or any(path == prefix or path.startswith(prefix + '/')
        for prefix in ('/api/agent/tasks', '/api/admin/agent-plugins'))


def local_trial_peer_allowed(request: Request) -> bool:
    return (request.client is not None and request.client.host in {'127.0.0.1', '::1'}
        and not any(key.lower() == 'forwarded' or key.lower().startswith('x-forwarded-')
            for key in request.headers))
