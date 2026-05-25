import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Card, Descriptions, Button, Space, Tag, Collapse, Input, Table,
  Modal, Form, Select, DatePicker, message, Spin, Popconfirm,
} from "antd";
import {
  collectData, refreshData, backToDraft, startReview, closeReview,
  reopenReview, getManagementReview, updateManagementReview,
  listOutputs, createOutput, updateOutput, deleteOutput, verifyOutput,
} from "../../api/managementReview";
import { useAuthStore } from "../../store/authStore";
import type { ManagementReview, ReviewOutput } from "../../types";

const { TextArea } = Input;

const statusMap: Record<string, { color: string; label: string }> = {
  draft: { color: "blue", label: "草稿" },
  data_collected: { color: "cyan", label: "数据已汇总" },
  in_review: { color: "orange", label: "评审中" },
  closed: { color: "green", label: "已关闭" },
};

const categoryLabels: Record<string, string> = {
  improvement_opportunity: "改进机会",
  system_change: "体系变更",
  resource_need: "资源需求",
};

const outputStatusMap: Record<string, { color: string; label: string }> = {
  pending: { color: "default", label: "待处理" },
  in_progress: { color: "processing", label: "进行中" },
  completed: { color: "warning", label: "待验证" },
  verified: { color: "success", label: "已验证" },
};

const autoDataSources = [
  { key: "quality_goals", title: "2. 质量目标实现程度" },
  { key: "internal_audits", title: "3. 审核结果" },
  { key: "capa_stats", title: "4. 不合格与纠正措施" },
  { key: "fmea_risks", title: "5. FMEA 风险分析" },
  { key: "spc_capability", title: "6. SPC 过程能力" },
  { key: "supplier_performance", title: "7. 外部供方绩效" },
  { key: "previous_review_actions", title: "1. 以往管理评审措施落实" },
];

const manualTextSources = [
  { key: "external_factors", title: "8. 内外部因素变化" },
  { key: "resource_adequacy", title: "9. 资源充分性" },
];

const manualRichSources = [
  { key: "customer_satisfaction", title: "10. 顾客满意与反馈" },
  { key: "equipment_monitoring", title: "11. 监视测量结果(设备)" },
  { key: "copq", title: "12. 不良质量成本" },
  { key: "manufacturing_feasibility", title: "13. 制造可行性评估" },
];

