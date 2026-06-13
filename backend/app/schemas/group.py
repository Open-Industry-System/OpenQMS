"""Group API schemas."""
import uuid
from datetime import date

from pydantic import BaseModel, Field


class FactoryKPI(BaseModel):
    """KPI data for a single factory."""
    factory_id: uuid.UUID
    factory_code: str
    factory_name: str
    open_fmea_count: int = 0
    open_capa_count: int = 0
    overdue_capa_count: int = 0
    active_spc_alarms: int = 0
    pending_iqc_inspections: int = 0
    open_scars: int = 0
    open_supplier_risk_alerts: int = 0
    recent_audit_findings: int = 0


class GroupDashboardResponse(BaseModel):
    """Group dashboard aggregated data."""
    factories: list[FactoryKPI]
    totals: FactoryKPI  # Aggregated totals across all factories
    snapshot_date: date | None = None


class FactoryComparisonItem(BaseModel):
    """Comparison data for a single factory."""
    factory_id: uuid.UUID
    factory_code: str
    factory_name: str
    metrics: dict  # Flexible metric key-value pairs


class FactoryComparisonResponse(BaseModel):
    """Factory comparison data."""
    factories: list[FactoryComparisonItem]
    metric_names: list[str]


class SharedSupplierResponse(BaseModel):
    """Shared supplier across factories."""
    shared_profile_id: uuid.UUID | None
    unified_credit_code: str | None
    name: str
    short_name: str | None
    industry: str | None
    factory_evaluations: list[dict]  # [{"factory_id": ..., "factory_code": ..., "grade": ..., "total_score": ...}]


class CrossFactoryAuditResponse(BaseModel):
    """Cross-factory audit program."""
    program_id: uuid.UUID
    program_no: str
    audit_type: str
    status: str
    target_factory_ids: list[uuid.UUID]
    target_factory_codes: list[str] = Field(default_factory=list)
    finding_count: int = 0


class SupplierMergeRequest(BaseModel):
    """Merge two+ supplier records from different factories into a shared profile."""
    supplier_ids: list[uuid.UUID]  # 2+ supplier IDs to merge
    shared_profile_id: uuid.UUID | None = None  # optional, create if None


class MergedSupplierResponse(BaseModel):
    """Result of a supplier merge."""
    shared_profile_id: uuid.UUID
    unified_credit_code: str | None
    name: str
    short_name: str | None
    industry: str | None
    supplier_ids: list[uuid.UUID]
    factory_ids: list[uuid.UUID]


class AuditFactoryAssignment(BaseModel):
    """Assign a factory to an audit program."""
    factory_id: uuid.UUID


class AuditProgramFactoriesResponse(BaseModel):
    """Target factories for an audit program."""
    program_id: uuid.UUID
    factory_ids: list[uuid.UUID]
    factory_codes: list[str] = Field(default_factory=list)