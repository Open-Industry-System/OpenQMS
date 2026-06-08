import uuid

from pydantic import BaseModel, Field


class WidgetLayoutItem(BaseModel):
    i: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=80)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class LayoutConfig(BaseModel):
    lg: list[WidgetLayoutItem] = Field(default_factory=list, max_length=20)


class DashboardLayoutResponse(BaseModel):
    layout_id: uuid.UUID | None
    user_id: uuid.UUID
    layout_config: LayoutConfig
    created_at: str | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class DashboardLayoutUpdate(BaseModel):
    layout_config: LayoutConfig


class DashboardWidgetsResponse(BaseModel):
    kpi: dict = Field(default_factory=dict)
    alerts: dict = Field(default_factory=dict)
    recent_actions: list = Field(default_factory=list)
    spc: dict = Field(default_factory=dict)
    msa: dict = Field(default_factory=dict)
    iqc: dict = Field(default_factory=dict)
    mes: dict = Field(default_factory=dict)
    supplier: dict = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)
