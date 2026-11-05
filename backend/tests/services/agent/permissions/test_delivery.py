from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.permissions import Module
from app.services.agent.permissions.delivery import (
    DeliveryAttempt, DerivedLabel, SourceLabel, can_deliver, can_view_derived, derive_label,
)


def test_raw_supplier_source_stays_restricted_after_capa_writeback():
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.confidential.raw.v1", "raw", "v3")
    label = derive_label((supplier,))
    authorized = frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, supplier.projection)})
    assert label.sensitivity == "restricted"
    assert label.sources[0].source_version == "v3"
    assert not can_view_derived(label, True, frozenset({(Module.CAPA, uuid4(), "capa.read.v1", "masked")}))
    assert not can_view_derived(label, False, authorized)
    assert not can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, "masked")}))
    assert can_view_derived(label, True, authorized)


def test_all_sources_and_their_actual_projection_are_required():
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.private.raw.v1", "raw", "v7")
    fmea = SourceLabel(Module.FMEA, uuid4(), "internal", "fmea.summary.masked.v1", "masked", "v1")
    label = derive_label((supplier, fmea))
    assert label.sensitivity == "restricted"
    assert not can_view_derived(label, True, frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, "raw")}))
    assert can_view_derived(label, True, frozenset({
        (supplier.owner, supplier.object_id, supplier.capability_id, "raw"),
        (fmea.owner, fmea.object_id, fmea.capability_id, "masked"),
    }))


def test_unlabeled_or_inconsistent_derived_content_fails_closed():
    with pytest.raises(ValueError, match="sources"):
        derive_label(())
    supplier = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.private.raw.v1", "raw", "v7")
    with pytest.raises(ValueError, match="authorization"):
        derive_label((replace(supplier, projection="unknown"),))
    with pytest.raises(ValueError, match="authorization"):
        derive_label((replace(supplier, capability_id=""),))
    authorized = frozenset({(supplier.owner, supplier.object_id, supplier.capability_id, "raw")})
    assert not can_view_derived(DerivedLabel((supplier,), "internal"), True, authorized)


def test_masking_never_implicitly_authorizes_delivery():
    attempt = DeliveryAttempt("restricted", "masked", "model-a", "model", frozenset(), True)
    assert not can_deliver(attempt)
    allowed = frozenset({("restricted", "masked", "model", "model-a")})
    assert can_deliver(replace(attempt, allowed=allowed))
    assert not can_deliver(replace(attempt, projection="raw", allowed=allowed))
    assert not can_deliver(replace(attempt, target_id="model-b", allowed=allowed))
    assert not can_deliver(replace(attempt, target_kind="plugin", allowed=allowed))
    assert not can_deliver(replace(attempt, controlled_egress=False, allowed=allowed))
    assert not can_deliver(replace(attempt, sensitivity="unknown", allowed=frozenset({("unknown", "masked", "model", "model-a")})))
    assert not can_deliver(replace(attempt, projection="other", allowed=frozenset({("restricted", "other", "model", "model-a")})))
    assert not can_deliver(replace(attempt, target_kind="other", allowed=frozenset({("restricted", "masked", "other", "model-a")})))


@pytest.mark.parametrize("version", ["", " "])
def test_missing_source_version_fails_closed(version):
    source = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.private.raw.v1", "raw", version)
    with pytest.raises(ValueError, match="source version"):
        derive_label((source,))


@pytest.mark.parametrize("target", ["", " "])
def test_empty_delivery_target_is_not_authorized_by_policy(target):
    policy = frozenset({("internal", "masked", "model", target)})
    assert not can_deliver(DeliveryAttempt("internal", "masked", target, "model", policy, True))


def test_derived_content_cannot_be_sent_using_a_lower_data_class():
    from app.services.agent.permissions.delivery import can_deliver_derived

    source = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.private.raw.v1", "raw", "v2")
    label = derive_label((source,))
    internal_policy = frozenset({("internal", "masked", "model", "model-a")})
    downgraded = DeliveryAttempt("internal", "masked", "model-a", "model", internal_policy, True)
    assert not can_deliver_derived(label, downgraded)
    restricted_policy = frozenset({("restricted", "masked", "model", "model-a")})
    matching = DeliveryAttempt("restricted", "masked", "model-a", "model", restricted_policy, True)
    assert can_deliver_derived(label, matching)


def test_forged_derived_label_cannot_downgrade_delivery():
    from app.services.agent.permissions.delivery import can_deliver_derived

    source = SourceLabel(Module.SUPPLIER, uuid4(), "restricted", "supplier.private.raw.v1", "raw", "v4")
    forged = DerivedLabel((source,), "internal")
    policy = frozenset({("internal", "masked", "model", "model-a")})
    assert not can_deliver_derived(
        forged, DeliveryAttempt("internal", "masked", "model-a", "model", policy, True),
    )
