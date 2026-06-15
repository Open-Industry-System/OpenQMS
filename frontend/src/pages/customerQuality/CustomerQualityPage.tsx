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
import { useTranslation } from "react-i18next";
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
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";
import {
  useCategoryOptions,
  useComplaintStatusMap,
  useRmaStatusMap,
  useResponsibilityOptions,
  useSeverityColor,
  useSeverityOptions,
  useSeverityReverseMap,
} from "./useOptions";
import { SEVERITY_MAP } from "./constants";

const { Title, Text } = Typography;

const riskColor: Record<string, string> = { red: "red", yellow: "gold", green: "green" };

export default function CustomerQualityPage() {
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
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

  const { canEdit } = usePermission();
  const assigneeId = mineOnly ? user?.user_id : undefined;

  const severityReverseMap = useSeverityReverseMap();
  const severityColorMap = useSeverityColor();
  const severityOptions = useSeverityOptions();
  const categoryOptions = useCategoryOptions();
  const complaintStatusMap = useComplaintStatusMap();
  const rmaStatusMap = useRmaStatusMap();
  const responsibilityOptions = useResponsibilityOptions();

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
      message.error(t("messages.loadDataFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      message.error(t("messages.loadShipmentsFailed"));
    } finally {
      setShipmentLoading(false);
    }
  };
  useEffect(() => { if (selectedCustomerId) fetchShipments(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCustomerId, shipmentPage]);

  // SCAR handlers
  const handleCreateSCAR = (type: "complaint" | "rma", record: CustomerComplaint | RMARecord) => {
    if (type === "complaint") {
      const c = record as CustomerComplaint;
      setScarTarget({ type, record: c });
      scarForm.setFieldsValue({ supplier_id: (c as CustomerComplaint & { supplier_id?: string }).supplier_id, description: c.defect_desc });
    } else {
      const r = record as RMARecord;
      setScarTarget({ type, record: r });
      scarForm.setFieldsValue({ description: `${r.defect_type || "RMA"}${r.analysis_result ? " - " + r.analysis_result : ""}` });
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
      message.success(t("messages.scarCreateSuccess"));
      setScarModalOpen(false);
      scarForm.resetFields();
      setScarTarget(null);
      loadData();
    } catch {
      message.error(t("messages.scarCreateFailed"));
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
        message.success(tc("messages.saveSuccess"));
      } else {
        await createShipment(selectedCustomerId!, payload);
        message.success(tc("messages.operationSuccess"));
      }
      setShipmentModalOpen(false);
      shipmentForm.resetFields();
      setEditingShipment(null);
      fetchShipments();
    } catch {
      message.error(tc("messages.operationFailed"));
    }
  };

  const handleDeleteShipment = async (record: ShipmentRecord) => {
    Modal.confirm({
      title: tc("messages.confirmDelete"),
      content: t("messages.confirmDeleteShipment", { date: record.shipment_date }),
      onOk: async () => {
        try {
          await deleteShipment(selectedCustomerId!, record.shipment_id);
          message.success(tc("messages.deleteSuccess"));
          fetchShipments();
        } catch { message.error(tc("messages.deleteFailed")); }
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
      message.success(t("messages.customerCreateSuccess"));
      setCustomerModalOpen(false);
      customerForm.resetFields();
      setSelectedCustomerId(customer.customer_id);
      await loadData();
    } catch {
      message.error(t("messages.customerCreateFailed"));
    }
  };

  const handleCreateComplaint = async (values: Record<string, unknown>) => {
    if (!selectedCustomerId || !productLine) {
      message.warning(t("messages.selectCustomerAndProductLine"));
      return;
    }
    try {
      const severityKey = values.severity as string;
      const complaint = await createComplaint({
        complaint_no: values.complaint_no as string,
        product_line_code: productLine,
        customer_id: selectedCustomerId,
        product_id: (values.product_id as string) || null,
        batch_no: (values.batch_no as string) || null,
        serial_number: (values.serial_number as string) || null,
        category: values.category as CustomerComplaint["category"],
        severity: (SEVERITY_MAP[severityKey] || severityKey) as CustomerComplaint["severity"],
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
      message.success(t("messages.complaintCreateSuccess"));
      setComplaintModalOpen(false);
      complaintForm.resetFields();
      navigate(`/customer-quality/complaints/${complaint.complaint_id}`);
    } catch {
      message.error(t("messages.complaintCreateFailed"));
    }
  };

  const handleCreateRMA = async (values: Record<string, unknown>) => {
    if (!selectedCustomerId || !productLine) {
      message.warning(t("messages.selectCustomerAndProductLine"));
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
      message.success(t("messages.rmaCreateSuccess"));
      setRmaModalOpen(false);
      rmaForm.resetFields();
      navigate(`/customer-quality/rma/${rma.rma_id}`);
    } catch {
      message.error(t("messages.rmaCreateFailed"));
    }
  };

  const customerColumns = [
    {
      title: t("table.customer.risk"),
      dataIndex: "customer_id",
      width: 70,
      render: (id: string) => {
        const summary = dashboard?.customers.find((item) => item.customer_id === id);
        return <Tag color={riskColor[summary?.risk_light || "green"]}>{summary?.risk_light || "green"}</Tag>;
      },
    },
    { title: t("table.customer.code"), dataIndex: "customer_code", width: 110 },
    { title: t("table.customer.name"), dataIndex: "name", ellipsis: true },
  ];

  const complaintColumns = [
    { title: t("table.complaint.no"), dataIndex: "complaint_no", width: 130 },
    {
      title: t("table.complaint.severity"),
      dataIndex: "severity",
      width: 90,
      render: (value: string) => {
        const key = severityReverseMap[value] || value;
        return <Tag color={severityColorMap[key]}>{t(`severity.${key}`, value)}</Tag>;
      },
    },
    { title: t("table.complaint.batchNo"), dataIndex: "batch_no", width: 130, render: (value: string | null) => value || "-" },
    {
      title: t("table.complaint.status"),
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{complaintStatusMap[value] || value}</Tag>,
    },
    { title: t("table.complaint.dueDate"), dataIndex: "due_date", width: 110, render: (value: string | null) => value || "-" },
    { title: t("table.complaint.description"), dataIndex: "defect_desc", ellipsis: true },
    {
      title: t("table.operations"),
      width: 140,
      render: (_: unknown, record: CustomerComplaint) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/customer-quality/complaints/${record.complaint_id}`)}>{t("actions.handle")}</Button>
          {record.supplier_responsibility && !record.scar_ref_id && (
            <Button size="small" onClick={() => handleCreateSCAR("complaint", record)}>{t("actions.createScar")}</Button>
          )}
          {record.scar_ref_id && (
            <Button size="small" type="link" onClick={() => navigate(`/scars/${record.scar_ref_id}`)}>{t("actions.viewScar")}</Button>
          )}
        </Space>
      ),
    },
  ];

  const rmaColumns = [
    { title: t("table.rma.no"), dataIndex: "rma_no", width: 130 },
    { title: t("table.rma.returnQty"), dataIndex: "return_qty", width: 80 },
    { title: t("table.rma.batchNo"), dataIndex: "batch_no", width: 130, render: (value: string | null) => value || "-" },
    {
      title: t("table.rma.status"),
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{rmaStatusMap[value] || value}</Tag>,
    },
    { title: t("table.rma.responsibility"), dataIndex: "responsibility", width: 120, render: (value: string | null) => (value ? t(`responsibility.${value}`, value) : "-") },
    { title: t("table.rma.defectType"), dataIndex: "defect_type", ellipsis: true },
    {
      title: t("table.operations"),
      width: 140,
      render: (_: unknown, record: RMARecord) => (
        <Space>
          <Button type="link" onClick={() => navigate(`/customer-quality/rma/${record.rma_id}`)}>{t("actions.analyze")}</Button>
          {record.responsibility === "supplier" && !record.scar_ref_id && (
            <Button size="small" onClick={() => handleCreateSCAR("rma", record)}>{t("actions.createScar")}</Button>
          )}
          {record.scar_ref_id && (
            <Button size="small" type="link" onClick={() => navigate(`/scars/${record.scar_ref_id}`)}>{t("actions.viewScar")}</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t("page.title")}</Title>
        <Space>
          <Text>{t("actions.myTodos")}</Text>
          <Switch checked={mineOnly} onChange={setMineOnly} />
          <Button icon={<ReloadOutlined />} onClick={loadData}>{tc("actions.refresh")}</Button>
          {canEdit('customer_quality') && <Button icon={<PlusOutlined />} onClick={() => setCustomerModalOpen(true)}>{t("actions.newCustomer")}</Button>}
        </Space>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
        <Card><Statistic title={t("kpi.customers")} value={customers.length} /></Card>
        <Card><Statistic title={t("kpi.openComplaints")} value={dashboard?.kpi.open_complaint_count || 0} /></Card>
        <Card><Statistic title={t("kpi.overdueComplaints")} value={dashboard?.kpi.overdue_count || 0} valueStyle={{ color: "#cf1322" }} /></Card>
        <Card><Statistic title={t("kpi.rmaCount")} value={dashboard?.kpi.rma_count || 0} /></Card>
        <Card><Statistic title={t("kpi.impactQty")} value={dashboard?.kpi.impact_qty || 0} /></Card>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 12, marginBottom: 16 }}>
        <Card size="small">
          <Statistic
            title={t("kpi.spcCpk")}
            value={dashboard?.spc_cpks?.length ? dashboard.spc_cpks.map((c) => c.cpk ?? "-").join(" / ") : "-"}
            valueStyle={{ fontSize: 16 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dashboard?.spc_cpks?.map((c) => c.product_line_code).join(", ") || tc("empty.data")}
          </Text>
        </Card>
        <Card size="small">
          <Statistic title={t("kpi.warrantyCost")} value={dashboard?.warranty_total ?? 0} precision={2} prefix="¥" />
        </Card>
        <Card size="small">
          <Statistic
            title={t("kpi.customerSatisfaction")}
            value={dashboard?.avg_satisfaction ?? "-"}
            suffix="/ 10"
            valueStyle={{ color: dashboard?.avg_satisfaction && dashboard.avg_satisfaction >= 8 ? "#3f8600" : dashboard?.avg_satisfaction && dashboard.avg_satisfaction < 6 ? "#cf1322" : undefined }}
          />
        </Card>
        <Card size="small">
          <Statistic
            title={t("kpi.customerAudit")}
            value={dashboard?.audit_summary ? t("kpi.auditCount", { count: dashboard.audit_summary.completed_count }) : "-"}
            valueStyle={{ fontSize: 16 }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dashboard?.audit_summary ? t("kpi.findingCount", { count: dashboard.audit_summary.finding_count }) : tc("empty.data")}
          </Text>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16 }}>
        <Card styles={{ body: { padding: 0 } }}>
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
                label: t("tabs.overview"),
                children: selectedCustomer ? (
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <Title level={5}>{selectedCustomer.name}</Title>
                    <Text>{t("detail.customerCode")}{selectedCustomer.customer_code}</Text>
                    <Text>{t("detail.segment")}{selectedCustomer.segment || "-"}</Text>
                    <Text>{t("detail.ppmTarget")}{selectedCustomer.ppm_target ?? "-"}</Text>
                    <Text>{t("detail.annualShipmentQty")}{selectedCustomer.annual_shipment_qty ?? "-"}</Text>
                    <Text>{t("detail.contactName")}{selectedCustomer.contact_name || "-"}</Text>
                  </Space>
                ) : <Text type="secondary">{tc("empty.select")}</Text>,
              },
              {
                key: "complaints",
                label: t("tabs.complaints"),
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit('customer_quality') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setComplaintModalOpen(true)}>{t("actions.newComplaint")}</Button>}
                    </div>
                    <Table columns={complaintColumns} dataSource={complaints} rowKey="complaint_id" loading={loading} />
                  </>
                ),
              },
              {
                key: "rma",
                label: t("tabs.rma"),
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit('customer_quality') && <Button type="primary" icon={<PlusOutlined />} onClick={() => setRmaModalOpen(true)}>{t("actions.newRma")}</Button>}
                    </div>
                    <Table columns={rmaColumns} dataSource={rmas} rowKey="rma_id" loading={loading} />
                  </>
                ),
              },
              {
                key: "profile",
                label: t("tabs.profile"),
                children: selectedCustomer ? (
                  <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                    {JSON.stringify(selectedCustomer.csr_list || [], null, 2)}
                  </pre>
                ) : <Text type="secondary">{tc("empty.select")}</Text>,
              },
              {
                key: "shipments",
                label: t("tabs.shipments"),
                children: (
                  <>
                    <div style={{ textAlign: "right", marginBottom: 12 }}>
                      {canEdit('customer_quality') && selectedCustomerId && (
                        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingShipment(null); shipmentForm.resetFields(); setShipmentModalOpen(true); }}>{t("actions.newShipment")}</Button>
                      )}
                    </div>
                    <Table
                      dataSource={shipments}
                      rowKey="shipment_id"
                      loading={shipmentLoading}
                      pagination={{ current: shipmentPage, total: shipmentTotal, pageSize: 10, onChange: setShipmentPage }}
                      columns={[
                        { title: t("table.shipment.date"), dataIndex: "shipment_date", render: (d: string) => dayjs(d).format("YYYY-MM-DD") },
                        { title: t("table.shipment.quantity"), dataIndex: "quantity" },
                        { title: t("table.shipment.batchNo"), dataIndex: "batch_no", render: (v: string | null) => v || "-" },
                        { title: t("table.shipment.destination"), dataIndex: "destination", render: (v: string | null) => v || "-" },
                        { title: t("table.operations"), key: "action", render: (_: unknown, record: ShipmentRecord) => (
                          <Space>
                            {canEdit('customer_quality') && <Button size="small" onClick={() => { setEditingShipment(record); shipmentForm.setFieldsValue({ shipment_date: dayjs(record.shipment_date), quantity: record.quantity, batch_no: record.batch_no, destination: record.destination, notes: record.notes }); setShipmentModalOpen(true); }}>{tc("actions.edit")}</Button>}
                            {canEdit('customer_quality') && <Button size="small" danger onClick={() => handleDeleteShipment(record)}>{tc("actions.delete")}</Button>}
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

      <Modal title={t("modal.newCustomer")} open={customerModalOpen} onOk={() => customerForm.submit()} onCancel={() => setCustomerModalOpen(false)}>
        <Form form={customerForm} layout="vertical" onFinish={handleCreateCustomer}>
          <Form.Item name="customer_code" label={t("form.customer.customerCode")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label={t("form.customer.name")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="segment" label={t("form.customer.segment")}><Input /></Form.Item>
          <Form.Item name="contact_name" label={t("form.customer.contactName")}><Input /></Form.Item>
          <Form.Item name="contact_email" label={t("form.customer.contactEmail")}><Input /></Form.Item>
          <Form.Item name="contact_phone" label={t("form.customer.contactPhone")}><Input /></Form.Item>
          <Form.Item name="ppm_target" label={t("form.customer.ppmTarget")}><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="annual_shipment_qty" label={t("form.customer.annualShipmentQty")}><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="notes" label={t("form.customer.notes")}><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t("modal.newComplaint")} open={complaintModalOpen} onOk={() => complaintForm.submit()} onCancel={() => setComplaintModalOpen(false)}>
        <Form form={complaintForm} layout="vertical" onFinish={handleCreateComplaint} initialValues={{ category: "function", severity: "general", received_date: dayjs(), impact_qty: 0 }}>
          <Form.Item name="complaint_no" label={t("form.complaint.complaintNo")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="category" label={t("form.complaint.category")}><Select options={categoryOptions} /></Form.Item>
          <Form.Item name="severity" label={t("form.complaint.severity")}><Select options={severityOptions} /></Form.Item>
          <Form.Item name="product_id" label={t("form.complaint.productId")}><Input /></Form.Item>
          <Form.Item name="batch_no" label={t("form.complaint.batchNo")}><Input /></Form.Item>
          <Form.Item name="serial_number" label={t("form.complaint.serialNumber")}><Input /></Form.Item>
          <Form.Item name="impact_qty" label={t("form.complaint.impactQty")}><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
          <Form.Item name="occurred_date" label={t("form.complaint.occurredDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="received_date" label={t("form.complaint.receivedDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="due_date" label={t("form.complaint.dueDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="defect_desc" label={t("form.complaint.defectDesc")} rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="supplier_responsibility" label={t("form.complaint.supplierResponsibility")} valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t("modal.newRma")} open={rmaModalOpen} onOk={() => rmaForm.submit()} onCancel={() => setRmaModalOpen(false)}>
        <Form form={rmaForm} layout="vertical" onFinish={handleCreateRMA} initialValues={{ return_qty: 1, responsibility: "unknown" }}>
          <Form.Item name="rma_no" label={t("form.rma.rmaNo")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="complaint_id" label={t("form.rma.complaintId")}><Select allowClear options={complaints.map((item) => ({ value: item.complaint_id, label: item.complaint_no }))} /></Form.Item>
          <Form.Item name="product_id" label={t("form.rma.productId")}><Input /></Form.Item>
          <Form.Item name="batch_no" label={t("form.rma.batchNo")}><Input /></Form.Item>
          <Form.Item name="serial_number" label={t("form.rma.serialNumber")}><Input /></Form.Item>
          <Form.Item name="return_qty" label={t("form.rma.returnQty")}><InputNumber style={{ width: "100%" }} min={1} /></Form.Item>
          <Form.Item name="defect_type" label={t("form.rma.defectType")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="responsibility" label={t("form.rma.responsibility")}><Select options={responsibilityOptions} /></Form.Item>
          <Form.Item name="tracking_number" label={t("form.rma.trackingNumber")}><Input /></Form.Item>
          <Form.Item name="received_date" label={t("form.rma.receivedDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
        </Form>
      </Modal>

      {/* SCAR Creation Modal */}
      <Modal
        title={t("modal.createScar")}
        open={scarModalOpen}
        onOk={handleConfirmSCAR}
        onCancel={() => { setScarModalOpen(false); scarForm.resetFields(); setScarTarget(null); }}
      >
        <Form form={scarForm} layout="vertical">
          <Form.Item name="supplier_id" label={t("form.scar.supplier")} rules={[{ required: true, message: t("form.scar.supplierRequired") }]}>
            <Select placeholder={t("form.scar.selectSupplier")}>
              {suppliers.map((s) => (
                <Select.Option key={s.supplier_id} value={s.supplier_id}>{s.name} ({s.supplier_no})</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="description" label={t("form.scar.description")}>
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="requested_action" label={t("form.scar.requestedAction")}>
            <Input />
          </Form.Item>
          <Form.Item name="due_date" label={t("form.scar.dueDate")}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Shipment Modal */}
      <Modal
        title={editingShipment ? t("modal.editShipment") : t("modal.newShipment")}
        open={shipmentModalOpen}
        onOk={handleSubmitShipment}
        onCancel={() => { setShipmentModalOpen(false); shipmentForm.resetFields(); setEditingShipment(null); }}
      >
        <Form form={shipmentForm} layout="vertical">
          <Form.Item name="shipment_date" label={t("form.shipment.shipmentDate")} rules={[{ required: true }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="quantity" label={t("form.shipment.quantity")} rules={[{ required: true, type: "number", min: 1 }]}>
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="batch_no" label={t("form.shipment.batchNo")}>
            <Input />
          </Form.Item>
          <Form.Item name="destination" label={t("form.shipment.destination")}>
            <Input />
          </Form.Item>
          <Form.Item name="notes" label={t("form.shipment.notes")}>
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
