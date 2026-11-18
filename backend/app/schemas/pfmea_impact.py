"""Immutable formal CAPA input to PFMEA assessment."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ImpactDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MeasureKey(_ImpactDTO):
    measure_id: UUID
    # None identifies the immutable adoption before any formal correction.
    formal_revision: UUID | None


class ImpactSourceRef(_ImpactDTO):
    source_id: UUID
    module: Literal["capa", "fmea"]
    object_id: UUID
    projection_id: str
    version: str
    factory_id: UUID
    product_line_code: str
    snapshot_id: UUID | None = None
    node_id: str | None = None
    source_version_counter: int | None = Field(default=None, ge=0)


class CapaImpactBinding(_ImpactDTO):
    tenant_id: UUID
    tenant_generation: int = Field(ge=0)
    report_id: UUID
    factory_id: UUID
    product_line_code: str
    root_revision: UUID
    proof_id: UUID
    verification_ref: UUID
    verification_version: str
    measures: tuple[MeasureKey, ...]
    sources: tuple[ImpactSourceRef, ...]


class CapaImpactMeasure(_ImpactDTO):
    key: MeasureKey
    adoption_ref: UUID
    revision_no: int = Field(ge=0)
    text: str = Field(repr=False)
    source_ids: tuple[UUID, ...]


class CapaImpactMaterial(_ImpactDTO):
    binding: CapaImpactBinding
    root_cause: str = Field(repr=False)
    problem_description: str | None = Field(repr=False)
    primary_source_id: UUID
    measures: tuple[CapaImpactMeasure, ...]
    implementation_verification: Literal["not_included"] = "not_included"
