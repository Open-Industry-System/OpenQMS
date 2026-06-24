import { lazy, Suspense, useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore } from "./store/authStore";
import { usePermission } from "./hooks/usePermission";
import type { ModuleKey } from "./hooks/usePermission";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/login/LoginPage";

const DashboardPage = lazy(() => import("./pages/dashboard/DashboardPage"));
const FMEAListPage = lazy(() => import("./pages/planning/fmea/FMEAListPage"));
const FMEAEditorPage = lazy(() => import("./pages/planning/fmea/FMEAEditorPage"));
const DFMEAWizardPage = lazy(() => import("./pages/planning/fmea/DFMEAWizardPage"));
const PFMEAWizardPage = lazy(() => import("./pages/planning/fmea/PFMEAWizardPage"));
const CAPAListPage = lazy(() => import("./pages/capa/CAPAListPage"));
const CAPADetailPage = lazy(() => import("./pages/capa/CAPADetailPage"));
const ControlPlanListPage = lazy(() => import("./pages/planning/control-plan/ControlPlanListPage"));
const ControlPlanEditorPage = lazy(() => import("./pages/planning/control-plan/ControlPlanEditorPage"));
const QualityGoalListPage = lazy(() => import("./pages/qualityGoal/QualityGoalListPage"));
const InternalAuditListPage = lazy(() => import("./pages/internalAudit/InternalAuditListPage"));
const InternalAuditDetailPage = lazy(() => import("./pages/internalAudit/InternalAuditDetailPage"));
const CustomerAuditListPage = lazy(() => import("./pages/customerAudit/CustomerAuditListPage"));
const CustomerAuditDetailPage = lazy(() => import("./pages/customerAudit/CustomerAuditDetailPage"));
const SPCListPage = lazy(() => import("./pages/spc/SPCListPage"));
const SPCDetailPage = lazy(() => import("./pages/spc/SPCDetailPage"));
const SupplierListPage = lazy(() => import("./pages/supplier/SupplierListPage"));
const SupplierDetailPage = lazy(() => import("./pages/supplier/SupplierDetailPage"));
const GaugeListPage = lazy(() => import("./pages/msa/GaugeListPage"));
const GaugeDetailPage = lazy(() => import("./pages/msa/GaugeDetailPage"));
const MsaStudyListPage = lazy(() => import("./pages/msa/MsaStudyListPage"));
const StudyDetailPage = lazy(() => import("./pages/msa/StudyDetailPage"));
const SCListPage = lazy(() => import("./pages/planning/special-characteristic/SCListPage"));
const SCMatrixPage = lazy(() => import("./pages/planning/special-characteristic/SCMatrixPage"));
const SCDetailPage = lazy(() => import("./pages/planning/special-characteristic/SCDetailPage"));
const TraceabilityPage = lazy(() => import("./pages/planning/special-characteristic/TraceabilityPage"));
const ManagementReviewListPage = lazy(() => import("./pages/managementReview/ManagementReviewListPage"));
const ManagementReviewDetailPage = lazy(() => import("./pages/managementReview/ManagementReviewDetailPage"));
const IqcInspectionListPage = lazy(() => import("./pages/iqc/IqcInspectionListPage"));
const IqcInspectionDetailPage = lazy(() => import("./pages/iqc/IqcInspectionDetailPage"));
const IqcMaterialListPage = lazy(() => import("./pages/iqc/IqcMaterialListPage"));
const AqlOptimizationPage = lazy(() => import("./pages/iqc/AqlOptimizationPage"));
const AqlProfileListPage = lazy(() => import("./pages/iqc/AqlProfileListPage"));
const AqlProfileDetailPage = lazy(() => import("./pages/iqc/AqlProfileDetailPage"));
const AqlConfigPage = lazy(() => import("./pages/iqc/AqlConfigPage"));
const CustomerQualityPage = lazy(() => import("./pages/customerQuality/CustomerQualityPage"));
const ComplaintDetailPage = lazy(() => import("./pages/customerQuality/ComplaintDetailPage"));
const RMADetailPage = lazy(() => import("./pages/customerQuality/RMADetailPage"));
const SupplierQualityPage = lazy(() => import("./pages/supplier/SupplierQualityPage"));
const SupplierRiskPage = lazy(() => import("./pages/supplierRisk/SupplierRiskPage"));
const RiskConfigPage = lazy(() => import("./pages/supplierRisk/RiskConfigPage"));
const SCARListPage = lazy(() => import("./pages/scar/SCARListPage"));
const SCARDetailPage = lazy(() => import("./pages/scar/SCARDetailPage"));
const APQPListPage = lazy(() => import("./pages/planning/apqp/APQPListPage"));
const APQPDetailPage = lazy(() => import("./pages/planning/apqp/APQPDetailPage"));
const PPAPListPage = lazy(() => import("./pages/planning/ppap/PPAPListPage"));
const PPAPDetailPage = lazy(() => import("./pages/planning/ppap/PPAPDetailPage"));
const KnowledgeGraphPage = lazy(() => import("./pages/graph/KnowledgeGraphPage"));
const ChangeImpactPage = lazy(() => import("./pages/ChangeImpactPage"));
const MESConnectionsPage = lazy(() => import("./pages/mes/MESConnectionsPage"));
const MESDashboardPage = lazy(() => import("./pages/mes/MESDashboardPage"));
const MESOrdersPage = lazy(() => import("./pages/mes/MESOrdersPage"));
const MESScrapPage = lazy(() => import("./pages/mes/MESScrapPage"));
const PLMDashboardPage = lazy(() => import("./pages/plm/PLMDashboardPage"));
const PLMConnectionsPage = lazy(() => import("./pages/plm/PLMConnectionsPage"));
const PLMPartsPage = lazy(() => import("./pages/plm/PLMPartsPage"));
const PLMChangeOrdersPage = lazy(() => import("./pages/plm/PLMChangeOrdersPage"));
const ERPDashboardPage = lazy(() => import("./pages/erp/ERPDashboardPage"));
const ERPConnectionsPage = lazy(() => import("./pages/erp/ERPConnectionsPage"));
const ERPMasterDataPage = lazy(() => import("./pages/erp/ERPMasterDataPage"));
const ERPSupplyChainPage = lazy(() => import("./pages/erp/ERPSupplyChainPage"));
const ERPSalesAndCostPage = lazy(() => import("./pages/erp/ERPSalesAndCostPage"));
const ERPTraceabilityPage = lazy(() => import("./pages/erp/ERPTraceabilityPage"));
const GroupDashboardPage = lazy(() => import("./pages/group/GroupDashboard"));
const FactoryManagementPage = lazy(() => import("./pages/group/FactoryManagement"));
const FactoryComparisonPage = lazy(() => import("./pages/group/FactoryComparison"));
const GroupSuppliersPage = lazy(() => import("./pages/group/GroupSuppliers"));
const GroupAuditsPage = lazy(() => import("./pages/group/GroupAudits"));
const SupplyChainRiskMapPage = lazy(() => import("./pages/supplyChainRiskMap/SupplyChainRiskMapPage"));
const TenantSuspended = lazy(() => import("./pages/TenantSuspended"));
const TenantDeactivated = lazy(() => import("./pages/TenantDeactivated"));
const AIConfigPage = lazy(() => import("./pages/admin/AIConfigPage"));
const ProductTypePage = lazy(() => import("./pages/admin/ProductTypePage"));
const ProductLinePage = lazy(() => import("./pages/admin/ProductLinePage"));

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

