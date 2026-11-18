"""R7 access stays on fixed routes and confirms only fully verified pages."""
import base64
import json
from dataclasses import replace
from hashlib import sha256

import pytest

from codec_fixtures import U, V, SECRET, codec, deny_network
from test_client import make_client


PAGE = "a" * 64
SNAPSHOT = "b" * 64
TOKEN = "c" * 64
SCOPE = "server.scope-ref"


def envelope(*, body=None, page=True):
    if body is None:
        body = json.dumps({"page_key": PAGE, "elements": [{
            "kind": "ProcessStep", "node_id": "node", "name": SECRET,
            "source_id": None, "target_id": None,
        }]} if page else {"state": "known", "material": SECRET}).encode()
    return {
        "run_id": str(U), "task_id": str(V), "lease_epoch": 0,
        "receipt_id": str(U), "projection_bytes": base64.b64encode(body).decode(),
        "payload_digest": sha256(body).hexdigest(), "page_key": PAGE if page else None,
        "confirmation_token": TOKEN if page else None, "next_cursor": None,
        "scope_ref": SCOPE if page else None, "snapshot_digest": SNAPSHOT,
    }


def ack(*, coverage=None):
    return {
        "run_id": str(U), "task_id": str(V), "lease_epoch": 0,
        "confirmation_id": str(U), "coverage_id": coverage,
    }


def test_material_page_and_explicit_confirm_use_exact_routes_and_bytes(monkeypatch):
    from openqms_agent_sdk.models import SUPPORTED_OPERATIONS

    parent, wire = make_client(monkeypatch)
    with parent.claim_run(request_key="test") as run:
        wire.calls.clear()
        wire.responses.update(pfmea_impact_material=envelope(page=False), pfmea_impact_page=envelope(),
                              pfmea_impact_confirm=ack(coverage=str(V)))
        material = run.pfmea_impact_material()
        page = run.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=material.snapshot_digest)
        assert page.projection_bytes == base64.b64decode(envelope()["projection_bytes"])
        assert page.page_key == PAGE and page.receipt_id == U and page.next_cursor is None
        assert SECRET not in repr(page) and TOKEN not in repr(page) and SCOPE not in repr(page)
        assert [call[0] for call in wire.calls] == ["pfmea_impact_material", "pfmea_impact_page"]

        confirmation = run.pfmea_impact_confirm(page)
        assert confirmation.confirmation_id == U and confirmation.coverage_id == V

    assert [SUPPORTED_OPERATIONS[c[0]] for c in wire.calls] == [
        ("GET", "/api/agent/runtime/pfmea-impact/material"),
        ("POST", "/api/agent/runtime/pfmea-impact/page"),
        ("POST", "/api/agent/runtime/pfmea-impact/confirm"),
    ]
    assert wire.calls[0][2].body is None and wire.calls[0][2].query == ()
    assert json.loads(wire.calls[1][2].body) == {"scope_ref": SCOPE, "cursor": None}
    assert json.loads(wire.calls[2][2].body) == {
        "release_id": str(U), "page_key": PAGE,
        "payload_digest": envelope()["payload_digest"], "token": TOKEN,
    }


@pytest.mark.parametrize("changes", [
    {"unknown": SECRET},
    {"run_id": str(V)},
    {"task_id": str(U)},
    {"lease_epoch": 1},
    {"lease_epoch": True},
    {"projection_bytes": "not a valid byte envelope"},
    {"payload_digest": "d" * 64},
    {"confirmation_token": None},
    {"scope_ref": "another.scope-ref"},
    {"snapshot_digest": "d" * 64},
])
def test_invalid_page_never_confirms(monkeypatch, changes):
    from openqms_agent_sdk.errors import ProtocolError

    parent, wire = make_client(monkeypatch)
    with parent.claim_run(request_key="test") as run:
        wire.calls.clear()
        wire.responses["pfmea_impact_page"] = envelope() | changes
        with pytest.raises(ProtocolError) as exc:
            page = run.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=SNAPSHOT)
            run.pfmea_impact_confirm(page)
        assert SECRET not in repr(exc.value) and TOKEN not in repr(exc.value)
        assert exc.value.__context__ is None
    assert [call[0] for call in wire.calls] == ["pfmea_impact_page"]


