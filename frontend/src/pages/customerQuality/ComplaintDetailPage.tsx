import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Select, Space, Switch, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import {
  cancelComplaint,
  closeComplaint,
  createCAPAFromComplaint,
  getComplaint,
  linkComplaintCAPA,
  linkComplaintFMEA,
  markComplaintResponded,
  startComplaintInvestigation,
  updateComplaint,
} from "../../api/customerQuality";
import type { CustomerComplaint } from "../../types";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import SupplierBadge from "../../components/cross-links/SupplierBadge";
import RelatedFMEALink from "../../components/cross-links/RelatedFMEALink";
import {
  useCategoryOptions,
  useComplaintStatusMap,
  useSeverityColor,
  useSeverityOptions,
  useSeverityReverseMap,
} from "./useOptions";
import { SEVERITY_MAP } from "./constants";

const { Title } = Typography;

export default function ComplaintDetailPage() {
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams();
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const [form] = Form.useForm();
  const [linkForm] = Form.useForm();
  const [data, setData] = useState<CustomerComplaint | null>(null);
  const [loading, setLoading] = useState(false);

  const { canEdit, canApprove } = usePermission();

  const severityReverseMap = useSeverityReverseMap();
  const severityColorMap = useSeverityColor();
  const severityOptions = useSeverityOptions();
  const categoryOptions = useCategoryOptions();
  const statusMap = useComplaintStatusMap();

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const complaint = await getComplaint(id);
      setData(complaint);
      form.setFieldsValue({
        ...complaint,
        severity: severityReverseMap[complaint.severity] || complaint.severity,
        occurred_date: complaint.occurred_date ? dayjs(complaint.occurred_date) : null,
        received_date: complaint.received_date ? dayjs(complaint.received_date) : null,
        due_date: complaint.due_date ? dayjs(complaint.due_date) : null,
      });
      linkForm.setFieldsValue({
        capa_ref_id: complaint.capa_ref_id,
        fmea_ref_id: complaint.fmea_ref_id,
      });
    } catch {
      message.error(t("messages.loadComplaintFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const save = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      const severityKey = values.severity as string;
      const updated = await updateComplaint(id, {
        ...values,
        severity: severityKey ? (SEVERITY_MAP[severityKey] || severityKey) as CustomerComplaint["severity"] : undefined,
        occurred_date: values.occurred_date ? (values.occurred_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
        received_date: values.received_date ? (values.received_date as dayjs.Dayjs).format("YYYY-MM-DD") : undefined,
        due_date: values.due_date ? (values.due_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
      });
      setData(updated);
      message.success(tc("messages.saveSuccess"));
    } catch {
      message.error(tc("messages.saveFailed"));
    }
  };

  const runAction = async (action: () => Promise<CustomerComplaint>, success: string) => {
    try {
      const updated = await action();
      setData(updated);
      message.success(success);
      await load();
    } catch {
      message.error(tc("messages.operationFailed"));
    }
  };

  const handleLinks = async (values: { capa_ref_id?: string; fmea_ref_id?: string; capa_document_no?: string }) => {
    if (!id) return;
    try {
      if (values.capa_ref_id) await linkComplaintCAPA(id, values.capa_ref_id);
      if (values.fmea_ref_id) await linkComplaintFMEA(id, values.fmea_ref_id);
      if (values.capa_document_no) await createCAPAFromComplaint(id, values.capa_document_no);
      message.success(t("messages.linksUpdated"));
      await load();
    } catch {
      message.error(t("messages.linksUpdateFailed"));
    }
  };

  const severityKey = data ? severityReverseMap[data.severity] || data.severity : undefined;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button onClick={() => navigate("/customer-quality")}>{tc("actions.back")}</Button>
          <Title level={4} style={{ margin: 0 }}>{data?.complaint_no || t("page.complaintDetailTitle")}</Title>
          {data && <Tag color={severityKey ? severityColorMap[severityKey] : undefined}>{severityKey ? t(`severity.${severityKey}`, data.severity) : data.severity}</Tag>}
          {data && <Tag>{statusMap[data.status] || data.status}</Tag>}
          {data?.supplier_id && <SupplierBadge supplierId={data.supplier_id} />}
          {data?.fmea_ref_id && <RelatedFMEALink fmeaRefId={data.fmea_ref_id} />}
        </Space>
        {canEdit('customer_quality') && data && (
          <Space>
            <Button onClick={() => runAction(() => startComplaintInvestigation(data.complaint_id), t("messages.investigationStarted"))}>{t("actions.investigate")}</Button>
            <Button onClick={() => runAction(() => markComplaintResponded(data.complaint_id), t("messages.markedResponded"))}>{t("actions.markResponded")}</Button>
            <Button onClick={() => runAction(() => cancelComplaint(data.complaint_id), t("messages.cancelled"))}>{tc("actions.cancel")}</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeComplaint(data.complaint_id), t("messages.closed"))}>{tc("actions.close")}</Button>}
          </Space>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <Card loading={loading}>
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <Form.Item name="category" label={t("form.complaint.category")}><Select options={categoryOptions} /></Form.Item>
              <Form.Item name="severity" label={t("form.complaint.severity")}><Select options={severityOptions} /></Form.Item>
              <Form.Item name="impact_qty" label={t("form.complaint.impactQty")}><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
              <Form.Item name="product_id" label={t("form.complaint.productId")}><Input /></Form.Item>
              <Form.Item name="batch_no" label={t("form.complaint.batchNo")}><Input /></Form.Item>
              <Form.Item name="serial_number" label={t("form.complaint.serialNumber")}><Input /></Form.Item>
              <Form.Item name="occurred_date" label={t("form.complaint.occurredDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
              <Form.Item name="received_date" label={t("form.complaint.receivedDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
              <Form.Item name="due_date" label={t("form.complaint.dueDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
            </div>
            <Form.Item name="defect_desc" label={t("form.complaint.defectDesc")}><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="preliminary_response" label={t("form.complaint.preliminaryResponse")}><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="root_cause" label={t("form.complaint.rootCause")}><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="corrective_action" label={t("form.complaint.correctiveAction")}><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="supplier_responsibility" label={t("form.complaint.supplierResponsibility")} valuePropName="checked"><Switch /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{tc("actions.save")}</Button>}
          </Form>
        </Card>

        <Card title={t("sections.linksAndEvidence")}>
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="capa_ref_id" label={t("form.links.capaRefId")}><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label={t("form.links.fmeaRefId")}><Input /></Form.Item>
            <Form.Item name="capa_document_no" label={t("form.links.eightDNo")}><Input placeholder={t("form.links.eightDPlaceholder")} /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{t("actions.updateLinks")}</Button>}
          </Form>
          <pre style={{ marginTop: 16, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(data?.attachments || [], null, 2)}
          </pre>
        </Card>
      </div>
    </div>
  );
}
