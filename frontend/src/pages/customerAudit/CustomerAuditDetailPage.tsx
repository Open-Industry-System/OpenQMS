import { useState, useEffect, useCallback } from "react";
import {
  Card, Button, Tag, Space, Form, Input, Select, DatePicker, App,
  Tabs, Table, Modal, Popconfirm, Row, Col, Statistic, Descriptions,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined,
  PlusOutlined, LinkOutlined, CheckOutlined, UploadOutlined,
  MinusCircleOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { AuditPlan, AuditFinding, User } from "../../types";
import {
  getAuditPlan, startAuditPlan, completeAuditPlan, cancelAuditPlan,
  listAuditFindings, createAuditFinding, updateAuditFinding,
  createCAPAFromFinding, transitionFinding, confirmCustomerFinding,
  confirmCustomerAudit,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";
import {
  useAuditModeMap,
  useAuditStatusColor,
  useAuditStatusMap,
  useCustomerTypeLabel,
  useFindingStatusColor,
  useFindingStatusMap,
  useFindingTypeMap,
} from "./useOptions";

const { Option } = Select;
const { Text } = Typography;

export default function CustomerAuditDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();
  const { canEdit, canApprove } = usePermission();

  const statusMap = useAuditStatusMap();
  const statusColor = useAuditStatusColor();
  const findingStatusMap = useFindingStatusMap();
  const findingStatusColor = useFindingStatusColor();
  const findingTypeMap = useFindingTypeMap();
  const auditModeMap = useAuditModeMap();
  const getCustomerTypeLabel = useCustomerTypeLabel();

  const [plan, setPlan] = useState<AuditPlan | null>(null);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [findingModalOpen, setFindingModalOpen] = useState(false);
  const [editingFinding, setEditingFinding] = useState<AuditFinding | null>(null);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [confirmFindingId, setConfirmFindingId] = useState<string | null>(null);
  const [confirmAttachments, setConfirmAttachments] = useState<{ file_name: string; file_url: string }[]>([]);
  const [planConfirmModalOpen, setPlanConfirmModalOpen] = useState(false);
  const [_users, setUsers] = useState<User[]>([]);
  const [findingForm] = Form.useForm();
  const [confirmForm] = Form.useForm();
  const [planConfirmForm] = Form.useForm();

  const fetchPlan = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [p, f] = await Promise.all([
        getAuditPlan(id),
        listAuditFindings({ audit_id: id, page_size: 1000 }),
      ]);
      setPlan(p);
      setFindings(f.items);
    } catch {
      message.error(t("messages.loadFailed"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);
  useEffect(() => { listUsers().then(setUsers).catch(() => {}); }, []);

  const handlePlanAction = async (action: string) => {
    if (!id) return;
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success(tc("messages.operationSuccess"));
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || tc("messages.operationFailed"));
    }
  };

  const handleCreateFinding = async () => {
    try {
      const values = await findingForm.validateFields();
      if (editingFinding) {
        await updateAuditFinding(editingFinding.finding_id, values);
        message.success(tc("messages.saveSuccess"));
      } else {
        await createAuditFinding({ ...values, audit_id: id });
        message.success(t("messages.createAuditSuccess"));
      }
      setFindingModalOpen(false);
      findingForm.resetFields();
      setEditingFinding(null);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || tc("messages.operationFailed"));
    }
  };

  const handleTransition = async (findingId: string, action: "start_progress" | "close") => {
    try {
      await transitionFinding(findingId, { action });
      message.success(tc("messages.operationSuccess"));
      fetchPlan();
    } catch (e: unknown) {
      message.error((e as Error).message || tc("messages.operationFailed"));
    }
  };

  const handleCustomerConfirm = async () => {
    try {
      const values = await confirmForm.validateFields();
      const date = values.confirmation_date.format("YYYY-MM-DD");
      const attachments = confirmAttachments
        .filter((a) => a.file_name.trim() && a.file_url.trim())
        .map((a) => ({ file_name: a.file_name.trim(), file_url: a.file_url.trim() }));
      if (confirmFindingId) {
        await confirmCustomerFinding(confirmFindingId, {
          confirmation_date: date,
          attachments,
        });
      }
      message.success(t("messages.confirmSuccess"));
      setConfirmModalOpen(false);
      confirmForm.resetFields();
      setConfirmFindingId(null);
      setConfirmAttachments([]);
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || t("messages.confirmFailed"));
    }
  };

  const handlePlanConfirm = async () => {
    try {
      const values = await planConfirmForm.validateFields();
      if (!id) return;
      const date = values.confirmation_date.format("YYYY-MM-DD");
      const attachments = (values.attachments || [])
        .filter((a: { file_name?: string; file_url?: string }) => a.file_name?.trim() && a.file_url?.trim())
        .map((a: { file_name: string; file_url: string }) => ({ file_name: a.file_name.trim(), file_url: a.file_url.trim() }));
      await confirmCustomerAudit(id, { confirmation_date: date, attachments });
      message.success(t("messages.auditConfirmSuccess"));
      setPlanConfirmModalOpen(false);
      planConfirmForm.resetFields();
      fetchPlan();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || t("messages.auditConfirmFailed"));
    }
  };

  const openEditFinding = (f: AuditFinding) => {
    setEditingFinding(f);
    findingForm.setFieldsValue({
      clause_ref: f.clause_ref,
      finding_type: f.finding_type,
      description: f.description,
      root_cause: f.root_cause,
      correction: f.correction,
      corrective_action: f.corrective_action,
      due_date: f.due_date ? dayjs(f.due_date) : undefined,
    });
    setFindingModalOpen(true);
  };

  const findingColumns = [
    { title: t("table.finding.clause"), dataIndex: "clause_ref", key: "clause_ref", width: 100, render: (v: string) => v || "-" },
    { title: t("table.finding.type"), dataIndex: "finding_type", key: "finding_type", width: 110,
      render: (v: string) => findingTypeMap[v] || v },
    { title: t("table.finding.description"), dataIndex: "description", key: "description", ellipsis: true },
    { title: t("table.finding.rootCause"), dataIndex: "root_cause", key: "root_cause", ellipsis: true, render: (v: string) => v || "-" },
    { title: t("table.finding.correctiveAction"), dataIndex: "corrective_action", key: "corrective_action", ellipsis: true, render: (v: string) => v || "-" },
    { title: t("table.finding.status"), dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <Tag color={findingStatusColor[v]}>{findingStatusMap[v]}</Tag> },
    { title: t("table.finding.customerConfirm"), dataIndex: "customer_confirmed", key: "customer_confirmed", width: 90,
      render: (v: boolean) => v ? <Tag color="success">{t("status.confirmed")}</Tag> : <Tag color="warning">{t("status.pendingConfirmation")}</Tag> },
    { title: t("table.finding.capa"), dataIndex: "capa_ref_id", key: "capa_ref_id", width: 80,
      render: (v: string) => v ? <Tag color="blue" style={{ cursor: "pointer" }} onClick={() => navigate(`/capa/${v}`)}>{tc("actions.view")}</Tag> : "-" },
    {
      title: t("table.operations"),
      key: "finding_actions",
      width: 280,
      render: (_: unknown, record: AuditFinding) => (
        <Space size="small">
          {canEdit('customer_audit') && <Button size="small" onClick={() => openEditFinding(record)}>{tc("actions.edit")}</Button>}
          {record.status === "open" && canEdit('customer_audit') && (
            <Button size="small" type="default" onClick={() => handleTransition(record.finding_id, "start_progress")}>{t("actions.startRectification")}</Button>
          )}
          {record.status === "in_progress" && canEdit('customer_audit') && (
            <Popconfirm title={t("messages.confirmCloseFinding")} onConfirm={() => handleTransition(record.finding_id, "close")}>
              <Button size="small" type="primary">{tc("actions.close")}</Button>
            </Popconfirm>
          )}
          {!record.customer_confirmed && canEdit('customer_audit') && (
            <Button size="small" icon={<CheckOutlined />}
              onClick={() => { setConfirmFindingId(record.finding_id); setConfirmAttachments([]); setConfirmModalOpen(true); }}>
              {t("actions.customerConfirm")}
            </Button>
          )}
          {!record.capa_ref_id && canEdit('customer_audit') && record.finding_type === "major_nc" && (
            <Popconfirm title={t("messages.confirmCreateCapa")} onConfirm={async () => {
              try { await createCAPAFromFinding(record.finding_id); message.success(t("messages.capaCreated")); fetchPlan(); }
              catch (e: unknown) { message.error((e as Error).message || t("messages.capaCreateFailed")); }
            }}>
              <Button size="small" icon={<LinkOutlined />}>CAPA</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  if (!plan) return null;

  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/customer-audits")}>{t("actions.backToList")}</Button>
      </div>

      <Card loading={loading}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{plan.plan_no} - {plan.customer_name}</h3>
          <Space>
            {plan.status === "planned" && canEdit('customer_audit') && (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handlePlanAction("start")}>{t("actions.startAudit")}</Button>
            )}
            {plan.status === "in_progress" && canApprove('customer_audit') && (
              <>
                <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handlePlanAction("complete")}>{t("actions.completeAudit")}</Button>
                <Button danger icon={<StopOutlined />} onClick={() => handlePlanAction("cancel")}>{tc("actions.cancel")}</Button>
              </>
            )}
            <Tag color={statusColor[plan.status]} style={{ fontSize: 14, padding: "4px 12px" }}>
              {statusMap[plan.status]}
            </Tag>
          </Space>
        </div>

        <Descriptions column={3} bordered size="small">
          <Descriptions.Item label={t("detail.audit.customerName")}>{plan.customer_name}</Descriptions.Item>
          <Descriptions.Item label={t("detail.audit.customerType")}>{getCustomerTypeLabel(plan.customer_type)}</Descriptions.Item>
          <Descriptions.Item label={t("detail.audit.auditMode")}>{plan.audit_mode ? auditModeMap[plan.audit_mode] : "-"}</Descriptions.Item>
          <Descriptions.Item label={t("detail.audit.auditScope")} span={2}>{plan.audit_scope}</Descriptions.Item>
          <Descriptions.Item label={t("detail.audit.plannedDate")}>{plan.planned_date}</Descriptions.Item>
          <Descriptions.Item label={t("detail.audit.auditCriteria")} span={3}>{plan.audit_criteria}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Tabs items={[
          {
            key: "findings",
            label: t("tabs.findingsWithCount", { count: findings.length }),
            children: (
              <>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
                  {canEdit('customer_audit') && (
                    <Button type="primary" icon={<PlusOutlined />}
                      onClick={() => { setEditingFinding(null); findingForm.resetFields(); setFindingModalOpen(true); }}>
                      {t("modal.newFinding")}
                    </Button>
                  )}
                </div>
                <Table
                  rowKey="finding_id"
                  columns={findingColumns}
                  dataSource={findings}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1200 }}
                />
              </>
            ),
          },
          {
            key: "confirmation",
            label: t("tabs.confirmation"),
            children: (
              <div>
                <Row gutter={16}>
                  <Col span={8}>
                    <Statistic
                      title={t("kpi.confirmedFindings")}
                      value={findings.filter((f) => f.customer_confirmed).length}
                      suffix={`/ ${findings.length}`}
                      valueStyle={{ color: "#52c41a" }}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title={t("kpi.pendingConfirmations")}
                      value={findings.filter((f) => !f.customer_confirmed && f.status !== "closed").length}
                      valueStyle={{ color: "#faad14" }}
                    />
                  </Col>
                  <Col span={8}>
                    <div style={{ marginTop: 32 }}>
                      {canEdit('customer_audit') && (
                        <Button type="primary" icon={<UploadOutlined />} onClick={() => setPlanConfirmModalOpen(true)}>
                          {t("actions.uploadConfirmationLetter")}
                        </Button>
                      )}
                    </div>
                  </Col>
                </Row>
                {plan.customer_confirmation_doc && plan.customer_confirmation_doc.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <Text strong>{t("sections.auditConfirmationAttachments")}</Text>
                    <ul>
                      {plan.customer_confirmation_doc.map((a, i) => (
                        <li key={i}>{a.file_name}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ),
          },
        ]} />
      </Card>

      {/* Create/Edit Finding Modal */}
      <Modal
        title={editingFinding ? t("modal.editFinding") : t("modal.newFinding")}
        open={findingModalOpen}
        onOk={handleCreateFinding}
        onCancel={() => { setFindingModalOpen(false); findingForm.resetFields(); setEditingFinding(null); }}
        width={640}
      >
        <Form form={findingForm} layout="vertical">
          <Form.Item name="finding_type" label={t("form.finding.findingType")} rules={[{ required: true }]}>
            <Select>
              <Option value="major_nc">{findingTypeMap.major_nc}</Option>
              <Option value="minor_nc">{findingTypeMap.minor_nc}</Option>
              <Option value="ofi">{findingTypeMap.ofi}</Option>
              <Option value="observation">{findingTypeMap.observation}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="clause_ref" label={t("form.finding.clauseRef")}>
            <Input placeholder={t("form.finding.clauseRefPlaceholder")} />
          </Form.Item>
          <Form.Item name="description" label={t("form.finding.description")} rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="root_cause" label={t("form.finding.rootCause")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="correction" label={t("form.finding.correction")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="corrective_action" label={t("form.finding.correctiveAction")}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="due_date" label={t("form.finding.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Customer Confirm Modal */}
      <Modal
        title={t("modal.customerConfirm")}
        open={confirmModalOpen}
        onOk={handleCustomerConfirm}
        onCancel={() => { setConfirmModalOpen(false); confirmForm.resetFields(); setConfirmFindingId(null); setConfirmAttachments([]); }}
      >
        <Form form={confirmForm} layout="vertical">
          <Form.Item name="confirmation_date" label={t("form.confirm.confirmationDate")} rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <div style={{ marginBottom: 8 }}>
            <Text strong>{t("sections.auditConfirmationAttachments")}</Text>
            {confirmAttachments.map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <Input
                  placeholder={t("form.attachments.fileName")}
                  value={a.file_name}
                  onChange={(e) => {
                    const next = [...confirmAttachments];
                    next[i].file_name = e.target.value;
                    setConfirmAttachments(next);
                  }}
                />
                <Input
                  placeholder={t("form.attachments.fileLink")}
                  value={a.file_url}
                  onChange={(e) => {
                    const next = [...confirmAttachments];
                    next[i].file_url = e.target.value;
                    setConfirmAttachments(next);
                  }}
                />
                <Button
                  icon={<MinusCircleOutlined />}
                  danger
                  onClick={() => setConfirmAttachments(confirmAttachments.filter((_, idx) => idx !== i))}
                />
              </div>
            ))}
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              style={{ marginTop: 8, width: "100%" }}
              onClick={() => setConfirmAttachments([...confirmAttachments, { file_name: "", file_url: "" }])}
            >
              {t("actions.addAttachment")}
            </Button>
          </div>
        </Form>
      </Modal>

      {/* Plan Confirm Modal */}
      <Modal
        title={t("modal.uploadConfirmationLetter")}
        open={planConfirmModalOpen}
        onOk={handlePlanConfirm}
        onCancel={() => { setPlanConfirmModalOpen(false); planConfirmForm.resetFields(); }}
      >
        <Form form={planConfirmForm} layout="vertical">
          <Form.Item name="confirmation_date" label={t("form.confirm.confirmationDate")} rules={[{ required: true }]} initialValue={dayjs()}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.List name="attachments">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <div key={key} style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                    <Form.Item {...restField} name={[name, "file_name"]} rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}>
                      <Input placeholder={t("form.attachments.fileName")} />
                    </Form.Item>
                    <Form.Item {...restField} name={[name, "file_url"]} rules={[{ required: true }]} style={{ flex: 1, marginBottom: 0 }}>
                      <Input placeholder={t("form.attachments.fileLink")} />
                    </Form.Item>
                    <Button icon={<MinusCircleOutlined />} danger onClick={() => remove(name)} />
                  </div>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} style={{ width: "100%" }} onClick={() => add()}>
                  {t("actions.addAttachment")}
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}
