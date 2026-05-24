import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Table, Button, Tag, Typography, Modal, Form, Input, Select,
  Popconfirm, App, Card, Row, Col, Statistic, Space, Alert,
} from "antd";
import {
  PlusOutlined, FileTextOutlined, DeleteOutlined,
  AreaChartOutlined, AlertOutlined, BarChartOutlined,
} from "@ant-design/icons";
import {
  listInspectionCharacteristics,
  createInspectionCharacteristic,
  deleteInspectionCharacteristic,
} from "../../api/spc";
import type { InspectionCharacteristic } from "../../types";
import { useAuthStore } from "../../store/authStore";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;

const chartTypeLabels: Record<string, string> = {
  xbar_r: "X-bar R（均值-极差图）",
  imr: "I-MR（单值移动极差图）",
  histogram: "直方图",
  p: "P图（不合格率）",
  np: "NP图（不合格品数）",
  c: "C图（缺陷数）",
  u: "U图（单位缺陷数）",
};

export default function SPCListPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<InspectionCharacteristic[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [searchProcess, setSearchProcess] = useState("");
  const [createChartType, setCreateChartType] = useState<string>("xbar_r");
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role !== "viewer";
  const productLine = useProductLineStore((s) => s.selected);

  const fetchData = (p: number = page) => {
    setLoading(true);
    listInspectionCharacteristics({
      page: p,
      page_size: 20,
      product_line: productLine || undefined,
      process_name: searchProcess || undefined,
    })
      .then((res) => {
        setData(res.items);
        setTotal(res.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData(1);
  }, [productLine]);

  const handleCreate = async (values: {
    process_name: string;
    characteristic_name: string;
    chart_type: "xbar_r" | "imr" | "histogram" | "p" | "np" | "c" | "u";
    subgroup_size: number;
    spec_lower: number;
    spec_upper: number;
    target_value?: number;
  }) => {
    try {
      const ic = await createInspectionCharacteristic({
        ...values,
        subgroup_size: ["p", "np", "c", "u"].includes(values.chart_type)
          ? 0
          : values.subgroup_size || (values.chart_type === "xbar_r" ? 5 : 1),
      });
      message.success("检验特性创建成功");
      setModalOpen(false);
      form.resetFields();
      navigate(`/spc/${ic.ic_id}`);
    } catch {
      message.error("创建失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteInspectionCharacteristic(id);
      message.success("删除成功");
      fetchData();
    } catch {
      message.error("删除失败");
    }
  };

  const totalCount = data.length;
  const lockedCount = data.filter((d) => d.control_limits_locked).length;

  const columns = [
    {
      title: "特性名称",
      dataIndex: "characteristic_name",
      key: "characteristic_name",
      ellipsis: true,
    },
    {
      title: "过程名称",
      dataIndex: "process_name",
      key: "process_name",
      width: 140,
    },
    {
      title: "控制图类型",
      dataIndex: "chart_type",
      key: "chart_type",
      width: 120,
      render: (t: string) => chartTypeLabels[t] || t,
    },
    {
      title: "规格上限",
      dataIndex: "spec_upper",
      key: "spec_upper",
      width: 100,
    },
    {
      title: "规格下限",
      dataIndex: "spec_lower",
      key: "spec_lower",
      width: 100,
    },
    {
      title: "控制限状态",
      dataIndex: "control_limits_locked",
      key: "control_limits_locked",
      width: 120,
      render: (locked: boolean) => (
        <Tag color={locked ? "green" : "orange"}>
          {locked ? "已锁定" : "自动计算"}
        </Tag>
      ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "actions",
      width: 160,
      render: (_: unknown, record: InspectionCharacteristic) => (
        <>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => navigate(`/spc/${record.ic_id}`)}
          >
            查看
          </Button>
          {canEdit && (
            <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.ic_id)}>
              <Button type="link" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </>
      ),
    },
  ];

  return (
    <div>
      {/* KPI Cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="检验特性总数"
              value={totalCount}
              prefix={<AreaChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="控制限已锁定"
              value={lockedCount}
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="未锁定控制限"
              value={totalCount - lockedCount}
              prefix={<AlertOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="本周新增批次"
              value="-"
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>SPC 控制图</Title>
          <Input.Search
            placeholder="搜索过程名称"
            allowClear
            onSearch={(v) => {
              setSearchProcess(v);
              setPage(1);
              fetchData(1);
            }}
            style={{ width: 240 }}
          />
        </Space>
        {canEdit && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建检验特性
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="ic_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => {
            setPage(p);
            fetchData(p);
          },
        }}
      />

      <Modal
        title="新建检验特性"
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="process_name"
            label="过程名称"
            rules={[{ required: true, message: "请输入过程名称" }]}
          >
            <Input placeholder="如 SMT焊接" />
          </Form.Item>
          <Form.Item
            name="characteristic_name"
            label="特性名称"
            rules={[{ required: true, message: "请输入特性名称" }]}
          >
            <Input placeholder="如 焊点高度" />
          </Form.Item>
          <Form.Item
            name="chart_type"
            label="控制图类型"
            initialValue="xbar_r"
            rules={[{ required: true }]}
          >
            <Select onChange={(v) => setCreateChartType(v)}>
              <Select.Option value="xbar_r">X-bar R（均值-极差图）</Select.Option>
              <Select.Option value="imr">I-MR（单值移动极差图）</Select.Option>
              <Select.Option value="p">P图（不合格率）</Select.Option>
              <Select.Option value="np">NP图（不合格品数）</Select.Option>
              <Select.Option value="c">C图（缺陷数）</Select.Option>
              <Select.Option value="u">U图（单位缺陷数）</Select.Option>
            </Select>
          </Form.Item>
          {!["p", "np", "c", "u"].includes(createChartType) && (
            <Form.Item name="subgroup_size" label="子组大小" initialValue={5}>
              <Input type="number" min={1} />
            </Form.Item>
          )}
          {["np", "c"].includes(createChartType) && (
            <Form.Item>
              <Alert type="info" showIcon message="使用 NP图/C图 时，每批次样本量需保持固定一致" />
            </Form.Item>
          )}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="spec_lower"
                label="规格下限"
                rules={[{ required: true, message: "必填" }]}
              >
                <Input type="number" step="0.01" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="spec_upper"
                label="规格上限"
                rules={[{ required: true, message: "必填" }]}
              >
                <Input type="number" step="0.01" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="target_value"
                label="目标值"
              >
                <Input type="number" step="0.01" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
}
