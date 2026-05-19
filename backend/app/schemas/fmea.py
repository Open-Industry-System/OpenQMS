import uuid
from datetime import datetime
from pydantic import BaseModel


class GraphNodeSchema(BaseModel):
    id: str
    type: str
    name: str
    process_number: str | None = None
    severity: int = 0
    occurrence: int = 0
    detection: int = 0


class GraphEdgeSchema(BaseModel):
    source: str
    target: str
    type: str


class GraphDataSchema(BaseModel):
    nodes: list[GraphNodeSchema] = []
    edges: list[GraphEdgeSchema] = []


class FMEACreate(BaseModel):
    title: str
    document_no: str
    fmea_type: str = "PFMEA"


class FMEAUpdate(BaseModel):
    title: str | None = None
    graph_data: GraphDataSchema | None = None


class FMEAResponse(BaseModel):
    fmea_id: uuid.UUID
    document_no: str
    title: str
    fmea_type: str
    product_line_code: str
    status: str
    version: int
    graph_data: dict
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class FMEAListResponse(BaseModel):
    items: list[FMEAResponse]
    total: int
    page: int
    page_size: int


class TransitionRequest(BaseModel):
    target_status: str
