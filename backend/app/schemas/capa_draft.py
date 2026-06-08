# backend/app/schemas/capa_draft.py
import uuid
from typing import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["structured", "paragraph"] = "structured"
    request_id: str


class DraftResponse(BaseModel):
    content: str
    structured_data: dict | None
    request_id: uuid.UUID
    step: str  # 生成草稿时的步骤，前端用于写入正确字段


# --- 段落模式输出 ---
class ParagraphLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str


# --- D2 结构化输出 ---
class D2StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_statement: str
    affected_product: str
    defect_description: str
    occurrence_context: str
    impact_scope: str


class D2StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D2StructuredData


# --- D3 结构化输出 ---
class ContainmentAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    responsible: Literal["[待填写]"] = "[待填写]"
    deadline: Literal["[待填写]"] = "[待填写]"


class D3StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    containment_actions: list[ContainmentAction]
    verification_method: str


class D3StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D3StructuredData


# --- D4 结构化输出 ---
class CandidateRootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["人", "机", "料", "法", "环", "测"]
    description: str
    evidence: str


class D4StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_root_causes: list[CandidateRootCause]


class D4StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D4StructuredData


# --- D5 结构化输出 ---
class CorrectiveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    target_root_cause: str = Field(default="[待填写]")
    responsible: Literal["[待填写]"] = "[待填写]"
    deadline: Literal["[待填写]"] = "[待填写]"


class D5StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corrective_actions: list[CorrectiveAction]


class D5StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D5StructuredData


# --- D6 结构化输出 ---
class D6StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_plan: str
    evidence_checklist: list[str]


class D6StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D6StructuredData


# --- D7 结构化输出 ---
class PreventionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    implementation_plan: str


class D7StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preventive_actions: list[PreventionAction]
    standardization_plan: str
    training_plan: str


class D7StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D7StructuredData


# --- D8 结构化输出 ---
class D8StructuredData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    lessons_learned: str


class D8StructuredLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structured_data: D8StructuredData


STEP_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "d2": D2StructuredLLMOutput,
    "d3": D3StructuredLLMOutput,
    "d4": D4StructuredLLMOutput,
    "d5": D5StructuredLLMOutput,
    "d6": D6StructuredLLMOutput,
    "d7": D7StructuredLLMOutput,
    "d8": D8StructuredLLMOutput,
}
