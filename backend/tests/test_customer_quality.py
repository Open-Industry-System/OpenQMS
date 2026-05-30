import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.customer_quality_service import (
    ComplaintStatus,
    RMAStatus,
    calculate_customer_ppm,
    complaint_is_overdue,
    transition_complaint_status,
    transition_rma_status,
    calculate_risk_light,
)


def test_complaint_status_transitions():
    assert transition_complaint_status("open", "start_investigation") == "investigating"
    assert transition_complaint_status("investigating", "mark_responded") == "responded"
    assert transition_complaint_status("responded", "close") == "closed"
    assert transition_complaint_status("open", "cancel") == "cancelled"
    with pytest.raises(ValueError, match="invalid complaint transition"):
        transition_complaint_status("closed", "start_investigation")


def test_rma_status_transitions():
    assert transition_rma_status("open", "start_analysis") == "analysis"
    assert transition_rma_status("analysis", "mark_action_pending") == "action_pending"
    assert transition_rma_status("action_pending", "close") == "closed"
    assert transition_rma_status("open", "cancel") == "cancelled"
    with pytest.raises(ValueError, match="invalid RMA transition"):
        transition_rma_status("closed", "start_analysis")


def test_complaint_overdue_excludes_closed_and_cancelled():
    yesterday = date.today() - timedelta(days=1)
    assert complaint_is_overdue("open", yesterday) is True
    assert complaint_is_overdue("investigating", yesterday) is True
    assert complaint_is_overdue("closed", yesterday) is False
    assert complaint_is_overdue("cancelled", yesterday) is False
    assert complaint_is_overdue("open", None) is False


def test_ppm_returns_none_without_shipment_denominator():
    assert calculate_customer_ppm(impact_qty=5, independent_rma_qty=2, shipment_qty=None, annual_shipment_qty=None, date_from=None, date_to=None) is None


def test_ppm_uses_explicit_window_shipment_without_prorating():
    result = calculate_customer_ppm(impact_qty=5, independent_rma_qty=5, shipment_qty=1000, annual_shipment_qty=365000, date_from=date(2026, 1, 1), date_to=date(2026, 1, 10))
    assert result == 10000.0


def test_ppm_prorates_annual_shipment_by_inclusive_window():
    result = calculate_customer_ppm(impact_qty=10, independent_rma_qty=0, shipment_qty=None, annual_shipment_qty=36500, date_from=date(2026, 1, 1), date_to=date(2026, 1, 10))
    assert result == 10000.0


def test_normalize_window_defaults_to_last_90_days_inclusive():
    from app.services import customer_quality_service

    today = date(2026, 5, 26)

    assert customer_quality_service._normalize_window(None, None, today=today) == (
        date(2026, 2, 26),
        today,
    )
    assert customer_quality_service._normalize_window(None, date(2026, 4, 30), today=today) == (
        date(2026, 1, 31),
        date(2026, 4, 30),
    )
    assert customer_quality_service._normalize_window(date(2026, 4, 1), None, today=today) == (
        date(2026, 4, 1),
        today,
    )


def test_direct_terminal_status_updates_are_rejected():
    from app.services import customer_quality_service

    with pytest.raises(ValueError, match="transition endpoint"):
        customer_quality_service._validate_direct_status_update(
            "responded",
            "closed",
            {status.value for status in ComplaintStatus},
            {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value},
            "complaint",
        )

    with pytest.raises(ValueError, match="transition endpoint"):
        customer_quality_service._validate_direct_status_update(
            "action_pending",
            "closed",
            {status.value for status in RMAStatus},
            {RMAStatus.CLOSED.value, RMAStatus.CANCELLED.value},
            "RMA",
        )


def test_initial_terminal_statuses_are_rejected():
    from app.services import customer_quality_service

    customer_quality_service._validate_initial_status(
        "open",
        {status.value for status in ComplaintStatus},
        {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value},
        "complaint",
    )

    with pytest.raises(ValueError, match="initial status cannot be terminal"):
        customer_quality_service._validate_initial_status(
            "closed",
            {status.value for status in ComplaintStatus},
            {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value},
            "complaint",
        )

    with pytest.raises(ValueError, match="initial status cannot be terminal"):
        customer_quality_service._validate_initial_status(
            "cancelled",
            {status.value for status in RMAStatus},
            {RMAStatus.CLOSED.value, RMAStatus.CANCELLED.value},
            "RMA",
        )


def test_rma_link_validation_uses_effective_update_tuple():
    from app.services import customer_quality_service

    complaint_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    rma = SimpleNamespace(
        complaint_id=complaint_id,
        customer_id=customer_id,
        product_line_code="DC-DC-100",
    )

    assert customer_quality_service._effective_rma_link_tuple(
        rma, {"product_line_code": "AC-DC-200"}
    ) == (complaint_id, customer_id, "AC-DC-200")
    assert customer_quality_service._effective_rma_link_tuple(rma, {"customer_id": None}) == (
        complaint_id,
        customer_id,
        "DC-DC-100",
    )


