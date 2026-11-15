"""Strict R6 employee commands; identity and source coordinates are server owned."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.agent_d5_command import D5Command


from app.schemas.database_text import DatabaseTextInput

class _R6Command(DatabaseTextInput):
    model_config = ConfigDict(extra='forbid')
    operation_key: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9._:-]+$')
    expected_material_version: str = Field(min_length=1, max_length=512)


class D4Confirm(_R6Command):
    expected_candidate_version: str = Field(min_length=1, max_length=512)
    mode: Literal['append', 'replace'] = 'append'
    final_text: str

    @field_validator('final_text')
    @classmethod
    def bounded_text(cls, value: str) -> str:
        if not value.strip() or len(value.encode('utf-8')) > 16384:
            raise ValueError('Invalid D4 final text')
        return value


class D5Correct(_R6Command):
    expected_measure_version: str = Field(min_length=1, max_length=512)
    final_text: str
    reason: str

    @field_validator('final_text', 'reason')
    @classmethod
    def bounded_text(cls, value: str) -> str:
        if not value.strip() or len(value.encode('utf-8')) > 16384:
            raise ValueError('Invalid D5 correction text or reason')
        return value


class D4CandidateCommand(D5Command):
    """Runtime input; complete origins/input versions come from delivered receipts."""
    supporting: list[str] = Field(default_factory=list, max_length=100)
    opposing: list[str] = Field(default_factory=list, max_length=100)
    missing_information: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('supporting', 'opposing', 'missing_information')
    @classmethod
    def bounded_evidence(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip() or len(value.encode('utf-8')) > 16384:
                raise ValueError('Invalid D4 candidate evidence')
        return values


class _SourceCoordinate(DatabaseTextInput):
    model_config = ConfigDict(extra='forbid')
    object_id: UUID
    version: str = Field(min_length=1, max_length=128)
    factory_id: UUID
    product_line_code: str = Field(min_length=1, max_length=20)


class ReportSnapshotOrigin(_SourceCoordinate):
    kind: Literal['report_snapshot'] = 'report_snapshot'
    module: Literal['capa'] = 'capa'
    projection_id: Literal['capa.d2.snapshot.v1', 'capa.d3.snapshot.v1']
    snapshot_id: UUID


class FmeaProjectionOrigin(_SourceCoordinate):
    kind: Literal['fmea_projection'] = 'fmea_projection'
    module: Literal['fmea'] = 'fmea'
    projection_id: Literal['fmea.failure_cause.reference.v1']
    version: str = Field(pattern=r'^[0-9a-f]{64}$')
    fmea_id: UUID
    node_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def same_object(self):
        if self.object_id != self.fmea_id:
            raise ValueError('FMEA source object mismatch')
        return self


SourceOrigin = Annotated[ReportSnapshotOrigin | FmeaProjectionOrigin, Field(discriminator='kind')]
