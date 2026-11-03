"""SDK foundation tests with network denied before SDK imports."""
import importlib.util
import socket

import pytest


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    attempts = []

    def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network forbidden")

    for name in ("connect", "connect_ex", "bind"):
        monkeypatch.setattr(socket.socket, name, denied)
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    yield
    assert not attempts


def models_module():
    assert importlib.util.find_spec("openqms_agent_sdk.models") is not None, "DTO module not implemented"
    import openqms_agent_sdk.models as models
    return models


FIELDS = {
    "ClientConfig": "base_url tenant_slug timeout response_budget",
    "EncodedRequest": "body query", "WireResponse": "status body may_have_been_sent",
    "RunClaim": "run_id task_id lease_epoch lease_expires_at accepted_message_seq has_resume_checkpoint",
    "ClaimEnvelope": "claim token", "Capability": "id allowed required projection",
    "Capabilities": "capabilities", "RuntimeMessage": "message_id sequence content",
    "MessageBatch": "batch_id messages accepted_sequence", "MessageAck": "accepted_sequence",
    "MessageHistory": "messages next_sequence complete",
    "Verification": "verification_id conclusion is_verified",
    "CapaContext": "receipt_id source_capa_id report_id factory_id projection_id data_class document_no status severity product_line_code updated_at projection_digest verifications",
    "EventPayload": "stage message completed total",
    "ResultPayload": "explanations support opposition missing_information conditional_recommendations",
    "Source": "receipt_id source_capa_id projection_id projection_digest data_class",
    "RuntimeEvent": "event_id task_id run_id event_type payload sources",
    "RuntimeResult": "result_id task_id run_id data_class payload sources",
    "ReadonlyCheckpoint": "checkpoint_id task_id run_id lease_epoch tenant_generation accepted_message_seq update_sequence created_at sources",
    "FinishResult": "task_id run_id task_status run_status lease_epoch",
}
HIDDEN = {
    "ClientConfig": "base_url tenant_slug", "EncodedRequest": "body", "WireResponse": "body",
    "ClaimEnvelope": "token", "RuntimeMessage": "content",
    "CapaContext": "document_no status severity product_line_code",
    "EventPayload": "stage message", "ResultPayload": FIELDS["ResultPayload"],
    "RuntimeEvent": "payload", "RuntimeResult": "payload",
}


@pytest.mark.parametrize("name,names", FIELDS.items())
def test_dto_contract(name, names):
    import dataclasses
    import openqms_agent_sdk as sdk
    cls = getattr(models_module(), name)
    fields = dataclasses.fields(cls)
    assert [f.name for f in fields] == names.split()
    assert cls.__dataclass_params__.frozen
    assert set(cls.__slots__) == set(names.split())
    for f in fields:
        if f.name in HIDDEN.get(name, "").split():
            assert not f.repr
    if name != "ClientConfig":
        obj = cls(**{f.name: "sensitive-marker" if not f.repr else None for f in fields})
        assert "sensitive-marker" not in repr(obj)
        assert not hasattr(obj, "__dict__")
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, fields[0].name, None)
    if name not in ("EncodedRequest", "WireResponse", "ClaimEnvelope"):
        assert getattr(sdk, name) is cls


@pytest.mark.parametrize("value", [True, False, 0, 121, float("nan"), float("inf"), "10", None, 10**1000])
def test_invalid_timeout(value):
    models = models_module()
    from openqms_agent_sdk import ConfigError
    with pytest.raises(ConfigError) as caught:
        models.ClientConfig("secret-origin", timeout=value)
    assert caught.value.kind == "invalid_timeout"
    assert "secret" not in repr(caught.value)


@pytest.mark.parametrize("value", [True, 65535, 16 * 1024 * 1024 + 1, 65536.0, "65536", None])
def test_invalid_budget(value):
    models = models_module()
    from openqms_agent_sdk import ConfigError
    with pytest.raises(ConfigError) as caught:
        models.ClientConfig("secret-origin", response_budget=value)
    assert caught.value.kind == "invalid_response_budget"


def test_defaults_and_tuple_annotations():
    import dataclasses
    from typing import get_type_hints
    models = models_module()
    cfg = models.ClientConfig("not-url-yet", "hidden-tenant")
    assert cfg.timeout == 10.0 and cfg.response_budget == 4 * 1024 * 1024
    assert models.REQUEST_BUDGET == 1024 * 1024
    assert "not-url" not in repr(cfg) and "hidden-tenant" not in repr(cfg)
    for timeout in (1, 1.5, 120):
        for budget in (65536, 16 * 1024 * 1024):
            models.ClientConfig("", timeout=timeout, response_budget=budget)
    for name, fields in {
        "EncodedRequest": ("query",), "Capabilities": ("capabilities",),
        "MessageBatch": ("messages",), "MessageHistory": ("messages",),
        "RuntimeEvent": ("sources",), "RuntimeResult": ("sources",),
        "ReadonlyCheckpoint": ("sources",), "ResultPayload": tuple(FIELDS["ResultPayload"].split()),
    }.items():
        for field in fields:
            assert get_type_hints(getattr(models, name))[field].__origin__ is tuple
    assert type(None) in get_type_hints(models.CapaContext)["verifications"].__args__
    assert all(getattr(models.ResultPayload(), f.name) == () for f in dataclasses.fields(models.ResultPayload))
    assert all(getattr(models.EventPayload(), f.name) is None for f in dataclasses.fields(models.EventPayload))
    assert models.EventPayload(completed=2, total=1).completed == 2


