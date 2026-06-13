import { useState, useEffect, useCallback } from "react";
import {
  Card, Table, Button, Space, Modal, Form, Input, Select,
  DatePicker, App, Row, Col, Statistic,
} from "antd";
import { PlusOutlined, ReloadOutlined, EyeOutlined, PlayCircleOutlined, CheckCircleOutlined, StopOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
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

const { Option } = Select;

const statusLabel: Record<string, string> = {
  planned: "已计划", in_progress: "进行中", completed: "已完成", cancelled: "已取消",
};

const statusVariant = (status: string): string => {
  switch (status) {
    case "completed": return "success";
    case "in_progress": return "warning";
    case "cancelled": return "info";
    default: return "info";
  }
};
const customerTypeLabel: Record<string, string> = {
  OEM: "OEM", "Tier 1": "Tier 1", "Tier 2": "Tier 2", 其他: "其他",
};
const auditModeLabel: Record<string, string> = {
  on_site: "现场", remote: "远程",
};

export default function CustomerAuditListPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();
  const { selected: currentProductLine } = useProductLineStore();
  const { canEdit, canApprove } = usePermission();

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
      message.error("加载失败");
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
        planned_date: values.planned_date.format("YYYY-MM-DD"),
        product_line_code: currentProductLine,
      });
      message.success("创建成功");
      setCreateOpen(false);
      form.resetFields();
      fetchData();
    } catch (e: unknown) {
      if (e && typeof e === "object" && "errorFields" in e) return;
      message.error((e as Error).message || "创建失败");
    }
  };

  const handleAction = async (action: string, id: string) => {
    try {
      if (action === "start") await startAuditPlan(id);
      else if (action === "complete") await completeAuditPlan(id);
      else if (action === "cancel") await cancelAuditPlan(id);
      message.success("操作成功");
      fetchData();
    } catch (e: unknown) {
      message.error((e as Error).message || "操作失败");
    }
  };

  const columns = [
    { title: "编号", dataIndex: "plan_no", key: "plan_no", width: 130 },
    { title: "客户名称", dataIndex: "customer_name", key: "customer_name", width: 120 },
    { title: "客户类型", dataIndex: "customer_type", key: "customer_type", width: 90,
      render: (v: string) => customerTypeLabel[v] || v },
    { title: "审核方式", dataIndex: "audit_mode", key: "audit_mode", width: 80,
      render: (v: string) => v ? auditModeLabel[v] || v : "-" },
    { title: "审核范围", dataIndex: "audit_scope", key: "audit_scope", ellipsis: true },
    { title: "计划日期", dataIndex: "planned_date", key: "planned_date", width: 110,
      render: (v: string) => v ? dayjs(v).format("YYYY-MM-DD") : "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90,
      render: (v: string) => <StatusBadge status={statusVariant(v)}>{statusLabel[v] || v}</StatusBadge> },
    {
      title: "操作", key: "actions", width: 180,
      render: (_: unknown, record: AuditPlan) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/customer-audits/${record.audit_id}`)}>查看</Button>
          {record.status === "planned" && canEdit('customer_audit') && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleAction("start", record.audit_id)}>开始</Button>
          )}
          {record.status === "in_progress" && canApprove('customer_audit') && (
            <>
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} onClick={() => handleAction("complete", record.audit_id)}>完成</Button>
              <Button size="small" danger icon={<StopOutlined />} onClick={() => handleAction("cancel", record.audit_id)}>取消</Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell
      title="客户审核管理"
      subtitle="客户审核计划与发现项跟踪"
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
          {canEdit('customer_audit') && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建客户审核</Button>
          )}
        </Space>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={3}><Card><Statistic title="总计" value={stats?.total_customer_audits ?? 0} /></Card></Col>
        <Col span={3}><Card><Statistic title="已计划" value={stats?.planned ?? 0} valueStyle={{ color: "#1890ff" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="进行中" value={stats?.in_progress ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="已完成" value={stats?.completed ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="未关闭发现项" value={stats?.open_findings ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="严重不符合" value={stats?.major_nc_count ?? 0} valueStyle={{ color: "#ff4d4f" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="已确认" value={stats?.customer_confirmed_count ?? 0} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={3}><Card><Statistic title="待确认" value={stats?.pending_confirmation_count ?? 0} valueStyle={{ color: "#faad14" }} /></Card></Col>
      </Row>

      <DataCard title="客户审核计划">
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
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      </DataCard>

      <Modal
        title="新建客户审核"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateOpen(false); form.resetFields(); }}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true, message: "请输入客户名称" }]}>
            <Input placeholder="如 Tesla、BYD" />
          </Form.Item>
          <Form.Item name="customer_type" label="客户类型" rules={[{ required: true, message: "请选择客户类型" }]}>
            <Select placeholder="选择客户类型">
              <Option value="OEM">OEM</Option>
              <Option value="Tier 1">Tier 1</Option>
              <Option value="Tier 2">Tier 2</Option>
              <Option value="其他">其他</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_mode" label="审核方式">
            <Select placeholder="选择审核方式" allowClear>
              <Option value="on_site">现场</Option>
              <Option value="remote">远程</Option>
            </Select>
          </Form.Item>
          <Form.Item name="audit_scope" label="审核范围" rules={[{ required: true, message: "请输入审核范围" }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="audit_criteria" label="审核准则" rules={[{ required: true, message: "请输入审核准则" }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="planned_date" label="计划日期" rules={[{ required: true, message: "请选择日期" }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="lead_auditor" label="审核组长">
            <Select placeholder="选择审核组长" allowClear>
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
