import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from app.models.audit_program import AuditProgram
from app.models.audit_plan import AuditPlan
from app.models.audit_finding import AuditFinding
from app.models.capa import CAPAEightD
from app.services import audit_service
from app.services import customer_audit_service


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


# -- Customer Audit Service Tests --

@pytest.mark.asyncio
async def test_get_or_create_customer_program_existing():
    db = create_mock_db()
    existing = AuditProgram(program_id=uuid.uuid4(), audit_type="customer", program_year=2026)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute.return_value = mock_result

    program = await customer_audit_service._get_or_create_customer_program(db, 2026, uuid.uuid4())
    assert program == existing
    assert not db.add.called


@pytest.mark.asyncio
async def test_get_or_create_customer_program_new():
    db = create_mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    user_id = uuid.uuid4()
    program = await customer_audit_service._get_or_create_customer_program(db, 2026, user_id)
    assert program.audit_type == "customer"
    assert program.program_year == 2026
    assert program.program_no == "AP-2026-CUS-001"
    assert db.add.called


@pytest.mark.asyncio
async def test_generate_customer_audit_no():
    db = create_mock_db()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 3
    db.execute.return_value = mock_result

    no = await customer_audit_service._generate_customer_audit_no(db, 2026)
    assert no == "CA-2026-004"


@pytest.mark.asyncio
async def test_create_customer_audit_success():
    db = create_mock_db()
    user_id = uuid.uuid4()

    # First call: program lookup (none exists)
    # Second call: count for plan_no generation
    mock_result_prog = MagicMock()
    mock_result_prog.scalar_one_or_none.return_value = None
    mock_result_count = MagicMock()
    mock_result_count.scalar.return_value = 3
    db.execute.side_effect = [mock_result_prog, mock_result_count]

    plan = await customer_audit_service.create_customer_audit(
        db,
        audit_scope="范围",
        audit_criteria="准则",
        planned_date=date(2026, 6, 1),
        customer_name="Tesla",
        customer_type="OEM",
        audit_mode="on_site",
        lead_auditor=None,
        team_members=None,
        checklist=None,
        product_line_code="DC-DC-100",
        user_id=user_id,
    )
    assert plan.audit_category == "customer"
    assert plan.customer_name == "Tesla"
    assert plan.customer_type == "OEM"
    assert plan.audit_mode == "on_site"
    assert plan.status == "planned"
    assert db.add.called
    assert db.commit.called


@pytest.mark.asyncio
async def test_create_customer_audit_empty_name():
    db = create_mock_db()
    with pytest.raises(ValueError, match="customer_name is required"):
        await customer_audit_service.create_customer_audit(
            db,
            audit_scope="范围",
            audit_criteria="准则",
            planned_date=date(2026, 6, 1),
            customer_name="",
            customer_type="OEM",
            audit_mode=None,
            lead_auditor=None,
            team_members=None,
            checklist=None,
            product_line_code=None,
            user_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_create_customer_audit_invalid_type():
    db = create_mock_db()
    with pytest.raises(ValueError, match="invalid customer_type"):
        await customer_audit_service.create_customer_audit(
            db,
            audit_scope="范围",
            audit_criteria="准则",
            planned_date=date(2026, 6, 1),
            customer_name="X",
            customer_type="invalid",
            audit_mode=None,
            lead_auditor=None,
            team_members=None,
            checklist=None,
            product_line_code=None,
            user_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_create_customer_audit_invalid_mode():
    db = create_mock_db()
    with pytest.raises(ValueError, match="invalid audit_mode"):
        await customer_audit_service.create_customer_audit(
            db,
            audit_scope="范围",
            audit_criteria="准则",
            planned_date=date(2026, 6, 1),
            customer_name="X",
            customer_type="OEM",
            audit_mode="fly_by",
            lead_auditor=None,
            team_members=None,
            checklist=None,
            product_line_code=None,
            user_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_update_customer_audit_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        customer_name="Old",
        customer_type="OEM",
        audit_mode="on_site",
        audit_category="customer",
    )

    updated = await customer_audit_service.update_customer_audit(
        db, plan, user_id=user_id, customer_name="New", audit_mode="remote"
    )
    assert updated.customer_name == "New"
    assert updated.audit_mode == "remote"
    assert db.commit.called


@pytest.mark.asyncio
async def test_update_customer_audit_invalid_type():
    db = create_mock_db()
    plan = AuditPlan(audit_id=uuid.uuid4(), customer_type="OEM", audit_category="customer")
    with pytest.raises(ValueError, match="invalid customer_type"):
        await customer_audit_service.update_customer_audit(
            db, plan, user_id=uuid.uuid4(), customer_type="bad"
        )


@pytest.mark.asyncio
async def test_complete_customer_audit_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(
        audit_id=uuid.uuid4(),
        status="in_progress",
        audit_category="customer",
    )

    # No unclosed findings
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    updated = await customer_audit_service.complete_customer_audit(db, plan, user_id)
    assert updated.status == "completed"
    assert db.commit.called


@pytest.mark.asyncio
async def test_complete_customer_audit_unclosed_findings():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(audit_id=uuid.uuid4(), status="in_progress", audit_category="customer")

    mock_result = MagicMock()
    mock_result.all.return_value = [(uuid.uuid4(), "open", False)]
    db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="cannot complete: 1 finding"):
        await customer_audit_service.complete_customer_audit(db, plan, user_id)


@pytest.mark.asyncio
async def test_complete_customer_audit_unconfirmed_findings():
    db = create_mock_db()
    user_id = uuid.uuid4()
    plan = AuditPlan(audit_id=uuid.uuid4(), status="in_progress", audit_category="customer")

    # First call: no unclosed findings
    # Second call: one unconfirmed closed finding
    mock_result1 = MagicMock()
    mock_result1.all.return_value = []
    mock_result2 = MagicMock()
    mock_result2.all.return_value = [(uuid.uuid4(),)]
    db.execute.side_effect = [mock_result1, mock_result2]

    with pytest.raises(ValueError, match="cannot complete: 1 finding"):
        await customer_audit_service.complete_customer_audit(db, plan, user_id)


@pytest.mark.asyncio
async def test_transition_finding_start_progress():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="open",
        audit_id=uuid.uuid4(),
    )

    updated = await customer_audit_service.transition_finding(
        db, finding, action="start_progress", user_id=user_id
    )
    assert updated.status == "in_progress"
    assert db.commit.called


