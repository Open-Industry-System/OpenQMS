import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Table, Button, Tag, Typography, Modal, Form, Input, Select, DatePicker, App } from "antd";
import { PlusOutlined, FileTextOutlined } from "@ant-design/icons";
import { listCAPAs, createCAPA } from "../../api/capa";
import type { CAPAReport } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import dayjs from "dayjs";

const { Title } = Typography;

const severityColors: Record<string, string> = {
  "致命": "red", "严重": "orange", "一般": "blue", "轻微": "default",
};

const statusLabels: Record<string, string> = {
  D1_TEAM: "D1 团队组建", D2_DESCRIPTION: "D2 问题描述",
  D3_INTERIM: "D3 临时措施", D4_ROOT_CAUSE: "D4 根因分析",
  D5_CORRECTION: "D5 永久措施", D6_VERIFICATION: "D6 实施验证",
  D7_PREVENTION: "D7 预防复发", D8_CLOSURE: "D8 关闭", ARCHIVED: "已归档",
};

export default function CAPAListPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<CAPAReport[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const productLine = useProductLineStore((s) => s.selected);
  const [searchParams] = useSearchParams();

  const fetchData = (p: number = page) => {
    setLoading(true);
    const overdue = searchParams.get("overdue") === "true";
    const pendingAction = searchParams.get("pending_action") === "true";
    listCAPAs({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      overdue: overdue || undefined,
      pending_action: pendingAction || undefined,
    })
      .then((res) => { setData(res.items); setTotal(res.total); })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(1); }, [productLine, searchParams]);

  const handleCreate = async (values: { title: string; document_no: string; severity: string; due_date?: dayjs.Dayjs; problem_description?: string }) => {
    try {
      const capa = await createCAPA({
        title: values.title,
        document_no: values.document_no,
        severity: values.severity,
        due_date: values.due_date?.format("YYYY-MM-DD"),
      });
      message.success("8D 报告创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/capa/${capa.report_id}`, { state: { showLessonsLearned: true, problemDescription: values.problem_description } });
    } catch { message.error("创建失败"); }
  };

  const columns = [
    { title: "报告编号", dataIndex: "document_no", key: "document_no", width: 150 },
    { title: "标题", dataIndex: "title", key: "title", ellipsis: true },
    {
      title: "当前步骤", dataIndex: "status", key: "status", width: 140,
      render: (s: string) => <Tag color="processing">{statusLabels[s] || s}</Tag>,
    },
    {
      title: "严重等级", dataIndex: "severity", key: "severity", width: 90,
      render: (s: string) => <Tag color={severityColors[s] || "default"}>{s}</Tag>,
    },
    { title: "期限", dataIndex: "due_date", key: "due_date", width: 110, render: (v: string | null) => v || "-" },
    {
      title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作", key: "actions", width: 80,
      render: (_: unknown, record: CAPAReport) => (
        <Button type="link" icon={<FileTextOutlined />} onClick={() => navigate(`/capa/${record.report_id}`)}>
          处理
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>8D / CAPA</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建 8D</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="report_id" loading={loading}
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); fetchData(p); } }}
      />
      <Modal title="新建 8D 报告" open={modalOpen} onOk={() => form.submit()} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="document_no" label="报告编号" rules={[{ required: true }]}>
            <Input placeholder="如 8D-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="如 焊接不良客诉" />
          </Form.Item>
          <Form.Item name="severity" label="严重等级" initialValue="一般">
            <Select options={["致命", "严重", "一般", "轻微"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="due_date" label="完成期限">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="problem_description" label="问题描述（可选）">
            <Input.TextArea rows={2} placeholder="简述问题现象（可选，用于智能推荐）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
