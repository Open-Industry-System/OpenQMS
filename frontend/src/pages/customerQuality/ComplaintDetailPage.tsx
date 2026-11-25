import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, DatePicker, Form, Input, InputNumber, Select, Space, Spin, Switch } from "antd";
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
import { DataCard, PageShell, StatusBadge } from "../../components/design";

const severityVariant = (severity: string) => {
  switch (severity) {
    case "致命":
      return "fatal";
    case "严重":
      return "rework";
    case "一般":
    case "轻微":
    default:
      return "normal";
  }
};

const complaintStatusVariant = (status: string) => {
  switch (status) {
    case "closed":
      return "closed";
    case "cancelled":
      return "reject";
    case "open":
    case "investigating":
    case "responded":
    default:
      return "pending";
  }
};

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

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const complaint = await getComplaint(id);
      setData(complaint);
      form.setFieldsValue({
        ...complaint,
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
      const updated = await updateComplaint(id, {
        ...values,
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

  return (
    <PageShell
      title={
        <Space>
          <Button onClick={() => navigate("/customer-quality")}>{tc("actions.back")}</Button>
          <span>{data?.complaint_no || t("page.complaintDetailTitle")}</span>
          {data && <StatusBadge status={severityVariant(data.severity)}>{data.severity}</StatusBadge>}
          {data && <StatusBadge status={complaintStatusVariant(data.status)}>{t(`status.complaint.${data.status}`, data.status)}</StatusBadge>}
          {data?.supplier_id && <SupplierBadge supplierId={data.supplier_id} />}
          {data?.fmea_ref_id && <RelatedFMEALink fmeaRefId={data.fmea_ref_id} />}
        </Space>
      }
      actions={
        canEdit('customer_quality') && data ? (
          <Space>
            <Button onClick={() => runAction(() => startComplaintInvestigation(data.complaint_id), t("messages.investigationStarted"))}>{t("actions.investigate")}</Button>
            <Button onClick={() => runAction(() => markComplaintResponded(data.complaint_id), t("messages.markedResponded"))}>{t("actions.markResponded")}</Button>
            <Button onClick={() => runAction(() => cancelComplaint(data.complaint_id), t("messages.cancelled"))}>{tc("actions.cancel")}</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeComplaint(data.complaint_id), t("messages.closed"))}>{tc("actions.close")}</Button>}
          </Space>
        ) : null
      }
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <DataCard title={t("form.complaint.complaintNo")}>
          <Spin spinning={loading}>
            <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                <Form.Item name="category" label={t("form.complaint.category")}><Select options={[
                  { value: "safety", label: t("category.safety") },
                  { value: "function", label: t("category.function") },
                  { value: "appearance", label: t("category.appearance") },
                  { value: "delivery", label: t("category.delivery") },
                ]} /></Form.Item>
                <Form.Item name="severity" label={t("form.complaint.severity")}><Select options={[
                  { value: "fatal", label: t("severity.fatal") },
                  { value: "serious", label: t("severity.serious") },
                  { value: "general", label: t("severity.general") },
                  { value: "minor", label: t("severity.minor") },
                ]} /></Form.Item>
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
          </Spin>
        </DataCard>

        <DataCard title={t("sections.linksAndEvidence")}>
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="capa_ref_id" label={t("form.links.capaRefId")}><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label={t("form.links.fmeaRefId")}><Input /></Form.Item>
            <Form.Item name="capa_document_no" label={t("form.links.eightDNo")}><Input placeholder={t("form.links.eightDPlaceholder")} /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{t("actions.updateLinks")}</Button>}
          </Form>
          <pre style={{ marginTop: 16, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(data?.attachments || [], null, 2)}
          </pre>
        </DataCard>
      </div>
    </PageShell>
  );
}
