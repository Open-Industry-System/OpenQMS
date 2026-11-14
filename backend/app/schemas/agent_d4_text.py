"""Strict local D4 candidate contracts; validation does not grant permission."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool,
    StrictStr, StringConstraints, field_validator,
)


def _canonical_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        parsed = UUID(value)
        if str(parsed) == value:
            return parsed
    raise ValueError('Canonical UUID required')


CanonicalUUID = Annotated[UUID, BeforeValidator(_canonical_uuid)]
OpaqueDigest = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
CauseNodeId = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]


class SourceDeclaration(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    declares_complete_coverage: StrictBool

    @field_validator('declares_complete_coverage')
    @classmethod
    def _explicit_complete(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError('Explicit complete coverage declaration required')
        return value


class DerivedSourceScopeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    target_report_id: CanonicalUUID
    fmea_id: CanonicalUUID
    cause_node_id: CauseNodeId


class D4RootCauseTextProjection(BaseModel):
    model_config = ConfigDict(
        extra='forbid', strict=True, protected_namespaces=('model_validate', 'model_dump'),
    )
    protocol: Literal['1']
    run_id: CanonicalUUID
    task_id: CanonicalUUID
    report_id: CanonicalUUID
    recipient_installation_id: CanonicalUUID
    plugin_version: StrictStr
    receipt_id: CanonicalUUID
    generated_at: AwareDatetime
    projection_id: Literal['capa.d4.root_cause_candidate.masked.v1']
    data_class: Literal['restricted']
    projection: Literal['masked']
    candidate_kind: Literal['redaction_candidate']
    declassification_status: Literal['not_approved']
    source_proof: Literal['employee_declared_complete_v1']
    source_authorization: Literal['current']
    model_delivery_allowed: StrictBool
    delivery_scope: Literal['local_plugin_only']
    rule_version: Literal['capa.d4.redaction.v1']
    source_version: OpaqueDigest
    source_proof_digest: OpaqueDigest
    policy_binding: OpaqueDigest
    projection_digest: OpaqueDigest
    field: Literal['d4_root_cause']
    text: StrictStr | None = Field(repr=False)

    @field_validator('model_delivery_allowed')
    @classmethod
    def _no_model_delivery(cls, value: bool) -> bool:
        if value is not False:
            raise ValueError('Model delivery forbidden')
        return value

    @field_validator('generated_at', mode='before')
    @classmethod
    def _aware_time_input(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        raise ValueError('Aware datetime required')
