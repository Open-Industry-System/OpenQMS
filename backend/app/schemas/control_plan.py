import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.characteristic import CharacteristicSourceRef


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
    # Optional: when present and matches an existing item under this CP,
    # update_control_plan reuses the UUID instead of regenerating (doc-gate
    # target_key stability). Temp client ids (e.g. "temp-…") are ignored.
    item_id: uuid.UUID | str | None = None


class ControlPlanItemUpdate(ControlPlanItemBase):
    item_id: str | None = None


class ControlPlanItemResponse(ControlPlanItemBase):
    item_id: uuid.UUID
    source_characteristic_ref: CharacteristicSourceRef | None = None

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
    sync_pending: bool = False
    source_fmea_version_id: uuid.UUID | None = None
    product_line_code: str
    status: str
    version: int
    lock_version: int = 0
    items: list[ControlPlanItemResponse] = []
    factory_id: uuid.UUID | None = None
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
    # Optional only so old clients receive 409/re-preview rather than unsafe defaults.
    source_fmea_version_id: uuid.UUID | None = None
    expected_lock_version: int | None = Field(default=None, ge=0)
    step_ids: list[str] | None = None
    step_nos: list[str] | None = None
    preview_digest: str | None = None
    selected_candidate_keys: list[str] | None = None

    model_config = {"extra": "forbid"}


class CharacteristicImportIssue(BaseModel):
    code: str
    node_id: str
    blocking: bool
    message: str


class CharacteristicImportCandidate(BaseModel):
    candidate_key: str
    action: str
    item_id: uuid.UUID | None = None
    source_ref: CharacteristicSourceRef
    fields: dict[str, str | None]


class CharacteristicImportPreview(BaseModel):
    source_fmea_version_id: uuid.UUID
    expected_lock_version: int
    mapping_version: int
    preview_digest: str
    items: list[CharacteristicImportCandidate]
    issues: list[CharacteristicImportIssue]
