import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


# ─── Material ───

class IqcMaterialCreate(BaseModel):
    part_no: str
    part_name: str
    part_spec: str | None = None
    material_type: str = "raw"
    default_aql: float | None = None
    default_inspection_level: str | None = None
    unit: str | None = None
    product_line_code: str = "DC-DC-100"

    @field_validator("part_no", "part_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class IqcMaterialUpdate(BaseModel):
    part_name: str | None = None
    part_spec: str | None = None
    material_type: str | None = None
    default_aql: float | None = None
    default_inspection_level: str | None = None
    unit: str | None = None
    product_line_code: str | None = None
    status: str | None = None


class IqcMaterialResponse(BaseModel):
    material_id: uuid.UUID
    part_no: str
    part_name: str
    part_spec: str | None
    material_type: str
    default_aql: float | None
    default_inspection_level: str | None
    unit: str | None
    product_line_code: str
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcMaterialListResponse(BaseModel):
    items: list[IqcMaterialResponse]
    total: int
    page: int
    page_size: int


# ─── Template Items ───

class IqcTemplateItemCreate(BaseModel):
    sort_order: int = 0
    category: str
    item_name: str
    inspection_method: str | None = None
    inspect_type: str = "attribute"
    spec_upper: float | None = None
    spec_lower: float | None = None
    target_value: float | None = None
    unit: str | None = None
    sample_size: int | None = None
    aql_level: float | None = None


class IqcTemplateItemResponse(BaseModel):
    item_id: uuid.UUID
    template_id: uuid.UUID
    sort_order: int
    category: str
    item_name: str
    inspection_method: str | None
    inspect_type: str
    spec_upper: float | None
    spec_lower: float | None
    target_value: float | None
    unit: str | None
    sample_size: int | None
    aql_level: float | None

    model_config = {"from_attributes": True}


# ─── Template ───

class IqcTemplateCreate(BaseModel):
    template_name: str
    material_id: uuid.UUID
    items: list[IqcTemplateItemCreate] = []


class IqcTemplateResponse(BaseModel):
    template_id: uuid.UUID
    template_name: str
    material_id: uuid.UUID
    version: int
    is_active: bool
    items: list[IqcTemplateItemResponse] = []
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcTemplateListResponse(BaseModel):
    items: list[IqcTemplateResponse]
    total: int
    page: int
    page_size: int


# ─── Inspection Items (instance) ───

class IqcItemMeasurementCreate(BaseModel):
    sequence_no: int = 1
    measured_value: float | None = None
    attribute_result: str | None = None
    remark: str | None = None


class IqcItemMeasurementResponse(BaseModel):
    measurement_id: uuid.UUID
    item_id: uuid.UUID
    sequence_no: int
    measured_value: float | None
    attribute_result: str | None
    remark: str | None

    model_config = {"from_attributes": True}


class IqcInspectionItemResponse(BaseModel):
    item_id: uuid.UUID
    inspection_id: uuid.UUID
    template_item_id: uuid.UUID | None
    sort_order: int
    category: str
    item_name: str
    inspect_type: str
    spec_upper: float | None
    spec_lower: float | None
    target_value: float | None
    sample_size: int | None
    accept_no: int | None
    reject_no: int | None
    defect_qty: int
    result: str
    remark: str | None
    measurements: list[IqcItemMeasurementResponse] = []

    model_config = {"from_attributes": True}


class IqcInspectionItemUpdate(BaseModel):
    defect_qty: int | None = None
    result: str | None = None
    remark: str | None = None
    measurements: list[IqcItemMeasurementCreate] | None = None


class IqcBatchItemUpdate(BaseModel):
    items: list[IqcInspectionItemUpdate]


# ─── Inspection ───

class IqcInspectionCreate(BaseModel):
    supplier_id: uuid.UUID
    inspection_mode: str = "quick"
    material_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    aql_level: float | None = None
    inspection_level: str = "II"
    inspection_date: date | None = None
    product_line_code: str | None = None


class IqcInspectionUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    inspection_date: date | None = None


class IqcInspectionJudge(BaseModel):
    inspection_result: str
    defect_qty: int = 0
    defect_description: str | None = None
    sample_qty: int | None = None


class IqcInspectionConcession(BaseModel):
    reason: str


class IqcInspectionResponse(BaseModel):
    inspection_id: uuid.UUID
    inspection_no: str
    supplier_id: uuid.UUID
    inspection_mode: str
    material_id: uuid.UUID | None
    template_id: uuid.UUID | None
    part_no: str | None
    part_name: str | None
    lot_no: str | None
    lot_qty: int | None
    sample_qty: int | None
    aql_level: str | None
    inspection_level: str | None
    sampling_standard: str | None
    code_letter: str | None
    accept_number: int | None
    reject_number: int | None
    inspection_result: str
    defect_qty: int
    defect_description: str | None
    status: str
    re_inspection: bool
    parent_inspection_id: uuid.UUID | None
    product_line_code: str | None
    linked_capa_id: uuid.UUID | None
    linked_scar_id: uuid.UUID | None
    judged_by: uuid.UUID | None
    judged_at: datetime | None
    inspection_date: date | None
    inspected_by: uuid.UUID | None
    items: list[IqcInspectionItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcInspectionListResponse(BaseModel):
    items: list[IqcInspectionResponse]
    total: int
    page: int
    page_size: int


# ─── AQL ───

class AqlCalculateRequest(BaseModel):
    lot_qty: int
    aql_level: float
    inspection_level: str = "II"


class AqlCalculateResponse(BaseModel):
    code_letter: str
    sample_size: int
    accept_number: int
    reject_number: int
    aql_level: float
    inspection_level: str


# ─── Stats ───

class IqcStatsResponse(BaseModel):
    total_inspections: int
    accepted_count: int
    rejected_count: int
    concession_count: int
    acceptance_rate: float
    rejection_rate: float
