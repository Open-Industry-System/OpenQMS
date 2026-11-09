"""Content-safe request and fixed restricted employee-preview contracts."""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from app.services.capa_d4_redaction import RULE_VERSION, validate_terms

Version = Annotated[str, Field(strict=True, pattern=r'^[0-9a-f]{64}$')]
CountKind = Literal['literal', 'credential', 'url', 'email', 'id_number', 'mobile', 'phone']
Count = Annotated[int, Field(strict=True, ge=0)]


class D4PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    replacement_terms: list[StrictStr] = Field(default_factory=list, repr=False)

    @field_validator('replacement_terms', mode='before')
    @classmethod
    def normalize_terms(cls, values):
        return list(validate_terms(values))


class D4PreviewSource(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    owner: Literal['fmea'] = 'fmea'
    object_id: UUID
    node_id: Annotated[str, Field(strict=True, min_length=1, max_length=128)]
    version: Version


class D4PreviewField(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    field: Literal['d4_root_cause', 'root_cause_text', 'result']
    verification_id: UUID | None
    redacted_text: StrictStr | None
    source_status: Literal['unverified', 'validated_reference']
    source_ref: D4PreviewSource | None
    match_counts: dict[CountKind, Count]

    @model_validator(mode='after')
    def associations(self):
        if ((self.field == 'd4_root_cause') != (self.verification_id is None)
                or (self.source_status == 'validated_reference') != (self.source_ref is not None)):
            raise ValueError('PREVIEW_CONTRACT_INVALID')
        return self


class D4PreviewVersion(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    report_id: UUID
    rule_version: Literal[RULE_VERSION] = RULE_VERSION
    source_version: Version


class D4TextPreview(D4PreviewVersion):
    generated_at: AwareDatetime
    expires_at: AwareDatetime
    data_class: Literal['restricted'] = 'restricted'
    projection: Literal['redaction_candidate'] = 'redaction_candidate'
    declassification_status: Literal['not_approved'] = 'not_approved'
    external_delivery_allowed: Literal[False] = False
    fields: list[D4PreviewField] = Field(min_length=1, max_length=401, repr=False)

    @model_validator(mode='after')
    def lifetime(self):
        if self.expires_at != self.generated_at + timedelta(seconds=30):
            raise ValueError('PREVIEW_CONTRACT_INVALID')
        return self


class D4PreviewAvailability(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    enabled: Literal[True] = True
