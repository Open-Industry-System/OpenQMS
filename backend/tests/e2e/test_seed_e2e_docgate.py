"""US-E2E-01.7 doc-gate seed: reseed hygiene + baseline/hash alignment.

Runs under the shared pytest `db` fixture (no E2E_MODE env required).
Proves reseed is idempotent after pollution and that baseline sha256 matches
PG jsonb::text digest of the canonical header+items snapshot.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.seed_e2e import (
    FACT_DC100_ID,
    _seed_accounts,
    _seed_doc_gate_capa,
    _seed_factories,
    _seed_product_line,
)
from app.seed_e2e_constants import (
    DOCGATE_E2E_CP_DOC_NO,
    DOCGATE_E2E_CP_ID,
    DOCGATE_E2E_CP_ITEM_ID,
    DOCGATE_E2E_CP_VER_ID,
    E2E_FACTORY_DC100,
    E2E_PRODUCT_LINE,
)
from app.services.version_service import compute_pg_jsonb_hash

DOCGATE_CP_ID = uuid.UUID(DOCGATE_E2E_CP_ID)
DOCGATE_CP_ITEM_ID = uuid.UUID(DOCGATE_E2E_CP_ITEM_ID)
DOCGATE_CP_VER_ID = uuid.UUID(DOCGATE_E2E_CP_VER_ID)

# Must match ITEM_CANON / CP_CANON / header_snapshot construction in _seed_doc_gate_capa
CP_HEADER_CANON = {
    "title": "E2E DocGate CP",
    "status": "draft",
    "phase": "production",
    "fmea_ref_id": None,
    "part_no": None,
    "part_name": None,
    "contact_info": None,
    "drawing_rev": None,
    "org_factory": None,
    "core_group": None,
}
ITEM_CANON = {
    "step_no": "10",
    "process_name": "定位",
    "equipment": None,
    "characteristic_no": "CP-DOC-001",
    "product_characteristic": "孔径",
    "process_characteristic": "定位销磨损检测",
    "special_class": "CC",
    "specification_tolerance": None,
    "evaluation_method": None,
    "sample_size": None,
    "sample_frequency": None,
    "control_method": "首件+巡检",
    "reaction_plan": "隔离并换销",
    "source_fmea_node_id": None,
    "sort_order": 0,
}


async def _assert_docgate_cp_canonical(db, *, expected_hash: str | None = None) -> str:
    """Assert live CP + baseline version match seed canon; return sha256_hash.

    Compares header/items against the hard-coded CANON (not against the version
    row alone) so a seed that omits part_no/etc. from both live + snapshot
    cannot self-consistently pass via hash-only checks.
    """
    cp = (await db.execute(
        select(ControlPlan).where(ControlPlan.document_no == DOCGATE_E2E_CP_DOC_NO)
    )).scalar_one()
    assert cp.cp_id == DOCGATE_CP_ID
    assert cp.approved_by is None
    assert cp.approved_at is None
    # Pin product-line + factory to seed constants (not just "item.factory_id == cp.factory_id"
    # self-consistency — both could be wrong-but-equal after a bad reseed).
    assert cp.product_line_code == E2E_PRODUCT_LINE["code"], (
        f"cp.product_line_code={cp.product_line_code!r} != {E2E_PRODUCT_LINE['code']!r}"
    )
    assert cp.factory_id == FACT_DC100_ID, (
        f"cp.factory_id={cp.factory_id} != FACT_DC100_ID={FACT_DC100_ID}"
    )
    for k, v in CP_HEADER_CANON.items():
        assert getattr(cp, k) == v, f"live cp.{k}: {getattr(cp, k)!r} != {v!r}"

    items = list((await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )).scalars().all())
    assert len(items) == 1
    item = items[0]
    assert item.item_id == DOCGATE_CP_ITEM_ID
    assert item.factory_id == FACT_DC100_ID, (
        f"item.factory_id={item.factory_id} != FACT_DC100_ID"
    )
    for k, v in ITEM_CANON.items():
        assert getattr(item, k) == v, f"item.{k}: {getattr(item, k)!r} != {v!r}"

    ver = (await db.execute(
        select(ControlPlanVersion).where(ControlPlanVersion.version_id == DOCGATE_CP_VER_ID)
    )).scalar_one()
    assert ver.cp_id == cp.cp_id
    assert ver.factory_id == FACT_DC100_ID

    header = ver.header_snapshot or {}
    # Full header contract (mirrors create_cp_version header_snapshot keys)
    expected_header = {
        "document_no": DOCGATE_E2E_CP_DOC_NO,
        "title": CP_HEADER_CANON["title"],
        "fmea_ref_id": None,
        "product_line_code": E2E_PRODUCT_LINE["code"],  # hard CANON, not live cp
        "status": CP_HEADER_CANON["status"],
        "phase": CP_HEADER_CANON["phase"],
        "part_no": CP_HEADER_CANON["part_no"],
        "part_name": CP_HEADER_CANON["part_name"],
        "contact_info": CP_HEADER_CANON["contact_info"],
        "drawing_rev": CP_HEADER_CANON["drawing_rev"],
        "org_factory": CP_HEADER_CANON["org_factory"],
        "core_group": CP_HEADER_CANON["core_group"],
    }
    for k, v in expected_header.items():
        assert header.get(k) == v, f"header_snapshot.{k}: {header.get(k)!r} != {v!r}"
    # No extra / missing keys vs create_cp_version shape
    assert set(header.keys()) >= set(expected_header.keys()), (
        f"header_snapshot missing keys: {set(expected_header) - set(header)}"
    )

    snap_items = ver.items_snapshot
    if isinstance(snap_items, dict):
        snap_items = snap_items.get("items", [])
    assert isinstance(snap_items, list) and len(snap_items) == 1
    row = snap_items[0]
    assert row.get("item_id") == str(DOCGATE_CP_ITEM_ID)
    for k, v in ITEM_CANON.items():
        assert row.get(k) == v, f"snapshot.{k}: {row.get(k)!r} != {v!r}"

    # Hash must match PG digest of the CANON-derived payload (not just stored snapshot
    # re-hash). Rebuild expected payload from expected_header + snap_items so a
    # polluted-but-self-consistent row still fails if live/canon diverged.
    combined = {"header": expected_header, "items": [
        {"item_id": str(DOCGATE_CP_ITEM_ID), **ITEM_CANON}
    ]}
    expected_hash_val = await compute_pg_jsonb_hash(db, combined)
    assert ver.sha256_hash == expected_hash_val, (
        f"baseline sha256 != CANON digest: stored={ver.sha256_hash} "
        f"canon={expected_hash_val}"
    )
    # Also equal when hashing the stored snapshots (they must equal CANON)
    stored_combined = {"header": header, "items": snap_items}
    stored_recomputed = await compute_pg_jsonb_hash(db, stored_combined)
    assert ver.sha256_hash == stored_recomputed

    if expected_hash is not None:
        assert ver.sha256_hash == expected_hash, (
            f"reseed hash not stable: before={expected_hash} after={ver.sha256_hash}"
        )
    return ver.sha256_hash


@pytest.fixture
async def docgate_seed_base(db):
    """Factories + PL + accounts required by _seed_doc_gate_capa."""
    factory_ids = await _seed_factories(db)
    await _seed_product_line(db, factory_ids)
    await _seed_accounts(db, factory_ids)
    await db.commit()
    return factory_ids


@pytest.mark.asyncio
async def test_docgate_cp_seed_twice_restores_canonical_and_baseline_hash(
    db, monkeypatch, docgate_seed_base,
):
    """Pollute live CP + baseline after first seed; second seed must restore canon + hash."""
    monkeypatch.setattr(settings, "E2E_MODE", True)
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    factory_ids = docgate_seed_base

    await _seed_doc_gate_capa(db, factory_ids)
    await db.flush()
    hash_before = await _assert_docgate_cp_canonical(db)

    # --- pollute live CP (simulates a prior walk) ---
    from app.models.user import User
    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
    # Second factory (seed creates SH-FACT-E2E) — valid FK but wrong for this CP.
    other_factory_id = next(
        fid for code, fid in factory_ids.items() if code != list(factory_ids)[0]
    ) if len(factory_ids) > 1 else list(factory_ids.values())[0]

    cp = (await db.execute(
        select(ControlPlan).where(ControlPlan.document_no == DOCGATE_E2E_CP_DOC_NO)
    )).scalar_one()
    original_factory_id = cp.factory_id
    assert original_factory_id == FACT_DC100_ID
    cp.status = "approved"
    cp.approved_by = admin.user_id  # valid FK; reseed must clear
    cp.approved_at = cp.created_at
    cp.title = "POLLUTED TITLE"
    # Move off the DC100 / E2E product-line — reseed must restore both constants
    # (not merely keep item.factory_id == cp.factory_id after a joint wrong move).
    cp.product_line_code = "POLLUTED-PL"
    cp.factory_id = other_factory_id if other_factory_id != FACT_DC100_ID else original_factory_id
    # Pollute every optional header field that seed restores to None — proves
    # reseed covers the full create_cp_version header contract, not a subset.
    cp.part_no = "POLLUTED-PN"
    cp.part_name = "POLLUTED-NAME"
    cp.contact_info = "polluted@example.com"
    cp.drawing_rev = "R99"
    cp.org_factory = "POLLUTED-ORG"
    cp.core_group = "POLLUTED-GROUP"
    cp.phase = "prototype"
    item = (await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.item_id == DOCGATE_CP_ITEM_ID)
    )).scalar_one()
    item.control_method = "POLLUTED-METHOD"
    item.equipment = "POLLUTED-EQ"  # seed ITEM_CANON fixes equipment=None
    # Pin item to SH factory when available — reseed must restore FACT_DC100_ID
    if other_factory_id != FACT_DC100_ID:
        item.factory_id = other_factory_id
        assert cp.factory_id == other_factory_id  # both wrong but equal — anti-pattern
    # Extra item that must be pruned on reseed
    db.add(ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        factory_id=original_factory_id,
        step_no="99",
        process_name="extra",
        characteristic_no="EXTRA",
        control_method="x",
        sort_order=9,
    ))
    await db.flush()

    # Pollute baseline version content + factory_id (trigger disabled — same as seed).
    # factory_id must be restored on reseed; without pollution the assertion is vacuous.
    await db.execute(text(
        'ALTER TABLE "control_plan_versions" DISABLE TRIGGER "trg_cp_version_no_update"'
    ))
    try:
        await db.execute(text(
            "UPDATE control_plan_versions SET "
            "factory_id = :fact, "
            "header_snapshot = CAST(:hdr AS JSONB), "
            "items_snapshot = CAST(:items AS JSONB), "
            "sha256_hash = 'deadbeef' "
            "WHERE version_id = :vid"
        ), {
            "fact": other_factory_id if other_factory_id != FACT_DC100_ID else FACT_DC100_ID,
            "hdr": '{"title":"POLLUTED"}',
            "items": "[]",
            "vid": str(DOCGATE_CP_VER_ID),
        })
        await db.flush()
        if other_factory_id != FACT_DC100_ID:
            dirty_ver = (await db.execute(
                select(ControlPlanVersion).where(
                    ControlPlanVersion.version_id == DOCGATE_CP_VER_ID)
            )).scalar_one()
            assert dirty_ver.factory_id == other_factory_id
    finally:
        await db.execute(text(
            'ALTER TABLE "control_plan_versions" ENABLE TRIGGER "trg_cp_version_no_update"'
        ))

    # Sanity: pollution took effect
    dirty = (await db.execute(
        select(ControlPlan).where(ControlPlan.cp_id == DOCGATE_CP_ID)
    )).scalar_one()
    assert dirty.status == "approved"
    assert dirty.approved_by is not None
    dirty_items = list((await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == DOCGATE_CP_ID)
    )).scalars().all())
    assert len(dirty_items) == 2

    # --- reseed ---
    await _seed_doc_gate_capa(db, factory_ids)
    await db.flush()
    # Raw SQL inside seed bypasses the identity map; expire so subsequent selects
    # see restored factory_id / snapshots (not the pollution-time ORM instance).
    db.expire_all()

    hash_after = await _assert_docgate_cp_canonical(db, expected_hash=hash_before)
    assert hash_after == hash_before
