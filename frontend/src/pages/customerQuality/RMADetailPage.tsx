import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Select, Space, Tag, Typography } from "antd";
import dayjs from "dayjs";
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
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";

const { Title } = Typography;
const statusLabel: Record<string, string> = {
  open: "已登记",
  analysis: "分析中",
  action_pending: "等待措施",
  closed: "已关闭",
  cancelled: "已取消",
};

export default function RMADetailPage() {
  const { message } = App.useApp();
  const { id } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [form] = Form.useForm();
  const [linkForm] = Form.useForm();
  const [data, setData] = useState<RMARecord | null>(null);
  const [loading, setLoading] = useState(false);
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
      message.error("RMA 加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [id]);

  const save = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      const updated = await updateRMARecord(id, {
        ...values,
        received_date: values.received_date ? (values.received_date as dayjs.Dayjs).format("YYYY-MM-DD") : null,
      });
      setData(updated);
      message.success("已保存");
    } catch {
      message.error("保存失败");
    }
  };

  const runAction = async (action: () => Promise<RMARecord>, success: string) => {
    try {
      const updated = await action();
      setData(updated);
      message.success(success);
      await load();
    } catch {
      message.error("操作失败");
    }
  };

  const handleLinks = async (values: { complaint_id?: string; capa_ref_id?: string; fmea_ref_id?: string }) => {
    if (!id) return;
    try {
      if (values.complaint_id) await linkRMAComplaint(id, values.complaint_id);
      if (values.capa_ref_id) await linkRMACAPA(id, values.capa_ref_id);
      if (values.fmea_ref_id) await linkRMAFMEA(id, values.fmea_ref_id);
      message.success("关联已更新");
      await load();
    } catch {
      message.error("关联失败");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button onClick={() => navigate("/customer-quality")}>返回</Button>
          <Title level={4} style={{ margin: 0 }}>{data?.rma_no || "RMA详情"}</Title>
          {data && <Tag>{statusLabel[data.status] || data.status}</Tag>}
        </Space>
        {canEdit('customer_quality') && data && (
          <Space>
            <Button onClick={() => runAction(() => startRMAAnalysis(data.rma_id), "已进入分析")}>分析</Button>
            <Button onClick={() => runAction(() => markRMAActionPending(data.rma_id), "已标记等待措施")}>等待措施</Button>
            <Button onClick={() => runAction(() => cancelRMA(data.rma_id), "已取消")}>取消</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeRMA(data.rma_id), "已关闭")}>关闭</Button>}
          </Space>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <Card loading={loading}>
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <Form.Item name="product_id" label="产品号"><Input /></Form.Item>
              <Form.Item name="batch_no" label="批次号"><Input /></Form.Item>
              <Form.Item name="serial_number" label="序列号"><Input /></Form.Item>
              <Form.Item name="return_qty" label="退货数量"><InputNumber style={{ width: "100%" }} min={1} /></Form.Item>
              <Form.Item name="defect_type" label="不良类型"><Input /></Form.Item>
              <Form.Item name="responsibility" label="责任判定"><Select allowClear options={[{ value: "supplier", label: "供应商" }, { value: "internal", label: "自制" }, { value: "transport", label: "运输" }, { value: "customer_misuse", label: "客户误用" }, { value: "unknown", label: "未知" }]} /></Form.Item>
              <Form.Item name="tracking_number" label="物流单号"><Input /></Form.Item>
              <Form.Item name="received_date" label="接收日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
            </div>
            <Form.Item name="analysis_result" label="分析结果"><Input.TextArea rows={4} /></Form.Item>
            <Form.Item name="corrective_action" label="纠正措施"><Input.TextArea rows={4} /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">保存</Button>}
          </Form>
        </Card>
        <Card title="关联与证据">
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="complaint_id" label="关联客诉 ID"><Input /></Form.Item>
            <Form.Item name="capa_ref_id" label="关联 CAPA ID"><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label="关联 FMEA ID"><Input /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">更新关联</Button>}
          </Form>
          <pre style={{ marginTop: 16, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(data?.attachments || [], null, 2)}
          </pre>
        </Card>
      </div>
    </div>
  );
}