def test_complaint_link_identity_change_detection():
    from app.services import customer_quality_service

    customer_id = uuid.uuid4()
    complaint = SimpleNamespace(
        customer_id=customer_id,
        product_line_code="DC-DC-100",
    )

    assert customer_quality_service._complaint_link_identity_changed(
        complaint, {"customer_id": customer_id}
    ) is False
    assert customer_quality_service._complaint_link_identity_changed(
        complaint, {"product_line_code": "DC-DC-100"}
    ) is False
    assert customer_quality_service._complaint_link_identity_changed(
        complaint, {"customer_id": uuid.uuid4()}
    ) is True
    assert customer_quality_service._complaint_link_identity_changed(
        complaint, {"product_line_code": "AC-DC-200"}
    ) is True


@pytest.mark.asyncio
async def test_link_target_guards_reject_missing_records():
    from app.services import customer_quality_service

    db = SimpleNamespace(get=AsyncMock(return_value=None))

    with pytest.raises(ValueError, match="CAPA not found"):
        await customer_quality_service._ensure_capa(db, uuid.uuid4())

    with pytest.raises(ValueError, match="FMEA not found"):
        await customer_quality_service._ensure_fmea(db, uuid.uuid4())


def test_risk_light_priority():
    assert calculate_risk_light(open_fatal_count=1, overdue_count=0, open_count=0, ppm=None, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=1, open_count=0, ppm=None, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=250, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=1, ppm=None, ppm_target=100) == "yellow"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=120, ppm_target=100) == "yellow"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=200, ppm_target=100) == "yellow"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=80, ppm_target=100) == "green"


def test_customer_quality_models_have_table_names():
    from app.models.customer_quality import Customer, CustomerComplaint, RMARecord

    assert Customer.__tablename__ == "customers"
    assert CustomerComplaint.__tablename__ == "customer_complaints"
    assert RMARecord.__tablename__ == "rma_records"


def test_complaint_schema_rejects_invalid_category():
    from app.schemas.customer_quality import ComplaintCreate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ComplaintCreate(
            complaint_no="CC-2026-001",
            product_line_code="DC-DC-100",
            customer_id="00000000-0000-0000-0000-000000000001",
            category="bad",
            severity="一般",
            defect_desc="功能异常",
            received_date=date.today(),
        )


# === Customer Quality Enhancements Tests ===

def test_scar_related_create_optional_supplier_id():
    from app.schemas.customer_quality import SCARRelatedCreate
    req = SCARRelatedCreate(description="test")
    assert req.supplier_id is None
    assert req.description == "test"


def test_scar_related_create_rejects_invalid_quantity():
    from app.schemas.customer_quality import ShipmentRecordCreate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ShipmentRecordCreate(shipment_date=date.today(), quantity=0)


def test_ppm_fallback_priority_explicit_shipment_qty_overrides():
    """When shipment_qty is passed, use it directly."""
    result = calculate_customer_ppm(
        impact_qty=5, independent_rma_qty=0,
        shipment_qty=100, annual_shipment_qty=36500,
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 10),
    )
    assert result == 50000.0


def test_ppm_returns_none_when_no_denominator():
    """No shipment_qty and no annual_shipment_qty returns None."""
    result = calculate_customer_ppm(
        impact_qty=5, independent_rma_qty=0,
        shipment_qty=None, annual_shipment_qty=None,
        date_from=date(2026, 1, 1), date_to=date(2026, 1, 10),
    )
    assert result is None


def test_customer_requirements_item_structure():
    from app.schemas.control_plan import CustomerRequirementItem
    item = CustomerRequirementItem(
        title="包装要求",
        description="外箱标识",
        source_customer_id=uuid.uuid4(),
        source="csr",
    )
    assert item.source == "csr"
    assert item.title == "包装要求"


def test_dashboard_schema_accepts_new_fields():
    from app.schemas.customer_quality import CustomerQualityDashboardResponse
    data = {
        "kpi": {},
        "customers": [],
        "trend": [],
        "complaints_by_status": {},
        "complaints_by_severity": {},
        "rma_by_status": {},
        "rma_by_responsibility": {},
        "spc_cpks": [{"product_line_code": "DC-DC-100", "cpk": 1.5, "ppk": 1.3}],
        "warranty_total": 10000.0,
        "avg_satisfaction": 8.5,
        "audit_summary": {"completed_count": 2, "finding_count": 3},
    }
    dashboard = CustomerQualityDashboardResponse(**data)
    assert dashboard.warranty_total == 10000.0
    assert dashboard.avg_satisfaction == 8.5
    assert len(dashboard.spc_cpks) == 1
