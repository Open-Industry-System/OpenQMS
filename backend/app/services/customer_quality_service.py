from datetime import date, timedelta
from enum import StrEnum


class ComplaintStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESPONDED = "responded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RMAStatus(StrEnum):
    OPEN = "open"
    ANALYSIS = "analysis"
    ACTION_PENDING = "action_pending"
    CLOSED = "closed"
    CANCELLED = "cancelled"


COMPLAINT_TRANSITIONS = {
    (ComplaintStatus.OPEN, "start_investigation"): ComplaintStatus.INVESTIGATING,
    (ComplaintStatus.INVESTIGATING, "mark_responded"): ComplaintStatus.RESPONDED,
    (ComplaintStatus.RESPONDED, "close"): ComplaintStatus.CLOSED,
    (ComplaintStatus.OPEN, "cancel"): ComplaintStatus.CANCELLED,
    (ComplaintStatus.INVESTIGATING, "cancel"): ComplaintStatus.CANCELLED,
    (ComplaintStatus.RESPONDED, "start_investigation"): ComplaintStatus.INVESTIGATING,
}

RMA_TRANSITIONS = {
    (RMAStatus.OPEN, "start_analysis"): RMAStatus.ANALYSIS,
    (RMAStatus.ANALYSIS, "mark_action_pending"): RMAStatus.ACTION_PENDING,
    (RMAStatus.ACTION_PENDING, "close"): RMAStatus.CLOSED,
    (RMAStatus.OPEN, "cancel"): RMAStatus.CANCELLED,
    (RMAStatus.ANALYSIS, "cancel"): RMAStatus.CANCELLED,
}


def transition_complaint_status(status: str, action: str) -> str:
    try:
        next_status = COMPLAINT_TRANSITIONS[(ComplaintStatus(status), action)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid complaint transition: {status} + {action}") from exc
    return next_status.value


def transition_rma_status(status: str, action: str) -> str:
    try:
        next_status = RMA_TRANSITIONS[(RMAStatus(status), action)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid RMA transition: {status} + {action}") from exc
    return next_status.value


def complaint_is_overdue(status: str, due_date: date | None, today: date | None = None) -> bool:
    if due_date is None or status in {ComplaintStatus.CLOSED.value, ComplaintStatus.CANCELLED.value}:
        return False
    return due_date < (today or date.today())


def calculate_customer_ppm(
    *,
    impact_qty: int,
    independent_rma_qty: int,
    shipment_qty: int | None,
    annual_shipment_qty: int | None,
    date_from: date | None,
    date_to: date | None,
) -> float | None:
    if shipment_qty is not None:
        denominator = shipment_qty
    elif annual_shipment_qty is not None:
        window_end = date_to or date.today()
        window_start = date_from or (window_end - timedelta(days=89))
        window_days = (window_end - window_start).days + 1
        if window_days <= 0:
            return None
        denominator = annual_shipment_qty * window_days / 365
    else:
        return None

    if denominator <= 0:
        return None

    return round(((impact_qty + independent_rma_qty) / denominator) * 1_000_000, 2)


def calculate_risk_light(
    *,
    open_fatal_count: int,
    overdue_count: int,
    open_count: int,
    ppm: float | None,
    ppm_target: float | None,
) -> str:
    if open_fatal_count > 0 or overdue_count > 0:
        return "red"
    if ppm is not None and ppm_target is not None and ppm_target > 0:
        if ppm > ppm_target * 2:
            return "red"
        if ppm > ppm_target:
            return "yellow"
    if open_count > 0:
        return "yellow"
    return "green"
