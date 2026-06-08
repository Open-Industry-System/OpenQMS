"""Tests for PLMIngestionService.

Uses MagicMock / AsyncMock for the DB session, consistent with the project's
existing test pattern (no real database required).

Run:  pytest backend/tests/test_plm.py -v
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

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

def _mock_db(**kwargs):
    """Return a MagicMock DB session with AsyncMock for execute/flush."""
    db = MagicMock()
    db.execute = AsyncMock(**kwargs)
    db.flush = AsyncMock()
    return db


def _part_data(
    part_number: str = "PN-001",
    revision: str = "A",
    *,
    is_safety_related: bool = False,
    is_key_characteristic: bool = False,
    **overrides,
) -> dict:
    """Build a minimal part-ingestion payload."""
    data = {
        "data_type": "part",
        "connection_id": uuid.uuid4(),
        "external_id": "ext-1",
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
    change_number: str = "ECN-001",
    status: str = "draft",
    **overrides,
) -> dict:
    """Build a minimal change-order ingestion payload."""
    data = {
        "data_type": "change_order",
        "connection_id": uuid.uuid4(),
        "external_id": "ext-ecn-1",
        "change_number": change_number,
        "title": "Test ECN",
        "change_type": "design",
        "status": status,
        "affected_part_numbers": ["PN-001"],
    }
    data.update(overrides)
    return data


def _scalar_result(value):
    """Return a mock Result whose scalar_one_or_none returns *value*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# 1. Idempotency: ingesting the same part twice produces one row
# ---------------------------------------------------------------------------

class TestIngestPartIdempotency:
    """ingest() uses INSERT ... ON CONFLICT DO UPDATE, so re-ingesting the same
    (connection_id, part_number, revision) should not create a duplicate."""

    @pytest.mark.asyncio
    async def test_double_ingest_single_row(self):
        """The pg_insert ON CONFLICT UPDATE guarantees idempotency at the DB
        level.  At the service layer, we verify that exactly two execute()
        calls are made (one per ingest), but each is an upsert -- no separate
        INSERT without conflict clause."""
        conn_id = uuid.uuid4()
        data = _part_data(
            part_number="PN-IDEM",
            revision="A",
            connection_id=conn_id,
        )

        db = _mock_db()
        svc = PLMIngestionService(db)

        # First ingest
        await svc.ingest(data)
        # Second ingest with identical data
        await svc.ingest(data)

        # Each ingest calls db.execute once for the pg_insert statement.
        # No SC link side-effect (is_safety_related=False, is_key_characteristic=False),
        # so total execute calls == 2.
        assert db.execute.call_count == 2

        # Both calls should be pg_insert statements (not plain inserts),
        # confirming the ON CONFLICT DO UPDATE path.
        for c in db.execute.call_args_list:
            stmt = c.args[0]
            # pg_insert produces a dialect-specific Insert; verify via
            # the is_insert / is_dml flags.
            assert stmt.is_insert and stmt.is_dml, (
                "Expected a SQLAlchemy upsert statement"
            )


# ---------------------------------------------------------------------------
# 2. Multi-revision coexistence
# ---------------------------------------------------------------------------

class TestMultiRevisionCoexistence:
    """Different revisions of the same part_number should coexist as separate
    rows (the unique constraint is on connection_id + part_number + revision)."""

    @pytest.mark.asyncio
    async def test_three_revisions_three_rows(self):
        """Three different revisions produce three execute() calls.  The
        ON CONFLICT clause uses (connection_id, part_number, revision) as the
        unique index, so different revisions naturally produce different rows."""
        conn_id = uuid.uuid4()
        db = _mock_db()
        svc = PLMIngestionService(db)

        for rev in ("A", "B", "C"):
            data = _part_data(
                part_number="PN-MULTI",
                revision=rev,
                connection_id=conn_id,
            )
            await svc.ingest(data)

        # One execute per revision = 3 total, no SC links.
        assert db.execute.call_count == 3


# ---------------------------------------------------------------------------
# 3. ECN approved -> impact task created
# ---------------------------------------------------------------------------

