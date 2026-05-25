from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ============ InspectionCharacteristic ============

class InspectionCharacteristicCreate(BaseModel):
    product_line: str = Field(default="DC-DC-100")
    process_name: str = Field(..., min_length=1, max_length=100)
    characteristic_name: str = Field(..., min_length=1, max_length=100)
    spec_upper: float
    spec_lower: float
    target_value: Optional[float] = None
    chart_type: str = Field(..., pattern="^(xbar_r|imr|histogram|p|np|c|u)$")
    subgroup_size: int = Field(default=5, ge=1, le=10)
    rules_config: Optional[Dict[str, bool]] = None

    @field_validator("spec_upper")
    @classmethod
    def spec_upper_must_be_greater(cls, v: float, info) -> float:
        if "spec_lower" in info.data and v <= info.data["spec_lower"]:
            raise ValueError("spec_upper must be greater than spec_lower")
        return v


class InspectionCharacteristicUpdate(BaseModel):
    process_name: Optional[str] = None
    characteristic_name: Optional[str] = None
    spec_upper: Optional[float] = None
    spec_lower: Optional[float] = None
    target_value: Optional[float] = None
    chart_type: Optional[str] = None
    subgroup_size: Optional[int] = Field(default=None, ge=1, le=10)
    rules_config: Optional[Dict[str, bool]] = None
    control_limits_locked: Optional[bool] = None


class InspectionCharacteristicOut(BaseModel):
    ic_id: UUID
    ic_code: str
    product_line: str
    process_name: str
    characteristic_name: str
    spec_upper: float
    spec_lower: float
    target_value: Optional[float]
    chart_type: str
    subgroup_size: int
    control_limits_locked: bool
    rules_config: Dict[str, bool]
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InspectionCharacteristicListResponse(BaseModel):
    items: List[InspectionCharacteristicOut]
    total: int
    page: int
    page_size: int


# ============ Sample Batch / Values ============

class SampleValueCreate(BaseModel):
    sequence_no: int = Field(..., ge=1)
    value: float


class SampleBatchCreate(BaseModel):
    batch_no: str = Field(..., min_length=1, max_length=50)
    sampled_at: datetime
    values: List[float] = Field(default_factory=list)
    inspected_count: Optional[int] = Field(default=None, ge=1)
    defect_count: Optional[int] = Field(default=None, ge=0)


class SampleBatchOut(BaseModel):
    batch_id: UUID
    ic_id: UUID
    batch_no: str
    sampled_at: datetime
    subgroup_size: int
    values: List[float]
    inspected_count: Optional[int] = None
    defect_count: Optional[int] = None

    model_config = {"from_attributes": True}


# ============ Chart Data ============

class ChartDataPoint(BaseModel):
    batch_index: int
    batch_no: str
    sampled_at: datetime
    x_value: Optional[float] = None  # subgroup mean or individual value
    r_value: Optional[float] = None  # subgroup range or moving range
    alarm_flags: List[int] = []


class ControlLimits(BaseModel):
    ucl: Optional[float] = None
    lcl: Optional[float] = None
    cl: Optional[float] = None
    r_ucl: Optional[float] = None
    r_lcl: Optional[float] = None
    r_cl: Optional[float] = None
    ucl_list: Optional[List[float]] = None
    lcl_list: Optional[List[float]] = None


# ============ Control Limit Snapshots ============

class ControlLimitSnapshotOut(BaseModel):
    snapshot_id: UUID
    ic_id: UUID
    ucl: float
    lcl: float
    cl: float
    r_ucl: Optional[float] = None
    r_lcl: Optional[float] = None
    r_cl: Optional[float] = None
    version_no: int
    is_active: bool
    is_locked: bool
    calculated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ChartDataResponse(BaseModel):
    chart_type: str
    data_points: List[ChartDataPoint]
    limits: ControlLimits
    total_batches: int
    active_snapshot: Optional[ControlLimitSnapshotOut] = None


# ============ Capability ============

class CapabilityResponse(BaseModel):
    cp: float
    cpk: float
    cpu: float
    cpl: float
    pp: float
    ppk: float
    ppu: float
    ppl: float
    cm: float
    cmk: float
    theoretical_ppm: float
    actual_ppm: float
    grade: str
    advice: str


# ============ Alarms ============

class SPCAlarmOut(BaseModel):
    alarm_id: UUID
    ic_id: UUID
    batch_id: Optional[UUID]
    rule_no: int
    triggered_at: datetime
    severity: str
    status: str
    linked_capa_id: Optional[UUID]
    linked_fmea_node_id: Optional[UUID] = None
    acknowledged_by_id: Optional[UUID]
    acknowledged_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SPCAlarmListResponse(BaseModel):
    items: List[SPCAlarmOut]
    total: int
    page: int
    page_size: int


# ============ External Ingestion ============

class ExternalDataIngestion(BaseModel):
    ic_code: str
    batch_no: str
    values: List[float]
    sampled_at: datetime
