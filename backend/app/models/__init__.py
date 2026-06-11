from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.quality_goal import QualityGoal
from app.models.audit_program import AuditProgram, AuditChecklistTemplate
from app.models.audit_plan import AuditPlan
from app.models.audit_finding import AuditFinding
from app.models.spc import InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm, ControlLimitSnapshot
from app.models.supplier import Supplier, SupplierCertification, SupplierEvaluation, SupplierPPAPSubmission, SupplierPPAPElement, SupplierSCAR
from app.models.gauge import Gauge, GaugeCalibration
from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
from app.models.bias import BiasStudy, BiasMeasurement, BiasResult
from app.models.linearity import LinearityStudy, LinearityMeasurement, LinearityResult
from app.models.stability import StabilityStudy, StabilityMeasurement, StabilityResult
from app.models.attribute import AttributeStudy, AttributeMeasurement, AttributeResult
from app.models.special_characteristic import SpecialCharacteristic
from app.models.product_line import ProductLine
from app.models.management_review import ManagementReview, ReviewOutput
from app.models.fmea_version import FMEAVersion
from app.models.control_plan_version import ControlPlanVersion
from app.models.iqc_inspection import IqcInspection
from app.models.iqc_material import IqcMaterial
from app.models.iqc_inspection_template import IqcInspectionTemplate, IqcTemplateItem
from app.models.iqc_inspection_item import IqcInspectionItem, IqcItemMeasurement
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
from app.models.apqp import APQPProject
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.recommendation_cache import RecommendationCache
from app.models.document_embedding import DocumentEmbedding, EmbeddingSyncOutbox
from app.models.change_impact import ChangeImpactAnalysis
from app.models.collaboration_session import CollaborationSession
from app.models.user_dashboard_layout import UserDashboardLayout
from app.models.cp_validation import CPValidationRun, CPValidationFinding, CPValidationOccurrence
from .plm import (
    PLMConnection, PLMPart, PLMBOM, PLMChangeOrder,
    PLMSyncJob, PLMPushOutbox, PLMChangeImpactTask,
    PLMPartFMEALink, PLMPartSCLink,
)
from app.models.mes import (
    MESConnection,
    MESProductionOrder,
    MESEquipmentStatus,
    MESScrapRecord,
    MESMeasurementIngestion,
    MESSyncJob,
    MESPushOutbox,
    MESScrapMonthlySummary,
    MESProductionOrderArchive,
)
from app.models.erp import (
    ERPConnection,
    ERPSyncJob,
    ERPPushOutbox,
    ERPSupplier,
    ERPCustomer,
    ERPMaterial,
    ERPLocation,
    ERPPurchaseOrder,
    ERPSalesOrder,
    ERPInventoryBalance,
    ERPShipment,
    ERPCostRecord,
)
from app.models.iqc_aql_profile import IqcAqlProfile
from app.models.iqc_aql_recommendation import IqcAqlRecommendation
from app.models.iqc_aql_quality_snapshot import IqcAqlQualitySnapshot
from app.models.iqc_aql_config import IqcAqlConfig
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig, SupplierRiskNotificationChannel

__all__ = [
    "User", "FMEADocument", "CAPAEightD", "AuditLog",
    "ControlPlan", "ControlPlanItem", "QualityGoal",
    "AuditProgram", "AuditPlan", "AuditFinding", "AuditChecklistTemplate",
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
    "ManagementReview", "ReviewOutput",
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
]
