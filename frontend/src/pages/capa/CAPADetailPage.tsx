import { useEffect, useState, useRef, useMemo } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import {
  Button, Space, Tag, Typography, Steps, Form, Input,
  Select, App, Spin, Empty, Row, Col, Table, Divider, Modal, DatePicker,
} from "antd";
import { ArrowLeftOutlined, ArrowRightOutlined, LinkOutlined, PlusOutlined, DeleteOutlined, UndoOutlined, CheckOutlined, FilePptOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { formatDateTime } from "../../utils/dateTime";
import { getCAPA, updateCAPA, advanceCAPA, linkFMEA, generatePpt, getPptExportReviewReport, triggerScar, confirmRepeat, listCapaSupplierOptions } from "../../api/capa";
import { getAIDraftCapabilities } from "../../api/capaDraft";
import { listFMEAs } from "../../api/fmea";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import D4RecPanel from "../../components/capa/D4RecPanel";
import D4VerificationCard from "../../components/capa/D4VerificationCard";
import D5RecPanel from "../../components/capa/D5RecPanel";
import D7RecPanel, { type D7UnconfirmedItem } from "../../components/capa/D7RecPanel";
import D3ContainmentPanel from "../../components/capa/D3ContainmentPanel";
import DocGatePanel from "../../components/capa/DocGatePanel";
import SupplierRiskInputCard from "../../components/capa/SupplierRiskInputCard";
import AIDraftButton from "../../components/capa/AIDraftButton";
import AIDraftPreview from "../../components/capa/AIDraftPreview";
import { useAIDraft } from "../../components/capa/useAIDraft";
import type { CAPAReport, FMEADocument, DraftFormat, LessonsLearnedResponse } from "../../types";
import LessonsLearnedModal from "../../components/lessons/LessonsLearnedModal";
import { getCAPALessons } from "../../api/lessonsLearned";
import axios from "axios";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { PageShell, StatusBadge, DataCard } from "../../components/design";

const { Title, Text } = Typography;
const { TextArea } = Input;

const stepIndex: Record<string, number> = {
  D1_TEAM: 0, D2_DESCRIPTION: 1, D3_INTERIM: 2, D4_ROOT_CAUSE: 3,
  D5_CORRECTION: 4, D6_VERIFICATION: 5,
  D7_PREVENTION: 6, D7_COMPLETED: 6,        // 折叠到 D7 主步骤
  D8_GATE_PENDING: 7, D8_APPROVAL_PENDING: 7, D8_CLOSURE: 7, ARCHIVED: 7,  // 折叠到 D8 主步骤
};

// 子状态标记：status → i18n key（在 useMemo 内用 t() 解析，确保 en-US 正确翻译，不硬编码中文）
const stepSubLabelKey: Record<string, string> = {
  D7_COMPLETED: "status.D7_COMPLETED",
  D8_GATE_PENDING: "status.D8_GATE_PENDING",
  D8_APPROVAL_PENDING: "status.D8_APPROVAL_PENDING",
  ARCHIVED: "status.ARCHIVED",
};

const severityMap: Record<string, string> = {
  致命: "fatal",
  严重: "error",
  一般: "warning",
  轻微: "info",
};

export default function CAPADetailPage() {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [capa, setCapa] = useState<CAPAReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [_saving, setSaving] = useState(false);
  const [fmeas, setFmeas] = useState<FMEADocument[]>([]);
  const [linkModal, setLinkModal] = useState(false);
  const [scarModalOpen, setScarModalOpen] = useState(false);
  const [scarSubmitting, setScarSubmitting] = useState(false);
  const [suppliers, setSuppliers] = useState<Array<{ supplier_id: string; supplier_no: string; name: string }>>([]);
  const supplierSearchSeq = useRef(0);
  const [supplierLocked, setSupplierLocked] = useState(false);
  const [scarForm] = Form.useForm();

  const _user = useAuthStore((s) => s.user);
  const { canEdit, canApprove, canCreate } = usePermission();

  const [localData, setLocalData] = useState<Record<string, any>>({});
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("quality_engineer");

  const location = useLocation();
  const [lessonsModalOpen, setLessonsModalOpen] = useState(false);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonsData, setLessonsData] = useState<LessonsLearnedResponse | null>(null);
  const lessonsShownRef = useRef(false);

  const [pptLoading, setPptLoading] = useState(false);
  const [reviewReport, setReviewReport] = useState<any>(null);

  const stepItems = useMemo(() => {
    const subLabelKey = capa?.status ? stepSubLabelKey[capa.status] : undefined;
    const subLabel = subLabelKey ? t(subLabelKey) : undefined;
    return [
      { title: t("steps.d1", "D1 团队组建") },
      { title: t("steps.d2", "D2 问题描述") },
      { title: t("steps.d3", "D3 临时措施") },
      { title: t("steps.d4", "D4 根因分析") },
      { title: t("steps.d5", "D5 永久措施") },
      { title: t("steps.d6", "D6 实施验证") },
      {
        title: t("steps.d7", "D7 预防复发"),
        // D7 主步骤副标：仅 D7_COMPLETED 时显示
        description: capa?.status === "D7_COMPLETED" ? subLabel : undefined,
      },
      {
        title: t("steps.d8", "D8 关闭"),
        // D8 主步骤副标：D8_GATE_PENDING/D8_APPROVAL_PENDING/ARCHIVED 时显示
        description: ["D8_GATE_PENDING", "D8_APPROVAL_PENDING", "ARCHIVED"].includes(capa?.status ?? "")
          ? subLabel : undefined,
        // ARCHIVED 时整步标 finish（已完成）
        status: capa?.status === "ARCHIVED" ? "finish" as const : undefined,
      },
    ];
  }, [t, capa?.status]);

  const roleOptions = [
    { value: "quality_engineer", label: t("team.roles.quality_engineer", "质量工程师") },
    { value: "process_engineer", label: t("team.roles.process_engineer", "工艺工程师") },
    { value: "rd_engineer", label: t("team.roles.rd_engineer", "研发工程师") },
    { value: "project_manager", label: t("team.roles.project_manager", "项目经理") },
    { value: "production_supervisor", label: t("team.roles.production_supervisor", "生产主管") },
  ];

  useEffect(() => {
    if (location.state?.showLessonsLearned && !lessonsShownRef.current) {
      lessonsShownRef.current = true;
      setLessonsModalOpen(true);
      setLessonsLoading(true);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => {
        controller.abort();
        setLessonsLoading(false);
        setLessonsModalOpen(false);
        message.warning(t("messages.searchTimeout", "检索超时，请稍后在编辑过程中使用推荐功能"));
      }, 10000);

      const problemDescription = location.state?.problemDescription;
      getCAPALessons(
        id!,
        problemDescription ? { problem_description: problemDescription } : undefined,
        { signal: controller.signal }
      )
        .then((res) => {
          clearTimeout(timeoutId);
          setLessonsData(res);
          setLessonsLoading(false);
        })
        .catch((err) => {
          clearTimeout(timeoutId);
          if (!axios.isCancel(err)) {
            message.error(t("messages.searchFailed", "检索经验教训失败"));
          }
          setLessonsLoading(false);
        });

      return () => {
        clearTimeout(timeoutId);
        controller.abort();
      };
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, id]);

  const [allD7Confirmed, setAllD7Confirmed] = useState(true);
  const [d7UnconfirmedItems, setD7UnconfirmedItems] = useState<D7UnconfirmedItem[]>([]);
  const [d7SkipDialogOpen, setD7SkipDialogOpen] = useState(false);
  const [d7SkipReasons, setD7SkipReasons] = useState<Record<string, string>>({});

  const [rejectDialogOpen, setRejectDialogOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const [aiDraftEnabled, setAiDraftEnabled] = useState(false);

  const {
    loading: draftLoading,
    draft,
    error: draftError,
    errorLevel,
    tempUnavailable,
    generate,
    clear,
    undo,
    saveUndo,
    canUndo,
  } = useAIDraft();
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    if (draft && !draftLoading) {
      setPreviewOpen(true);
    }
  }, [draft, draftLoading]);

  useEffect(() => {
    if (!draftError || draftLoading) return;
    if (errorLevel === "error") {
      message.error(draftError);
    } else {
      message.warning(draftError);
    }
  }, [draftError, errorLevel, draftLoading, message]);

  useEffect(() => {
    if (!id) return;
    getCAPA(id).then(setCapa).finally(() => setLoading(false));
    listFMEAs({ page_size: 100 }).then((res) => setFmeas(res.items));
    getAIDraftCapabilities()
      .then((caps) => setAiDraftEnabled(caps.ai_draft_enabled))
      .catch(() => setAiDraftEnabled(false));
    // Prefetch supplier options so readonly labels can resolve names
    listCapaSupplierOptions({ page_size: 50 })
      .then((res) => setSuppliers(res.items))
      .catch(() => { /* leave empty; fall back to UUID */ });
  }, [id]);

  useEffect(() => {
    if (capa) {
      setLocalData({
        d1_team: capa.d1_team || [],
        d2_description: capa.d2_description || "",
        d3_interim: capa.d3_interim || "",
        d4_root_cause: capa.d4_root_cause || "",
        d5_correction: capa.d5_correction || "",
        d6_verification: capa.d6_verification || "",
        d7_prevention: capa.d7_prevention || "",
        d8_closure: capa.d8_closure || "",
      });
    }
  }, [capa]);

  const currentStep = capa ? (stepIndex[capa.status] ?? 0) : 0;

  const handleUpdate = async (field: string, value: unknown, throwOnError = false) => {
    if (!id || !canEdit('capa')) return;
    if (capa && JSON.stringify(capa[field as keyof CAPAReport]) === JSON.stringify(value)) {
      return;
    }
    setSaving(true);
    try {
      const updated = await updateCAPA(id, { [field]: value });
      setCapa(updated);
    } catch (e) {
      message.error(tc("messages.saveFailed", "保存失败"));
      if (throwOnError) throw e;
    } finally {
      setSaving(false);
    }
  };

  const refreshCapa = async () => {
    const updated = await getCAPA(id!);
    setCapa(updated);
    // 不在此处用闭包 localData 覆盖 d4/d5——交给下方 useEffect([capa]) 统一同步全部 localData，
    // 避免闭包陈旧 localData 覆盖刚同步的其它字段（如 d6/d7/d8）造成闪回
  };

  const stepToField: Record<string, string> = {
    d2: "d2_description", d3: "d3_interim", d4: "d4_root_cause",
    d5: "d5_correction", d6: "d6_verification", d7: "d7_prevention", d8: "d8_closure",
  };

  const handleGenerate = (step: string, format: DraftFormat) => {
    if (!id) return;
    clear();
    generate(id, step, format);
  };

  const handleReplace = async () => {
    if (!draft) return;
    const field = stepToField[draft.step];
    if (!field) return;
    const originalValue = localData[field] || "";
    saveUndo(field, originalValue);
    setLocalData((p) => ({ ...p, [field]: draft.content }));
    try {
      await handleUpdate(field, draft.content, true);
    } catch {
      setLocalData((p) => ({ ...p, [field]: originalValue }));
      return;
    }
    setPreviewOpen(false);
    clear();
  };

  const handleAppend = async () => {
    if (!draft) return;
    const field = stepToField[draft.step];
    if (!field) return;
    const originalValue = localData[field] || "";
    const appended = originalValue ? `${originalValue}\n\n${draft.content}` : draft.content;
    saveUndo(field, originalValue);
    setLocalData((p) => ({ ...p, [field]: appended }));
    try {
      await handleUpdate(field, appended, true);
    } catch {
      setLocalData((p) => ({ ...p, [field]: originalValue }));
      return;
    }
    setPreviewOpen(false);
    clear();
  };

  const handleUndo = (field: string) => {
    const prev = undo(field);
    if (prev !== undefined) {
      setLocalData((p) => ({ ...p, [field]: prev }));
      handleUpdate(field, prev);
      message.success(t("messages.undoSuccess", "已撤销 AI 修改"));
    }
  };

  const renderLabelWithDraft = (step: string, label: string) => {
    const field = stepToField[step];
    const hasHistory = canUndo(field);
    const showAIButton = aiDraftEnabled && canEdit('capa');
    return (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ color: "var(--qf-text-secondary)", fontWeight: 500 }}>{label}</span>
        <Space size="small">
          {hasHistory && (
            <Button
              size="small"
              type="link"
              icon={<UndoOutlined />}
              onClick={() => handleUndo(field)}
            >
              {t("actions.undoChange", "撤销修改")}
            </Button>
          )}
          {showAIButton && (
            <span data-e2e="capa-ai-draft">
              <AIDraftButton
                loading={draftLoading}
                tempUnavailable={tempUnavailable}
                error={errorLevel === "error" ? draftError : null}
                onGenerate={(format) => handleGenerate(step, format)}
              />
            </span>
          )}
        </Space>
      </div>
    );
  };

  const handleAdvance = async () => {
    if (!id) return;
    // D7_PREVENTION 未全确认 → skip 对话框
    if (capa?.status === "D7_PREVENTION" && !allD7Confirmed) {
      setD7SkipDialogOpen(true);
      return;
    }
    // 分支态显式 target_state；线性态（D1-D6、D8_CLOSURE→ARCHIVED 已单独处理）传空对象（无 target_state）
    const branchTarget: Record<string, string> = {
      D7_PREVENTION: "D7_COMPLETED",
      D7_COMPLETED: "D8_GATE_PENDING",
      D8_GATE_PENDING: "D8_APPROVAL_PENDING",
    };
    const target = branchTarget[capa?.status || ""];
    try {
      const updated = await advanceCAPA(id, target ? { target_state: target } : {});
      setCapa(updated);
      message.success(t("messages.advanceSuccess", "已推进到下一步"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed", "推进失败"));
    }
  };

  const handleD7SkipConfirm = async () => {
    if (!id) return;
    setD7SkipDialogOpen(false);

    const globalReason = (d7SkipReasons["__global__"] || "").trim();
    const skipReasonsList = d7UnconfirmedItems.map((item) => ({
      fmea_id: item.fmea_id,
      node_id: item.failure_mode_node_id,
      reason: globalReason || t("d7.skipReasonEmpty", "未填写理由"),
    }));

    try {
      const updated = await advanceCAPA(id, {
        target_state: "D7_COMPLETED",
        d7_skip_reasons: skipReasonsList.length > 0 ? skipReasonsList : undefined,
      });
      setCapa(updated);
      message.success(t("messages.advanceSuccess", "已推进到下一步"));
      setD7SkipReasons({});
      setD7UnconfirmedItems([]);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed", "推进失败"));
    }
  };

  const handleApprove = async () => {
    if (!id) return;
    try {
      const updated = await advanceCAPA(id, { target_state: "D8_CLOSURE" });
      setCapa(updated);
      message.success(t("messages.approveSuccess", "已审批关闭"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed", "推进失败"));
    }
  };

  const handleArchive = async () => {
    if (!id) return;
    try {
      const updated = await advanceCAPA(id, {});  // target_state 缺省 → ARCHIVED（线性）
      setCapa(updated);
      message.success(t("messages.archiveSuccess", "已归档"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed", "推进失败"));
    }
  };

  const handleRejectSubmit = async () => {
    if (!id || !rejectReason.trim()) return;
    try {
      const updated = await advanceCAPA(id, { target_state: "D7_PREVENTION", reject_reason: rejectReason.trim() });
      setCapa(updated);
      setRejectDialogOpen(false);
      setRejectReason("");
      message.success(t("messages.rejectSuccess", "已驳回"));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err?.response?.data?.detail || t("messages.advanceFailed", "推进失败"));
    }
  };

  const handleGeneratePpt = async () => {
    if (!capa) return;
    setPptLoading(true);
    try {
      const { reviewStatus, reviewRounds, exportId } = await generatePpt(capa.report_id);
      if (reviewStatus === "skipped") {
        message.warning(t("capa:ppt.llmNotConfigured"));
      } else if (reviewStatus === "needs_review") {
        // rounds=0 = 内置规则校验未通过（数据/结构缺口）；>0 = LLM 审查 3 轮仍不合格
        message.warning(reviewRounds > 0
          ? t("capa:ppt.needsReview", { rounds: reviewRounds })
          : t("capa:ppt.needsReviewRuleIssues"));
        if (exportId) {
          const { reviewReport: rr } = await getPptExportReviewReport(capa.report_id, exportId);
          setReviewReport(rr);
        }
      } else {
        message.success(t("capa:ppt.generated", { rounds: reviewRounds }));
      }
    } catch {
      message.error(t("capa:ppt.generateFailed"));
    } finally {
      setPptLoading(false);
    }
  };

  const handleLinkFMEA = async (fmeaId: string) => {
    if (!id) return;
    try {
      const updated = await linkFMEA(id, fmeaId);
      setCapa(updated);
      setLinkModal(false);
      message.success(t("messages.linkFMEASuccess", "已关联 FMEA"));
    } catch { message.error(t("messages.linkFMEAFailed", "关联失败")); }
  };

  const buildScarDescriptionPrefill = (report: CAPAReport) => {
    // Narrative only — lots live in affected_batches so [] = clear is honored server-side
    const parts = [`${report.document_no} ${report.title}`.trim()];
    if (report.d2_description) parts.push(`[问题描述] ${report.d2_description}`);
    if (report.d4_root_cause) parts.push(`[根因] ${report.d4_root_cause}`);
    return parts.join("\n");
  };

  const openScarModal = async () => {
    if (!capa) return;
    scarForm.setFieldsValue({
      supplier_id: capa.supplier_id || undefined,
      description: buildScarDescriptionPrefill(capa),
      requested_action: undefined,
      due_date: undefined,
      affected_batches: capa.d3_affected_lots || [],
    });
    setScarModalOpen(true);
    try {
      const res = await listCapaSupplierOptions({ page_size: 50 });
      setSuppliers(res.items);
    } catch {
      // keep empty list; user can still search
    }
  };

  const supplierEditable =
    canEdit("capa") &&
    !["D7_COMPLETED", "D8_GATE_PENDING", "D8_APPROVAL_PENDING", "D8_CLOSURE", "ARCHIVED"].includes(
      capa?.status ?? "",
    ) &&
    !supplierLocked &&
    !capa?.supplier_risk_input;

  const handleSupplierChange = async (supplierId: string | null) => {
    if (!id) return;
    try {
      const updated = await updateCAPA(id, { supplier_id: supplierId });
      setCapa(updated);
      // If backend froze (input already exists), reflect lock for subsequent edits
      if (updated.supplier_risk_input) setSupplierLocked(true);
      message.success(t("messages.supplierSaved", "供应商已保存"));
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (typeof detail === "string" && detail.includes("供应商风险输入")) {
        setSupplierLocked(true);
      }
      message.error(detail || t("messages.supplierSaveFailed", "供应商保存失败"));
    }
  };

  const handleTriggerScar = async () => {
    if (!id) return;
    try {
      const values = await scarForm.validateFields();
      setScarSubmitting(true);
      await triggerScar(id, {
        supplier_id: values.supplier_id,
        description: values.description || undefined,
        requested_action: values.requested_action || undefined,
        due_date: values.due_date
          ? (values.due_date as { format: (f: string) => string }).format("YYYY-MM-DD")
          : undefined,
        affected_batches: values.affected_batches || [],
      });
      const updated = await getCAPA(id);
      setCapa(updated);
      setScarModalOpen(false);
      scarForm.resetFields();
      message.success(t("messages.triggerScarSuccess", "SCAR 发起成功"));
    } catch (err: any) {
      if (err?.errorFields) return; // form validation
      message.error(t("messages.triggerScarFailed", "SCAR 发起失败"));
    } finally {
      setScarSubmitting(false);
    }
  };

  if (loading) return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;
  if (!capa) return <Empty description={t("messages.capaNotFound", "8D 报告未找到")} />;

  const actions = (
    <Space>
      {capa.fmea_ref_id && (
        <Tag style={{ background: "var(--qf-green-dim)", color: "var(--qf-green)", borderColor: "var(--qf-green)" }} icon={<LinkOutlined />}>
          {t("fmea.linked", "已关联 FMEA")}
        </Tag>
      )}
      <RelatedFMEALink fmeaRefId={capa.fmea_ref_id ?? null} fmeaNodeId={capa.fmea_node_id ?? null} />
      {canEdit('capa') && (
        <Button icon={<LinkOutlined />} onClick={() => setLinkModal(true)}>
          {capa.fmea_ref_id ? t("fmea.changeFMEA", "更换FMEA关联") : t("fmea.linkFMEA", "关联FMEA")}
        </Button>
      )}
      {capa.status !== "ARCHIVED" && canEdit('capa') && (
        <>
          {capa.status === "D8_APPROVAL_PENDING" && canApprove('capa') && (
            <>
              <Button type="primary" icon={<CheckOutlined />} onClick={handleApprove} data-e2e="capa-approve">
                {t("reject.approve", "审批关闭")}
              </Button>
              <Button danger icon={<UndoOutlined />} onClick={() => setRejectDialogOpen(true)} data-e2e="capa-reject">
                {t("reject.confirm", "驳回")}
              </Button>
            </>
          )}
          {capa.status === "D8_CLOSURE" && canApprove('capa') && (
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleArchive} data-e2e="capa-archive">
              {t("reject.archive", "归档")}
            </Button>
          )}
          {!["D8_GATE_PENDING", "D8_APPROVAL_PENDING", "D8_CLOSURE"].includes(capa.status) && (
            <Button type="primary" icon={<ArrowRightOutlined />} onClick={handleAdvance} data-e2e="capa-advance">
              {t("actions.advance", "推进下一步")}
            </Button>
          )}
        </>
      )}
      {canCreate("capa") && (capa.status === "D8_CLOSURE" || capa.status === "ARCHIVED") && (
        <Button icon={<FilePptOutlined />} loading={pptLoading} onClick={handleGeneratePpt} data-e2e="capa-ppt">
          {t("capa:ppt.generate")}
        </Button>
      )}
    </Space>
  );

  const subtitle = (
    <Space size="middle">
      <span style={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-text-secondary)" }}>{capa.document_no}</span>
      <StatusBadge status={severityMap[capa.severity] || "warning"}>{capa.severity}</StatusBadge>
    </Space>
  );

  return (
    <PageShell
      title={<Space><Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/capa")}>{tc("actions.back", "返回")}</Button><Title level={4} style={{ margin: 0, color: "var(--qf-text-primary)" }}>{capa.title}</Title></Space>}
      subtitle={subtitle}
      actions={actions}
    >
      <Steps current={currentStep} items={stepItems} style={{ marginBottom: 24 }} />

      <Row gutter={16}>
        <Col span={16}>
          <DataCard title={t("detail.currentStepDetails", "当前步骤详情")}>
            {capa.status === "D1_TEAM" && (
              <div>
                <Table
                  className="qf-table"
                  dataSource={localData.d1_team || []}
                  rowKey="name"
                  size="small"
                  pagination={false}
                  columns={[
                    { title: t("team.name", "成员姓名"), dataIndex: "name", key: "name" },
                    { title: t("team.role", "项目职责"), dataIndex: "role", key: "role" },
                    {
                      title: tc("table.operations", "操作"),
                      key: "action",
                      width: 80,
                      render: (_, record: any) => (
                        <Button
                          type="text"
                          danger
                          disabled={!canEdit('capa')}
                          icon={<DeleteOutlined />}
                          onClick={() => {
                            const filtered = (localData.d1_team || []).filter(
                              (m: any) => m.name !== record.name
                            );
                            handleUpdate("d1_team", filtered);
                          }}
                        />
                      ),
                    },
                  ]}
                />
                {canEdit('capa') && (
                  <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
                    <Input
                      placeholder={t("team.namePlaceholder", "成员姓名")}
                      value={newMemberName}
                      onChange={(e) => setNewMemberName(e.target.value)}
                      style={{ width: 150 }}
                    />
                    <Select
                      value={newMemberRole}
                      onChange={(val) => setNewMemberRole(val)}
                      style={{ width: 150 }}
                      options={roleOptions}
                    />
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        if (!newMemberName.trim()) {
                          message.warning(t("messages.enterName", "请输入姓名"));
                          return;
                        }
                        const exists = (localData.d1_team || []).some(
                          (m: any) => m.name === newMemberName.trim()
                        );
                        if (exists) {
                          message.warning(t("messages.memberExists", "成员已存在"));
                          return;
                        }
                        const newTeam = [
                          ...(localData.d1_team || []),
                          { name: newMemberName.trim(), role: newMemberRole },
                        ];
                        handleUpdate("d1_team", newTeam);
                        setNewMemberName("");
                      }}
                    >
                      {t("actions.addMember", "添加成员")}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {capa.status === "D2_DESCRIPTION" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d2", t("fields.d2Label", "5W2H 问题描述"))}>
                  <TextArea
                    rows={6}
                    disabled={!canEdit('capa')}
                    value={localData.d2_description || ""}
                    onChange={(e) => setLocalData({ ...localData, d2_description: e.target.value })}
                    onBlur={() => handleUpdate("d2_description", localData.d2_description)}
                    placeholder="What / Who / When / Where / Why / How / How much"
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "D3_INTERIM" && (
              <>
                <D3ContainmentPanel capa={capa} canEdit={canEdit('capa')} />
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d3", t("fields.d3Label", "临时遏制措施"))}>
                    <TextArea
                      rows={4}
                      disabled={!canEdit('capa')}
                      value={localData.d3_interim || ""}
                      onChange={(e) => setLocalData({ ...localData, d3_interim: e.target.value })}
                      onBlur={() => handleUpdate("d3_interim", localData.d3_interim)}
                    />
                  </Form.Item>
                </Form>
              </>
            )}

            {capa.status === "D4_ROOT_CAUSE" && (
              <>
                <D4RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  beforeAdopt={async () => {
                    await handleUpdate("d4_root_cause", localData.d4_root_cause, true);
                  }}
                  onAdopted={() => refreshCapa()}
                />
                <D4VerificationCard capaId={id!} canEdit={canEdit('capa')} currentRootCause={localData.d4_root_cause} fmeaRefId={capa.fmea_ref_id ?? null} />
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d4", t("fields.d4Label", "根因分析 (5Why / 鱼骨图)"))}>
                    <TextArea
                      rows={6}
                      disabled={!canEdit('capa')}
                      value={localData.d4_root_cause || ""}
                      onChange={(e) => setLocalData({ ...localData, d4_root_cause: e.target.value })}
                      onBlur={() => handleUpdate("d4_root_cause", localData.d4_root_cause)}
                    />
                  </Form.Item>
                </Form>
              </>
            )}

            {capa.status === "D5_CORRECTION" && (
              <>
                <D5RecPanel
                  capaId={id!}
                  canAdopt={canEdit('capa')}
                  beforeAdopt={async () => {
                    await handleUpdate("d5_correction", localData.d5_correction, true);
                  }}
                  onAdopted={() => refreshCapa()}
                />
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d5", t("fields.d5Label", "永久纠正措施"))}>
                    <TextArea
                      rows={4}
                      disabled={!canEdit('capa')}
                      value={localData.d5_correction || ""}
                      onChange={(e) => setLocalData({ ...localData, d5_correction: e.target.value })}
                      onBlur={() => handleUpdate("d5_correction", localData.d5_correction)}
                    />
                  </Form.Item>
                </Form>
              </>
            )}

            {capa.status === "D6_VERIFICATION" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d6", t("fields.d6Label", "效果验证"))}>
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d6_verification || ""}
                    onChange={(e) => setLocalData({ ...localData, d6_verification: e.target.value })}
                    onBlur={() => handleUpdate("d6_verification", localData.d6_verification)}
                  />
                </Form.Item>
              </Form>
            )}

            {["D7_PREVENTION", "D7_COMPLETED", "D8_GATE_PENDING", "D8_APPROVAL_PENDING"].includes(capa.status) && (
              <>
                <Form layout="vertical">
                  <Form.Item label={renderLabelWithDraft("d7", t("fields.d7Label", "预防复发措施"))}>
                    <TextArea
                      rows={4}
                      disabled={capa.status !== "D7_PREVENTION" || !canEdit('capa')}
                      value={localData.d7_prevention || ""}
                      onChange={(e) => setLocalData({ ...localData, d7_prevention: e.target.value })}
                      onBlur={() => handleUpdate("d7_prevention", localData.d7_prevention)}
                    />
                  </Form.Item>
                </Form>
                <Divider />
                <D7RecPanel
                  capaId={id!}
                  d5Correction={localData.d5_correction}
                  canAdopt={capa.status === "D7_PREVENTION" && canEdit('capa')}
                  canAutoFill={capa.status === "D7_PREVENTION" && canEdit('fmea')}
                  onConfirmationChange={(allConfirmed, unconfirmed) => {
                    setAllD7Confirmed(allConfirmed);
                    setD7UnconfirmedItems(unconfirmed);
                  }}
                />
              </>
            )}

            {capa.status === "D8_GATE_PENDING" && (
              <DocGatePanel
                capaId={id!}
                canEdit={canEdit("capa")}
                onAdvanced={() => refreshCapa()}
              />
            )}

            {capa.status === "D8_CLOSURE" && (
              <Form layout="vertical">
                <Form.Item label={renderLabelWithDraft("d8", t("fields.d8Label", "关闭确认"))}>
                  <TextArea
                    rows={4}
                    disabled={!canEdit('capa')}
                    value={localData.d8_closure || ""}
                    onChange={(e) => setLocalData({ ...localData, d8_closure: e.target.value })}
                    onBlur={() => handleUpdate("d8_closure", localData.d8_closure)}
                  />
                </Form.Item>
              </Form>
            )}

            {capa.status === "ARCHIVED" && <Empty description={t("messages.reportArchived", "报告已归档")} />}
          </DataCard>
        </Col>

        <Col span={8}>
          <DataCard title={t("detail.reportInfo", "报告信息")}>
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.documentNo", "编号")}:</Text> <span style={{ fontFamily: "var(--qf-font-mono)" }}>{capa.document_no}</span></p>
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.status", "状态")}:</Text> <span data-e2e="capa-status">{capa.status}</span></p>
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.severity", "严重等级")}:</Text> <StatusBadge status={severityMap[capa.severity] || "warning"}>{capa.severity}</StatusBadge></p>
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.dueDate", "期限")}:</Text> {capa.due_date || t("detail.notSet", "未设定")}</p>
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.relatedFMEA", "关联 FMEA")}:</Text> {capa.fmea_ref_id || t("detail.notLinked", "未关联")}</p>
            <p data-e2e="capa-supplier-row">
              <Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.supplier", "关联供应商")}:</Text>{" "}
              {supplierEditable ? (
                <Select
                  data-e2e="capa-supplier-select"
                  allowClear
                  showSearch
                  filterOption={false}
                  style={{ minWidth: 220 }}
                  size="small"
                  placeholder={t("fields.supplierPlaceholder", "请选择供应商")}
                  value={capa.supplier_id || undefined}
                  onSearch={async (q) => {
                    const seq = ++supplierSearchSeq.current;
                    try {
                      const res = await listCapaSupplierOptions({
                        page_size: 50,
                        search: q?.trim() || undefined,
                      });
                      if (seq !== supplierSearchSeq.current) return;
                      setSuppliers(res.items);
                    } catch {
                      /* leave existing options */
                    }
                  }}
                  onFocus={async () => {
                    if (suppliers.length === 0) {
                      try {
                        const res = await listCapaSupplierOptions({ page_size: 50 });
                        setSuppliers(res.items);
                      } catch {
                        /* leave empty */
                      }
                    }
                  }}
                  onChange={(val) => handleSupplierChange(val ?? null)}
                  options={suppliers.map((s) => ({
                    value: s.supplier_id,
                    label: `${s.supplier_no} - ${s.name}`,
                  }))}
                />
              ) : (
                <span data-e2e="capa-supplier-readonly">
                  {(() => {
                    if (!capa.supplier_id) return t("detail.notLinked", "未关联");
                    if (capa.supplier_no) {
                      return capa.supplier_name
                        ? `${capa.supplier_no} - ${capa.supplier_name}`
                        : capa.supplier_no;
                    }
                    const s = suppliers.find((x) => x.supplier_id === capa.supplier_id);
                    return s ? `${s.supplier_no} - ${s.name}` : capa.supplier_id;
                  })()}
                  {(supplierLocked || !!capa.supplier_risk_input) && capa.supplier_id && (
                    <Tag style={{ marginLeft: 8 }}>{t("detail.supplierLocked", "已锁定")}</Tag>
                  )}
                </span>
              )}
            </p>
            <p>
              <Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.relatedSCAR", "关联 SCAR")}:</Text>{" "}
              {capa.linked_scar ? (
                <a
                  data-e2e="capa-linked-scar"
                  onClick={() => navigate(`/scars/${capa.linked_scar!.scar_id}`)}
                  style={{ cursor: "pointer" }}
                >
                  {capa.linked_scar.scar_no} <Tag>{capa.linked_scar.status}</Tag>
                </a>
              ) : canEdit("capa") &&
                !["D1_TEAM", "D2_DESCRIPTION", "ARCHIVED"].includes(capa.status) ? (
                <Button data-e2e="capa-trigger-scar" size="small" onClick={openScarModal}>
                  {t("actions.triggerScar", "发起 SCAR")}
                </Button>
              ) : (
                t("detail.notLinked", "未关联")
              )}
            </p>
            {capa.supplier_risk_input && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ marginBottom: 4 }}>
                  <Text strong style={{ color: "var(--qf-text-secondary)" }}>
                    {t("riskInput.related", "供应商风险输入")}:
                  </Text>
                </p>
                <SupplierRiskInputCard
                  input={capa.supplier_risk_input}
                  canEdit={canEdit("capa") && canEdit("supplier_risk")}
                  onConfirm={async (confirmed) => {
                    if (!id) return;
                    try {
                      await confirmRepeat(id, confirmed);
                      await refreshCapa();
                      message.success(t("riskInput.confirmSuccess", "复发确认已保存"));
                    } catch {
                      message.error(t("riskInput.confirmFailed", "复发确认失败"));
                    }
                  }}
                />
              </div>
            )}
            <p><Text strong style={{ color: "var(--qf-text-secondary)" }}>{t("detail.createdAt", "创建时间")}:</Text> {formatDateTime(capa.created_at)}</p>
          </DataCard>

          {linkModal && canEdit('capa') && (
            <DataCard title={t("fmea.selectTitle", "选择关联的 FMEA")} style={{ marginTop: 16 }}>
              <Select
                showSearch
                style={{ width: "100%" }}
                placeholder={t("fmea.searchPlaceholder", "搜索 FMEA 文档")}
                filterOption={(input, option) =>
                  (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                }
                options={fmeas.map((f) => ({
                  value: f.fmea_id,
                  label: `${f.document_no} - ${f.title}`,
                }))}
                onChange={(val) => handleLinkFMEA(val)}
              />
              <Button style={{ marginTop: 8 }} onClick={() => setLinkModal(false)}>{tc("actions.cancel", "取消")}</Button>
            </DataCard>
          )}
        </Col>
      </Row>

      <Modal
        title={t("d7.skipDialogTitle", "⚠️ 以下 FMEA 节点尚未确认")}
        open={d7SkipDialogOpen}
        onOk={handleD7SkipConfirm}
        onCancel={() => setD7SkipDialogOpen(false)}
        okText={t("d7.skipConfirm", "确认跳过并推进")}
        cancelText={tc("actions.cancel", "取消")}
        width={600}
      >
        <p>{t("d7.skipDialogDescription", "以下推荐的 FMEA 节点尚未标记为「已更新」或「无需更新」：")}</p>
        <ul>
          {d7UnconfirmedItems.map((item) => (
            <li key={item.failure_mode_node_id}>
              {item.failure_mode_name}
              {item.failure_cause_node_id && ` (${t("d7.causeLabel", "原因")}: ${item.failure_cause_node_id})`}
            </li>
          ))}
        </ul>
        <p>{t("d7.skipReasonLabel", "如需跳过，请填写理由（可选）：")}</p>
        <Input.TextArea
          rows={3}
          placeholder={t("d7.skipReasonPlaceholder", "跳过理由（可选）")}
          value={d7SkipReasons["__global__"] || ""}
          onChange={(e) =>
            setD7SkipReasons({ ...d7SkipReasons, __global__: e.target.value })
          }
        />
      </Modal>

      <Modal
        open={rejectDialogOpen}
        title={t("reject.title", "驳回 8D")}
        onCancel={() => { setRejectDialogOpen(false); setRejectReason(""); }}
        onOk={handleRejectSubmit}
        okText={t("reject.confirm", "驳回")}
        okButtonProps={{ danger: true, disabled: !rejectReason.trim() }}
        cancelText={tc("actions.cancel", "取消")}
      >
        <Input.TextArea
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder={t("reject.reasonPlaceholder", "请填写驳回理由（必填）")}
          rows={4}
          data-e2e="capa-reject-reason"
        />
      </Modal>

      <Modal
        title={t("scar.modalTitle", "从 8D 发起 SCAR")}
        open={scarModalOpen}
        onCancel={() => {
          setScarModalOpen(false);
          scarForm.resetFields();
        }}
        onOk={handleTriggerScar}
        confirmLoading={scarSubmitting}
        okText={t("actions.triggerScar", "发起 SCAR")}
        cancelText={tc("actions.cancel", "取消")}
        destroyOnHidden
        width={640}
      >
        <Form form={scarForm} layout="vertical">
          <Form.Item
            name="supplier_id"
            label={t("scar.supplier", "供应商")}
            rules={[{ required: true, message: t("scar.supplierRequired", "请选择供应商") }]}
          >
            <Select
              showSearch
              filterOption={false}
              placeholder={t("scar.supplier", "供应商")}
              onSearch={async (search) => {
                const res = await listCapaSupplierOptions({ search, page_size: 20 });
                setSuppliers(res.items);
              }}
              options={suppliers.map((s) => ({
                value: s.supplier_id,
                label: `${s.supplier_no} - ${s.name}`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="description"
            label={t("scar.description", "问题描述")}
            rules={[{ required: true, message: t("scar.descriptionRequired", "请输入问题描述") }]}
          >
            <TextArea rows={5} />
          </Form.Item>
          <Form.Item name="requested_action" label={t("scar.requestedAction", "要求措施")}>
            <TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label={t("scar.dueDate", "到期日")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="affected_batches" label={t("scar.affectedBatches", "受影响批次")}>
            <Select
              mode="tags"
              tokenSeparators={[",", "\n"]}
              placeholder={t("scar.affectedBatchesPlaceholder", "输入批次号后回车添加")}
              open={false}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={reviewReport !== null}
        title={t("capa:ppt.reviewReport")}
        onCancel={() => setReviewReport(null)}
        footer={null}
      >
        {reviewReport && (
          <>
            <h4>{t("capa:ppt.issues")}</h4>
            <ul>{(reviewReport.issues || []).map((i: string, idx: number) => <li key={idx}>{i}</li>)}</ul>
            <h4>{t("capa:ppt.suggestions")}</h4>
            <ul>{(reviewReport.suggestions || []).map((s: string, idx: number) => <li key={idx}>{s}</li>)}</ul>
          </>
        )}
      </Modal>

      <AIDraftPreview
        open={previewOpen}
        content={draft?.content || ""}
        onClose={() => {
          setPreviewOpen(false);
          clear();
        }}
        onReplace={handleReplace}
        onAppend={handleAppend}
      />
      <LessonsLearnedModal
        open={lessonsModalOpen}
        loading={lessonsLoading}
        data={lessonsData}
        onClose={() => setLessonsModalOpen(false)}
        onViewDetail={(card) => {
          if (card.source_type === "fmea") {
            window.open(`/fmea/${card.source_id}`, "_blank");
          } else if (card.source_type === "capa") {
            window.open(`/capa/${card.source_id}`, "_blank");
          } else if (card.source_type === "audit") {
            const auditId = card.metadata?.audit_id;
            const category = card.metadata?.audit_category;
            if (auditId) {
              const path = category === "customer" ? `/customer-audits/${auditId}` : `/internal-audits/${auditId}`;
              window.open(path, "_blank");
            }
          }
        }}
      />
    </PageShell>
  );
}