export default function ManagementReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  const [review, setReview] = useState<ManagementReview | null>(null);
  const [outputs, setOutputs] = useState<ReviewOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [outputModalOpen, setOutputModalOpen] = useState(false);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [activeOutput, setActiveOutput] = useState<ReviewOutput | null>(null);
  const [form] = Form.useForm();
  const [verifyForm] = Form.useForm();

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [r, o] = await Promise.all([
        getManagementReview(id),
        listOutputs(id),
      ]);
      setReview(r);
      setOutputs(o);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [id]);

  if (loading || !review) return <Spin style={{ display: "block", margin: "100px auto" }} />;

  const s = review.status;
  const isClosed = s === "closed";
  const manualInputs = (review.manual_inputs || {}) as Record<string, unknown>;

  const handleTransition = async (action: () => Promise<ManagementReview>) => {
    try {
      const updated = await action();
      setReview(updated);
      message.success("操作成功");
    } catch (e: unknown) {
      message.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "操作失败");
    }
  };

  const handleSaveManualInput = async (key: string, value: any) => {
    if (!id) return;
    const inputs = { ...manualInputs, [key]: value };
    const updated = await updateManagementReview(id, { manual_inputs: inputs });
    setReview(updated);
  };

  // Data package collapse items
  const dataPackageItems: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

  // Auto data sources
  if (review.data_package) {
    for (const src of autoDataSources) {
      const data = review.data_package[src.key];
      dataPackageItems.push({
        key: src.key,
        label: src.title,
        children: data ? (
          <Descriptions column={2} size="small" bordered>
            {Object.entries(data as Record<string, unknown>).map(([k, v]) => (
              <Descriptions.Item key={k} label={k}>
                {typeof v === "object" ? JSON.stringify(v) : String(v ?? "-")}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : <span style={{ color: "#999" }}>暂无数据</span>,
      });
    }
  }

  // Manual text sources
  for (const src of manualTextSources) {
    dataPackageItems.push({
      key: src.key,
      label: src.title,
      children: (
        <TextArea
          rows={3}
          defaultValue={String(manualInputs[src.key] || "")}
          disabled={isClosed || isViewer}
          onBlur={(e) => handleSaveManualInput(src.key, e.target.value)}
          placeholder="请输入..."
        />
      ),
    });
  }

  // Manual rich sources (placeholder modules) — CRITICAL: parse existing, merge, save as object
  for (const src of manualRichSources) {
    const existing = manualInputs[src.key];
    const parsed = typeof existing === "string" ? JSON.parse(existing) : (typeof existing === "object" && existing !== null ? existing : {});
    const summary = (parsed as { summary?: string })?.summary || "";
    dataPackageItems.push({
      key: src.key,
      label: <>{src.title} <Tag color="orange">手动录入</Tag></>,
      children: (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Tag color="blue">待模块上线后自动切换</Tag>
          <TextArea
            rows={3}
            defaultValue={summary}
            disabled={isClosed || isViewer}
            onBlur={(e) => {
              const val = { ...parsed, summary: e.target.value };
              handleSaveManualInput(src.key, val);
            }}
            placeholder="请输入汇总文字..."
          />
        </Space>
      ),
    });
  }

  // Output table columns
  const outputColumns = [
    {
      title: "类别", dataIndex: "category", width: 120,
      render: (c: string) => categoryLabels[c] || c,
    },
    { title: "描述", dataIndex: "description" },
    {
      title: "截止日期", dataIndex: "due_date", width: 120,
      render: (v: string | null) => v || "-",
    },
    {
      title: "状态", dataIndex: "status", width: 100,
      render: (st: string) => {
        const info = outputStatusMap[st] || { color: "default", label: st };
        return <Tag color={info.color}>{info.label}</Tag>;
      },
    },
    {
      title: "操作", width: 200,
      render: (_: unknown, record: ReviewOutput) => (
        <Space>
          {!isClosed && record.status === "pending" && (
            <Button size="small" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "in_progress" });
              fetchData();
            }}>开始</Button>
          )}
          {!isClosed && record.status === "in_progress" && (
            <Button size="small" type="primary" onClick={async () => {
              await updateOutput(id!, record.output_id, { status: "completed" });
              fetchData();
            }}>完成</Button>
          )}
          {record.status === "completed" && isAdminOrManager && (
            <Button size="small" type="primary" onClick={() => {
              setActiveOutput(record);
              setVerifyModalOpen(true);
            }}>验证</Button>
          )}
          {!isClosed && (
            <Popconfirm title="确认删除?" onConfirm={async () => {
              await deleteOutput(id!, record.output_id);
              fetchData();
            }}>
              <Button size="small" danger>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      {/* Basic info */}
      <Card
        title={
          <Space>
            <span>{review.doc_no}</span>
            <Tag color={statusMap[s]?.color}>{statusMap[s]?.label}</Tag>
          </Space>
        }
        extra={
          <Space>
            {s === "draft" && !isViewer && (
              <Button type="primary" onClick={() => handleTransition(() => collectData(id!))}>汇总数据</Button>
            )}
            {s === "data_collected" && !isViewer && (
              <>
                <Button onClick={() => handleTransition(() => refreshData(id!))}>刷新数据</Button>
                <Button onClick={() => handleTransition(() => backToDraft(id!))}>返回草稿</Button>
                <Button type="primary" onClick={() => handleTransition(() => startReview(id!))}>开始评审</Button>
              </>
            )}
            {s === "in_review" && isAdminOrManager && (
              <Button type="primary" onClick={() => handleTransition(() => closeReview(id!))}>关闭评审</Button>
            )}
            {s === "closed" && isAdminOrManager && (
              <Popconfirm title="确认重新打开?" onConfirm={() => handleTransition(() => reopenReview(id!))}>
                <Button>重新打开</Button>
              </Popconfirm>
            )}
            <Button onClick={() => navigate("/management-reviews")}>返回列表</Button>
          </Space>
        }
      >
        <Descriptions column={2}>
          <Descriptions.Item label="评审主题">{review.title}</Descriptions.Item>
          <Descriptions.Item label="评审日期">{review.review_date}</Descriptions.Item>
          <Descriptions.Item label="实际日期">{review.actual_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="产品线">{review.product_line_code || "全厂"}</Descriptions.Item>
          <Descriptions.Item label="地点">{review.location || "-"}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Data package */}
      {(s === "data_collected" || s === "in_review" || s === "closed") && (
        <Card title="评审输入数据包">
          <Collapse items={dataPackageItems} />
        </Card>
      )}

      {/* Meeting minutes */}
      {(s === "in_review" || s === "closed") && (
        <Card title="会议纪要">
          <TextArea
            rows={6}
            defaultValue={review.meeting_minutes || ""}
            disabled={isClosed || isViewer}
            onBlur={async (e) => {
              if (!id) return;
              const updated = await updateManagementReview(id, { meeting_minutes: e.target.value });
              setReview(updated);
            }}
            placeholder="请输入评审会议纪要..."
          />
        </Card>
      )}

      {/* Outputs */}
      {(s === "in_review" || s === "closed") && (
        <Card
          title="评审输出措施"
          extra={!isClosed && !isViewer ? (
            <Button type="primary" onClick={() => setOutputModalOpen(true)}>添加措施</Button>
          ) : undefined}
        >
          <Table rowKey="output_id" columns={outputColumns} dataSource={outputs} pagination={false} size="small" />
        </Card>
      )}

      {/* Add output modal */}
      <Modal
        title="添加措施"
        open={outputModalOpen}
        onCancel={() => setOutputModalOpen(false)}
        onOk={async () => {
          const values = await form.validateFields();
          await createOutput(id!, values);
          setOutputModalOpen(false);
          form.resetFields();
          fetchData();
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="improvement_opportunity">改进机会</Select.Option>
              <Select.Option value="system_change">体系变更</Select.Option>
              <Select.Option value="resource_need">资源需求</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="description" label="描述" rules={[{ required: true }]}>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Verify output modal */}
      <Modal
        title="效果验证"
        open={verifyModalOpen}
        onCancel={() => { setVerifyModalOpen(false); setActiveOutput(null); }}
        onOk={async () => {
          const values = await verifyForm.validateFields();
          if (activeOutput && id) {
            await verifyOutput(id, activeOutput.output_id, values.verification_notes);
            setVerifyModalOpen(false);
            setActiveOutput(null);
            verifyForm.resetFields();
            fetchData();
          }
        }}
      >
        <Form form={verifyForm} layout="vertical">
          <Form.Item name="verification_notes" label="验证结论" rules={[{ required: true }]}>
            <TextArea rows={3} placeholder="请输入效果验证结论..." />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}