from starlette.datastructures import State
from starlette.requests import Request

from app.core.tenant import tenant_schema


class _Tenant:
    def __init__(self, schema_name: str):
        self.schema_name = schema_name


def _make_request(tenant=None) -> Request:
    scope = {"type": "http", "method": "GET", "headers": [], "path": "/", "query_string": b""}
    req = Request(scope)
    req._state = State()
    if tenant is not None:
        req.state.tenant = tenant
    return req


def test_tenant_schema_returns_schema_name_when_tenant_set():
    req = _make_request(_Tenant("tenant_acme"))
    assert tenant_schema(req) == "tenant_acme"


def test_tenant_schema_defaults_to_public_when_no_tenant():
    req = _make_request(None)
    assert tenant_schema(req) == "public"