function ProtectedRoute({ children, requiredModule, requireAdmin }: { children: React.ReactNode; requiredModule?: ModuleKey; requireAdmin?: boolean }) {
  const token = useAuthStore((s) => s.token);
  const _loading = useAuthStore((s) => s.loading);
  const fetchUser = useAuthStore((s) => s.fetchUser);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { canView, isAdmin } = usePermission();

  useEffect(() => {
    if (token && !user) fetchUser();
  }, [token, user, fetchUser]);

  if (token && !user) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!token || isTokenExpired(token)) {
    if (token && isTokenExpired(token)) logout();
    return <Navigate to="/login" replace />;
  }

  if (requiredModule && !canView(requiredModule)) return <Navigate to="/dashboard" replace />;
  if (requireAdmin && !isAdmin) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}><Spin size="large" /></div>}>
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/tenant-suspended" element={<TenantSuspended />} />
      <Route path="/tenant-deactivated" element={<TenantDeactivated />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<ProtectedRoute requiredModule="dashboard"><DashboardPage /></ProtectedRoute>} />
        <Route path="/fmea" element={<ProtectedRoute requiredModule="fmea"><FMEAListPage /></ProtectedRoute>} />
        <Route path="/fmea/wizard/:id" element={<ProtectedRoute requiredModule="fmea"><DFMEAWizardPage /></ProtectedRoute>} />
        <Route path="/fmea/pfmea-wizard/:id" element={<ProtectedRoute requiredModule="fmea"><PFMEAWizardPage /></ProtectedRoute>} />
        <Route path="/fmea/:id" element={<ProtectedRoute requiredModule="fmea"><FMEAEditorPage /></ProtectedRoute>} />
        <Route path="/capa" element={<ProtectedRoute requiredModule="capa"><CAPAListPage /></ProtectedRoute>} />
        <Route path="/capa/:id" element={<ProtectedRoute requiredModule="capa"><CAPADetailPage /></ProtectedRoute>} />
        <Route path="/control-plans" element={<ProtectedRoute requiredModule="planning"><ControlPlanListPage /></ProtectedRoute>} />
        <Route path="/control-plans/:id" element={<ProtectedRoute requiredModule="planning"><ControlPlanEditorPage /></ProtectedRoute>} />
        <Route path="/quality-goals" element={<ProtectedRoute requiredModule="quality_goal"><QualityGoalListPage /></ProtectedRoute>} />
        <Route path="/internal-audits" element={<ProtectedRoute requiredModule="audit"><InternalAuditListPage /></ProtectedRoute>} />
        <Route path="/internal-audits/:id" element={<ProtectedRoute requiredModule="audit"><InternalAuditDetailPage /></ProtectedRoute>} />
        <Route path="/customer-audits" element={<ProtectedRoute requiredModule="customer_audit"><CustomerAuditListPage /></ProtectedRoute>} />
        <Route path="/customer-audits/:id" element={<ProtectedRoute requiredModule="customer_audit"><CustomerAuditDetailPage /></ProtectedRoute>} />
        <Route path="/spc" element={<ProtectedRoute requiredModule="spc"><SPCListPage /></ProtectedRoute>} />
        <Route path="/spc/:id" element={<ProtectedRoute requiredModule="spc"><SPCDetailPage /></ProtectedRoute>} />
        <Route path="/suppliers" element={<ProtectedRoute requiredModule="supplier"><SupplierListPage /></ProtectedRoute>} />
        <Route path="/suppliers/:id" element={<ProtectedRoute requiredModule="supplier"><SupplierDetailPage /></ProtectedRoute>} />
        <Route path="/suppliers/quality" element={<ProtectedRoute requiredModule="supplier"><SupplierQualityPage /></ProtectedRoute>} />
        <Route path="/suppliers/quality/:supplierId" element={<ProtectedRoute requiredModule="supplier"><SupplierQualityPage /></ProtectedRoute>} />
        <Route
          path="/supplier-risk"
          element={
            <ProtectedRoute requiredModule="supplier_risk">
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<SupplierRiskPage />} />
          <Route path="config" element={<RiskConfigPage />} />
        </Route>
        <Route path="/supply-chain-risk-map" element={<ProtectedRoute requiredModule="supply_chain_risk_map"><SupplyChainRiskMapPage /></ProtectedRoute>} />
        <Route path="/msa" element={<ProtectedRoute requiredModule="msa"><Navigate to="/msa/gauges" replace /></ProtectedRoute>} />
        <Route path="/msa/gauges" element={<ProtectedRoute requiredModule="msa"><GaugeListPage /></ProtectedRoute>} />
        <Route path="/msa/gauges/:id" element={<ProtectedRoute requiredModule="msa"><GaugeDetailPage /></ProtectedRoute>} />
        <Route path="/msa/studies" element={<ProtectedRoute requiredModule="msa"><MsaStudyListPage /></ProtectedRoute>} />
        <Route path="/msa/studies/:type/:id" element={<ProtectedRoute requiredModule="msa"><StudyDetailPage /></ProtectedRoute>} />
        <Route path="/special-characteristics" element={<ProtectedRoute requiredModule="special_characteristic"><SCListPage /></ProtectedRoute>} />
        <Route path="/special-characteristics/matrix" element={<ProtectedRoute requiredModule="special_characteristic"><SCMatrixPage /></ProtectedRoute>} />
        <Route path="/special-characteristics/traceability" element={<ProtectedRoute requiredModule="special_characteristic"><TraceabilityPage /></ProtectedRoute>} />
        <Route path="/special-characteristics/:id" element={<ProtectedRoute requiredModule="special_characteristic"><SCDetailPage /></ProtectedRoute>} />
        <Route path="/management-reviews" element={<ProtectedRoute requiredModule="management_review"><ManagementReviewListPage /></ProtectedRoute>} />
        <Route path="/management-reviews/:id" element={<ProtectedRoute requiredModule="management_review"><ManagementReviewDetailPage /></ProtectedRoute>} />
        <Route path="/iqc" element={<ProtectedRoute requiredModule="iqc"><Navigate to="/iqc/inspections" replace /></ProtectedRoute>} />
        <Route path="/iqc/inspections" element={<ProtectedRoute requiredModule="iqc"><IqcInspectionListPage /></ProtectedRoute>} />
        <Route path="/iqc/inspections/:id" element={<ProtectedRoute requiredModule="iqc"><IqcInspectionDetailPage /></ProtectedRoute>} />
        <Route path="/iqc/materials" element={<ProtectedRoute requiredModule="iqc"><IqcMaterialListPage /></ProtectedRoute>} />
        <Route path="/iqc/aql-optimization" element={<ProtectedRoute requiredModule="iqc"><AqlOptimizationPage /></ProtectedRoute>} />
        <Route path="/iqc/aql-optimization/profiles" element={<ProtectedRoute requiredModule="iqc"><AqlProfileListPage /></ProtectedRoute>} />
        <Route path="/iqc/aql-optimization/profiles/:supplierId/:materialId" element={<ProtectedRoute requiredModule="iqc"><AqlProfileDetailPage /></ProtectedRoute>} />
        <Route path="/iqc/aql-optimization/config" element={<ProtectedRoute requiredModule="iqc"><AqlConfigPage /></ProtectedRoute>} />
        <Route path="/scars" element={<ProtectedRoute requiredModule="scar"><SCARListPage /></ProtectedRoute>} />
        <Route path="/scars/:id" element={<ProtectedRoute requiredModule="scar"><SCARDetailPage /></ProtectedRoute>} />
        <Route path="/apqp" element={<ProtectedRoute requiredModule="planning"><APQPListPage /></ProtectedRoute>} />
        <Route path="/apqp/:id" element={<ProtectedRoute requiredModule="planning"><APQPDetailPage /></ProtectedRoute>} />
        <Route path="/ppap" element={<ProtectedRoute requiredModule="ppap"><PPAPListPage /></ProtectedRoute>} />
        <Route path="/ppap/:id" element={<ProtectedRoute requiredModule="ppap"><PPAPDetailPage /></ProtectedRoute>} />
        <Route path="/customer-quality" element={<ProtectedRoute requiredModule="customer_quality"><CustomerQualityPage /></ProtectedRoute>} />
        <Route path="/customer-quality/complaints/:id" element={<ProtectedRoute requiredModule="customer_quality"><ComplaintDetailPage /></ProtectedRoute>} />
        <Route path="/customer-quality/rma/:id" element={<ProtectedRoute requiredModule="customer_quality"><RMADetailPage /></ProtectedRoute>} />
        <Route path="/knowledge-graph" element={<ProtectedRoute requiredModule="knowledge_graph"><KnowledgeGraphPage /></ProtectedRoute>} />
        <Route path="/change-impact" element={<ProtectedRoute requiredModule="fmea"><ChangeImpactPage /></ProtectedRoute>} />
        <Route path="/mes/dashboard" element={<ProtectedRoute requiredModule="mes"><MESDashboardPage /></ProtectedRoute>} />
        <Route path="/mes/connections" element={<ProtectedRoute requiredModule="mes"><MESConnectionsPage /></ProtectedRoute>} />
        <Route path="/mes/orders" element={<ProtectedRoute requiredModule="mes"><MESOrdersPage /></ProtectedRoute>} />
        <Route path="/mes/scrap" element={<ProtectedRoute requiredModule="mes"><MESScrapPage /></ProtectedRoute>} />
        <Route path="/plm/dashboard" element={<ProtectedRoute requiredModule="plm"><PLMDashboardPage /></ProtectedRoute>} />
        <Route path="/plm/connections" element={<ProtectedRoute requiredModule="plm"><PLMConnectionsPage /></ProtectedRoute>} />
        <Route path="/plm/parts" element={<ProtectedRoute requiredModule="plm"><PLMPartsPage /></ProtectedRoute>} />
        <Route path="/plm/change-orders" element={<ProtectedRoute requiredModule="plm"><PLMChangeOrdersPage /></ProtectedRoute>} />
        <Route path="/erp" element={<ProtectedRoute requiredModule="erp"><ERPDashboardPage /></ProtectedRoute>} />
        <Route path="/erp/connections" element={<ProtectedRoute requiredModule="erp"><ERPConnectionsPage /></ProtectedRoute>} />
        <Route path="/erp/master-data" element={<ProtectedRoute requiredModule="erp"><ERPMasterDataPage /></ProtectedRoute>} />
        <Route path="/erp/supply-chain" element={<ProtectedRoute requiredModule="erp"><ERPSupplyChainPage /></ProtectedRoute>} />
        <Route path="/erp/commercial" element={<ProtectedRoute requiredModule="erp"><ERPSalesAndCostPage /></ProtectedRoute>} />
        <Route path="/erp/traceability" element={<ProtectedRoute requiredModule="erp"><ERPTraceabilityPage /></ProtectedRoute>} />
        {/* Group Management */}
        <Route path="/group/dashboard" element={<ProtectedRoute requiredModule="group"><GroupDashboardPage /></ProtectedRoute>} />
        <Route path="/group/factories" element={<ProtectedRoute requiredModule="group"><FactoryManagementPage /></ProtectedRoute>} />
        <Route path="/group/comparison" element={<ProtectedRoute requiredModule="group"><FactoryComparisonPage /></ProtectedRoute>} />
        <Route path="/group/suppliers" element={<ProtectedRoute requiredModule="group"><GroupSuppliersPage /></ProtectedRoute>} />
        <Route path="/group/audits" element={<ProtectedRoute requiredModule="group"><GroupAuditsPage /></ProtectedRoute>} />
        {/* Admin */}
        <Route path="/admin/ai-config" element={<ProtectedRoute requireAdmin><AIConfigPage /></ProtectedRoute>} />
        <Route path="/admin/product-types" element={<ProtectedRoute requireAdmin><ProductTypePage /></ProtectedRoute>} />
        <Route path="/admin/product-lines" element={<ProtectedRoute requireAdmin><ProductLinePage /></ProtectedRoute>} />
      </Route>
      </Routes>
    </Suspense>
  );
}
