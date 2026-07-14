/**
 * US-E2E-01.7 D8 doc update gate panel.
 * Six zones: impact analysis / affected docs / audit / decision / empty-confirm / defer.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Button, Card, DatePicker, Form, Input, Modal, Space, Table, Tag, Typography, message,
} from "antd";
import {
  AuditOutlined, CheckOutlined, ReloadOutlined, ThunderboltOutlined, ClockCircleOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import {
  advanceCAPA,
  confirmNoAffected,
  docGateImpact,
  getDocGateAudit,
  getDocGateDecision,
  getDocGateImpact,
  recordDocGateDefer,
  runDocGateAudit,
  type DocGateAffectedDoc,
  type DocGateAnalysis,
  type DocGateAuditRow,
  type DocGateDecision,
} from "../../api/capa";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

export interface DocGatePanelProps {
  capaId: string;
  canEdit: boolean;
  /** Optional preloaded state for unit tests (skips initial fetch). */
  analysis?: DocGateAnalysis | null;
  decision?: DocGateDecision | null;
  audits?: DocGateAuditRow[];
  onAdvanced?: () => void;
}

function isBlockedError(err: unknown): boolean {
  const ax = err as { response?: { status?: number; data?: { detail?: { blocked?: boolean } } } };
  return ax?.response?.status === 422 && ax?.response?.data?.detail?.blocked === true;
}

function errMsg(err: unknown): string {
  const ax = err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string };
  const d = ax?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && d.message) return d.message;
  return ax?.message || "error";
}

