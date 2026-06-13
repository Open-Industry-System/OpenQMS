import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { App, Button, Card, DatePicker, Form, Input, InputNumber, Select, Space, Switch, Tag, Typography } from "antd";
import dayjs from "dayjs";
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

const { Title } = Typography;

const severityColor: Record<string, string> = { "致命": "red", "严重": "orange", "一般": "blue", "轻微": "default" };
const statusLabel: Record<string, string> = {
  open: "已接收",
  investigating: "调查中",
  responded: "已回复",
  closed: "已关闭",
  cancelled: "已取消",
};

export default function ComplaintDetailPage() {
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
      message.error("客诉加载失败");
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
      message.success("已保存");
    } catch {
      message.error("保存失败");
    }
  };

  const runAction = async (action: () => Promise<CustomerComplaint>, success: string) => {
    try {
      const updated = await action();
      setData(updated);
      message.success(success);
      await load();
    } catch {
      message.error("操作失败");
    }
  };

  const handleLinks = async (values: { capa_ref_id?: string; fmea_ref_id?: string; capa_document_no?: string }) => {
    if (!id) return;
    try {
      if (values.capa_ref_id) await linkComplaintCAPA(id, values.capa_ref_id);
      if (values.fmea_ref_id) await linkComplaintFMEA(id, values.fmea_ref_id);
      if (values.capa_document_no) await createCAPAFromComplaint(id, values.capa_document_no);
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
          <Title level={4} style={{ margin: 0 }}>{data?.complaint_no || "客诉详情"}</Title>
          {data && <Tag color={severityColor[data.severity]}>{data.severity}</Tag>}
          {data && <Tag>{statusLabel[data.status] || data.status}</Tag>}
          {data?.supplier_id && <SupplierBadge supplierId={data.supplier_id} />}
          {data?.fmea_ref_id && <RelatedFMEALink fmeaRefId={data.fmea_ref_id} />}
        </Space>
        {canEdit('customer_quality') && data && (
          <Space>
            <Button onClick={() => runAction(() => startComplaintInvestigation(data.complaint_id), "已进入调查")}>调查</Button>
            <Button onClick={() => runAction(() => markComplaintResponded(data.complaint_id), "已标记回复")}>已回复</Button>
            <Button onClick={() => runAction(() => cancelComplaint(data.complaint_id), "已取消")}>取消</Button>
            {canApprove('customer_quality') && <Button type="primary" onClick={() => runAction(() => closeComplaint(data.complaint_id), "已关闭")}>关闭</Button>}
          </Space>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 16 }}>
        <Card loading={loading}>
          <Form form={form} layout="vertical" onFinish={save} disabled={!canEdit('customer_quality')}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <Form.Item name="category" label="分类"><Select options={[{ value: "safety", label: "安全" }, { value: "function", label: "功能" }, { value: "appearance", label: "外观" }, { value: "delivery", label: "交付" }]} /></Form.Item>
              <Form.Item name="severity" label="严重等级"><Select options={["致命", "严重", "一般", "轻微"].map((value) => ({ value, label: value }))} /></Form.Item>
              <Form.Item name="impact_qty" label="影响数量"><InputNumber style={{ width: "100%" }} min={0} /></Form.Item>
              <Form.Item name="product_id" label="产品号"><Input /></Form.Item>
              <Form.Item name="batch_no" label="批次号"><Input /></Form.Item>
              <Form.Item name="serial_number" label="序列号"><Input /></Form.Item>
              <Form.Item name="occurred_date" label="发生日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
              <Form.Item name="received_date" label="接收日期"><DatePicker style={{ width: "100%" }} /></Form.Item>
              <Form.Item name="due_date" label="期限"><DatePicker style={{ width: "100%" }} /></Form.Item>
            </div>
            <Form.Item name="defect_desc" label="投诉描述"><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="preliminary_response" label="初步回复"><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="root_cause" label="根因"><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="corrective_action" label="纠正措施"><Input.TextArea rows={3} /></Form.Item>
            <Form.Item name="supplier_responsibility" label="供应商责任" valuePropName="checked"><Switch /></Form.Item>
            {canEdit('customer_quality') && <Button type="primary" htmlType="submit">保存</Button>}
          </Form>
        </Card>

        <Card title="关联与证据">
          <Form form={linkForm} layout="vertical" onFinish={handleLinks} disabled={!canEdit('customer_quality')}>
            <Form.Item name="capa_ref_id" label="关联 CAPA ID"><Input /></Form.Item>
            <Form.Item name="fmea_ref_id" label="关联 FMEA ID"><Input /></Form.Item>
            <Form.Item name="capa_document_no" label="新建 8D 编号"><Input placeholder="如 8D-2026-010" /></Form.Item>
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
