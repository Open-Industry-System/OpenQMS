import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  App,
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  createComplaint,
  createCustomer,
  createRMARecord,
  createSCARFromComplaint,
  createSCARFromRMA,
  getCustomerQualityDashboard,
  listComplaints,
  listCustomers,
  listRMARecords,
  listShipments,
  createShipment,
  updateShipment,
  deleteShipment,
} from "../../api/customerQuality";
import { listSuppliers } from "../../api/supplier";
import type { Customer, CustomerComplaint, CustomerQualityDashboard, RMARecord, ShipmentRecord } from "../../types";
import type { Supplier } from "../../types";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";

const { Title, Text } = Typography;

const riskColor: Record<string, string> = { red: "red", yellow: "gold", green: "green" };
const severityColor: Record<string, string> = { "致命": "red", "严重": "orange", "一般": "blue", "轻微": "default" };
const complaintStatusLabel: Record<string, string> = {
  open: "已接收",
  investigating: "调查中",
  responded: "已回复",
  closed: "已关闭",
  cancelled: "已取消",
};
const rmaStatusLabel: Record<string, string> = {
  open: "已登记",
  analysis: "分析中",
  action_pending: "等待措施",
  closed: "已关闭",
  cancelled: "已取消",
};

export default function CustomerQualityPage() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const productLine = useProductLineStore((s) => s.selected);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [complaints, setComplaints] = useState<CustomerComplaint[]>([]);
  const [rmas, setRmas] = useState<RMARecord[]>([]);
  const [dashboard, setDashboard] = useState<CustomerQualityDashboard | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mineOnly, setMineOnly] = useState(false);
  const [customerModalOpen, setCustomerModalOpen] = useState(false);
  const [complaintModalOpen, setComplaintModalOpen] = useState(false);
  const [rmaModalOpen, setRmaModalOpen] = useState(false);
  const [customerForm] = Form.useForm();
  const [complaintForm] = Form.useForm();
  const [rmaForm] = Form.useForm();
  const [searchParams] = useSearchParams();

  // SCAR creation state
  const [scarModalOpen, setScarModalOpen] = useState(false);
  const [scarTarget, setScarTarget] = useState<
    | { type: "complaint"; record: CustomerComplaint }
    | { type: "rma"; record: RMARecord }
    | null
  >(null);
  const [scarForm] = Form.useForm();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  // Shipment records state
  const [shipments, setShipments] = useState<ShipmentRecord[]>([]);
  const [shipmentTotal, setShipmentTotal] = useState(0);
  const [shipmentPage, setShipmentPage] = useState(1);
  const [shipmentLoading, setShipmentLoading] = useState(false);
  const [shipmentModalOpen, setShipmentModalOpen] = useState(false);
  const [shipmentForm] = Form.useForm();
  const [editingShipment, setEditingShipment] = useState<ShipmentRecord | null>(null);

  const canEdit = user?.role !== "viewer";
  const assigneeId = mineOnly ? user?.user_id : undefined;

  const loadData = async () => {
    setLoading(true);
    try {
      const customerRes = await listCustomers({ page: 1, page_size: 100 });
      const effectiveCustomerId = selectedCustomerId || customerRes.items[0]?.customer_id || null;
      setCustomers(customerRes.items);
      setSelectedCustomerId(effectiveCustomerId);

      const statusParam = searchParams.get("status");

      const [complaintRes, rmaRes, dashboardRes] = await Promise.all([
        listComplaints({
          page: 1,
          page_size: 100,
          product_line: productLine || undefined,
          customer_id: effectiveCustomerId || undefined,
          assignee_id: assigneeId,
          status: statusParam || undefined,
        }),
        listRMARecords({
          page: 1,
          page_size: 100,
          product_line: productLine || undefined,
          customer_id: effectiveCustomerId || undefined,
          assignee_id: assigneeId,
        }),
        getCustomerQualityDashboard({
          product_line: productLine || undefined,
          customer_id: effectiveCustomerId || undefined,
        }),
      ]);
      setComplaints(complaintRes.items);
      setRmas(rmaRes.items);
      setDashboard(dashboardRes);
    } catch {
      message.error("客户质量数据加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [productLine, mineOnly, selectedCustomerId]);

  // Load suppliers for SCAR modal
  useEffect(() => {
    listSuppliers({ page_size: 200 }).then((r) => setSuppliers(r.items)).catch(() => {});
  }, []);

  // Fetch shipment records when customer selected
  const fetchShipments = async () => {
    if (!selectedCustomerId) return;
    setShipmentLoading(true);
    try {
      const resp = await listShipments(selectedCustomerId, { page: shipmentPage, page_size: 10 });
      setShipments(resp.items);
      setShipmentTotal(resp.total);
    } catch {
      message.error("加载发运记录失败");
    } finally {
      setShipmentLoading(false);
    }
  };
  useEffect(() => { if (selectedCustomerId) fetchShipments(); }, [selectedCustomerId, shipmentPage]);

  // SCAR handlers
  const handleCreateSCAR = (type: "complaint" | "rma", record: CustomerComplaint | RMARecord) => {
    if (type === "complaint") {
      const c = record as CustomerComplaint;
      setScarTarget({ type, record: c });
      scarForm.setFieldsValue({ supplier_id: (c as CustomerComplaint & { supplier_id?: string }).supplier_id, description: c.defect_desc });
    } else {
      const r = record as RMARecord;
      setScarTarget({ type, record: r });
      scarForm.setFieldsValue({ description: `${r.defect_type || "RMA"}${r.analysis_result ? " — " + r.analysis_result : ""}` });
    }
    setScarModalOpen(true);
  };

  const handleConfirmSCAR = async () => {
    const values = await scarForm.validateFields();
    if (!scarTarget) return;
    try {
      const data = { ...values, due_date: values.due_date?.format("YYYY-MM-DD") };
      if (scarTarget.type === "complaint") {
        await createSCARFromComplaint(scarTarget.record.complaint_id, data);
      } else {
        await createSCARFromRMA(scarTarget.record.rma_id, data);
      }
      message.success("SCAR 创建成功");
      setScarModalOpen(false);
      scarForm.resetFields();
      setScarTarget(null);
      loadData();
    } catch {
      message.error("SCAR 创建失败");
    }
  };

  // Shipment handlers
  const handleSubmitShipment = async () => {
    const values = await shipmentForm.validateFields();
    const payload = {
      shipment_date: values.shipment_date.format("YYYY-MM-DD"),
      quantity: values.quantity,
      batch_no: values.batch_no,
      destination: values.destination,
      notes: values.notes,
      product_line_code: productLine || undefined,
    };
    try {
      if (editingShipment) {
        await updateShipment(selectedCustomerId!, editingShipment.shipment_id, payload);
        message.success("更新成功");
      } else {
        await createShipment(selectedCustomerId!, payload);
        message.success("创建成功");
      }
      setShipmentModalOpen(false);
      shipmentForm.resetFields();
      setEditingShipment(null);
      fetchShipments();
    } catch {
      message.error(editingShipment ? "更新失败" : "创建失败");
    }
  };

  const handleDeleteShipment = async (record: ShipmentRecord) => {
    Modal.confirm({
      title: "确认删除",
      content: `删除 ${record.shipment_date} 的发运记录？`,
      onOk: async () => {
        try {
          await deleteShipment(selectedCustomerId!, record.shipment_id);
          message.success("删除成功");
          fetchShipments();
        } catch { message.error("删除失败"); }
      },
    });
  };

  const selectedCustomer = useMemo(
    () => customers.find((item) => item.customer_id === selectedCustomerId) || null,
    [customers, selectedCustomerId]
  );

  const handleCreateCustomer = async (values: {
    customer_code: string;
    name: string;
    segment?: string;
    contact_name?: string;
    contact_email?: string;
    contact_phone?: string;
    ppm_target?: number;
    annual_shipment_qty?: number;
    notes?: string;
  }) => {
    try {
      const customer = await createCustomer({ ...values, csr_list: [] });
      message.success("客户创建成功");
      setCustomerModalOpen(false);
      customerForm.resetFields();
      setSelectedCustomerId(customer.customer_id);
      await loadData();
    } catch {
      message.error("客户创建失败");
    }
  };

  const handleCreateComplaint = async (values: Record<string, unknown>) => {
    if (!selectedCustomerId || !productLine) {
      message.warning("请先选择客户和产品线");
      return;
    }
    try {
      const complaint = await createComplaint({
        complaint_no: values.complaint_no as string,
        product_line_code: productLine,
        customer_id: selectedCustomerId,
        product_id: (values.product_id as string) || null,
        batch_no: (values.batch_no as string) || null,
        serial_number: (values.serial_number as string) || null,
        category: values.category as CustomerComplaint["category"],
        severity: values.severity as CustomerComplaint["severity"],
        defect_desc: values.defect_desc as string,
        impact_qty: Number(values.impact_qty || 0),
        occurred_date: values.occurred_date ? (values.occurred_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
        received_date: values.received_date ? (values.received_date as dayjs.Dayjs).format("YYYY-MM-DD") : dayjs().format("YYYY-MM-DD"),
        due_date: values.due_date ? (values.due_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
        status: "open",
        fmea_ref_id: null,
        capa_ref_id: null,
        has_rma: false,
        preliminary_response: null,
        root_cause: null,
        corrective_action: null,
        attachments: [],
        assignee_id: user?.user_id || null,
        supplier_responsibility: Boolean(values.supplier_responsibility),
        scar_ref_id: null,
      });
      message.success("客诉创建成功");
      setComplaintModalOpen(false);
      complaintForm.resetFields();
      navigate(`/customer-quality/complaints/${complaint.complaint_id}`);
    } catch {
      message.error("客诉创建失败");
    }
  };

  const handleCreateRMA = async (values: Record<string, unknown>) => {
    if (!selectedCustomerId || !productLine) {
      message.warning("请先选择客户和产品线");
      return;
    }
    try {
      const rma = await createRMARecord({
        rma_no: values.rma_no as string,
        product_line_code: productLine,
        customer_id: selectedCustomerId,
        complaint_id: (values.complaint_id as string) || null,
        product_id: (values.product_id as string) || null,
        batch_no: (values.batch_no as string) || null,
        serial_number: (values.serial_number as string) || null,
        return_qty: Number(values.return_qty || 0),
        defect_type: values.defect_type as string,
        responsibility: (values.responsibility as RMARecord["responsibility"]) || null,
        analysis_result: null,
        corrective_action: null,
        status: "open",
        fmea_ref_id: null,
        capa_ref_id: null,
        scar_ref_id: null,
        attachments: [],
        assignee_id: user?.user_id || null,
        tracking_number: (values.tracking_number as string) || null,
        received_date: values.received_date ? (values.received_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
      });
      message.success("RMA 创建成功");
      setRmaModalOpen(false);
      rmaForm.resetFields();
      navigate(`/customer-quality/rma/${rma.rma_id}`);
    } catch {
      message.error("RMA 创建失败");
    }
  };

  const customerColumns = [
    {
      title: "风险",
      dataIndex: "customer_id",
      width: 70,
      render: (id: string) => {
        const summary = dashboard?.customers.find((item) => item.customer_id === id);
        return <Tag color={riskColor[summary?.risk_light || "green"]}>{summary?.risk_light || "green"}</Tag>;
      },
    },
    { title: "客户编号", dataIndex: "customer_code", width: 110 },
    { title: "客户名称", dataIndex: "name", ellipsis: true },
  ];

  const complaintColumns = [
    { title: "编号", dataIndex: "complaint_no", width: 130 },
    {
      title: "严重度",
      dataIndex: "severity",
      width: 90,
      render: (value: string) => <Tag color={severityColor[value]}>{value}</Tag>,
    },
    { title: "批次", dataIndex: "batch_no", width: 130, render: (value: string | null) => value || "-" },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{complaintStatusLabel[value] || value}</Tag>,
    },
    { title: "期限", dataIndex: "due_date", width: 110, render: (value: string | null) => value || "-" },
    { title: "描述", dataIndex: "defect_desc", ellipsis: true },
    {
      title: "操作",
      width: 140,
      render: (_: unknown, record: CustomerComplaint) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/customer-quality/complaints/${record.complaint_id}`)}>处理</Button>
          {record.supplier_responsibility && !record.scar_ref_id && (
            <Button size="small" onClick={() => handleCreateSCAR("complaint", record)}>创建SCAR</Button>
          )}
          {record.scar_ref_id && (
            <Button size="small" type="link" onClick={() => navigate(`/scars/${record.scar_ref_id}`)}>查看SCAR</Button>
          )}
        </Space>
      ),
    },
  ];

  const rmaColumns = [
    { title: "编号", dataIndex: "rma_no", width: 130 },
    { title: "退货数", dataIndex: "return_qty", width: 80 },
    { title: "批次", dataIndex: "batch_no", width: 130, render: (value: string | null) => value || "-" },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{rmaStatusLabel[value] || value}</Tag>,
    },
    { title: "责任", dataIndex: "responsibility", width: 120, render: (value: string | null) => value || "-" },
    { title: "不良类型", dataIndex: "defect_type", ellipsis: true },
    {
      title: "操作",
      width: 140,
      render: (_: unknown, record: RMARecord) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/customer-quality/rma/${record.rma_id}`)}>分析</Button>
          {record.responsibility === "supplier" && !record.scar_ref_id && (
            <Button size="small" onClick={() => handleCreateSCAR("rma", record)}>创建SCAR</Button>
          )}
          {record.scar_ref_id && (
            <Button size="small" type="link" onClick={() => navigate(`/scars/${record.scar_ref_id}`)}>查看SCAR</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>客户质量</Title>
        <Space>
          <Text>我的待办</Text>
          <Switch checked={mineOnly} onChange={setMineOnly} />
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          {canEdit && <Button icon={<PlusOutlined />} onClick={() => setCustomerModalOpen(true)}>新建客户</Button>}
        </Space>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
        <Card><Statistic title="客户数" value={customers.length} /></Card>
        <Card><Statistic title="开放客诉" value={dashboard?.kpi.open_complaint_count || 0} /></Card>
        <Card><Statistic title="超期客诉" value={dashboard?.kpi.overdue_count || 0} valueStyle={{ color: "#cf1322" }} /></Card>
        <Card><Statistic title="RMA 数" value={dashboard?.kpi.rma_count || 0} /></Card>
        <Card><Statistic title="影响数量" value={dashboard?.kpi.impact_qty || 0} /></Card>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
        <Card size="small">
          <Statistic
            title="SPC CPK"
            value={dashboard?.spc_cpks?.length ? dashboard.spc_cpks.map((c) => c.cpk ?? "-").join(" / ") : "-"}
            valueStyle={{ fontSize: 16 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dashboard?.spc_cpks?.map((c) => c.product_line_code).join(", ") || "无数据"}
          </Text>
        </Card>
        <Card size="small">
          <Statistic title="保修费用" value={dashboard?.warranty_total ?? 0} precision={2} prefix="¥" />
        </Card>
        <Card size="small">
          <Statistic
            title="客户满意度"
            value={dashboard?.avg_satisfaction ?? "-"}
            suffix="/ 10"
            valueStyle={{ color: dashboard?.avg_satisfaction && dashboard.avg_satisfaction >= 8 ? "#3f8600" : dashboard?.avg_satisfaction && dashboard.avg_satisfaction < 6 ? "#cf1322" : undefined }}
          />
        </Card>
        <Card size="small">
          <Statistic
            title="客户审核"
            value={dashboard?.audit_summary ? `${dashboard.audit_summary.completed_count} 次` : "-"}
            valueStyle={{ fontSize: 16 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dashboard?.audit_summary ? `发现项 ${dashboard.audit_summary.finding_count}` : "无数据"}
          </Text>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16 }}>
        <Card bodyStyle={{ padding: 0 }}>
          <Table
            columns={customerColumns}
            dataSource={customers}
            rowKey="customer_id"
            loading={loading}
            pagination={false}
            size="small"
            rowClassName={(record) => record.customer_id === selectedCustomerId ? "ant-table-row-selected" : ""}
            onRow={(record) => ({ onClick: () => setSelectedCustomerId(record.customer_id) })}
          />
        </Card>
        <Card>
          <Tabs
            items={[
              {
                key: "overview",
                label: "概览",
                children: selectedCustomer ? (
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Title level={5}>{selectedCustomer.name}</Title>
                    <Text>客户编号：{selectedCustomer.customer_code}</Text>
                    <Text>行业：{selectedCustomer.segment || "-"}</Text>
                    <Text>PPM 目标：{selectedCustomer.ppm_target ?? "-"}</Text>
                    <Text>默认年发运量：{selectedCustomer.annual_shipment_qty ?? "-"}</Text>
                    <Text>联系人：{selectedCustomer.contact_name || "-"}</Text>
                  </Space>
                ) : <Text type="secondary">请选择客户</Text>,
              },
              {
                key: "complaints",
                label: "客诉",
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit && <Button type="primary" icon={<PlusOutlined />} onClick={() => setComplaintModalOpen(true)}>新建客诉</Button>}
                    </div>
                    <Table columns={complaintColumns} dataSource={complaints} rowKey="complaint_id" loading={loading} />
                  </>
                ),
              },
              {
                key: "rma",
                label: "RMA",
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit && <Button type="primary" icon={<PlusOutlined />} onClick={() => setRmaModalOpen(true)}>新建 RMA</Button>}
                    </div>
                    <Table columns={rmaColumns} dataSource={rmas} rowKey="rma_id" loading={loading} />
                  </>
                ),
              },
              {
                key: "profile",
                label: "档案",
                children: selectedCustomer ? (
                  <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                    {JSON.stringify(selectedCustomer.csr_list || [], null, 2)}
                  </pre>
                ) : <Text type="secondary">请选择客户</Text>,
              },
              {
                key: "shipments",
                label: "发运记录",
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit && selectedCustomerId && (
                        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingShipment(null); shipmentForm.resetFields(); setShipmentModalOpen(true); }}>新增发运</Button>
                      )}
                    </div>
                    <Table
                      dataSource={shipments}
                      rowKey="shipment_id"
                      loading={shipmentLoading}
                      pagination={{ current: shipmentPage, total: shipmentTotal, pageSize: 10, onChange: setShipmentPage }}
                      columns={[
                        { title: "日期", dataIndex: "shipment_date", render: (d: string) => dayjs(d).format("YYYY-MM-DD") },
                        { title: "数量", dataIndex: "quantity" },
                        { title: "批次号", dataIndex: "batch_no", render: (v: string | null) => v || "-" },
                        { title: "目的地", dataIndex: "destination", render: (v: string | null) => v || "-" },
                        { title: "操作", key: "action", render: (_: unknown, record: ShipmentRecord) => (
                          <Space>
                            {canEdit && <Button size="small" onClick={() => { setEditingShipment(record); shipmentForm.setFieldsValue({ shipment_date: dayjs(record.shipment_date), quantity: record.quantity, batch_no: record.batch_no, destination: record.destination, notes: record.notes }); setShipmentModalOpen(true); }}>编辑</Button>}
                            {canEdit && <Button size="small" danger onClick={() => handleDeleteShipment(record)}>删除</Button>}
                          </Space>
                        )},
                      ]}
                    />
                  </>
                ),
              },
            ]}
          />
        </Card>
      </div>

      <Modal title="新建客户" open={customerModalOpen} onOk={() => customerForm.submit()} onCancel={() => setCustomerModalOpen(false)}>
        <Form form={customerForm} layout="vertical" onFinish={handleCreateCustomer}>
          <Form.Item name="customer_code" label="客户编号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label="客户名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="segment" label="行业"><Input /></Form.Item>
          <Form.Item name="contact_name" label="联系人"><Input /></Form.Item>
          <Form.Item name="contact_email" label="邮箱"><Input /></Form.Item>
          <Form.Item name="contact_phone" label="电话"><Input /></Form.Item>
          <Form.Item name="ppm_target" label="PPM 目标"><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="annual_shipment_qty" label="默认年发运量"><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal title="新建客诉" open={complaintModalOpen} onOk={() => complaintForm.submit()} onCancel={() => setComplaintModalOpen(false)}>
        <Form form={complaintForm} layout="vertical" onFinish={handleCreateComplaint} initialValues={{ category: "function", severity: "一般", received_date: dayjs(), impact_qty: 0 }}>
          <Form.Item name="complaint_no" label="客诉编号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="category" label="分类"><Select options={[{ value: "safety", label: "安全" }, { value: "function", label: "功能" }, { value: "appearance", label: "外观" }, { value: "delivery", label: "交付" }]} /></Form.Item>
          <Form.Item name="severity" label="严重等级"><Select options={["致命", "严重", "一般", "轻微"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="product_id" label="产品号"><Input /></Form.Item>
          <Form.Item name="batch_no" label="批次号"><Input /></Form.Item>
          <Form.Item name="serial_number" label="序列号"><Input /></Form.Item>
          <Form.Item name="impact_qty" label="影响数量"><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="occurred_date" label="发生日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="received_date" label="接收日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="due_date" label="期限"><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="defect_desc" label="投诉描述" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="supplier_responsibility" label="供应商责任" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>

      <Modal title="新建 RMA" open={rmaModalOpen} onOk={() => rmaForm.submit()} onCancel={() => setRmaModalOpen(false)}>
        <Form form={rmaForm} layout="vertical" onFinish={handleCreateRMA} initialValues={{ return_qty: 1, responsibility: "unknown" }}>
          <Form.Item name="rma_no" label="RMA 编号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="complaint_id" label="关联客诉"><Select allowClear options={complaints.map((item) => ({ value: item.complaint_id, label: item.complaint_no }))} /></Form.Item>
          <Form.Item name="product_id" label="产品号"><Input /></Form.Item>
          <Form.Item name="batch_no" label="批次号"><Input /></Form.Item>
          <Form.Item name="serial_number" label="序列号"><Input /></Form.Item>
          <Form.Item name="return_qty" label="退货数量"><InputNumber style={{ width: "100%" }} min={1} /></Form.Item>
          <Form.Item name="defect_type" label="不良类型" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="responsibility" label="责任判定"><Select options={[{ value: "supplier", label: "供应商" }, { value: "internal", label: "自制" }, { value: "transport", label: "运输" }, { value: "customer_misuse", label: "客户误用" }, { value: "unknown", label: "未知" }]} /></Form.Item>
          <Form.Item name="tracking_number" label="物流单号"><Input /></Form.Item>
          <Form.Item name="received_date" label="接收日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
        </Form>
      </Modal>

      {/* SCAR Creation Modal */}
      <Modal
        title="创建 SCAR"
        open={scarModalOpen}
        onOk={handleConfirmSCAR}
        onCancel={() => { setScarModalOpen(false); scarForm.resetFields(); setScarTarget(null); }}
      >
        <Form form={scarForm} layout="vertical">
          <Form.Item name="supplier_id" label="责任供应商" rules={[{ required: true, message: "请选择供应商" }]}>
            <Select placeholder="选择供应商">
              {suppliers.map((s) => (
                <Select.Option key={s.supplier_id} value={s.supplier_id}>{s.name} ({s.supplier_no})</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label="问题描述">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="requested_action" label="要求措施">
            <Input />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Shipment Modal */}
      <Modal
        title={editingShipment ? "编辑发运记录" : "新增发运记录"}
        open={shipmentModalOpen}
        onOk={handleSubmitShipment}
        onCancel={() => { setShipmentModalOpen(false); shipmentForm.resetFields(); setEditingShipment(null); }}
      >
        <Form form={shipmentForm} layout="vertical">
          <Form.Item name="shipment_date" label="发运日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true, type: "number", min: 1 }]}>
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="batch_no" label="批次号">
            <Input />
          </Form.Item>
          <Form.Item name="destination" label="目的地">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