@pytest.mark.asyncio
async def test_transition_finding_close_missing_fields():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="in_progress",
        root_cause=None,
        corrective_action=None,
    )

    with pytest.raises(ValueError, match="root_cause is required"):
        await customer_audit_service.transition_finding(
            db, finding, action="close", user_id=user_id
        )


@pytest.mark.asyncio
async def test_transition_finding_close_customer_not_confirmed():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="in_progress",
        root_cause="root",
        corrective_action="action",
        customer_confirmed=False,
        audit_id=uuid.uuid4(),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "customer"
    db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="customer confirmation is required"):
        await customer_audit_service.transition_finding(
            db, finding, action="close", user_id=user_id
        )


@pytest.mark.asyncio
async def test_transition_finding_close_with_capa_not_closed():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="in_progress",
        root_cause="root",
        corrective_action="action",
        capa_ref_id=uuid.uuid4(),
        customer_confirmed=True,
        audit_id=uuid.uuid4(),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "D7_PREVENTION"
    db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="linked CAPA status"):
        await customer_audit_service.transition_finding(
            db, finding, action="close", user_id=user_id
        )


@pytest.mark.asyncio
async def test_transition_finding_close_success():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="in_progress",
        root_cause="root",
        corrective_action="action",
        customer_confirmed=True,
        audit_id=uuid.uuid4(),
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "internal"
    db.execute.return_value = mock_result

    updated = await customer_audit_service.transition_finding(
        db, finding, action="close", user_id=user_id
    )
    assert updated.status == "closed"
    assert db.commit.called


@pytest.mark.asyncio
async def test_customer_confirm_finding():
    db = create_mock_db()
    user_id = uuid.uuid4()
    finding = AuditFinding(
        finding_id=uuid.uuid4(),
        status="in_progress",
        customer_confirmed=False,
    )

    updated = await customer_audit_service.customer_confirm_finding(
        db, finding, confirmation_date=date(2026, 6, 15), attachments=[], user_id=user_id
    )
    assert updated.customer_confirmed is True
    assert updated.customer_confirmation_date == date(2026, 6, 15)
    assert db.commit.called


@pytest.mark.asyncio
async def test_get_customer_audit_stats():
    db = create_mock_db()

    def mock_scalar():
        return 5

    mock_result = MagicMock()
    mock_result.scalar = mock_scalar
    db.execute.return_value = mock_result

    stats = await customer_audit_service.get_customer_audit_stats(db)
    assert stats["total_customer_audits"] == 5
    assert "planned" in stats
    assert "in_progress" in stats
    assert "completed" in stats
    assert "open_findings" in stats
    assert "major_nc_count" in stats
    assert "customer_confirmed_count" in stats
    assert "pending_confirmation_count" in stats

