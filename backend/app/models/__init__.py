from app.database import (
    PlatformBase,  # noqa: F401 — ensures models register with PlatformBase
    TenantBase,  # noqa: F401 — ensures models register with TenantBase
)
from app.models.apqp import APQPProject
from app.models.attribute import AttributeMeasurement, AttributeResult, AttributeStudy
from app.models.audit import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.audit_plan import AuditPlan
from app.models.audit_program import AuditChecklistTemplate, AuditProgram, AuditProgramTargetFactory
from app.models.bias import BiasMeasurement, BiasResult, BiasStudy
from app.models.capa import CAPAEightD
from app.models.change_impact import ChangeImpactAnalysis
from app.models.collaboration_session import CollaborationSession
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.cp_validation import CPValidationFinding, CPValidationOccurrence, CPValidationRun
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
from app.models.document_embedding import DocumentEmbedding, EmbeddingSyncOutbox
from app.models.erp import (
    ERPConnection,
    ERPCostRecord,
    ERPCustomer,
    ERPInventoryBalance,
    ERPLocation,
    ERPMaterial,
    ERPPurchaseOrder,
    ERPPushOutbox,
    ERPSalesOrder,
    ERPShipment,
    ERPSupplier,
    ERPSyncJob,
)
from app.models.factory import Factory, UserFactory
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.gauge import Gauge, GaugeCalibration
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.models.group_kpi_snapshot import GroupKPISnapshot
from app.models.grr import GrrMeasurement, GrrResult, GrrStudy
from app.models.iqc_aql_config import IqcAqlConfig
from app.models.iqc_aql_profile import IqcAqlProfile
from app.models.iqc_aql_quality_snapshot import IqcAqlQualitySnapshot
from app.models.iqc_aql_recommendation import IqcAqlRecommendation
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem
from app.models.iqc_material import IqcMaterial
from app.models.linearity import LinearityMeasurement, LinearityResult, LinearityStudy
from app.models.management_review import ManagementReview, ReviewOutput
from app.models.management_review_report import ReviewReport
from app.models.mes import (
    MESConnection,
    MESEquipmentStatus,
    MESMeasurementIngestion,
    MESProductionOrder,
    MESProductionOrderArchive,
    MESPushOutbox,
    MESScrapMonthlySummary,
    MESScrapRecord,
    MESSyncJob,
)
from app.models.platform_admin import PlatformAdminUser  # noqa: F401
from app.models.product_line import ProductLine
from app.models.quality_goal import QualityGoal
from app.models.recommendation_cache import RecommendationCache
from app.models.reference_template import ReferenceTemplate  # noqa: F401
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.spc import ControlLimitSnapshot, InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm
from app.models.special_characteristic import SpecialCharacteristic
from app.models.stability import StabilityMeasurement, StabilityResult, StabilityStudy
from app.models.system_setting import SystemSetting
from app.models.supplier import (
    Supplier,
    SupplierCertification,
    SupplierEvaluation,
    SupplierPPAPElement,
    SupplierPPAPSubmission,
    SupplierSCAR,
)
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig, SupplierRiskNotificationChannel
from app.models.supplier_shared_profile import SupplierSharedProfile
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot

# Platform-level models (public schema)
from app.models.tenant import Tenant  # noqa: F401
from app.models.tenant_migration import TenantMigration  # noqa: F401
from app.models.user import User
from app.models.user_dashboard_layout import UserDashboardLayout

from .plm import (
    PLMBOM,
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartFMEALink,
    PLMPartSCLink,
    PLMPushOutbox,
    PLMSyncJob,
)

__all__ = [
    "User", "FMEADocument", "CAPAEightD", "AuditLog",
    "ControlPlan", "ControlPlanItem", "QualityGoal",
    "AuditProgram", "AuditPlan", "AuditFinding", "AuditChecklistTemplate", "AuditProgramTargetFactory",
    "InspectionCharacteristic", "SampleBatch", "SampleValue", "SPCAlarm", "ControlLimitSnapshot",
    "Supplier", "SupplierCertification", "SupplierEvaluation",
    "SupplierPPAPSubmission", "SupplierPPAPElement", "SupplierSCAR",
    "Gauge", "GaugeCalibration",
    "GrrStudy", "GrrMeasurement", "GrrResult",
    "BiasStudy", "BiasMeasurement", "BiasResult",
    "LinearityStudy", "LinearityMeasurement", "LinearityResult",
    "StabilityStudy", "StabilityMeasurement", "StabilityResult",
    "AttributeStudy", "AttributeMeasurement", "AttributeResult",
    "SpecialCharacteristic",
    "ProductLine",
    "ManagementReview", "ReviewOutput", "ReviewReport",
    "FMEAVersion", "ControlPlanVersion", "IqcInspection", "IqcMaterial",
    "IqcInspectionTemplate", "IqcTemplateItem", "IqcInspectionItem", "IqcItemMeasurement",
    "Customer", "CustomerComplaint", "RMARecord",
    "APQPProject",
    "GraphSyncOutbox",
    "RoleDefinition", "RolePermission", "UserProductLine",
    "RecommendationCache",
    "DocumentEmbedding",
    "EmbeddingSyncOutbox",
    "ChangeImpactAnalysis",
    "CollaborationSession",
    "UserDashboardLayout",
    "CPValidationRun",
    "CPValidationFinding",
    "CPValidationOccurrence",
    "PLMConnection",
    "PLMPart",
    "PLMBOM",
    "PLMChangeOrder",
    "PLMSyncJob",
    "PLMPushOutbox",
    "PLMChangeImpactTask",
    "PLMPartFMEALink",
    "PLMPartSCLink",
    "MESConnection",
    "MESProductionOrder",
    "MESEquipmentStatus",
    "MESScrapRecord",
    "MESMeasurementIngestion",
    "MESSyncJob",
    "MESPushOutbox",
    "MESScrapMonthlySummary",
    "MESProductionOrderArchive",
    "ERPConnection",
    "ERPSyncJob",
    "ERPPushOutbox",
    "ERPSupplier",
    "ERPCustomer",
    "ERPMaterial",
    "ERPLocation",
    "ERPPurchaseOrder",
    "ERPSalesOrder",
    "ERPInventoryBalance",
    "ERPShipment",
    "ERPCostRecord",
    "IqcAqlProfile",
    "IqcAqlRecommendation",
    "IqcAqlQualitySnapshot",
    "IqcAqlConfig",
    "SupplierRiskAlert",
    "SupplierRiskConfig",
    "SupplierRiskNotificationChannel",
    "SystemSetting",
    "Factory",
    "UserFactory",
    "GroupKPISnapshot",
    "SupplierSharedProfile",
    "SupplyChainRiskSnapshot",
    "Tenant",
    "PlatformAdminUser",
    "ReferenceTemplate",
    "TenantMigration",
]
