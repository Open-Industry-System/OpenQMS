import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Characteristic(BaseModel):
    id: uuid.UUID
    kind: Literal["product", "process"]
    name: str
    specification: str | None = None
    unit: str | None = None
    classification: str | None = None
    reference: str | None = None
    related_product_characteristic_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("characteristic name must not be empty")
        return value


class CharacteristicSourceRef(BaseModel):
    mapping_version: int
    fmea_id: uuid.UUID
    step_id: str
    function_id: str
    work_element_id: str | None = None
    characteristic_id: uuid.UUID
    accepted_source_version_id: uuid.UUID | None = None
