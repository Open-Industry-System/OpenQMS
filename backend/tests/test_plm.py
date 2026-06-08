"""Tests for PLMIngestionService using real DB queries with pytest fixtures.

Each test uses the shared ``db``, ``admin_user``, and ``plm_connection`` fixtures
from conftest.py, exercises the actual PLMIngestionService, and verifies results
via SELECT queries against the database.

Run:  pytest backend/tests/test_plm.py -v
"""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plm import (
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartSCLink,
)
from app.services.plm_service import PLMIngestionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _part_data(
    connection_id: uuid.UUID,
    part_number: str = "TEST-001",
    revision: str = "A",
    *,
    is_safety_related: bool = False,
    is_key_characteristic: bool = False,
    **overrides,
) -> dict:
    """Build a minimal part-ingestion payload."""
    data = {
        "data_type": "part",
        "connection_id": str(connection_id),
        "external_id": f"ext-{part_number}",
        "part_number": part_number,
        "name": f"Part {part_number}",
        "revision": revision,
        "is_safety_related": is_safety_related,
        "is_key_characteristic": is_key_characteristic,
        "product_line_code": "DC-DC-100",
    }
    data.update(overrides)
    return data


def _ecn_data(
    connection_id: uuid.UUID,
    change_number: str = "ECN-001",
    status: str = "draft",
    **overrides,
) -> dict:
    """Build a minimal change-order ingestion payload."""
    data = {
        "data_type": "change_order",
        "connection_id": str(connection_id),
        "external_id": "ext-ecn-1",
        "change_number": change_number,
        "title": "Test ECN",
        "change_type": "design",
        "status": status,
        "affected_part_numbers": ["TEST-001"],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# 1. Idempotency: ingesting the same part twice produces one row
# ---------------------------------------------------------------------------


async def test_plm_part_ingestion_idempotent(
    db: AsyncSession, plm_connection: PLMConnection
):
    """Ingesting the same (connection_id, part_number, revision) twice should
    produce exactly one PLMPart row (UPSERT idempotency)."""
    svc = PLMIngestionService(db)
    conn_id = plm_connection.connection_id
    data = _part_data(conn_id, part_number="TEST-001", revision="A")

    await svc.ingest(data)
    await svc.ingest(data)
    await db.commit()

    result = await db.execute(
        select(PLMPart).where(
            PLMPart.connection_id == conn_id,
            PLMPart.part_number == "TEST-001",
        )
    )
    parts = list(result.scalars().all())

    assert len(parts) == 1
    assert parts[0].is_safety_related is False


# ---------------------------------------------------------------------------
# 2. Multi-revision coexistence
# ---------------------------------------------------------------------------


async def test_plm_multi_revision_coexist(
    db: AsyncSession, plm_connection: PLMConnection
):
    """Different revisions of the same part_number should coexist as separate
    rows (unique constraint is on connection_id + part_number + revision)."""
    svc = PLMIngestionService(db)
    conn_id = plm_connection.connection_id

    for rev in ("A", "B", "C"):
        data = _part_data(conn_id, part_number="MULTI-001", revision=rev)
        await svc.ingest(data)

    await db.commit()

    result = await db.execute(
        select(PLMPart).where(
            PLMPart.connection_id == conn_id,
            PLMPart.part_number == "MULTI-001",
        )
    )
    parts = list(result.scalars().all())

    assert len(parts) == 3
    assert {p.revision for p in parts} == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# 3. ECN approved -> impact task created
# ---------------------------------------------------------------------------


async def test_ecn_approved_creates_impact_task(
    db: AsyncSession, plm_connection: PLMConnection
):
    """Ingesting a draft ECN then the same ECN with status='approved' should
    create exactly one PLMChangeImpactTask with status='pending'."""
    svc = PLMIngestionService(db)
    conn_id = plm_connection.connection_id
    change_number = "ECN-IMPACT-001"

    # First ingest: draft -- no impact task
    draft = _ecn_data(conn_id, change_number=change_number, status="draft")
    await svc.ingest(draft)
    await db.commit()

    # Second ingest: approved -- should create impact task
    approved = _ecn_data(conn_id, change_number=change_number, status="approved")
    await svc.ingest(approved)
    await db.commit()

    result = await db.execute(
        select(PLMChangeImpactTask).join(PLMChangeOrder).where(
            PLMChangeOrder.connection_id == conn_id,
            PLMChangeOrder.change_number == change_number,
        )
    )
    tasks = list(result.scalars().all())

    assert len(tasks) == 1
    assert tasks[0].status == "pending"


# ---------------------------------------------------------------------------
# 4. Safety-related part -> SC link with characteristic_type="safety"
# ---------------------------------------------------------------------------


async def test_part_sc_link_created_for_safety_related(
    db: AsyncSession, plm_connection: PLMConnection
):
    """A part with is_safety_related=True should create a PLMPartSCLink with
    characteristic_type='safety'."""
    svc = PLMIngestionService(db)
    conn_id = plm_connection.connection_id
    data = _part_data(
        conn_id,
        part_number="SAFETY-001",
        revision="A",
        is_safety_related=True,
    )

    await svc.ingest(data)
    await db.commit()

    result = await db.execute(
        select(PLMPartSCLink).join(PLMPart).where(
            PLMPart.connection_id == conn_id,
            PLMPart.part_number == "SAFETY-001",
        )
    )
    links = list(result.scalars().all())

    assert len(links) == 1
    assert links[0].characteristic_type == "safety"
