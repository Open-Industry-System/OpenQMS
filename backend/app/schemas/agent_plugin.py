"""Explicit plugin DTOs: metadata never exposes the persisted credential hash."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StringConstraints

CapabilityID = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=160)]
PluginKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
PluginVersion = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=40)]


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol_versions: list[Literal["1"]] = Field(min_length=1)
    required_capabilities: list[CapabilityID] = Field(default_factory=list)
    optional_capabilities: list[CapabilityID] = Field(default_factory=list)
    supports_resume: StrictBool = False


class PluginRegister(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plugin_key: PluginKey
    plugin_version: PluginVersion
    manifest: PluginManifest


class PluginOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    installation_id: UUID
    plugin_key: str
    plugin_version: str
    manifest: PluginManifest
    enabled: bool
    credential_epoch: int
    created_by: UUID
    created_at: datetime


class PluginSecretOut(BaseModel):
    """One-time registration or rotation result; never a list/detail DTO."""

    plugin: PluginOut
    secret: str = Field(repr=False)


class PluginEnabledUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


class PluginList(BaseModel):
    items: list[PluginOut]
    total: int
    page: int
    page_size: int


ProductLineCode = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=50)]


class PluginGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: CapabilityID
    factory_ids: list[UUID] = Field(min_length=1, max_length=100)
    product_line_codes: list[ProductLineCode] | None = Field(default=None, min_length=1, max_length=100)
    object_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    expires_at: AwareDatetime | None = None
    enabled: StrictBool = False


class PluginGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grant_id: UUID
    installation_id: UUID
    capability_id: str
    factory_ids: list[UUID]
    product_line_codes: list[str] | None
    object_ids: list[UUID] | None
    expires_at: datetime | None
    enabled: bool
    granted_by: UUID


class LocalTrialRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_credential_epoch: Annotated[int, Field(strict=True, ge=0, le=2147483646)]


class LocalTrialRevokeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    credential_epoch: int
    enabled: Literal[False]
    outcome: Literal["revoked", "already_fenced"]


class PluginGrantList(BaseModel):
    items: list[PluginGrantOut]
    total: int
    page: int
    page_size: int
