from __future__ import annotations

from pydantic import BaseModel, model_validator


class LateralDecisionRequest(BaseModel):
    decision: str  # notify | skip
    skip_reason: str | None = None
    product_type_codes: list[str] | None = None  # forbidden (full-set only)

    @model_validator(mode="after")
    def _check(self):
        if self.decision not in ("notify", "skip"):
            raise ValueError("decision must be notify|skip")
        if self.product_type_codes is not None:
            raise ValueError("product_type_codes is forbidden (full-set decide only)")
        if self.decision == "skip" and not (self.skip_reason and self.skip_reason.strip()):
            raise ValueError("skip_reason required for skip")
        return self


class LateralNotificationOut(BaseModel):
    notification_id: str
    product_type_code: str
    product_line_code: str | None = None
    recipient_label: str
    decision: str
    status: str


class LateralDiffusionProjection(BaseModel):
    check_id: str
    status: str  # done | empty
    llm_status: str  # done | skipped
    truncated: bool
    similar_products: list
    decision: str | None = None  # notified | skipped | null
    notifications: list[LateralNotificationOut] = []
