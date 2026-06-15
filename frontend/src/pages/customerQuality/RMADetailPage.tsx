import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, DatePicker, Form, Input, InputNumber, Select, Space } from "antd";
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
import { DataCard, PageShell, StatusBadge } from "../../components/design";

const rmaStatusVariant = (status: string) => {
  switch (status) {
    case "closed":
      return "closed";
    case "cancelled":
      return "reject";
    case "open":
    case "analysis":
    case "action_pending":
    default:
      return "pending";
  }
};

export default function RMADetailPage() {
  const { t } = useTranslation("customerQuality");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const { id } = useParams();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [linkForm] = Form.useForm();
  const [data, setData] = useState<RMARecord | null>(null);
  const [_loading, setLoading] = useState(false);
  const { canEdit, canApprove } = usePermission();

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
      message.error(t("messages.rmaLoadFailed", "RMA 加载失败"));
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
      message.success(tc("messages.saveSuccess", "已保存"));
    } catch {
      message.error(tc("messages.saveFailed", "保存失败"));
    }
  };

  const runAction = async (action: () => Promise<RMARecord>, success: string) => {
    try {
      const updated = await action();
      setData(updated);
      message.success(success);
      await load();
    } catch {
      message.error(tc("messages.operationFailed", "操作失败"));
    }
  };

  const handleLinks = async (values: { complaint_id?: string; capa_ref_id?: string; fmea_ref_id?: string }) => {
    if (!id) return;
    try {
      if (values.complaint_id) await linkRMAComplaint(id, values.complaint_id);
      if (values.capa_ref_id) await linkRMACAPA(id, values.capa_ref_id);
      if (values.fmea_ref_id) await linkRMAFMEA(id, values.fmea_ref_id);
      message.success(t("messages.linksUpdated", "关联已更新"));
      await load();
    } catch {
      message.error(t("messages.linksUpdateFailed", "关联失败"));
    }
  };

  return (
    <PageShell
      title={
        <Space>
          <Button onClick={() => navigate("/customer-quality")}>{tc("actions.back", "返回")}</Button>
          <span>{data?.rma_no || t("page.rmaDetailTitle", "RMA详情")}</span>
          {data && <StatusBadge status={rmaStatusVariant(data.status)}>{t(`status.rma.${data.status}`, data.status)}</StatusBadge>}
        </Space>
      }
      actions={
        canEdit('customer_quality') && data ? (
          <Space>
            <Button onClick={() => runAction(() => startRMAAnalysis(data.rma_id), t("messages.analysisStarted", "已进入分析"))}>{t("actions.analyze", "分析")}</Button>
            <Button onClick={() => runAction(() => markRMAActionPending(data.rma_id), t("messages.markedActionPending", "已标记等待措施"))}>{t("actions.markActionPending", "等待措施")}</Button>
            <Button onClick={() => runAction(() => cancelRMA(data.rma_id), t("messages.cancelled", "已取消"))}>{tc("actions.cancel", "取消")}</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeRMA(data.rma_id), t("messages.closed", "已关闭"))}>{tc("actions.close", "关闭")}</Button>}
          </Space>
        ) : null
      }
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <DataCard title={t("form.rma.rmaNo", "RMA 信息")}>
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <Form.Item name="product_id" label={t("form.rma.productId", "产品号")}><Input /></Form.Item>
              <Form.Item name="batch_no" label={t("form.rma.batchNo", "批次号")}><Input /></Form.Item>
              <Form.Item name="serial_number" label={t("form.rma.serialNumber", "序列号")}><Input /></Form.Item>
              <Form.Item name="return_qty" label={t("form.rma.returnQty", "退货数量")}><InputNumber style={{ width: "100%" }} min={1} /></Form.Item>
              <Form.Item name="defect_type" label={t("form.rma.defectType", "不良类型")}><Input /></Form.Item>
              <Form.Item name="responsibility" label={t("form.rma.responsibility", "责任判定")}><Select allowClear options={[
                { value: "supplier", label: t("responsibility.supplier", "供应商") },
                { value: "internal", label: t("responsibility.internal", "自制") },
                { value: "transport", label: t("responsibility.transport", "运输") },
                { value: "customer_misuse", label: t("responsibility.customer_misuse", "客户误用") },
                { value: "unknown", label: t("responsibility.unknown", "未知") },
              ]} /></Form.Item>
              <Form.Item name="tracking_number" label={t("form.rma.trackingNumber", "物流单号")}><Input /></Form.Item>
              <Form.Item name="received_date" label={t("form.rma.receivedDate", "接收日期")}><DatePicker style={{ width: "100%" }} /></Form.Item>
            </div>
            <Form.Item name="analysis_result" label={t("form.rma.analysisResult", "分析结果")}><Input.TextArea rows={4} /></Form.Item>
            <Form.Item name="corrective_action" label={t("form.rma.correctiveAction", "纠正措施")}><Input.TextArea rows={4} /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{tc("actions.save", "保存")}</Button>}
          </Form>
        </DataCard>
        <DataCard title={t("sections.linksAndEvidence", "关联与证据")}>
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="complaint_id" label={t("form.links.complaintId", "关联客诉 ID")}><Input /></Form.Item>
            <Form.Item name="capa_ref_id" label={t("form.links.capaRefId", "关联 CAPA ID")}><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label={t("form.links.fmeaRefId", "关联 FMEA ID")}><Input /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">{t("actions.updateLinks", "更新关联")}</Button>}
          </Form>
          <pre style={{ marginTop: 16, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(data?.attachments || [], null, 2)}
          </pre>
        </DataCard>
      </div>
    </PageShell>
  );
}