export default function DocGatePanel({
  capaId, canEdit, analysis: analysisProp, decision: decisionProp,
  audits: auditsProp, onAdvanced,
}: DocGatePanelProps) {
  const { t } = useTranslation("capa");
  const [analysis, setAnalysis] = useState<DocGateAnalysis | null>(analysisProp ?? null);
  const [decision, setDecision] = useState<DocGateDecision | null>(decisionProp ?? null);
  const [audits, setAudits] = useState<DocGateAuditRow[]>(auditsProp ?? []);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [auditing, setAuditing] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [deferOpen, setDeferOpen] = useState(false);
  const [deferForm] = Form.useForm();

  const load = useCallback(async () => {
    if (analysisProp !== undefined) return; // test mode
    setLoading(true);
    try {
      try {
        const a = await getDocGateImpact(capaId);
        setAnalysis(a);
        if (a.status === "failed" && a.error?.includes("LLM")) setBlocked(true);
      } catch (e: unknown) {
        const ax = e as { response?: { status?: number } };
        if (ax?.response?.status === 404) setAnalysis(null);
        else throw e;
      }
      const d = await getDocGateDecision(capaId);
      setDecision(d);
      const au = await getDocGateAudit(capaId);
      setAudits(au.audits || []);
    } catch {
      /* silent: empty state is valid */
    } finally {
      setLoading(false);
    }
  }, [capaId, analysisProp]);

  useEffect(() => {
    if (analysisProp !== undefined) {
      setAnalysis(analysisProp ?? null);
      setDecision(decisionProp ?? null);
      setAudits(auditsProp ?? []);
      if (analysisProp?.status === "failed" && analysisProp.error?.includes("LLM")) {
        setBlocked(true);
      }
      return;
    }
    load();
  }, [load, analysisProp, decisionProp, auditsProp]);

  const handleGenerate = async () => {
    setGenerating(true);
    setBlocked(false);
    try {
      const result = await docGateImpact(capaId);
      setAnalysis(result as DocGateAnalysis);
      if (result.status === "running") {
        message.info(t("docGate.retryAfter", "生成进行中，请稍后刷新"));
      } else if (result.status === "done") {
        message.success(t("docGate.generateDone", "影响分析已生成"));
      } else if (result.status === "failed") {
        message.error(result.error || t("docGate.generateFailed", "影响分析失败"));
      }
      await load();
    } catch (e: unknown) {
      if (isBlockedError(e)) {
        setBlocked(true);
        setAnalysis({ status: "failed", error: "LLM 未配置", is_current: false });
      } else {
        message.error(errMsg(e));
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleAudit = async () => {
    setAuditing(true);
    try {
      const result = await runDocGateAudit(capaId);
      setAudits(result.audits || []);
      setDecision({ decision: result.decision as DocGateDecision["decision"] });
      message.success(
        result.decision === "passed"
          ? t("docGate.auditPassed", "审核通过")
          : t("docGate.auditBlocked", "审核未通过，门禁阻断"),
      );
      await load();
    } catch (e: unknown) {
      message.error(errMsg(e));
    } finally {
      setAuditing(false);
    }
  };

  const handleConfirmEmpty = async () => {
    try {
      const result = await confirmNoAffected(capaId);
      setDecision({
        decision: result.decision as DocGateDecision["decision"],
        no_affected_confirmed: result.no_affected_confirmed,
      });
      message.success(t("docGate.confirmEmptyDone", "已确认无受影响文档"));
      await load();
    } catch (e: unknown) {
      message.error(errMsg(e));
    }
  };

  const handleDefer = async () => {
    try {
      const values = await deferForm.validateFields();
      await recordDocGateDefer(capaId, {
        reason: values.reason,
        owner_id: values.owner_id,
        deadline: values.deadline.format("YYYY-MM-DD"),
      });
      message.success(t("docGate.deferDone", "已记录延期（门禁仍阻断）"));
      setDeferOpen(false);
      deferForm.resetFields();
      await load();
    } catch (e: unknown) {
      if ((e as { errorFields?: unknown }).errorFields) return;
      message.error(errMsg(e));
    }
  };

  const handleAdvance = async () => {
    setAdvancing(true);
    try {
      await advanceCAPA(capaId, { target_state: "D8_APPROVAL_PENDING" });
      message.success(t("docGate.advanceDone", "已推进到审批"));
      onAdvanced?.();
    } catch (e: unknown) {
      const msg = errMsg(e);
      if (msg.includes("文档已变更")) {
        message.error(t("docGate.docChanged", "文档已变更，请重新审核"));
      } else if (msg.includes("分析输入已变更")) {
        message.error(t("docGate.inputChanged", "分析输入已变更，请重新生成"));
      } else {
        message.error(msg);
      }
      await load();
    } finally {
      setAdvancing(false);
    }
  };

  const affectedDocs: DocGateAffectedDoc[] = analysis?.affected_docs || [];
  const isDone = analysis?.status === "done";
  const isEmpty = isDone && affectedDocs.length === 0;
  const decisionPassed = decision?.decision === "passed";

  const statusTag = () => {
    if (!analysis) return <Tag data-e2e="doc-gate-status">{t("docGate.noAnalysis", "未分析")}</Tag>;
    if (analysis.status === "running") return <Tag color="processing" data-e2e="doc-gate-status">running</Tag>;
    if (analysis.status === "done") return <Tag color="success" data-e2e="doc-gate-status">done</Tag>;
    if (analysis.status === "failed") return <Tag color="error" data-e2e="doc-gate-status">failed</Tag>;
    return <Tag data-e2e="doc-gate-status">{analysis.status}</Tag>;
  };

  return (
    <Card
      title={t("docGate.title", "D8 文档更新审核门禁")}
      data-e2e="doc-gate-panel"
      loading={loading}
      extra={statusTag()}
      style={{ marginBottom: 16 }}
    >
      {/* Zone 1: Impact analysis */}
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        {blocked && (
          <Alert
            type="warning"
            showIcon
            data-e2e="doc-gate-blocked-banner"
            message={t("docGate.blocked", "LLM 凭证未配置，影响分析被阻断")}
          />
        )}
        {analysis?.status === "failed" && !blocked && (
          <Alert
            type="error"
            showIcon
            data-e2e="doc-gate-failed-banner"
            message={t("docGate.failed", "影响分析失败")}
            description={analysis.error || undefined}
          />
        )}

        <Space>
          {canEdit && (!isDone || analysis?.status === "failed") && (
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={generating}
              onClick={handleGenerate}
              data-e2e="doc-gate-generate"
            >
              {analysis ? t("docGate.regenerate", "重新生成影响分析") : t("docGate.generate", "生成影响分析")}
            </Button>
          )}
          {canEdit && isDone && (
            <Button
              icon={<ReloadOutlined />}
              loading={generating}
              onClick={handleGenerate}
              data-e2e="doc-gate-regenerate"
            >
              {t("docGate.regenerate", "重新生成影响分析")}
            </Button>
          )}
        </Space>

        {/* Zone 2: Affected docs list */}
        {isDone && (
          <div data-e2e="doc-gate-affected-list">
            <Text strong>{t("docGate.affectedTitle", "受影响文档")}</Text>
            {isEmpty ? (
              <Alert
                type="info"
                style={{ marginTop: 8 }}
                data-e2e="doc-gate-empty-list"
                message={t("docGate.emptyList", "影响清单为空，请确认确实无受影响文档")}
                action={
                  canEdit ? (
                    <Button size="small" onClick={handleConfirmEmpty} data-e2e="doc-gate-confirm-empty">
                      {t("docGate.confirmEmpty", "确认无受影响文档")}
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <Table
                size="small"
                style={{ marginTop: 8 }}
                pagination={false}
                rowKey={(r) => `${r.doc_type}-${r.doc_id}`}
                dataSource={affectedDocs}
                columns={[
                  { title: t("docGate.colType", "类型"), dataIndex: "doc_type", width: 120 },
                  { title: t("docGate.colName", "名称"), dataIndex: "doc_name" },
                  {
                    title: t("docGate.colKeyPoints", "关键点"),
                    dataIndex: "key_points",
                    render: (kps: unknown[]) => kps?.length ?? 0,
                  },
                  {
                    title: t("docGate.colSuggestion", "更新建议"),
                    dataIndex: "update_suggestion",
                    ellipsis: true,
                  },
                ]}
              />
            )}
            {!isEmpty && affectedDocs.map((d) => (
              <Paragraph key={d.doc_id} type="secondary" style={{ marginTop: 4, marginBottom: 0 }}>
                {d.doc_name}: {d.update_suggestion}
              </Paragraph>
            ))}
          </div>
        )}

        {/* Zone 3: Audit */}
        {isDone && !isEmpty && (
          <div data-e2e="doc-gate-audit-zone">
            <Space>
              {canEdit && (
                <Button
                  icon={<AuditOutlined />}
                  loading={auditing}
                  onClick={handleAudit}
                  data-e2e="doc-gate-run-audit"
                >
                  {t("docGate.runAudit", "运行文档审核")}
                </Button>
              )}
              {canEdit && decision?.decision === "blocked" && (
                <Button
                  icon={<ClockCircleOutlined />}
                  onClick={() => setDeferOpen(true)}
                  data-e2e="doc-gate-defer-btn"
                >
                  {t("docGate.defer", "记录延期")}
                </Button>
              )}
            </Space>
            {audits.length > 0 && (
              <Table
                size="small"
                style={{ marginTop: 8 }}
                pagination={false}
                rowKey={(r) => `${r.doc_type}-${r.doc_id}`}
                dataSource={audits}
                data-e2e="doc-gate-audit-table"
                columns={[
                  { title: t("docGate.colName", "名称"), dataIndex: "doc_name" },
                  {
                    title: t("docGate.colStatus", "状态"),
                    dataIndex: "status",
                    render: (s: string) => (
                      <Tag color={s === "passed" ? "success" : s === "incomplete" ? "warning" : "default"}>
                        {s}
                      </Tag>
                    ),
                  },
                  {
                    title: t("docGate.colCoverage", "覆盖"),
                    render: (_: unknown, r: DocGateAuditRow) =>
                      `${r.covered_count}/${r.total_count}`,
                  },
                  {
                    title: t("docGate.colBump", "版本变更"),
                    dataIndex: "version_bump",
                    render: (v: boolean) => (v ? "✓" : "—"),
                  },
                ]}
              />
            )}
          </div>
        )}

        {/* Zone 4: Decision + advance */}
        <div data-e2e="doc-gate-decision-zone">
          <Text strong>{t("docGate.decisionTitle", "门禁决策")}: </Text>
          {decision?.decision ? (
            <Tag
              color={
                decision.decision === "passed" ? "success"
                  : decision.decision === "deferred" ? "warning" : "error"
              }
              data-e2e="doc-gate-decision"
            >
              {decision.decision}
            </Tag>
          ) : (
            <Tag data-e2e="doc-gate-decision">{t("docGate.noDecision", "尚未决策")}</Tag>
          )}
          {decision?.no_affected_confirmed && (
            <Tag color="blue">{t("docGate.emptyConfirmed", "空清单已确认")}</Tag>
          )}
          {decision?.defer_reason && (
            <Paragraph type="secondary" style={{ marginTop: 4 }}>
              {t("docGate.deferInfo", "延期")}: {decision.defer_reason}
              {decision.defer_deadline ? ` / ${decision.defer_deadline}` : ""}
            </Paragraph>
          )}
          {canEdit && decisionPassed && (
            <div style={{ marginTop: 8 }}>
              <Button
                type="primary"
                icon={<CheckOutlined />}
                loading={advancing}
                onClick={handleAdvance}
                data-e2e="doc-gate-advance"
              >
                {t("docGate.advance", "推进到审批")}
              </Button>
            </div>
          )}
        </div>
      </Space>

      <Modal
        title={t("docGate.deferTitle", "记录延期（仍阻断推进）")}
        open={deferOpen}
        onOk={handleDefer}
        onCancel={() => setDeferOpen(false)}
        okText={t("docGate.deferConfirm", "确认延期")}
        data-e2e="doc-gate-defer-modal"
      >
        <Form form={deferForm} layout="vertical">
          <Form.Item
            name="reason"
            label={t("docGate.deferReason", "延期原因")}
            rules={[{ required: true, message: t("docGate.deferReasonRequired", "必填") }]}
          >
            <TextArea rows={3} data-e2e="doc-gate-defer-reason" />
          </Form.Item>
          <Form.Item
            name="owner_id"
            label={t("docGate.deferOwner", "负责人 user_id")}
            rules={[{ required: true }]}
          >
            <Input data-e2e="doc-gate-defer-owner" />
          </Form.Item>
          <Form.Item
            name="deadline"
            label={t("docGate.deferDeadline", "截止日期")}
            rules={[{ required: true }]}
            initialValue={dayjs().add(7, "day")}
          >
            <DatePicker style={{ width: "100%" }} data-e2e="doc-gate-defer-deadline" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
