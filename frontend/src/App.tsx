import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore } from "./store/authStore";
import { usePermission } from "./hooks/usePermission";
import type { ModuleKey } from "./hooks/usePermission";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/login/LoginPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import FMEAListPage from "./pages/planning/fmea/FMEAListPage";
import FMEAEditorPage from "./pages/planning/fmea/FMEAEditorPage";
import CAPAListPage from "./pages/capa/CAPAListPage";
import CAPADetailPage from "./pages/capa/CAPADetailPage";
import ControlPlanListPage from "./pages/planning/control-plan/ControlPlanListPage";
import ControlPlanEditorPage from "./pages/planning/control-plan/ControlPlanEditorPage";
import QualityGoalListPage from "./pages/qualityGoal/QualityGoalListPage";
import InternalAuditListPage from "./pages/internalAudit/InternalAuditListPage";
import InternalAuditDetailPage from "./pages/internalAudit/InternalAuditDetailPage";
import CustomerAuditListPage from "./pages/customerAudit/CustomerAuditListPage";
import CustomerAuditDetailPage from "./pages/customerAudit/CustomerAuditDetailPage";
import SPCListPage from "./pages/spc/SPCListPage";
import SPCDetailPage from "./pages/spc/SPCDetailPage";
import SupplierListPage from "./pages/supplier/SupplierListPage";
import SupplierDetailPage from "./pages/supplier/SupplierDetailPage";
import GaugeListPage from "./pages/msa/GaugeListPage";
import GaugeDetailPage from "./pages/msa/GaugeDetailPage";
import MsaStudyListPage from "./pages/msa/MsaStudyListPage";
import StudyDetailPage from "./pages/msa/StudyDetailPage";
import SCListPage from "./pages/planning/special-characteristic/SCListPage";
import SCMatrixPage from "./pages/planning/special-characteristic/SCMatrixPage";
import SCDetailPage from "./pages/planning/special-characteristic/SCDetailPage";
import TraceabilityPage from "./pages/planning/special-characteristic/TraceabilityPage";
import ManagementReviewListPage from "./pages/managementReview/ManagementReviewListPage";
import ManagementReviewDetailPage from "./pages/managementReview/ManagementReviewDetailPage";
import IqcInspectionListPage from "./pages/iqc/IqcInspectionListPage";
import IqcInspectionDetailPage from "./pages/iqc/IqcInspectionDetailPage";
import IqcMaterialListPage from "./pages/iqc/IqcMaterialListPage";
import AqlOptimizationPage from "./pages/iqc/AqlOptimizationPage";
import AqlProfileListPage from "./pages/iqc/AqlProfileListPage";
import AqlProfileDetailPage from "./pages/iqc/AqlProfileDetailPage";
import AqlConfigPage from "./pages/iqc/AqlConfigPage";
import CustomerQualityPage from "./pages/customerQuality/CustomerQualityPage";
import ComplaintDetailPage from "./pages/customerQuality/ComplaintDetailPage";
import RMADetailPage from "./pages/customerQuality/RMADetailPage";
import SupplierQualityPage from "./pages/supplier/SupplierQualityPage";
import SupplierRiskPage from "./pages/supplierRisk/SupplierRiskPage";
import RiskConfigPage from "./pages/supplierRisk/RiskConfigPage";
import SCARListPage from "./pages/scar/SCARListPage";
import SCARDetailPage from "./pages/scar/SCARDetailPage";
import APQPListPage from "./pages/planning/apqp/APQPListPage";
import APQPDetailPage from "./pages/planning/apqp/APQPDetailPage";
import PPAPListPage from "./pages/planning/ppap/PPAPListPage";
import PPAPDetailPage from "./pages/planning/ppap/PPAPDetailPage";
import KnowledgeGraphPage from "./pages/graph/KnowledgeGraphPage";
import ChangeImpactPage from "./pages/ChangeImpactPage";
import MESConnectionsPage from "./pages/mes/MESConnectionsPage";
import MESDashboardPage from "./pages/mes/MESDashboardPage";
import MESOrdersPage from "./pages/mes/MESOrdersPage";
import MESScrapPage from "./pages/mes/MESScrapPage";
import PLMDashboardPage from "./pages/plm/PLMDashboardPage";
import PLMConnectionsPage from "./pages/plm/PLMConnectionsPage";
import PLMPartsPage from "./pages/plm/PLMPartsPage";
import PLMChangeOrdersPage from "./pages/plm/PLMChangeOrdersPage";
import ERPDashboardPage from "./pages/erp/ERPDashboardPage";
import ERPConnectionsPage from "./pages/erp/ERPConnectionsPage";
import ERPMasterDataPage from "./pages/erp/ERPMasterDataPage";
import ERPSupplyChainPage from "./pages/erp/ERPSupplyChainPage";
import ERPSalesAndCostPage from "./pages/erp/ERPSalesAndCostPage";
import ERPTraceabilityPage from "./pages/erp/ERPTraceabilityPage";

function ProtectedRoute({ children, requiredModule }: { children: React.ReactNode; requiredModule?: ModuleKey }) {
  const token = useAuthStore((s) => s.token);
  const loading = useAuthStore((s) => s.loading);
  const fetchUser = useAuthStore((s) => s.fetchUser);
  const user = useAuthStore((s) => s.user);
  const { canView } = usePermission();

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

  if (!token) return <Navigate to="/login" replace />;

  if (requiredModule && !canView(requiredModule)) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/fmea" element={<ProtectedRoute requiredModule="fmea"><FMEAListPage /></ProtectedRoute>} />
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
        <Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
        <Route path="/change-impact" element={<ChangeImpactPage />} />
        <Route path="/mes/dashboard" element={<ProtectedRoute><MESDashboardPage /></ProtectedRoute>} />
        <Route path="/mes/connections" element={<ProtectedRoute><MESConnectionsPage /></ProtectedRoute>} />
        <Route path="/mes/orders" element={<ProtectedRoute><MESOrdersPage /></ProtectedRoute>} />
        <Route path="/mes/scrap" element={<ProtectedRoute><MESScrapPage /></ProtectedRoute>} />
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
      </Route>
    </Routes>
  );
}
