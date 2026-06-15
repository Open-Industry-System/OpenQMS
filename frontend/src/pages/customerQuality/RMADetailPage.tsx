import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Select, Space, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useTranslation } from "react-i18next";
import {
  cancelRMA,
  closeRMA,
  getRMARecord,
  linkRMACAPA,
  linkRMAComplaint,
  linkRMAFMEA,
  markRMAActionPending,
  startRMAAnalysis,
  updateRMARecord,
} from "../../api/customerQuality";
import type { RMARecord } from "../../types";
import { usePermission } from "../../hooks/usePermission";
import { useResponsibilityOptions, useRmaStatusMap } from "./useOptions";

const { Title } = Typography;

export default function RMADetailPage() {
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [linkForm] = Form.useForm();
  const [data, setData] = useState<RMARecord | null>(null);
  const [loading, setLoading] = useState(false);
  const { canEdit, canApprove } = usePermission();

  const statusMap = useRmaStatusMap();
  const responsibilityOptions = useResponsibilityOptions();

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const rma = await getRMARecord(id);
      setData(rma);
      form.setFieldsValue({
        ...rma,
        received_date: rma.received_date ? dayjs(rma.received_date) : null,
      });
      linkForm.setFieldsValue({
        complaint_id: rma.complaint_id,
        capa_ref_id: rma.capa_ref_id,
        fmea_ref_id: rma.fmea_ref_id,
      });
    } catch {
      message.error(t("messages.rmaLoadFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const save = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      const updated = await updateRMARecord(id, {
        ...values,
        received_date: values.received_date ? (values.received_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
      });
      setData(updated);
      message.success(tc("messages.saveSuccess"));
    } catch {
      message.error(tc("messages.saveFailed"));
    }
  };

  const runAction = async (action: () => Promise<RMARecord>, success: string) => {
    try {
      const updated = await action();
      setData(updated);
      message.success(success);
      await load();
    } catch {
      message.error(tc("messages.operationFailed"));
    }
  };

  const handleLinks = async (values: { complaint_id?: string; capa_ref_id?: string; fmea_ref_id?: string }) => {
    if (!id) return;
    try {
      if (values.complaint_id) await linkRMAComplaint(id, values.complaint_id);
      if (values.capa_ref_id) await linkRMACAPA(id, values.capa_ref_id);
      if (values.fmea_ref_id) await linkRMAFMEA(id, values.fmea_ref_id);
      message.success(t("messages.linksUpdated"));
      await load();
    } catch {
      message.error(t("messages.linksUpdateFailed"));
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button onClick={() => navigate("/customer-quality")}>{tc("actions.back")}</Button>
          <Title level={4} style={{ margin: 0 }}>{data?.rma_no || t("page.rmaDetailTitle")}</Title>
          {data && <Tag>{statusMap[data.status] || data.status}</Tag>}
        </Space>
        {canEdit('customer_quality') && data && (
          <Space>
            <Button onClick={() => runAction(() => startRMAAnalysis(data.rma_id), t("messages.analysisStarted"))}>{t("actions.analyze")}</Button>
            <Button onClick={() => runAction(() => markRMAActionPending(data.rma_id), t("messages.markedActionPending"))}>{t("actions.markActionPending")}</Button>
            <Button onClick={() => runAction(() => cancelRMA(data.rma_id), t("messages.cancelled"))}>{tc("actions.cancel")}</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeRMA(data.rma_id), t("messages.closed"))}>{tc("actions.close")}</Button>}
          </Space>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <Card loading={loading}>
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <Form.Item name="product_id" label={t("form.rma.productId")}><Input /></Form.Item>
              <Form.Item name="batch_no" label={t("form.rma.batchNo")}><Input /></Form.Item>
              <Form.Item name="serial_number" label={t("form.rma.serialNumber")}><Input /></Form.Item>
              <Form.Item name="return_qty" label={t("form.rma.returnQty")}><InputNumber style={{ width: "100%" }} min={1} /></Form.Item>
              <Form.Item name="defect_type" label={t("form.rma.defectType")}><Input /></Form.Item>
              <Form.Item name="responsibility" label={t("form.rma.responsibility")}><Select allowClear options={responsibilityOptions} /></Form.Item>
              <Form.Item name="tracking_number" label={t("form.rma.trackingNumber")}><Input /></Form.Item>
              <Form.Item name="received_date" label={t("form.rma.receivedDate")}><DatePicker style={{ width: "100%" }} /></Form.Item>
            </div>
            <Form.Item name="analysis_result" label={t("form.rma.analysisResult")}><Input.TextArea rows={4} /></Form.Item>
            <Form.Item name="corrective_action" label={t("form.rma.correctiveAction")}><Input.TextArea rows={4} /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{tc("actions.save")}</Button>}
          </Form>
        </Card>
        <Card title={t("sections.linksAndEvidence")}>
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="complaint_id" label={t("form.links.complaintId")}><Input /></Form.Item>
            <Form.Item name="capa_ref_id" label={t("form.links.capaRefId")}><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label={t("form.links.fmeaRefId")}><Input /></Form.Item>
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
