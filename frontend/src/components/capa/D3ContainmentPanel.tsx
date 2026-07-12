import { useEffect, useState, useMemo } from "react";
import {
  Card, Button, Space, Tag, List, Typography, Empty, Spin, App, Alert,
  Modal, Form, Input, Select, Divider, Switch, message,
} from "antd";
import {
  ImportOutlined, ReloadOutlined, CheckOutlined, CloseOutlined,
  PlusOutlined, EditOutlined,
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

  // Show import button only when canEdit and status is D3_INTERIM
  const showImportButton = canEdit && capa.status === "D3_INTERIM";

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
      loadSnapshots(currentRun.run_id);
      loadReport(currentRun.run_id);
      loadAdvice(currentRun.run_id);
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

  const loadSnapshots = async (runId: string) => {
    try {
      const data = await getD3Snapshots(runId);
      setSnapshots(data);
    } catch {
      message.error(t("d3.loadSnapshotsFailed", "加载快照失败"));
    }
  };

  const loadReport = async (runId: string) => {
    try {
      const data = await getD3Report(runId);
      setReport(data);
    } catch {
      message.error(t("d3.loadReportFailed", "加载报告失败"));
    }
  };

  const loadAdvice = async (runId: string) => {
    try {
      const data = await getD3Advice(runId);
      setAdvice(data);
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
      await loadReport(currentRun.run_id);
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
      await loadAdvice(currentRun.run_id);
    } catch {
      message.error(t("d3.adviceGenerateFailed", "建议生成失败"));
    } finally {
      setGeneratingAdvice(false);
    }
  };

  const handleAcceptAdvice = (item: D3AiAdvice) => {
    modal.confirm({
      title: t("d3.acceptAdviceTitle", "采纳建议"),
      content: (
        <Form layout="vertical">
          <Form.Item label={t("d3.adoptedTextLabel", "采纳文本")}>
            <TextArea
              id="d3-adopted-text"
              rows={4}
              defaultValue={item.advice_text}
            />
          </Form.Item>
        </Form>
      ),
      onOk: async () => {
        const textarea = document.getElementById("d3-adopted-text") as HTMLTextAreaElement;
        const adoptedText = textarea?.value || item.advice_text;
        try {
          await decideD3Advice(capa.report_id, item.advice_id, {
            decision: "accept",
            adopted_text: adoptedText,
          });
          message.success(t("d3.acceptSuccess", "已采纳"));
          await loadAdoptions();
          await loadAdvice(currentRun!.run_id);
        } catch {
          message.error(t("d3.acceptFailed", "采纳失败"));
        }
      },
    });
  };

  const handleRejectAdvice = async (item: D3AiAdvice) => {
    modal.confirm({
      title: t("d3.rejectAdviceTitle", "拒绝建议"),
      content: (
        <Form layout="vertical">
          <Form.Item label={t("d3.rejectReasonLabel", "拒绝理由")}>
            <TextArea
              id="d3-reject-reason"
              rows={3}
            />
          </Form.Item>
        </Form>
      ),
      onOk: async () => {
        const textarea = document.getElementById("d3-reject-reason") as HTMLTextAreaElement;
        const reason = textarea?.value || "";
        try {
          await decideD3Advice(capa.report_id, item.advice_id, {
            decision: "reject",
            rejection_reason: reason,
          });
          message.success(t("d3.rejectSuccess", "已拒绝"));
          await loadAdvice(currentRun!.run_id);
        } catch {
          message.error(t("d3.rejectFailed", "拒绝失败"));
        }
      },
    });
  };

  const handleAddExecution = () => {
    modal.confirm({
      title: t("d3.addExecutionTitle", "添加执行记录"),
      content: (
        <Form layout="vertical">
          <Form.Item label={t("d3.executionMeasureLabel", "措施")}>
            <TextArea
              id="d3-execution-measure"
              rows={3}
              data-e2e="d3-execution-measure"
            />
          </Form.Item>
          <Form.Item label={t("d3.evidenceUrlLabel", "证据 URL")}>
            <Input
              id="d3-execution-evidence-url"
              data-e2e="d3-execution-evidence-url"
            />
          </Form.Item>
        </Form>
      ),
      okButtonProps: { "data-e2e": "d3-execution-save" },
      onOk: async () => {
        const measureTextarea = document.getElementById("d3-execution-measure") as HTMLTextAreaElement;
        const evidenceInput = document.getElementById("d3-execution-evidence-url") as HTMLInputElement;
        const measure = measureTextarea?.value || "";
        const evidenceUrl = evidenceInput?.value || "";
        if (!measure.trim()) {
          message.warning(t("d3.measureRequired", "请填写措施"));
          return;
        }
        try {
          await recordD3Execution(capa.report_id, {
            measure,
            evidence_url: evidenceUrl,
          });
          message.success(t("d3.executionAdded", "执行记录已添加"));
          await loadExecutions();
        } catch {
          message.error(t("d3.executionAddFailed", "添加执行记录失败"));
        }
      },
    });
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
          description={currentRun.error_message}
          style={{ marginBottom: 16 }}
        />
      );
    }
    if (currentRun.status === "running") {
      return (
        <Alert
          type="info"
          showIcon
          message={t("d3.runRunning", "正在运行")}
          style={{ marginBottom: 16 }}
        />
      );
    }
    if (currentRun.status === "superseded") {
      return (
        <Alert
          type="warning"
          showIcon
          message={t("d3.runSuperseded", "已被新代次取代")}
          action={
            canEdit && (
              <Button size="small" icon={<ReloadOutlined />} onClick={handleImport}>
                {t("d3.refresh", "刷新")}
              </Button>
            )
          }
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
                    <Text>{s.record_key}</Text>
                    <Tag>{s.source_type}</Tag>
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
            {report.summary && <Text>{report.summary}</Text>}
            {report.inventory_impact && (
              <Text>
                {t("d3.inventoryImpact", "库存影响")}: {report.inventory_impact.affected_qty} 受影响
              </Text>
            )}
            {report.shipment_impact && (
              <Text>
                {t("d3.shipmentImpact", "发货影响")}: {report.shipment_impact.affected_customers} 客户
              </Text>
            )}
            {report.iqc_impact && (
              <Text>
                {t("d3.iqcImpact", "IQC 影响")}: {report.iqc_impact.affected_batches} 批次
              </Text>
            )}
            {report.spc_impact && (
              <Text>
                {t("d3.spcImpact", "SPC 影响")}: {report.spc_impact.affected_charts} 图表
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
                  !isReadOnly && item.status === "pending"
                    ? [
                        <Button
                          key="accept"
                          type="link"
                          size="small"
                          icon={<CheckOutlined />}
                          onClick={() => handleAcceptAdvice(item)}
                        >
                          {t("d3.accept", "采纳")}
                        </Button>,
                        <Button
                          key="reject"
                          type="link"
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          onClick={() => handleRejectAdvice(item)}
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
                        {item.provenance.record_key} ({item.provenance.source_type})
                      </Text>
                      <Tag>{item.status}</Tag>
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
                  description={item.adopted_at}
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
                title={item.measure}
                description={
                  <Space>
                    <Text type="secondary">{item.executed_at}</Text>
                    {item.evidence_url && (
                      <Button type="link" size="small" href={item.evidence_url} target="_blank">
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
            onClick={handleAddExecution}
            data-e2e="d3-execution-add"
            style={{ marginTop: 8 }}
          >
            {t("d3.addExecution", "添加执行记录")}
          </Button>
        )}
      </Card>
    </Card>
  );
}