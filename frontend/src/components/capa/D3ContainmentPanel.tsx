import { useEffect, useState, useMemo } from "react";
import {
  Card, Button, Space, Tag, List, Typography, Spin, App, Alert,
  Modal, Form, Input, Select, message,
} from "antd";
import {
  ImportOutlined, ReloadOutlined, CheckOutlined, CloseOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  importD3Containment, getD3Runs, getD3Snapshots,
  generateD3Report, getD3Report,
  generateD3Advice, getD3Advice,
  decideD3Advice, getD3Adoptions,
  recordD3Execution, getD3Executions,
} from "../../api/capa";
import type {
  CAPAReport, D3ImportRun, D3ContainmentSnapshot, D3ImpactReport,
  D3AiAdvice, D3AdviceAdoption, D3Execution, D3AdviceType,
} from "../../types";

const { Text } = Typography;
const { TextArea } = Input;

interface D3ContainmentPanelProps {
  capa: CAPAReport;
  canEdit: boolean;
}

const adviceTypeColors: Record<D3AdviceType, string> = {
  recall: "red",
  isolate: "orange",
  notify_customer: "blue",
  strict_inspection: "purple",
  alternative: "green",
};

type ModalMode = "adopt" | "reject" | "execution" | null;

export default function D3ContainmentPanel({ capa, canEdit }: D3ContainmentPanelProps) {
  const { t } = useTranslation("capa");
  const { modal } = App.useApp();

  const [runs, setRuns] = useState<D3ImportRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<D3ContainmentSnapshot[]>([]);
  const [report, setReport] = useState<D3ImpactReport | null>(null);
  const [advice, setAdvice] = useState<D3AiAdvice[]>([]);
  const [adoptions, setAdoptions] = useState<D3AdviceAdoption[]>([]);
  const [executions, setExecutions] = useState<D3Execution[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [generatingAdvice, setGeneratingAdvice] = useState(false);

  // Controlled modal state (replaces document.getElementById anti-pattern)
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [activeAdvice, setActiveAdvice] = useState<D3AiAdvice | null>(null);
  const [adoptedText, setAdoptedText] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [executionMeasure, setExecutionMeasure] = useState("");
  const [executionEvidenceUrl, setExecutionEvidenceUrl] = useState("");

  // Current run is the one with is_current=true, or selected from historical runs
  const currentRun = useMemo(() => {
    if (selectedRunId) {
      return runs.find(r => r.run_id === selectedRunId);
    }
    return runs.find(r => r.is_current);
  }, [runs, selectedRunId]);

  // Historical runs are those with is_current=false
  const historicalRuns = useMemo(() => runs.filter(r => !r.is_current), [runs]);

  // For historical runs, disable all write buttons
  const isReadOnly = !currentRun?.is_current || !canEdit;

  // Show import button when canEdit, status is D3_INTERIM, and not viewing a historical run
  const showImportButton = canEdit && capa.status === "D3_INTERIM" && (!currentRun || (!!currentRun.is_current && !selectedRunId));

  useEffect(() => {
    if (capa.report_id) {
      loadRuns();
      loadAdoptions();
      loadExecutions();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capa.report_id]);

  useEffect(() => {
    if (currentRun?.run_id) {
      loadSnapshots();
      loadReport();
      loadAdvice();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRun?.run_id]);

  const loadRuns = async () => {
    setLoading(true);
    try {
      const data = await getD3Runs(capa.report_id);
      setRuns(data);
    } catch {
      message.error(t("d3.loadRunsFailed", "加载代次失败"));
    } finally {
      setLoading(false);
    }
  };

  const loadSnapshots = async () => {
    try {
      const data = await getD3Snapshots(capa.report_id);
      setSnapshots(data);
    } catch {
      message.error(t("d3.loadSnapshotsFailed", "加载快照失败"));
    }
  };

  const loadReport = async () => {
    try {
      const data = await getD3Report(capa.report_id);
      setReport(data);
    } catch {
      message.error(t("d3.loadReportFailed", "加载报告失败"));
    }
  };

  const loadAdvice = async () => {
    try {
      const resp = await getD3Advice(capa.report_id);
      setAdvice(resp.advice ?? []);
    } catch {
      message.error(t("d3.loadAdviceFailed", "加载建议失败"));
    }
  };

  const loadAdoptions = async () => {
    try {
      const data = await getD3Adoptions(capa.report_id);
      setAdoptions(data);
    } catch {
      message.error(t("d3.loadAdoptionsFailed", "加载采纳记录失败"));
    }
  };

  const loadExecutions = async () => {
    try {
      const data = await getD3Executions(capa.report_id);
      setExecutions(data);
    } catch {
      message.error(t("d3.loadExecutionsFailed", "加载执行记录失败"));
    }
  };

  const handleImport = async () => {
    setImporting(true);
    try {
      await importD3Containment(capa.report_id);
      message.success(t("d3.importSuccess", "导入成功"));
      await loadRuns();
    } catch {
      message.error(t("d3.importFailed", "导入失败"));
    } finally {
      setImporting(false);
    }
  };

  const handleGenerateReport = async () => {
    if (!currentRun) return;
    setGeneratingReport(true);
    try {
      await generateD3Report(capa.report_id, { run_id: currentRun.run_id });
      message.success(t("d3.reportGenerated", "报告生成中"));
      await loadReport();
    } catch {
      message.error(t("d3.reportGenerateFailed", "报告生成失败"));
    } finally {
      setGeneratingReport(false);
    }
  };

  const handleGenerateAdvice = async () => {
    if (!currentRun) return;
    setGeneratingAdvice(true);
    try {
      await generateD3Advice(capa.report_id, { run_id: currentRun.run_id });
      message.success(t("d3.adviceGenerated", "建议生成中"));
      await loadAdvice();
    } catch {
      message.error(t("d3.adviceGenerateFailed", "建议生成失败"));
    } finally {
      setGeneratingAdvice(false);
    }
  };

  const openAdoptModal = (item: D3AiAdvice) => {
    setActiveAdvice(item);
    setAdoptedText(item.advice_text);
    setModalMode("adopt");
  };

  const openRejectModal = (item: D3AiAdvice) => {
    setActiveAdvice(item);
    setRejectReason("");
    setModalMode("reject");
  };

  const openExecutionModal = () => {
    setExecutionMeasure("");
    setExecutionEvidenceUrl("");
    setModalMode("execution");
  };

  const closeModal = () => {
    setModalMode(null);
    setActiveAdvice(null);
  };

  const handleAdoptOk = async () => {
    if (!activeAdvice) return;
    try {
      await decideD3Advice(capa.report_id, activeAdvice.advice_id, {
        decision: "adopted",
        adopted_text: adoptedText,
      });
      message.success(t("d3.acceptSuccess", "已采纳"));
      closeModal();
      await loadAdoptions();
      await loadAdvice();
    } catch {
      message.error(t("d3.acceptFailed", "采纳失败"));
    }
  };

  const handleRejectOk = async () => {
    if (!activeAdvice) return;
    try {
      await decideD3Advice(capa.report_id, activeAdvice.advice_id, {
        decision: "rejected",
        adopted_text: null,
      });
      message.success(t("d3.rejectSuccess", "已拒绝"));
      closeModal();
      await loadAdvice();
    } catch {
      message.error(t("d3.rejectFailed", "拒绝失败"));
    }
  };

  const handleExecutionOk = async () => {
    if (!executionMeasure.trim()) {
      message.warning(t("d3.measureRequired", "请填写措施"));
      return;
    }
    try {
      await recordD3Execution(capa.report_id, {
        source: "manual",
        measure_text: executionMeasure,
        evidence_refs: executionEvidenceUrl.trim()
          ? [{ type: "url", url: executionEvidenceUrl.trim() }]
          : [],
      });
      message.success(t("d3.executionAdded", "执行记录已添加"));
      closeModal();
      await loadExecutions();
    } catch {
      message.error(t("d3.executionAddFailed", "添加执行记录失败"));
    }
  };

  // Group snapshots by type
  const snapshotsByType = useMemo(() => {
    const groups: Record<string, D3ContainmentSnapshot[]> = {
      inventory: [],
      shipment: [],
      iqc: [],
      spc: [],
    };
    snapshots.forEach(s => {
      if (groups[s.snapshot_type]) {
        groups[s.snapshot_type].push(s);
      }
    });
    return groups;
  }, [snapshots]);

  if (loading) return <Spin size="small" />;

  // Status banners
  const renderStatusBanner = () => {
    if (!currentRun) return null;
    if (currentRun.status === "failed") {
      return (
        <Alert
          type="error"
          showIcon
          message={t("d3.runFailed", "代次失败")}
          description={report?.error || currentRun.status}
          style={{ marginBottom: 16 }}
        />
      );
    }
    if (currentRun.status === "importing") {
      return (
        <Alert
          type="info"
          showIcon
          message={t("d3.runRunning", "正在运行")}
          style={{ marginBottom: 16 }}
        />
      );
    }
    return null;
  };

  return (
    <Card
      size="small"
      title={t("d3.title", "D3 临时遏制措施")}
      extra={
        showImportButton && (
          <Button
            type="primary"
            icon={<ImportOutlined />}
            loading={importing}
            onClick={handleImport}
            data-e2e="d3-import-button"
          >
            {t("d3.import", "导入")}
          </Button>
        )
      }
    >
      {renderStatusBanner()}

      {/* Run switcher for historical runs */}
      {historicalRuns.length > 0 && (
        <Space style={{ marginBottom: 16 }}>
          <Text strong>{t("d3.selectRun", "选择代次")}</Text>
          <Select
            style={{ width: 200 }}
            value={selectedRunId || currentRun?.run_id}
            onChange={(val) => setSelectedRunId(val)}
            options={[
              { value: currentRun?.run_id, label: t("d3.currentRun", "当前代次") },
              ...historicalRuns.map(r => ({
                value: r.run_id,
                label: `${t("d3.runLabel", "代次")} ${r.created_at}`,
              })),
            ]}
          />
        </Space>
      )}

      {/* 4 Snapshot Cards */}
      {(snapshots.length > 0) && (
        <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
          <Text strong>{t("d3.snapshotsTitle", "数据快照")}</Text>
          {(["inventory", "shipment", "iqc", "spc"] as const).map(type => (
            <Card
              key={type}
              size="small"
              data-e2e={`d3-snapshot-card-${type}`}
              style={{ background: "#fafafa" }}
            >
              <Text strong>{t(`d3.snapshotType.${type}`, type)}</Text>
              <List
                size="small"
                dataSource={snapshotsByType[type]}
                renderItem={(s) => (
                  <List.Item>
                    <Text>{t("d3.recordCount", "记录数")}: {s.record_count}</Text>
                    <Tag>{s.snapshot_type}</Tag>
                  </List.Item>
                )}
              />
            </Card>
          ))}
        </Space>
      )}

      {/* Impact Report */}
      {report && (
        <Card size="small" title={t("d3.reportTitle", "影响报告")} style={{ marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            {report.risk_level && (
              <Text>
                {t("d3.riskLevel", "风险等级")}: {report.risk_level} ({t("d3.riskFloor", "底线")}: {report.risk_floor})
              </Text>
            )}
            {report.risk_explanation && <Text>{report.risk_explanation}</Text>}
            {!!report.customer_impact?.length && (
              <Text>
                {t("d3.customerImpact", "客户影响")}: {report.customer_impact.length} 条
              </Text>
            )}
          </Space>
          {!isReadOnly && report.status !== "running" && (
            <Button
              size="small"
              loading={generatingReport}
              onClick={handleGenerateReport}
              style={{ marginTop: 8 }}
            >
              {t("d3.generateReport", "生成报告")}
            </Button>
          )}
        </Card>
      )}

      {/* AI Advice */}
      {advice.length > 0 && (
        <Card size="small" title={t("d3.adviceTitle", "AI 建议")} style={{ marginBottom: 16 }}>
          <List
            dataSource={advice}
            renderItem={(item) => (
              <List.Item
                actions={
                  !isReadOnly && !item.adoption_status
                    ? [
                        <Button
                          key="accept"
                          type="link"
                          size="small"
                          icon={<CheckOutlined />}
                          onClick={() => openAdoptModal(item)}
                        >
                          {t("d3.accept", "采纳")}
                        </Button>,
                        <Button
                          key="reject"
                          type="link"
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          onClick={() => openRejectModal(item)}
                        >
                          {t("d3.reject", "拒绝")}
                        </Button>,
                      ]
                    : undefined
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={adviceTypeColors[item.advice_type]} data-e2e={`d3-advice-type-${item.advice_type}`}>
                        {t(`d3.adviceType.${item.advice_type}`, item.advice_type)}
                      </Tag>
                      {item.advice_text}
                    </Space>
                  }
                  description={
                    <Space>
                      <Text type="secondary" data-e2e="d3-advice-provenance">
                        {item.source_provenance?.map(p => p.record_key).join(", ") || "-"}
                      </Text>
                      {item.adoption_status && <Tag>{item.adoption_status}</Tag>}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
          {!isReadOnly && (
            <Button
              size="small"
              loading={generatingAdvice}
              onClick={handleGenerateAdvice}
              style={{ marginTop: 8 }}
            >
              {t("d3.generateAdvice", "生成建议")}
            </Button>
          )}
        </Card>
      )}

      {/* Adoption List */}
      {adoptions.length > 0 && (
        <Card size="small" title={t("d3.adoptionsTitle", "采纳记录")} style={{ marginBottom: 16 }} data-e2e="d3-adoption-list">
          <List
            dataSource={adoptions}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={adviceTypeColors[item.advice_type]}>
                        {t(`d3.adviceType.${item.advice_type}`, item.advice_type)}
                      </Tag>
                      {item.adopted_text}
                    </Space>
                  }
                  description={item.decided_at}
                />
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* Execution List */}
      <Card size="small" title={t("d3.executionsTitle", "执行记录")} data-e2e="d3-execution-list">
        <List
          dataSource={executions}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={item.measure_text}
                description={
                  <Space>
                    <Text type="secondary">{item.result_status}</Text>
                    {item.evidence_refs?.[0] && (
                      <Button type="link" size="small" href={String(item.evidence_refs[0].url || "")} target="_blank">
                        {t("d3.evidenceLink", "证据")}
                      </Button>
                    )}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
        {!isReadOnly && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openExecutionModal}
            data-e2e="d3-execution-add"
            style={{ marginTop: 8 }}
          >
            {t("d3.addExecution", "添加执行记录")}
          </Button>
        )}
      </Card>

      {/* Adopt Modal */}
      <Modal
        open={modalMode === "adopt"}
        title={t("d3.acceptAdviceTitle", "采纳建议")}
        onCancel={closeModal}
        onOk={handleAdoptOk}
        okText={t("d3.accept", "采纳")}
      >
        <Form layout="vertical">
          <Form.Item label={t("d3.adoptedTextLabel", "采纳文本")}>
            <TextArea
              rows={4}
              value={adoptedText}
              onChange={(e) => setAdoptedText(e.target.value)}
              data-e2e="d3-adopted-text"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Reject Modal */}
      <Modal
        open={modalMode === "reject"}
        title={t("d3.rejectAdviceTitle", "拒绝建议")}
        onCancel={closeModal}
        onOk={handleRejectOk}
        okText={t("d3.reject", "拒绝")}
        okButtonProps={{ danger: true }}
      >
        <Form layout="vertical">
          <Form.Item label={t("d3.rejectReasonLabel", "拒绝理由")}>
            <TextArea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              data-e2e="d3-reject-reason"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Execution Modal */}
      <Modal
        open={modalMode === "execution"}
        title={t("d3.addExecutionTitle", "添加执行记录")}
        onCancel={closeModal}
        onOk={handleExecutionOk}
        okText={t("d3.addExecution", "添加")}
        okButtonProps={{ "data-e2e": "d3-execution-save" }}
      >
        <Form layout="vertical">
          <Form.Item label={t("d3.executionMeasureLabel", "措施")}>
            <TextArea
              rows={3}
              value={executionMeasure}
              onChange={(e) => setExecutionMeasure(e.target.value)}
              data-e2e="d3-execution-measure"
            />
          </Form.Item>
          <Form.Item label={t("d3.evidenceUrlLabel", "证据 URL")}>
            <Input
              value={executionEvidenceUrl}
              onChange={(e) => setExecutionEvidenceUrl(e.target.value)}
              data-e2e="d3-execution-evidence-url"
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
