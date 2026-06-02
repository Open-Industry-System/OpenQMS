import uuid
from datetime import datetime
from pydantic import BaseModel


class ControlPlanItemBase(BaseModel):
    step_no: str | None = None
    process_name: str | None = None
    equipment: str | None = None
    characteristic_no: str | None = None
    product_characteristic: str | None = None
    process_characteristic: str | None = None
    special_class: str | None = None
    specification_tolerance: str | None = None
    evaluation_method: str | None = None
    sample_size: str | None = None
    sample_frequency: str | None = None
    control_method: str | None = None
    reaction_plan: str | None = None
    source_fmea_node_id: str | None = None
    sop_ref: str | None = None
    spc_chart_id: uuid.UUID | None = None
    gauge_id: uuid.UUID | None = None
    sort_order: int = 0


class ControlPlanItemCreate(ControlPlanItemBase):
    pass


class ControlPlanItemUpdate(ControlPlanItemBase):
    item_id: str | None = None


class ControlPlanItemResponse(ControlPlanItemBase):
    item_id: uuid.UUID

    model_config = {"from_attributes": True}


class ControlPlanBase(BaseModel):
    title: str
    document_no: str
    fmea_ref_id: uuid.UUID | None = None
    phase: str = "production"
    part_no: str | None = None
    part_name: str | None = None
    contact_info: str | None = None
    drawing_rev: str | None = None
    org_factory: str | None = None
    core_group: str | None = None
    product_line_code: str = "DC-DC-100"


class ControlPlanCreate(ControlPlanBase):
    pass


class ControlPlanUpdate(BaseModel):
    title: str | None = None
    document_no: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    phase: str | None = None
    part_no: str | None = None
    part_name: str | None = None
    contact_info: str | None = None
    drawing_rev: str | None = None
    org_factory: str | None = None
    core_group: str | None = None
    product_line_code: str | None = None
    items: list[ControlPlanItemCreate] | None = None
    lock_version: int | None = None
    confirmed_latest_lock_version: int | None = None


# ─── CSR Sync ───

class CSRSyncRequest(BaseModel):
    customer_ids: list[uuid.UUID]


class CustomerRequirementItem(BaseModel):
    title: str
    description: str = ""
    source_customer_id: uuid.UUID | None = None
    synced_at: datetime | None = None
    source: str = "manual"  # "csr" | "manual"


class ControlPlanResponse(ControlPlanBase):
    cp_id: uuid.UUID
    product_line_code: str
    status: str
    version: int
    items: list[ControlPlanItemResponse] = []
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    customer_requirements: list[CustomerRequirementItem] = []

    model_config = {"from_attributes": True}


class ControlPlanListResponse(BaseModel):
    items: list[ControlPlanResponse]
    total: int
    page: int
    page_size: int


class ImportFromFMEARequest(BaseModel):
    fmea_id: uuid.UUID
    step_nos: list[str] | None = None
