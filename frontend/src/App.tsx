import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Spin } from "antd";
import { useAuthStore } from "./store/authStore";
import AppLayout from "./components/layout/AppLayout";
import LoginPage from "./pages/login/LoginPage";
import DashboardPage from "./pages/dashboard/DashboardPage";
import FMEAListPage from "./pages/fmea/FMEAListPage";
import FMEAEditorPage from "./pages/fmea/FMEAEditorPage";
import CAPAListPage from "./pages/capa/CAPAListPage";
import CAPADetailPage from "./pages/capa/CAPADetailPage";
import ControlPlanListPage from "./pages/control-plan/ControlPlanListPage";
import ControlPlanEditorPage from "./pages/control-plan/ControlPlanEditorPage";
import QualityGoalListPage from "./pages/qualityGoal/QualityGoalListPage";
import InternalAuditListPage from "./pages/internalAudit/InternalAuditListPage";
import InternalAuditDetailPage from "./pages/internalAudit/InternalAuditDetailPage";
import SPCListPage from "./pages/spc/SPCListPage";
import SPCDetailPage from "./pages/spc/SPCDetailPage";
import SupplierListPage from "./pages/supplier/SupplierListPage";
import SupplierDetailPage from "./pages/supplier/SupplierDetailPage";
import GaugeListPage from "./pages/msa/GaugeListPage";
import GaugeDetailPage from "./pages/msa/GaugeDetailPage";
import MsaStudyListPage from "./pages/msa/MsaStudyListPage";
import StudyDetailPage from "./pages/msa/StudyDetailPage";
import SCListPage from "./pages/special-characteristic/SCListPage";
import SCMatrixPage from "./pages/special-characteristic/SCMatrixPage";
import SCDetailPage from "./pages/special-characteristic/SCDetailPage";
import TraceabilityPage from "./pages/special-characteristic/TraceabilityPage";
import ManagementReviewListPage from "./pages/managementReview/ManagementReviewListPage";
import ManagementReviewDetailPage from "./pages/managementReview/ManagementReviewDetailPage";
import IqcInspectionListPage from "./pages/iqc/IqcInspectionListPage";
import IqcInspectionDetailPage from "./pages/iqc/IqcInspectionDetailPage";
import IqcMaterialListPage from "./pages/iqc/IqcMaterialListPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const loading = useAuthStore((s) => s.loading);
  const fetchUser = useAuthStore((s) => s.fetchUser);
  const user = useAuthStore((s) => s.user);

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
        <Route path="/fmea" element={<FMEAListPage />} />
        <Route path="/fmea/:id" element={<FMEAEditorPage />} />
        <Route path="/capa" element={<CAPAListPage />} />
        <Route path="/capa/:id" element={<CAPADetailPage />} />
        <Route path="/control-plans" element={<ControlPlanListPage />} />
        <Route path="/control-plans/:id" element={<ControlPlanEditorPage />} />
        <Route path="/quality-goals" element={<QualityGoalListPage />} />
        <Route path="/internal-audits" element={<InternalAuditListPage />} />
        <Route path="/internal-audits/:id" element={<InternalAuditDetailPage />} />
        <Route path="/spc" element={<SPCListPage />} />
        <Route path="/spc/:id" element={<SPCDetailPage />} />
        <Route path="/suppliers" element={<SupplierListPage />} />
        <Route path="/suppliers/:id" element={<SupplierDetailPage />} />
        <Route path="/msa" element={<Navigate to="/msa/gauges" replace />} />
        <Route path="/msa/gauges" element={<GaugeListPage />} />
        <Route path="/msa/gauges/:id" element={<GaugeDetailPage />} />
        <Route path="/msa/studies" element={<MsaStudyListPage />} />
        <Route path="/msa/studies/:type/:id" element={<StudyDetailPage />} />
        <Route path="/special-characteristics" element={<SCListPage />} />
        <Route path="/special-characteristics/matrix" element={<SCMatrixPage />} />
        <Route path="/special-characteristics/traceability" element={<TraceabilityPage />} />
        <Route path="/special-characteristics/:id" element={<SCDetailPage />} />
        <Route path="/management-reviews" element={<ManagementReviewListPage />} />
        <Route path="/management-reviews/:id" element={<ManagementReviewDetailPage />} />
        <Route path="/iqc" element={<Navigate to="/iqc/inspections" replace />} />
        <Route path="/iqc/inspections" element={<IqcInspectionListPage />} />
        <Route path="/iqc/inspections/:id" element={<IqcInspectionDetailPage />} />
        <Route path="/iqc/materials" element={<IqcMaterialListPage />} />
      </Route>
    </Routes>
  );
}
