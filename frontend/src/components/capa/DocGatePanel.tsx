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
import { useCapaChildRequests } from "./useCapaViewRequests";
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
import { tr } from "../../i18n/tr";

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
  const requests = useCapaChildRequests(capaId, canEdit);
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

  useEffect(() => {
    setGenerating(false); setAuditing(false); setAdvancing(false); setDeferOpen(false); deferForm.resetFields();
  }, [requests, deferForm]);

  const load = useCallback(async () => {
    if (analysisProp !== undefined) return; // test mode
    const request = requests.begin();
    if (!request.current()) return;
    setLoading(true);
    try {
      try {
        const a = await getDocGateImpact(capaId, request.signal);
        if (!request.current()) return;
        setAnalysis(a);
        if (a.status === "failed" && a.error?.includes("LLM")) setBlocked(true);
      } catch (e: unknown) {
        if (!request.current()) return;
        const ax = e as { response?: { status?: number } };
        if (ax?.response?.status === 404) setAnalysis(null);
        else throw e;
      }
      const d = await getDocGateDecision(capaId, request.signal);
      if (!request.current()) return;
      setDecision(d);
      const au = await getDocGateAudit(capaId, request.signal);
      if (!request.current()) return;
      setAudits(au.audits || []);
    } catch {
      /* silent: empty state is valid */
    } finally {
      if (request.current()) setLoading(false);
      request.finish();
    }
  }, [capaId, analysisProp, requests]);

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
    const request = requests.begin();
    if (!request.current()) return;
    setGenerating(true);
    setBlocked(false);
    try {
      const result = await docGateImpact(capaId, request.signal);
      if (!request.current()) return;
      setAnalysis(result as DocGateAnalysis);
      if (result.status === "running") {
        message.info(t("docGate.retryAfter"));
      } else if (result.status === "done") {
        message.success(t("docGate.generateDone"));
      } else if (result.status === "failed") {
        message.error(result.error || t("docGate.generateFailed"));
      }
      await load();
      if (!request.current()) return;
    } catch (e: unknown) {
      if (!request.current()) return;
      if (isBlockedError(e)) {
        setBlocked(true);
        setAnalysis({ status: "failed", error: tr("Kein LLM konfiguriert", "LLM not configured"), is_current: false });
      } else {
        message.error(errMsg(e));
      }
    } finally {
      if (request.current()) setGenerating(false);
      request.finish();
    }
  };

  const handleAudit = async () => {
    const request = requests.begin();
    if (!request.current()) return;
    setAuditing(true);
    try {
      const result = await runDocGateAudit(capaId, request.signal);
      if (!request.current()) return;
      setAudits(result.audits || []);
      setDecision({ decision: result.decision as DocGateDecision["decision"] });
      message.success(
        result.decision === "passed"
          ? t("docGate.auditPassed")
          : t("docGate.auditBlocked"),
      );
      await load();
      if (!request.current()) return;
    } catch (e: unknown) {
      if (!request.current()) return;
      message.error(errMsg(e));
    } finally {
      if (request.current()) setAuditing(false);
      request.finish();
    }
  };

  const handleConfirmEmpty = async () => {
    const request = requests.begin();
    if (!request.current()) return;
    try {
      const result = await confirmNoAffected(capaId, request.signal);
      if (!request.current()) return;
      setDecision({
        decision: result.decision as DocGateDecision["decision"],
        no_affected_confirmed: result.no_affected_confirmed,
      });
      message.success(t("docGate.confirmEmptyDone"));
      await load();
      if (!request.current()) return;
    } catch (e: unknown) {
      if (!request.current()) return;
      message.error(errMsg(e));
    } finally { request.finish(); }
  };

  const handleDefer = async () => {
    const request = requests.begin();
    if (!request.current()) return;
    try {
      const values = await deferForm.validateFields();
      if (!request.current()) return;
      await recordDocGateDefer(capaId, {
        reason: values.reason,
        owner_id: values.owner_id,
        deadline: values.deadline.format("YYYY-MM-DD"),
      }, request.signal);
      if (!request.current()) return;
      message.success(t("docGate.deferDone"));
      setDeferOpen(false);
      deferForm.resetFields();
      await load();
      if (!request.current()) return;
    } catch (e: unknown) {
      if (!request.current()) return;
      if ((e as { errorFields?: unknown }).errorFields) return;
      message.error(errMsg(e));
    } finally { request.finish(); }
  };

  const handleAdvance = async () => {
    const request = requests.begin();
    if (!request.current()) return;
    setAdvancing(true);
    try {
      await advanceCAPA(capaId, { target_state: "D8_APPROVAL_PENDING" }, request.signal);
      if (!request.current()) return;
      await onAdvanced?.();
      if (!request.current()) return;
      message.success(t("docGate.advanceDone"));
    } catch (e: unknown) {
      if (!request.current()) return;
      const msg = errMsg(e);
      if (["文档已变更", "Dokument wurde", "Document changed"].some((m) => msg.includes(m))) {
        message.error(t("docGate.docChanged"));
      } else if (["分析输入已变更", "Analyseeingaben haben sich geändert", "Analysis inputs changed"].some((m) => msg.includes(m))) {
        message.error(t("docGate.inputChanged"));
      } else {
        message.error(msg);
      }
      await load();
      if (!request.current()) return;
    } finally {
      if (request.current()) setAdvancing(false);
      request.finish();
    }
  };

  const affectedDocs: DocGateAffectedDoc[] = analysis?.affected_docs || [];
  const isDone = analysis?.status === "done";
  const isEmpty = isDone && affectedDocs.length === 0;
  const decisionPassed = decision?.decision === "passed";

  const statusTag = () => {
    if (!analysis) return <Tag data-e2e="doc-gate-status">{t("docGate.noAnalysis")}</Tag>;
    if (analysis.status === "running") return <Tag color="processing" data-e2e="doc-gate-status">running</Tag>;
    if (analysis.status === "done") return <Tag color="success" data-e2e="doc-gate-status">done</Tag>;
    if (analysis.status === "failed") return <Tag color="error" data-e2e="doc-gate-status">failed</Tag>;
    return <Tag data-e2e="doc-gate-status">{analysis.status}</Tag>;
  };

  return (
    <Card
      title={t("docGate.title")}
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
            message={t("docGate.blocked")}
          />
        )}
        {analysis?.status === "failed" && !blocked && (
          <Alert
            type="error"
            showIcon
            data-e2e="doc-gate-failed-banner"
            message={t("docGate.failed")}
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
              {analysis ? t("docGate.regenerate") : t("docGate.generate")}
            </Button>
          )}
          {canEdit && isDone && (
            <Button
              icon={<ReloadOutlined />}
              loading={generating}
              onClick={handleGenerate}
              data-e2e="doc-gate-regenerate"
            >
              {t("docGate.regenerate")}
            </Button>
          )}
        </Space>

        {/* Zone 2: Affected docs list */}
        {isDone && (
          <div data-e2e="doc-gate-affected-list">
            <Text strong>{t("docGate.affectedTitle")}</Text>
            {isEmpty ? (
              <Alert
                type="info"
                style={{ marginTop: 8 }}
                data-e2e="doc-gate-empty-list"
                message={t("docGate.emptyList")}
                action={
                  canEdit ? (
                    <Button size="small" onClick={handleConfirmEmpty} data-e2e="doc-gate-confirm-empty">
                      {t("docGate.confirmEmpty")}
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
                  { title: t("docGate.colType"), dataIndex: "doc_type", width: 120 },
                  { title: t("docGate.colName"), dataIndex: "doc_name" },
                  {
                    title: t("docGate.colKeyPoints"),
                    dataIndex: "key_points",
                    render: (kps: unknown[]) => kps?.length ?? 0,
                  },
                  {
                    title: t("docGate.colSuggestion"),
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
                  {t("docGate.runAudit")}
                </Button>
              )}
              {canEdit && decision?.decision === "blocked" && (
                <Button
                  icon={<ClockCircleOutlined />}
                  onClick={() => setDeferOpen(true)}
                  data-e2e="doc-gate-defer-btn"
                >
                  {t("docGate.defer")}
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
                expandable={{
                  expandedRowRender: (r: DocGateAuditRow) => (
                    <div data-e2e={`doc-gate-coverage-${r.doc_id}`}>
                      {(r.coverage || []).map((raw, i) => {
                        const c = raw as {
                          covered?: boolean;
                          evidence?: string;
                          key_point?: {
                            expected_action?: string;
                            target_kind?: string;
                            target_key?: string;
                            field?: string;
                            add_anchor?: {
                              parent_node_id?: string;
                              node_type?: string;
                              business_key?: string;
                            };
                          };
                        };
                        const kp = c.key_point || {};
                        const label = kp.target_key
                          ? `${kp.expected_action}/${kp.target_kind}/${kp.target_key}${kp.field ? `:${kp.field}` : ""}`
                          : kp.add_anchor
                            ? `add/${kp.target_kind}/${kp.add_anchor.parent_node_id}/${kp.add_anchor.node_type}/${kp.add_anchor.business_key}`
                            : `${kp.expected_action}/${kp.target_kind}`;
                        return (
                          <div key={i}>
                            <Tag color={c.covered ? "success" : "error"}>
                              {c.covered ? "covered" : "miss"}
                            </Tag>{" "}
                            {label}
                            {c.evidence ? ` — ${c.evidence}` : ""}
                          </div>
                        );
                      })}
                    </div>
                  ),
                  rowExpandable: (r) => (r.coverage?.length ?? 0) > 0,
                }}
                columns={[
                  { title: t("docGate.colName"), dataIndex: "doc_name" },
                  {
                    title: t("docGate.colStatus"),
                    dataIndex: "status",
                    render: (s: string) => (
                      <Tag color={s === "passed" ? "success" : s === "incomplete" ? "warning" : "default"}>
                        {s}
                      </Tag>
                    ),
                  },
                  {
                    title: t("docGate.colVersion"),
                    render: (_: unknown, r: DocGateAuditRow) => {
                      const before = r.version_before as { major?: number; minor?: number } | null | undefined;
                      const after = r.version_after as { major?: number; minor?: number } | null | undefined;
                      const b = before && before.major != null ? `v${before.major}.${before.minor}` : "—";
                      const a = after && after.major != null ? `v${after.major}.${after.minor}` : "—";
                      return `${b} → ${a}`;
                    },
                  },
                  {
                    title: t("docGate.colCoverage"),
                    render: (_: unknown, r: DocGateAuditRow) =>
                      `${r.covered_count}/${r.total_count}`,
                  },
                  {
                    title: t("docGate.colBump"),
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
          <Text strong>{t("docGate.decisionTitle")}: </Text>
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
            <Tag data-e2e="doc-gate-decision">{t("docGate.noDecision")}</Tag>
          )}
          {decision?.no_affected_confirmed && (
            <Tag color="blue">{t("docGate.emptyConfirmed")}</Tag>
          )}
          {decision?.defer_reason && (
            <Paragraph type="secondary" style={{ marginTop: 4 }}>
              {t("docGate.deferInfo")}: {decision.defer_reason}
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
                {t("docGate.advance")}
              </Button>
            </div>
          )}
        </div>
      </Space>

      <Modal
        title={t("docGate.deferTitle")}
        open={deferOpen}
        onOk={handleDefer}
        onCancel={() => setDeferOpen(false)}
        okText={t("docGate.deferConfirm")}
        data-e2e="doc-gate-defer-modal"
      >
        <Form form={deferForm} layout="vertical">
          <Form.Item
            name="reason"
            label={t("docGate.deferReason")}
            rules={[{ required: true, message: t("docGate.deferReasonRequired") }]}
          >
            <TextArea rows={3} data-e2e="doc-gate-defer-reason" />
          </Form.Item>
          <Form.Item
            name="owner_id"
            label={t("docGate.deferOwner")}
            rules={[{ required: true }]}
          >
            <Input data-e2e="doc-gate-defer-owner" />
          </Form.Item>
          <Form.Item
            name="deadline"
            label={t("docGate.deferDeadline")}
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
