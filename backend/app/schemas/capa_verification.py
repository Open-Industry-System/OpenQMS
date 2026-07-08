import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator


class AdoptRequest(BaseModel):
    d_step: Literal["d4", "d5"]
    adopted_text: str
    source: str
    stage_index: int | None = None
    item_ref: dict | None = None


class AdoptResponse(BaseModel):
    adoption_id: uuid.UUID
    d_step: str
    field_value: str


class VerificationCreate(BaseModel):
    root_cause_text: str
    method: str | None = None
    result: str | None = None
    is_verified: bool = False
    evidence_attachments: list[dict] = []
    source_ref: dict | None = None

    @field_validator("root_cause_text")
    @classmethod
    def root_cause_text_must_be_non_empty(cls, v: str) -> str:
        # 防 D4 门禁被空验证记录绕过：gate 只数 is_verified=True 且绑定当前 d4_root_cause，
        # 根因文本必须非空白；strip 归一化后落库，与 gate 的 strip 比较一致
        if not v or not v.strip():
            raise ValueError("root_cause_text 不能为空")
        return v.strip()


class VerificationUpdate(BaseModel):
    method: str | None = None
    result: str | None = None
    is_verified: bool | None = None
    evidence_attachments: list[dict] | None = None


class VerificationResponse(BaseModel):
    verification_id: uuid.UUID
    capa_id: uuid.UUID
    root_cause_text: str
    method: str | None
    result: str | None
    is_verified: bool
    evidence_attachments: list[dict]
    source_ref: dict | None
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class D7NodeActionCreate(BaseModel):
    action: Literal["confirmed", "skipped"]
    fmea_id: uuid.UUID | None = None  # 规则引擎兜底推荐无关联 FMEA
    failure_mode_node_id: str  # FMEA 节点 id 或合成 key（rule:<hash>）
    failure_cause_node_id: str | None = None
    match_source: str
    reason: str | None = None


class D7AutoFillRequest(BaseModel):
    fmea_id: uuid.UUID | None = None
    failure_mode_node_id: str
    failure_cause_node_id: str
    match_source: str


class D7AutoFillResponse(BaseModel):
    action_id: uuid.UUID
    prevention_control_node_id: str
    prevention_control_name_after: str
    is_new_control: bool


class D7NodeActionResponse(BaseModel):
    action_id: uuid.UUID
    capa_id: uuid.UUID
    action: str
    fmea_id: uuid.UUID | None
    failure_mode_node_id: str
    failure_cause_node_id: str | None
    match_source: str
    prevention_control_node_id: str | None
    prevention_control_name_before: str | None
    prevention_control_name_after: str | None
    reason: str | None
    acted_by: uuid.UUID
    acted_at: datetime
    model_config = ConfigDict(from_attributes=True)
