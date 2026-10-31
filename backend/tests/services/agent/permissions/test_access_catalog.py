from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import CAPA_CAPABILITIES, get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, CapabilitySpec, Grant


def _attempt(spec: CapabilitySpec) -> AccessAttempt:
    factory_id, object_id = uuid4(), uuid4()
    grant = Grant(
        spec.id, frozenset({factory_id}), frozenset({object_id}),
        frozenset({"DC-DC-100"}),
    )
    return AccessAttempt(
        spec, {Module.CAPA: PermissionLevel.ADMIN}, frozenset({factory_id}),
        frozenset({"DC-DC-100"}), grant, grant,
        factory_id, object_id, "DC-DC-100", datetime.now(UTC),
    )


def test_declared_disabled_capa_capability_is_denied_with_full_grants():
    spec = get_capability("capa.d4.summary.masked.v1")
    assert spec is not None
    result = authorize(_attempt(spec))
    assert not result.allowed
    assert result.approval_floor == ApprovalFloor.DENY


def test_caller_cannot_lower_declared_approval_floor():
    disabled = get_capability("capa.d4.summary.masked.v1")
    assert disabled is not None
    forged = replace(disabled, approval_floor=ApprovalFloor.DIRECT)
    assert not authorize(_attempt(forged)).allowed


def test_unlisted_capability_is_denied_even_with_matching_grants():
    invented = CapabilitySpec(
        "capa.d4.invented.v1", Module.CAPA, "context",
        PermissionLevel.VIEW, ApprovalFloor.DIRECT, "masked",
    )
    assert not authorize(_attempt(invented)).allowed


def test_module_catalog_cannot_be_mutated_in_place():
    key = "capa.test.invented.v1"
    invented = CapabilitySpec(
        key, Module.CAPA, "context", PermissionLevel.VIEW,
        ApprovalFloor.DIRECT, "masked",
    )
    try:
        with pytest.raises(TypeError):
            CAPA_CAPABILITIES[key] = invented
    finally:
        if key in CAPA_CAPABILITIES:
            CAPA_CAPABILITIES.pop(key)
