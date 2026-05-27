import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Button,
  Tag,
  Space,
  Form,
  Input,
  Select,
  App,
  Tabs,
  Table,
  Row,
  Col,
  Steps,
  InputNumber,
  Descriptions,
  Divider,
} from "antd";
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import type { IqcInspection, IqcInspectionItem } from "../../types";
import {
  getInspection,
  startInspection,
  updateInspectionItems,
  judgeInspection,
  closeInspection,
  triggerScar,
  requestReinspect,
  approveConcession,
} from "../../api/iqc";

const { Option } = Select;
const { TextArea } = Input;

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待检验", color: "orange" },
  inspecting: { label: "检验中", color: "blue" },
  judged: { label: "已判定", color: "cyan" },
  closed: { label: "已关闭", color: "default" },
};

const RESULT_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待定", color: "default" },
  accepted: { label: "合格", color: "green" },
  rejected: { label: "拒收", color: "red" },
  concession: { label: "让步接收", color: "gold" },
};

function statusToStep(status: string): number {
  switch (status) {
    case "pending":
      return 0;
    case "inspecting":
      return 1;
    case "judged":
      return 2;
    case "closed":
      return 3;
    default:
      return 0;
  }
}

export default function IqcInspectionDetailPage() {
  const { message } = App.useApp();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isAdminOrManager = user?.role === "admin" || user?.role === "manager";

  const [inspection, setInspection] = useState<IqcInspection | null>(null);
  const [loading, setLoading] = useState(false);
  const [itemForm] = Form.useForm();
  const [judgeForm] = Form.useForm();

  const fetchInspection = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await getInspection(id);
      setInspection(data);
    } catch {
      message.error("加载检验单失败");
    } finally {
      setLoading(false);
    }
  }, [id, message]);

  useEffect(() => {
    fetchInspection();
  }, [fetchInspection]);

  const handleStart = async () => {
    if (!id) return;
    try {
      await startInspection(id);
      message.success("检验已开始");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleUpdateItems = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await updateInspectionItems(id, values.items as Record<string, unknown>[]);
      message.success("检验项目已更新");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleJudge = async (values: Record<string, unknown>) => {
    if (!id) return;
    try {
      await judgeInspection(id, {
        inspection_result: values.inspection_result as string,
        defect_qty: (values.defect_qty as number) || 0,
        defect_description: (values.defect_description as string) || null,
        sample_qty: (values.sample_qty as number) || null,
      });
      message.success("判定已提交");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleClose = async () => {
    if (!id) return;
    try {
      await closeInspection(id);
      message.success("检验单已关闭");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleTriggerScar = async () => {
    if (!id) return;
    try {
      const result = await triggerScar(id);
      message.success("SCAR已触发");
      if (result.linked_scar_id) {
        navigate(`/scars/${result.linked_scar_id}`);
      } else {
        fetchInspection();
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleReinspect = async () => {
    if (!id) return;
    try {
      await requestReinspect(id);
      message.success("复检申请已提交");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const handleConcession = async () => {
    if (!id) return;
    try {
      await approveConcession(id, "让步接收");
      message.success("让步接收已批准");
      fetchInspection();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "操作失败");
    }
  };

  const itemColumns = [
    { title: "序号", dataIndex: "sort_order", width: 60 },
    { title: "类别", dataIndex: "category", width: 100 },
    { title: "项目名称", dataIndex: "item_name", width: 200 },
    { title: "检验类型", dataIndex: "inspect_type", width: 100 },
    { title: "规格上限", dataIndex: "spec_upper", width: 100, render: (v: number | null) => v ?? "—" },
    { title: "规格下限", dataIndex: "spec_lower", width: 100, render: (v: number | null) => v ?? "—" },
    { title: "样本量", dataIndex: "sample_size", width: 80, render: (v: number | null) => v ?? "—" },
    { title: "Ac", dataIndex: "accept_no", width: 60, render: (v: number | null) => v ?? "—" },
    { title: "Re", dataIndex: "reject_no", width: 60, render: (v: number | null) => v ?? "—" },
    { title: "缺陷数", dataIndex: "defect_qty", width: 80 },
    {
      title: "结果",
      dataIndex: "result",
      width: 100,
      render: (result: string) => {
        const cfg = RESULT_MAP[result] || { label: result, color: "default" };
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    { title: "备注", dataIndex: "remark", ellipsis: true, render: (v: string | null) => v || "—" },
  ];

  if (!inspection) {
    return <div>加载中...</div>;
  }

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/iqc/inspections")}>
          返回列表
        </Button>
        {inspection.status === "pending" && !isViewer && (
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart}>
            开始检验
          </Button>
        )}
        {inspection.status === "judged" && !isViewer && (
          <Button type="primary" onClick={handleClose}>
            关闭检验单
          </Button>
        )}
        {inspection.status === "judged" && inspection.inspection_result === "rejected" && !isViewer && (
          <>
            <Button danger onClick={handleTriggerScar}>
              触发SCAR
            </Button>
            <Button onClick={handleReinspect}>申请复检</Button>
            {isAdminOrManager && (
              <Button onClick={handleConcession}>让步接收</Button>
            )}
          </>
        )}
      </Space>

      <Card title="检验单信息" loading={loading}>
        <Steps current={statusToStep(inspection.status)} style={{ marginBottom: 24 }}>
          <Steps.Step title="待检验" />
          <Steps.Step title="检验中" />
          <Steps.Step title="已判定" />
          <Steps.Step title="已关闭" />
        </Steps>

        <Descriptions bordered column={3}>
          <Descriptions.Item label="检验单号">{inspection.inspection_no}</Descriptions.Item>
          <Descriptions.Item label="物料号">{inspection.part_no || "—"}</Descriptions.Item>
          <Descriptions.Item label="物料名称">{inspection.part_name || "—"}</Descriptions.Item>
          <Descriptions.Item label="批号">{inspection.lot_no || "—"}</Descriptions.Item>
          <Descriptions.Item label="批量">{inspection.lot_qty || "—"}</Descriptions.Item>
          <Descriptions.Item label="样本量">{inspection.sample_qty || "—"}</Descriptions.Item>
          <Descriptions.Item label="检验模式">
            {inspection.inspection_mode === "quick" ? "快速检验" : "详细检验"}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_MAP[inspection.status]?.color}>
              {STATUS_MAP[inspection.status]?.label}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="检验结果">
            <Tag color={RESULT_MAP[inspection.inspection_result]?.color}>
              {RESULT_MAP[inspection.inspection_result]?.label}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="AQL等级">{inspection.aql_level || "—"}</Descriptions.Item>
          <Descriptions.Item label="检验水平">{inspection.inspection_level || "—"}</Descriptions.Item>
          <Descriptions.Item label="代码字">{inspection.code_letter || "—"}</Descriptions.Item>
          <Descriptions.Item label="Ac">{inspection.accept_number ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Re">{inspection.reject_number ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="缺陷数">{inspection.defect_qty}</Descriptions.Item>
          <Descriptions.Item label="检验日期">{inspection.inspection_date || "—"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Divider />

      {inspection.status === "inspecting" && !isViewer && (
        <Card title="录入检验结果">
          <Form form={itemForm} onFinish={handleUpdateItems} layout="vertical">
            <Form.Item
              name="items"
              rules={[{ required: true, message: "请录入检验项目结果" }]}
            >
              <TextArea
                rows={6}
                placeholder={`请输入检验项目结果，JSON格式：
[
  {"item_id": "...", "defect_qty": 0, "result": "accepted", "remark": ""},
  ...
]`}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              提交结果
            </Button>
          </Form>
        </Card>
      )}

      {inspection.status === "inspecting" && !isViewer && (
        <Card title="判定" style={{ marginTop: 16 }}>
          <Form form={judgeForm} onFinish={handleJudge} layout="vertical">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item
                  name="inspection_result"
                  label="检验结果"
                  rules={[{ required: true }]}
                >
                  <Select placeholder="选择结果">
                    <Option value="accepted">合格</Option>
                    <Option value="rejected">拒收</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="defect_qty" label="缺陷数" initialValue={0}>
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="sample_qty" label="实际样本量">
                  <InputNumber min={0} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="defect_description" label="缺陷描述">
              <TextArea rows={3} />
            </Form.Item>
            <Button type="primary" htmlType="submit" icon={<CheckCircleOutlined />}>
              提交判定
            </Button>
          </Form>
        </Card>
      )}

      <Divider />

      <Card title="检验项目">
        <Table
          rowKey="item_id"
          columns={itemColumns}
          dataSource={inspection.items || []}
          scroll={{ x: 1200 }}
          pagination={false}
        />
      </Card>
    </div>
  );
}