def test_exact_immutable_routes():
    from types import MappingProxyType
    models = models_module()
    expected = {
        "claim": ("POST", "/api/agent/runtime/claim"),
        "capabilities": ("GET", "/api/agent/runtime/capabilities"),
        "claim_messages": ("POST", "/api/agent/runtime/messages/claim"),
        "ack_messages": ("POST", "/api/agent/runtime/messages/ack"),
        "capa_context": ("GET", "/api/agent/runtime/capa/context"),
        "record_event": ("POST", "/api/agent/runtime/events"),
        "save_result": ("POST", "/api/agent/runtime/results"),
        "save_checkpoint": ("POST", "/api/agent/runtime/checkpoints"),
        "message_history": ("GET", "/api/agent/runtime/messages/history"),
        "finish": ("POST", "/api/agent/runtime/finish"),
    }
    assert isinstance(models.SUPPORTED_OPERATIONS, MappingProxyType)
    assert models.SUPPORTED_OPERATIONS == expected
    with pytest.raises(TypeError):
        models.SUPPORTED_OPERATIONS["claim"] = ("GET", "/arbitrary")
    import openqms_agent_sdk as sdk
    assert not {"ClaimEnvelope", "EncodedRequest", "WireResponse", "SUPPORTED_OPERATIONS"}.intersection(sdk.__all__)


def test_package_exists():
    assert importlib.util.find_spec("openqms_agent_sdk") is not None, "SDK package is not implemented"


def test_package_version():
    assert importlib.util.find_spec("openqms_agent_sdk") is not None, "SDK package is not implemented"
    import openqms_agent_sdk
    assert openqms_agent_sdk.__version__ == "0.1.0"


@pytest.mark.parametrize("name", ["SDKError", "ConfigError", "ValidationError", "TransportError", "RequestTimeout", "HTTPError", "ProtocolError", "ResponseTooLarge", "UnknownOutcome", "ClientClosed", "ClientBusy"])
def test_all_error_signatures_and_safe_diagnostics(name):
    import inspect
    import openqms_agent_sdk as sdk
    cls = getattr(sdk, name)
    signature = inspect.signature(cls)
    assert list(signature.parameters) == ["operation", "kind", "status", "may_have_been_sent", "outcome_unknown"]
    assert signature.parameters["kind"].kind is inspect.Parameter.KEYWORD_ONLY
    assert issubclass(cls, sdk.SDKError)
    error = cls("finish", kind="timeout", status=503, may_have_been_sent=True)
    assert error.may_have_been_sent
    for output in (str(error), repr(error), repr(error.args)):
        assert "finish" in output and "timeout" in output and "503" in output
    assert not hasattr(error, "original") and not hasattr(error, "response")
    for value in (None, [], {}, object(), "private-url", True):
        error = cls(value, kind=value, status=value)
        assert (error.operation, error.kind, error.status) == ("unknown", "unknown", None)
        assert "private" not in repr(vars(error)) + repr(error.args)
    for status, expected in ((99, None), (600, None), (200.0, None), (100, 100), (599, 599)):
        assert cls("finish", kind="http_status", status=status).status == expected


def test_no_backend_imports_or_internal_client_exports():
    import sys
    import openqms_agent_sdk as sdk
    assert {"InstallationClient", "RunClient"} <= set(sdk.__all__)
    assert not {"ClaimEnvelope", "EncodedRequest", "WireResponse", "SUPPORTED_OPERATIONS"} & set(sdk.__all__)
    for cls in (sdk.InstallationClient, sdk.RunClient):
        assert not {"request", "get", "post", "user", "admin"} & set(dir(cls))
    for module in ("app", "fastapi", "pydantic", "sqlalchemy", "jwt"):
        assert module not in sys.modules
    assert socket.socket.connect.__name__ == "denied"
    assert socket.getaddrinfo.__name__ == "denied"
    assert socket.socket.bind.__name__ == "denied"


@pytest.mark.parametrize("kind", ["deadline", "dns_busy", "connection_closed"])
def test_shared_transport_kind_names(kind):
    from openqms_agent_sdk import SDKError
    assert SDKError("finish", kind=kind).kind == kind


def test_safe_error_contract():
    assert importlib.util.find_spec("openqms_agent_sdk") is not None, "SDK package is not implemented"
    from openqms_agent_sdk.errors import SDKError, UnknownOutcome
    err = SDKError("private-url", kind="private-token", status=True)
    assert (err.operation, err.kind, err.status) == ("unknown", "unknown", None)
    assert "private" not in str(err) + repr(err) + repr(err.args)
    assert UnknownOutcome("finish", kind="timeout", outcome_unknown=False).outcome_unknown
    assert SDKError("finish", kind="timeout", status=503).status == 503


def test_package_metadata():
    import tomllib
    from pathlib import Path
    assert importlib.util.find_spec("openqms_agent_sdk") is not None, "SDK package is not implemented"
    data = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    assert data["build-system"] == {"requires": ["setuptools==79.0.1"], "build-backend": "setuptools.build_meta"}
    assert data["project"]["name"] == "openqms-agent-sdk"
    assert data["project"]["version"] == "0.1.0"
    assert data["project"]["requires-python"] == ">=3.11"
    assert data["project"]["dependencies"] == []
    assert data["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert data["tool"]["setuptools"]["packages"]["find"].get("include") == ["openqms_agent_sdk*"]
