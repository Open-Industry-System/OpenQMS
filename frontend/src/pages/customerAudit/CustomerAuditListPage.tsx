import { useState, useEffect, useCallback } from "react";
import {
  Card, Table, Button, Space, Modal, Form, Input, Select,
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
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";
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
      message.error(t("messages.loadFailed", "加载失败"));
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
      message.success(t("messages.createAuditSuccess", "创建成功"));
      setCreateOpen(false);
      form.resetFields();
      fetchData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || t("messages.createAuditFailed", "创建失败"));
    }
  };

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success(tc("messages.operationSuccess", "操作成功"));
      fetchData();
    } catch (e: unknown) {
      message.error((e as Error).message || tc("messages.operationFailed", "操作失败"));
    }
  };

  const columns = [
    { title: t("table.audit.no", "编号"), dataIndex: "plan_no", key: "plan_no", width: 130 },
    { title: t("table.audit.customerName", "客户名称"), dataIndex: "customer_name", key: "customer_name", width: 120 },
    { title: t("table.audit.customerType", "客户类型"), dataIndex: "customer_type", key: "customer_type", width: 90,
      render: (v: string) => getCustomerTypeLabel(v) },
    { title: t("table.audit.auditMode", "审核方式"), dataIndex: "audit_mode", key: "audit_mode", width: 80,
      render: (v: string) => v ? auditModeMap[v] || v : "-" },
    { title: t("table.audit.auditScope", "审核范围"), dataIndex: "audit_scope", key: "audit_scope", ellipsis: true },
    { title: t("table.audit.plannedDate", "计划日期"), dataIndex: "planned_date", key: "planned_date", width: 110,
      render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD") : "-" },
    { title: t("table.audit.status", "状态"), dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <StatusBadge status={statusColor[v]}>{statusMap[v]}</StatusBadge> },
    {
      title: t("table.operations", "操作"),
      key: "actions",
      width: 180,
      render: (_: unknown, record: AuditPlan) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/customer-audits/${record.audit_id}`)}>{tc("actions.view", "查看")}</Button>
          {record.status === "planned" && canEdit('customer_audit') && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction("start", record.audit_id)}>{t("actions.startAudit", "开始")}</Button>
          )}
          {record.status === "in_progress" && canApprove('customer_audit') && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleAction("complete", record.audit_id)}>{t("actions.completeAudit", "完成")}</Button>
              <Button size="small" danger icon={<StopOutlined />} onClick={() => handleAction("cancel", record.audit_id)}>{tc("actions.cancel", "取消")}</Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title={t("page.title", "客户审核管理")}
      subtitle={t("page.subtitle", "客户审核计划与发现项跟踪")}
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>{tc("actions.refresh", "刷新")}</Button>
          {canEdit('customer_audit') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("modal.newAudit", "新建客户审核")}</Button>
          )}
        </Space>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={3}><Card><Statistic title={t("kpi.total", "总计")} value={stats?.total_customer_audits ?? 0} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.planned", "已计划")} value={stats?.planned ?? 0} valueStyle={{ color: "#1890ff" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.inProgress", "进行中")} value={stats?.in_progress ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.completed", "已完成")} value={stats?.completed ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.openFindings", "未关闭发现项")} value={stats?.open_findings ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.majorNc", "严重不符合")} value={stats?.major_nc_count ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.confirmed", "已确认")} value={stats?.customer_confirmed_count ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title={t("kpi.pendingConfirmation", "待确认")} value={stats?.pending_confirmation_count ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
      </Row>

      <DataCard title={t("page.listTitle", "客户审核计划")} noPadding>
        <Table
          className="qf-table"
          rowKey="audit_id"
          columns={columns}
          dataSource={audits}
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (totalCount) => tc("pagination.total", `共 ${totalCount} 条`, { total: totalCount }),
          }}
        />
      </DataCard>

      <Modal
        title={t("modal.newAudit", "新建客户审核")}
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" label={t("form.audit.customerName", "客户名称")} rules={[{ required: true, message: t("form.audit.validation.customerNameRequired", "请输入客户名称") }]}>
            <Input placeholder={t("form.audit.customerNamePlaceholder", "如 Tesla、BYD")} />
          </Form.Item>
          <Form.Item name="customer_type" label={t("form.audit.customerType", "客户类型")} rules={[{ required: true, message: t("form.audit.validation.customerTypeRequired", "请选择客户类型") }]}>
            <Select placeholder={t("form.audit.selectCustomerType", "选择客户类型")}>
              {customerTypeOptions.map((opt) => (
                <Option key={opt.value} value={opt.value}>{opt.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="audit_mode" label={t("form.audit.auditMode", "审核方式")}>
            <Select placeholder={t("form.audit.selectAuditMode", "选择审核方式")} allowClear>
              <Option value="on_site">{auditModeMap.on_site}</Option>
              <Option value="remote">{auditModeMap.remote}</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label={t("form.audit.auditScope", "审核范围")} rules={[{ required: true, message: t("form.audit.validation.auditScopeRequired", "请输入审核范围") }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="audit_criteria" label={t("form.audit.auditCriteria", "审核准则")} rules={[{ required: true, message: t("form.audit.validation.auditCriteriaRequired", "请输入审核准则") }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="planned_date" label={t("form.audit.plannedDate", "计划日期")} rules={[{ required: true, message: t("form.audit.validation.plannedDateRequired", "请选择日期") }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="lead_auditor" label={t("form.audit.leadAuditor", "审核组长")}>
            <Select placeholder={t("form.audit.selectLeadAuditor", "选择审核组长")} allowClear>
              {users.map((u) => (
                <Option key={u.user_id} value={u.user_id}>{u.username}</Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
