import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from app.models.audit_program import AuditProgram
from app.models.audit_plan import AuditPlan
from app.models.audit_finding import AuditFinding
from app.services import audit_service


def create_mock_db():
    db = MagicMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_update_program_status_empty():
    db = create_mock_db()
    # Mock db.execute to return a mock result with empty list
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    program = AuditProgram(
        program_id=uuid.uuid4(),
        status="planned"
    )

    await audit_service._update_program_status(db, program)
    assert program.status == "planned"  # remains unchanged


@pytest.mark.asyncio
async def test_update_program_status_all_completed_or_cancelled():
    db = create_mock_db()
    # Mock db.execute to return completed and cancelled statuses
    mock_result = MagicMock()
    mock_result.all.return_value = [("completed",), ("cancelled",)]
    db.execute.return_value = mock_result

    program = AuditProgram(
        program_id=uuid.uuid4(),
        status="planned"
    )

    await audit_service._update_program_status(db, program)
    assert program.status == "completed"


@pytest.mark.asyncio
async def test_update_program_status_any_active():
    db = create_mock_db()
    # Mock db.execute to return planned and in_progress statuses
    mock_result = MagicMock()
    mock_result.all.return_value = [("planned",), ("in_progress",)]
    db.execute.return_value = mock_result

    program = AuditProgram(
        program_id=uuid.uuid4(),
        status="planned"
    )

    await audit_service._update_program_status(db, program)
    assert program.status == "active"


@pytest.mark.asyncio
async def test_start_audit_plan_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        program_id=uuid.uuid4(),
        status="planned",
        actual_date=None
    )

    # Mock get AuditProgram during status update
    db.get.return_value = AuditProgram(program_id=plan.program_id, status="planned")
    # Mock db.execute for status update query
    mock_result = MagicMock()
    mock_result.all.return_value = [("in_progress",)]
    db.execute.return_value = mock_result

    updated_plan = await audit_service.start_audit_plan(db, plan, user_id)
    assert updated_plan.status == "in_progress"
    assert updated_plan.actual_date == date.today()
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_start_audit_plan_invalid_status():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        status="in_progress"
    )

    with pytest.raises(ValueError, match="only planned audits can be started"):
        await audit_service.start_audit_plan(db, plan, user_id)


@pytest.mark.asyncio
async def test_complete_audit_plan_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        program_id=uuid.uuid4(),
        status="in_progress"
    )

    # Mock get AuditProgram during status update
    db.get.return_value = AuditProgram(program_id=plan.program_id, status="active")
    # Mock db.execute for status update query
    mock_result = MagicMock()
    mock_result.all.return_value = [("completed",)]
    db.execute.return_value = mock_result

    updated_plan = await audit_service.complete_audit_plan(db, plan, user_id)
    assert updated_plan.status == "completed"
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_complete_audit_plan_invalid_status():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        status="planned"
    )

    with pytest.raises(ValueError, match="only in-progress audits can be completed"):
        await audit_service.complete_audit_plan(db, plan, user_id)


@pytest.mark.asyncio
async def test_cancel_audit_plan_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        program_id=uuid.uuid4(),
        status="planned"
    )

    # Mock get AuditProgram during status update
    db.get.return_value = AuditProgram(program_id=plan.program_id, status="planned")
    # Mock db.execute for status update query
    mock_result = MagicMock()
    mock_result.all.return_value = [("cancelled",)]
    db.execute.return_value = mock_result

    updated_plan = await audit_service.cancel_audit_plan(db, plan, user_id)
    assert updated_plan.status == "cancelled"
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_cancel_audit_plan_invalid_status():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        status="in_progress"
    )

    with pytest.raises(ValueError, match="only planned audits can be cancelled"):
        await audit_service.cancel_audit_plan(db, plan, user_id)


@pytest.mark.asyncio
async def test_create_capa_from_finding_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        finding_type="major_nc",
        description="严重不符合项描述",
        clause_ref="8.1",
        due_date=date.today(),
        capa_ref_id=None
    )

    # Mock count for CAPA doc number generation
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    db.execute.return_value = mock_result

    capa = await audit_service.create_capa_from_finding(db, finding, user_id)
    assert capa.title == "【审核发现】8.1 - 严重不符合项描述"
    assert capa.severity == "严重"
    assert capa.d2_description == "严重不符合项描述"
    assert capa.status == "D1_TEAM"
    assert capa.created_by == user_id
    assert finding.capa_ref_id == capa.report_id
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_create_capa_from_finding_already_exists():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        capa_ref_id=uuid.uuid4()
    )

    with pytest.raises(ValueError, match="finding already has an associated CAPA"):
        await audit_service.create_capa_from_finding(db, finding, user_id)

