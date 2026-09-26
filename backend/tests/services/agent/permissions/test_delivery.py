from uuid import uuid4

import pytest

from app.core.permissions import Module


def test_supplier_source_stays_restricted_after_capa_writeback():
    from app.services.agent.permissions.delivery import (
        SourceLabel, derive_label, can_view_derived,
    )

    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "v3", "restricted")
    label = derive_label((supplier,))
    assert label.sensitivity == "restricted"
    assert label.sources[0].source_version == "v3"
    assert not can_view_derived(label, True, frozenset({(Module.CAPA, uuid4(), "restricted")}))
    assert not can_view_derived(label, False, frozenset({(supplier.owner, supplier.object_id, "restricted")}))
    assert not can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, "internal")}))
    assert can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, "restricted")}))


def test_multiple_sources_require_all_origins_and_keep_highest_restriction():
    from app.services.agent.permissions.delivery import (
        SourceLabel, derive_label, can_view_derived,
    )

    capa = SourceLabel(Module.CAPA, uuid4(), "v1", "internal")
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "v7", "restricted")
    label = derive_label((capa, supplier))
    assert label.sensitivity == "restricted"
    assert not can_view_derived(label, True, frozenset({(capa.owner, capa.object_id, "internal")}))
    assert can_view_derived(label, True, frozenset({
        (capa.owner, capa.object_id, "internal"), (supplier.owner, supplier.object_id, "restricted"),
    }))


def test_unknown_or_missing_sources_never_become_unrestricted():
    from app.services.agent.permissions.delivery import SourceLabel, derive_label

    with pytest.raises(ValueError, match="requires server-attached sources"):
        derive_label(())
    with pytest.raises(ValueError, match="unknown sensitivity"):
        derive_label((SourceLabel(Module.SUPPLIER, uuid4(), "v1", "unknown"),))
    with pytest.raises(ValueError, match="source version"):
        derive_label((SourceLabel(Module.SUPPLIER, uuid4(), "", "restricted"),))


def test_masked_delivery_requires_target_specific_policy_and_controlled_egress():
    from app.services.agent.permissions.delivery import DeliveryAttempt, can_deliver

    assert not can_deliver(DeliveryAttempt("restricted", "masked", "model-a", "model", frozenset(), True))
    model_allowed = frozenset({("restricted", "masked", "model", "model-a")})
    assert can_deliver(DeliveryAttempt("restricted", "masked", "model-a", "model", model_allowed, True))
    assert not can_deliver(DeliveryAttempt("restricted", "raw", "model-a", "model", model_allowed, True))
    assert not can_deliver(DeliveryAttempt("restricted", "masked", "model-b", "model", model_allowed, True))
    plugin_allowed = frozenset({("restricted", "masked", "plugin", "plugin-a")})
    assert not can_deliver(DeliveryAttempt("restricted", "masked", "plugin-a", "plugin", plugin_allowed, False))
    empty_target_allowed = frozenset({("internal", "masked", "model", "")})
    assert not can_deliver(DeliveryAttempt("internal", "masked", "", "model", empty_target_allowed, True))


def test_derived_content_cannot_be_sent_using_a_lower_data_class():
    from app.services.agent.permissions.delivery import (
        DeliveryAttempt, SourceLabel, can_deliver_derived, derive_label,
    )

    label = derive_label((SourceLabel(Module.SUPPLIER, uuid4(), "v2", "restricted"),))
    internal_policy = frozenset({("internal", "masked", "model", "model-a")})
    downgraded = DeliveryAttempt("internal", "masked", "model-a", "model", internal_policy, True)
    assert not can_deliver_derived(label, downgraded)
    restricted_policy = frozenset({("restricted", "masked", "model", "model-a")})
    matching = DeliveryAttempt("restricted", "masked", "model-a", "model", restricted_policy, True)
    assert can_deliver_derived(label, matching)


def test_forged_derived_label_cannot_downgrade_read_or_delivery():
    from app.services.agent.permissions.delivery import (
        DeliveryAttempt, DerivedLabel, SourceLabel,
        can_deliver_derived, can_view_derived,
    )

    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "v4", "restricted")
    forged = DerivedLabel((supplier,), "internal")
    granted = frozenset({(supplier.owner, supplier.object_id, "restricted")})
    assert not can_view_derived(forged, True, granted)
    policy = frozenset({("internal", "masked", "model", "model-a")})
    assert not can_deliver_derived(
        forged, DeliveryAttempt("internal", "masked", "model-a", "model", policy, True),
    )


def test_unknown_delivery_class_or_target_fails_even_when_named_in_policy():
    from app.services.agent.permissions.delivery import DeliveryAttempt, can_deliver

    for sensitivity, projection, target_kind in (
        ("unknown", "masked", "model"),
        ("restricted", "unknown", "model"),
        ("restricted", "masked", "unknown"),
    ):
        policy = frozenset({(sensitivity, projection, target_kind, "target")})
        assert not can_deliver(DeliveryAttempt(
            sensitivity, projection, "target", target_kind, policy, True,
        ))
