import { useState, useEffect, useCallback } from "react";
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input, Select,
  DatePicker, App, Row, Col, Statistic,
} from "antd";
import { PlusOutlined, ReloadOutlined, EyeOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import type { AuditPlan, CustomerAuditStats } from "../../types";
import {
  listCustomerAudits, createCustomerAudit, getCustomerAuditStats,
  startAuditPlan, completeAuditPlan, cancelAuditPlan,
} from "../../api/audit";
import { listUsers } from "../../api/auth";
import dayjs from "dayjs";
import {
  useAuditModeMap,
  useAuditStatusColor,
  useAuditStatusMap,
  useCustomerTypeLabel,
  useCustomerTypeOptions,
} from "./useOptions";

const { Option } = Select;

export default function CustomerAuditListPage() {
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();
  const { selected: currentProductLine } = useProductLineStore();
  const { canEdit, canApprove } = usePermission();

  const statusMap = useAuditStatusMap();
  const statusColor = useAuditStatusColor();
  const auditModeMap = useAuditModeMap();
  const customerTypeOptions = useCustomerTypeOptions();
  const getCustomerTypeLabel = useCustomerTypeLabel();

  const [audits, setAudits] = useState<AuditPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<CustomerAuditStats | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm();
  const [users, setUsers] = useState<{ user_id: string; username: string }[]>([]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [auditsResp, statsResp] = await Promise.all([
        listCustomerAudits({ page, page_size: 20, product_line_code: currentProductLine }),
        getCustomerAuditStats({ product_line_code: currentProductLine || undefined }),
      ]);
      setAudits(auditsResp.items);
      setTotal(auditsResp.total);
      setStats(statsResp);
    } catch {
      message.error(t("messages.loadFailed"));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, currentProductLine]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    listUsers().then(setUsers).catch(() => {});
  }, []);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      await createCustomerAudit({
        ...values,
        customer_type: values.customer_type,
        planned_date: values.planned_date.format("YYYY-MM-DD"),
        product_line_code: currentProductLine,
      });
      message.success(t("messages.createAuditSuccess"));
      setCreateOpen(false);
      form.resetFields();
      fetchData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || t("messages.createAuditFailed"));
    }
  };

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success(tc("messages.operationSuccess"));
      fetchData();
    } catch (e: unknown) {
      message.error((e as Error).message || tc("messages.operationFailed"));
    }
  };

  const columns = [
    { title: t("table.audit.no"), dataIndex: "plan_no", key: "plan_no", width: 130 },
    { title: t("table.audit.customerName"), dataIndex: "customer_name", key: "customer_name", width: 120 },
    { title: t("table.audit.customerType"), dataIndex: "customer_type", key: "customer_type", width: 90,
      render: (v: string) => getCustomerTypeLabel(v) },
    { title: t("table.audit.auditMode"), dataIndex: "audit_mode", key: "audit_mode", width: 80,
      render: (v: string) => v ? auditModeMap[v] || v : "-" },
    { title: t("table.audit.auditScope"), dataIndex: "audit_scope", key: "audit_scope", ellipsis: true },
    { title: t("table.audit.plannedDate"), dataIndex: "planned_date", key: "planned_date", width: 110,
      render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD") : "-" },
    { title: t("table.audit.status"), dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <Tag color={statusColor[v]}>{statusMap[v]}</Tag> },
    {
      title: t("table.operations"),
      key: "actions",
      width: 180,
      render: (_: unknown, record: AuditPlan) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/customer-audits/${record.audit_id}`)}>{tc("actions.view")}</Button>
          {record.status === "planned" && canEdit('customer_audit') && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction("start", record.audit_id)}>{t("actions.startAudit")}</Button>
          )}
          {record.status === "in_progress" && canApprove('customer_audit') && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleAction("complete", record.audit_id)}>{t("actions.completeAudit")}</Button>
              <Button size="small" danger icon={<StopOutlined />} onClick={() => handleAction("cancel", record.audit_id)}>{tc("actions.cancel")}</Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={3}><Card><Statistic title={t("kpi.total")} value={stats?.total_customer_audits ?? 0} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.planned")} value={stats?.planned ?? 0} valueStyle={{ color: "#1890ff" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.inProgress")} value={stats?.in_progress ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.completed")} value={stats?.completed ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.openFindings")} value={stats?.open_findings ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.majorNc")} value={stats?.major_nc_count ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.confirmed")} value={stats?.customer_confirmed_count ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.pendingConfirmation")} value={stats?.pending_confirmation_count ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
      </Row>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{t("page.title")}</h3>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>{tc("actions.refresh")}</Button>
            {canEdit('customer_audit') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("modal.newAudit")}</Button>
            )}
          </Space>
        </div>

        <Table
          rowKey="audit_id"
          columns={columns}
          dataSource={audits}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (totalCount) => tc("pagination.total", { total: totalCount }),
          }}
        />
      </Card>

      <Modal
        title={t("modal.newAudit")}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" label={t("form.audit.customerName")} rules={[{ required: true, message: t("form.audit.validation.customerNameRequired") }]}>
            <Input placeholder={t("form.audit.customerNamePlaceholder")} />
          </Form.Item>
          <Form.Item name="customer_type" label={t("form.audit.customerType")} rules={[{ required: true, message: t("form.audit.validation.customerTypeRequired") }]}>
            <Select placeholder={t("form.audit.selectCustomerType")}>
              {customerTypeOptions.map((opt) => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="audit_mode" label={t("form.audit.auditMode")}>
            <Select placeholder={t("form.audit.selectAuditMode")} allowClear>
              <Option value="on_site">{auditModeMap.on_site}</Option>
              <Option value="remote">{auditModeMap.remote}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label={t("form.audit.auditScope")} rules={[{ required: true, message: t("form.audit.validation.auditScopeRequired") }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="audit_criteria" label={t("form.audit.auditCriteria")} rules={[{ required: true, message: t("form.audit.validation.auditCriteriaRequired") }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="planned_date" label={t("form.audit.plannedDate")} rules={[{ required: true, message: t("form.audit.validation.plannedDateRequired") }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="lead_auditor" label={t("form.audit.leadAuditor")}>
            <Select placeholder={t("form.audit.selectLeadAuditor")} allowClear>
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>{u.username}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
