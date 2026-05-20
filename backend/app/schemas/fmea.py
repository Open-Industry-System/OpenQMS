import uuid
from datetime import datetime
from pydantic import BaseModel, Field


# DFMEA 专用节点类型（语义标识，字段与现有 Function 节点相同）
# SystemFunction = "SystemFunction"
# SubsystemFunction = "SubsystemFunction"
# ComponentFunction = "ComponentFunction"

class GraphNodeSchema(BaseModel):
    id: str
    type: str
    name: str
    
    # 结构分析层级属性 (Step 2)
    process_number: str | None = None  # 仅用于 ProcessStep 的工序号，如 "OP30"
    classification: str | None = None  # 用于 ProcessWorkElement 的 4M 类型（Man/Machine/Material/Environment）或特性分类 (CC/SC)
    
    # 功能分析与要求属性 (Step 3)
    requirement: str | None = None     # 期望功能描述/技术要求
    specification: str | None = None   # 产品特性参数公差规格
    
    # 风险分析属性 (Step 4 & 5)
    severity: int = Field(default=0, ge=0, le=10)            # 综合严重度 (1-10)
    severity_plant: int | None = Field(default=None, ge=0, le=10)     # 本厂影响严重度 (1-10)
    severity_customer: int | None = Field(default=None, ge=0, le=10)  # 直接客户/下级工厂影响严重度 (1-10)
    severity_user: int | None = Field(default=None, ge=0, le=10)      # 最终用户影响严重度 (1-10)
    
    occurrence: int = Field(default=0, ge=0, le=10)          # 频度 (1-10)
    detection: int = Field(default=0, ge=0, le=10)           # 探测度 (1-10)
    
    # 优化措施跟进属性 (Step 6)
    responsible: str | None = None      # 措施责任人
    due_date: str | None = None         # 计划完成日期
    status: str | None = None           # 措施状态 (如 open / closed / in_progress)
    action_taken: str | None = None     # 实际采取的措施描述
    completion_date: str | None = None  # 实际完成日期
    
    revised_severity: int = Field(default=0, ge=0, le=10)    # 改进后严重度 (1-10)
    revised_occurrence: int = Field(default=0, ge=0, le=10)  # 改进后频度 (1-10)
    revised_detection: int = Field(default=0, ge=0, le=10)   # 改进后探测度 (1-10)
    revised_ap: str | None = None                            # 改进后的措施优先级 (H / M / L)


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
