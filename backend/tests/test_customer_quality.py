from datetime import date, timedelta

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
