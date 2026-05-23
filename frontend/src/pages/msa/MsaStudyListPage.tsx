import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Input,
  Select,
  message,
  Row,
  Col,
  Statistic,
  Modal,
  Form,
  DatePicker,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import type { MsaStudyOverview } from "../../types";
import { listMsaStudies, deleteGrrStudy, deleteBiasStudy, deleteLinearityStudy, deleteStabilityStudy, deleteAttributeStudy } from "../../api/msa";
import dayjs from "dayjs";

const { Option } = Select;

const TYPE_MAP: Record<string, { label: string; color: string }> = {
  GRR: { label: "GRR", color: "blue" },
  偏倚: { label: "偏倚", color: "cyan" },
  线性: { label: "线性", color: "purple" },
  稳定性: { label: "稳定性", color: "orange" },
  计数型: { label: "计数型", color: "green" },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "default" },
  ongoing: { label: "进行中", color: "processing" },
  completed: { label: "已完成", color: "success" },
};

export default function MsaStudyListPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isViewer = user?.role === "viewer";
  const isEngineerOrAbove =
    user?.role === "quality_engineer" ||
    user?.role === "manager" ||
    user?.role === "admin";

  const [studies, setStudies] = useState<MsaStudyOverview[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [filterSearch, setFilterSearch] = useState("");
  const [filterType, setFilterType] = useState<string | undefined>();
  const [filterStatus, setFilterStatus] = useState<string | undefined>();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  const fetchStudies = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterType) params.type = filterType;
      if (filterStatus) params.status = filterStatus;
      const resp = await listMsaStudies(params);
      let items = resp.items;
      if (filterSearch) {
        const s = filterSearch.toLowerCase();
        items = items.filter(
          (i) =>
            i.study_no.toLowerCase().includes(s) ||
            i.title.toLowerCase().includes(s) ||
            (i.gauge_name && i.gauge_name.toLowerCase().includes(s))
        );
      }
      setStudies(items);
      setTotal(resp.total);
    } catch {
      message.error("加载研究列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterSearch, filterType, filterStatus]);

  useEffect(() => {
    fetchStudies();
  }, [fetchStudies]);

  const handleDelete = async (record: MsaStudyOverview) => {
    try {
      const typeMap: Record<string, (id: string) => Promise<void>> = {
        GRR: deleteGrrStudy,
        偏倚: deleteBiasStudy,
        线性: deleteLinearityStudy,
        稳定性: deleteStabilityStudy,
        计数型: deleteAttributeStudy,
      };
      const fn = typeMap[record.type];
      if (!fn) return;
      await fn(record.study_id);
      message.success("研究已删除");
      fetchStudies();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "删除失败");
    }
  };

  const typeToRoute = (type: string): string => {
    switch (type) {
      case "GRR": return "grr";
      case "偏倚": return "bias";
      case "线性": return "linearity";
      case "稳定性": return "stability";
      case "计数型": return "attribute";
      default: return "grr";
    }
  };

  const columns = [
    {
      title: "研究编号",
      dataIndex: "study_no",
      width: 160,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    {
      title: "类型",
      dataIndex: "type",
      width: 90,
      render: (type: string) => {
        const cfg = TYPE_MAP[type];
        return <Tag color={cfg?.color}>{cfg?.label || type}</Tag>;
      },
    },
    { title: "标题", dataIndex: "title" },
    {
      title: "关联量具",
      dataIndex: "gauge_name",
      render: (v: string | null) => v || "—",
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <Tag color={cfg?.color}>{cfg?.label || status}</Tag>;
      },
    },
    {
      title: "研究日期",
      dataIndex: "study_date",
      width: 120,
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "—"),
    },
    {
      title: "操作",
      width: 160,
      render: (_: unknown, record: MsaStudyOverview) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/msa/studies/${typeToRoute(record.type)}/${record.study_id}`)}
          >
            查看
          </Button>
          {isEngineerOrAbove && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            >
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const counts = {
    grr: studies.filter((s) => s.type === "GRR").length,
    bias: studies.filter((s) => s.type === "偏倚").length,
    linearity: studies.filter((s) => s.type === "线性").length,
    stability: studies.filter((s) => s.type === "稳定性").length,
    attribute: studies.filter((s) => s.type === "计数型").length,
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic title="GRR" value={counts.grr} valueStyle={{ color: "#1890ff" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title="偏倚" value={counts.bias} valueStyle={{ color: "#13c2c2" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title="线性" value={counts.linearity} valueStyle={{ color: "#722ed1" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title="稳定性" value={counts.stability} valueStyle={{ color: "#fa8c16" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title="计数型" value={counts.attribute} valueStyle={{ color: "#52c41a" }} />
          </Card>
        </Col>
      </Row>

      <Card
        title="MSA 研究管理"
        extra={
          <Space>
            {!isViewer && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                新建研究
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchStudies}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder="搜索编号 / 标题 / 量具"
            allowClear
            style={{ width: 220 }}
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            onPressEnter={() => setPage(1)}
          />
          <Select
            placeholder="类型"
            allowClear
            style={{ width: 120 }}
            value={filterType}
            onChange={(v) => {
              setFilterType(v || undefined);
              setPage(1);
            }}
          >
            <Option value="GRR">GRR</Option>
            <Option value="偏倚">偏倚</Option>
            <Option value="线性">线性</Option>
            <Option value="稳定性">稳定性</Option>
            <Option value="计数型">计数型</Option>
          </Select>
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => {
              setFilterStatus(v || undefined);
              setPage(1);
            }}
          >
            <Option value="draft">草稿</Option>
            <Option value="ongoing">进行中</Option>
            <Option value="completed">已完成</Option>
          </Select>
          <Button type="primary" onClick={() => setPage(1)}>
            查询
          </Button>
        </Space>

        <Table
          rowKey="study_id"
          columns={columns}
          dataSource={studies}
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps || 20);
            },
          }}
        />
      </Card>

      <Modal
        title="新建 MSA 研究"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        footer={null}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item label="研究类型" name="study_type" rules={[{ required: true }]}>
            <Select placeholder="选择研究类型">
              <Option value="grr">GRR（重复性与再现性）</Option>
              <Option value="bias">偏倚</Option>
              <Option value="linearity">线性</Option>
              <Option value="stability">稳定性</Option>
              <Option value="attribute">计数型</Option>
            </Select>
          </Form.Item>
          <Button
            type="primary"
            block
            onClick={() => {
              const type = createForm.getFieldValue("study_type");
              if (!type) {
                message.error("请选择研究类型");
                return;
              }
              navigate(`/msa/studies/${type}/new`);
            }}
          >
            下一步
          </Button>
        </Form>
      </Modal>
    </div>
  );
}