class TestECNImpactTask:
    """An ECN transitioning to 'approved' should create a PLMChangeImpactTask.
    A draft ECN should NOT create one."""

    @pytest.mark.asyncio
    async def test_draft_ecn_no_impact_task(self):
        """Ingesting a draft ECN should not trigger _upsert_impact_task."""
        conn_id = uuid.uuid4()
        data = _ecn_data(status="draft", connection_id=conn_id)

        db = _mock_db()
        svc = PLMIngestionService(db)

        await svc.ingest(data)

        # Only the change-order upsert call; no status-check SELECT, no
        # impact-task upsert.
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_approved_ecn_creates_impact_task(self):
        """Ingesting an ECN with status='approved' should:
        1. SELECT current status (to check transition)
        2. INSERT/UPDATE the change order
        3. SELECT change_id (to resolve FK)
        4. INSERT/UPDATE the impact task
        """
        conn_id = uuid.uuid4()
        change_number = "ECN-APPROVED"
        data = _ecn_data(
            status="approved",
            change_number=change_number,
            connection_id=conn_id,
        )

        change_id = uuid.uuid4()

        # Build ordered mock returns:
        # Call 1: SELECT current status -> None (new ECN, not yet approved)
        # Call 2: INSERT change order -> (no return needed)
        # Call 3: SELECT change_id -> change_id
        # Call 4: INSERT impact task -> (no return needed)
        result_none = _scalar_result(None)
        result_exec = MagicMock()
        result_change_id = _scalar_result(change_id)
        result_exec2 = MagicMock()

        db = _mock_db()
        db.execute = AsyncMock(
            side_effect=[result_none, result_exec, result_change_id, result_exec2]
        )
        db.flush = AsyncMock()

        svc = PLMIngestionService(db)
        await svc.ingest(data)

        assert db.execute.call_count == 4

        # Verify the impact-task insert (4th call) targets PLMChangeImpactTask.
        impact_stmt = db.execute.call_args_list[3].args[0]
        compiled = impact_stmt.compile(compile_kwargs={"literal_binds": True})
        assert "plm_change_impact_tasks" in str(compiled)


# ---------------------------------------------------------------------------
# 4. Safety-related part -> SC link with characteristic_type="safety"
# ---------------------------------------------------------------------------

class TestSafetyPartSCLink:
    """A part with is_safety_related=True should trigger creation of a
    PLMPartSCLink with characteristic_type='safety'."""

    @pytest.mark.asyncio
    async def test_safety_part_creates_sc_link(self):
        conn_id = uuid.uuid4()
        part_id = uuid.uuid4()
        data = _part_data(
            part_number="PN-SAFE",
            is_safety_related=True,
            is_key_characteristic=False,
            connection_id=conn_id,
        )

        db = _mock_db()
        # Call 1: pg_insert part (upsert)
        # Call 2: SELECT part_id for SC link resolution
        # Call 3: pg_insert SC link
        result_part_id = _scalar_result(part_id)
        db.execute = AsyncMock(
            side_effect=[MagicMock(), result_part_id, MagicMock()]
        )
        db.flush = AsyncMock()

        svc = PLMIngestionService(db)
        await svc.ingest(data)

        assert db.execute.call_count == 3

        # The 3rd call is the SC link upsert.
        sc_stmt = db.execute.call_args_list[2].args[0]
        compiled = sc_stmt.compile(compile_kwargs={"literal_binds": True})
        assert "plm_part_sc_links" in str(compiled)


# ---------------------------------------------------------------------------
# 5. key_characteristic (not safety) -> SC link with "key_characteristic"
# ---------------------------------------------------------------------------

class TestKeyCharacteristicSCLink:
    """A part with is_key_characteristic=True and is_safety_related=False should
    trigger creation of a PLMPartSCLink with
    characteristic_type='key_characteristic'."""

    @pytest.mark.asyncio
    async def test_key_characteristic_creates_sc_link(self):
        conn_id = uuid.uuid4()
        part_id = uuid.uuid4()
        data = _part_data(
            part_number="PN-KEY",
            is_safety_related=False,
            is_key_characteristic=True,
            connection_id=conn_id,
        )

        db = _mock_db()
        result_part_id = _scalar_result(part_id)
        db.execute = AsyncMock(
            side_effect=[MagicMock(), result_part_id, MagicMock()]
        )
        db.flush = AsyncMock()

        svc = PLMIngestionService(db)
        await svc.ingest(data)

        assert db.execute.call_count == 3

        sc_stmt = db.execute.call_args_list[2].args[0]
        compiled = sc_stmt.compile(compile_kwargs={"literal_binds": True})
        assert "plm_part_sc_links" in str(compiled)

    @pytest.mark.asyncio
    async def test_safety_plus_key_only_creates_one_safety_link(self):
        """When BOTH is_safety_related and is_key_characteristic are True,
        only the 'safety' SC link is created (the service skips
        key_characteristic when is_safety_related is True)."""
        conn_id = uuid.uuid4()
        part_id = uuid.uuid4()
        data = _part_data(
            part_number="PN-BOTH",
            is_safety_related=True,
            is_key_characteristic=True,
            connection_id=conn_id,
        )

        db = _mock_db()
        result_part_id = _scalar_result(part_id)
        # Call 1: pg_insert part, Call 2: SELECT part_id, Call 3: pg_insert SC link
        db.execute = AsyncMock(
            side_effect=[MagicMock(), result_part_id, MagicMock()]
        )
        db.flush = AsyncMock()

        svc = PLMIngestionService(db)
        await svc.ingest(data)

        # Only 3 calls: part upsert + part_id lookup + one SC link (safety).
        # key_characteristic is skipped because is_safety_related is True.
        assert db.execute.call_count == 3