def test_client_rechecks_canonical_page_key_on_parse_and_rechecks_ack_input(monkeypatch):
    from openqms_agent_sdk.errors import ProtocolError, ValidationError

    parent, wire = make_client(monkeypatch)
    with parent.claim_run(request_key="test") as run:
        wire.responses["pfmea_impact_page"] = envelope() | {"page_key": "d" * 64}
        with pytest.raises(ProtocolError):
            run.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=SNAPSHOT)
        wire.responses["pfmea_impact_page"] = envelope()
        page = run.pfmea_impact_page(scope_ref=SCOPE, snapshot_digest=SNAPSHOT)
        wire.calls.clear()
        for bad in (replace(page, projection_bytes=b"{}"), replace(page, run_id=V)):
            with pytest.raises(ValidationError):
                run.pfmea_impact_confirm(bad)
        wire.responses["pfmea_impact_search"] = envelope(page=False)
        search = run.pfmea_impact_search(term="OP40", cursor="cursor-2", snapshot_digest=SNAPSHOT)
        assert json.loads(wire.calls[0][2].body) == {"term": "OP40", "cursor": "cursor-2"}
        with pytest.raises(ValidationError):
            run.pfmea_impact_confirm(search)
    assert [call[0] for call in wire.calls] == ["pfmea_impact_search"]


@pytest.mark.parametrize("operation,fields", [
    ("pfmea_impact_material", {}),
    ("pfmea_impact_search", {"term": "OP40", "cursor": None}),
    ("pfmea_impact_page", {"scope_ref": SCOPE, "cursor": None}),
    ("pfmea_impact_confirm", {"release_id": U, "page_key": PAGE, "payload_digest": SNAPSHOT, "token": TOKEN}),
    ("pfmea_impact_result", {"operation_key": "once", "analyses": (), "assessments": ()}),
])
def test_caller_cannot_supply_routing_or_authority_metadata(operation, fields):
    from openqms_agent_sdk.errors import ValidationError

    for name in ("report_id", "target_id", "version_id", "source_ids", "endpoint", "run_id", "task_id", "scope_digest"):
        with pytest.raises(ValidationError):
            codec().encode_request(operation, fields | {name: str(U)})


def test_result_submission_uses_typed_narrow_wire_contract(monkeypatch):
    import openqms_agent_sdk as sdk

    parent, wire = make_client(monkeypatch)
    with parent.claim_run(request_key="test") as run:
        wire.responses["pfmea_impact_result"] = {
            "run_id": str(U), "task_id": str(V), "lease_epoch": 0, "result_id": str(V),
        }
        analysis = sdk.PfmeaImpactAnalysis("evaluation", "reason", ("fact",), "inference")
        measure = sdk.PfmeaImpactAssessment(U, None, "evaluation", "insufficient_evidence",
                                            missing_information=("bound scope unavailable",))
        result = run.pfmea_impact_submit(operation_key="same-on-replay", analyses=(analysis,), assessments=(measure,))
        assert result.result_id == V
        actual = json.loads(wire.calls[-1][2].body)
        assert actual["operation_key"] == "same-on-replay"
        assert actual["analyses"] == [
            {"analysis_ref": "evaluation", "reason": "reason", "fact_refs": ["fact"], "inference": "inference"},
        ]
        assert actual["assessments"] == [{
            "measure_id": str(U), "formal_revision": None, "analysis_ref": "evaluation",
            "conclusion": "insufficient_evidence", "evidence_refs": [], "coverage_refs": [],
            "exclusion_refs": [], "missing_information": ["bound scope unavailable"], "node_adjustments": [],
        }]
        for invalid in (replace(measure, formal_revision=True), replace(measure, missing_information=["wrong"])):
            with pytest.raises(sdk.ValidationError):
                run.pfmea_impact_submit(operation_key="same-on-replay", analyses=(analysis,), assessments=(invalid,))


def test_managed_launch_accepts_only_the_r7_profile_for_r7_protocol(monkeypatch):
    import openqms_agent_sdk as sdk
    from openqms_agent_sdk import client
    from test_client import FakeTransport
    from test_r6_candidates import launch_wire

    monkeypatch.setattr(client, "Transport", FakeTransport)
    r7 = launch_wire() | {"protocol": "r7.pfmea.launch.v1", "profile": "model_pfmea_impact_v1"}
    launch = sdk.ManagedLaunch.from_dict(r7)
    with sdk.RunClient.from_launch(launch) as run:
        assert run.claim.run_id == launch.run_id
        assert run._parent._transport.calls == []
    for changes in (
        {"profile": "model_d4_candidate_v1"}, {"protocol": "r6.d4.launch.v1"},
        {"protocol": "https://unsafe.invalid"},
    ):
        with pytest.raises(sdk.ConfigError):
            sdk.ManagedLaunch.from_dict(r7 | changes)
