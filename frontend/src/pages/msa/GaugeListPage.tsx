import { useState, useEffect, useCallback } from "react";
import {
  Table,
  Button,
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
  Drawer,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  EditOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { usePermission } from "../../hooks/usePermission";
import type { Gauge } from "../../types";
import { listGauges, getExpiringGauges, createGauge, deleteGauge } from "../../api/msa";
import dayjs from "dayjs";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const { Option } = Select;

const STATUS_MAP: Record<string, { label: string; status: string }> = {
  active: { label: "在用", status: "success" },
  inactive: { label: "闲置", status: "draft" },
  calibrating: { label: "校准中", status: "info" },
  scrapped: { label: "报废", status: "error" },
};

export default function GaugeListPage() {
  const navigate = useNavigate();
  const { canEdit } = usePermission();

  const [gauges, setGauges] = useState<Gauge[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [filterSearch, setFilterSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterDepartment, setFilterDepartment] = useState<string | undefined>();

  const [expiryDrawerOpen, setExpiryDrawerOpen] = useState(false);
  const [expiryGauges, setExpiryGauges] = useState<Gauge[]>([]);
  const [expiryLoading, setExpiryLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalForm] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const fetchGauges = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterSearch) params.search = filterSearch;
      if (filterStatus) params.status = filterStatus;
      if (filterDepartment) params.department = filterDepartment;
      const resp = await listGauges(params);
      setGauges(resp.items);
      setTotal(resp.total);
    } catch {
      message.error("加载量具列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterSearch, filterStatus, filterDepartment]);

  useEffect(() => {
    fetchGauges();
  }, [fetchGauges]);

  const handleOpenExpiryDrawer = async () => {
    setExpiryDrawerOpen(true);
    setExpiryLoading(true);
    try {
      const resp = await getExpiringGauges(30);
      setExpiryGauges(resp.items);
    } catch {
      message.error("加载到期提醒失败");
    } finally {
      setExpiryLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteGauge(id);
      message.success("量具已删除");
      fetchGauges();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || "删除失败");
    }
  };

  const handleCreate = async () => {
    try {
      const values = await modalForm.validateFields();
      setSaving(true);
      await createGauge({
        ...values,
        next_calibration_date: values.next_calibration_date
          ? values.next_calibration_date.format("YYYY-MM-DD")
          : null,
      });
      message.success("量具已创建");
      setModalOpen(false);
      modalForm.resetFields();
      fetchGauges();
    } catch (err: unknown) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error("创建失败");
    } finally {
      setSaving(false);
    }
  };

  const activeCount = gauges.filter((g) => g.status === "active").length;
  const expiringCount = gauges.filter((g) => {
    if (!g.next_calibration_date) return false;
    const days = dayjs(g.next_calibration_date).diff(dayjs(), "day");
    return days <= 30 && days >= 0;
  }).length;

  const columns = [
    {
      title: "量具编号",
      dataIndex: "gauge_no",
      width: 160,
      render: (no: string) => <span className="qf-mono">{no}</span>,
    },
    { title: "名称", dataIndex: "name", width: 180 },
    { title: "型号", dataIndex: "model", render: (v: string | null) => v || "—" },
    { title: "部门", dataIndex: "department", width: 120, render: (v: string | null) => v || "—" },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_MAP[status];
        return <StatusBadge status={cfg?.status || "draft"}>{cfg?.label || status}</StatusBadge>;
      },
    },
    {
      title: "下次校准",
      dataIndex: "next_calibration_date",
      width: 140,
      render: (v: string | null) => {
        if (!v) return "—";
        const days = dayjs(v).diff(dayjs(), "day");
        const isExpiringSoon = days <= 30;
        return (
          <span style={isExpiringSoon ? { color: "var(--qf-red)", fontWeight: 500 } : {}}>
            {dayjs(v).format("YYYY-MM-DD")}
            {isExpiringSoon && days >= 0 && <span style={{ marginLeft: 4, fontSize: 12 }}>({days}天)</span>}
            {days < 0 && <span style={{ marginLeft: 4, fontSize: 12, color: "var(--qf-red)" }}>(已过期)</span>}
          </span>
        );
      },
    },
    {
      title: "操作",
      width: 200,
      render: (_: unknown, record: Gauge) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/msa/gauges/${record.gauge_id}`)}
          >
            查看
          </Button>
          {canEdit('msa') && (
            <>
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => navigate(`/msa/gauges/${record.gauge_id}`)}
              >
                编辑
              </Button>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => handleDelete(record.gauge_id)}
              >
                删除
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <PageShell title="量具管理" subtitle="MSA 测量系统分析 · 量具台账与校准跟踪">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <DataCard title="量具总数" noPadding>
            <Statistic
              value={total}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-text-primary)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="在用" noPadding>
            <Statistic
              value={activeCount}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-green)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="闲置/其他" noPadding>
            <Statistic
              value={total - activeCount}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-text-secondary)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard
            title="30天内到期"
            noPadding
            elevated={expiringCount > 0}
            style={{ cursor: "pointer" }}
            onClick={handleOpenExpiryDrawer}
          >
            <Statistic
              value={expiringCount}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: expiringCount > 0 ? "var(--qf-red)" : "var(--qf-text-primary)" }}
            />
          </DataCard>
        </Col>
      </Row>

      <DataCard
        title="量具台账"
        extra={
          <Space>
            {canEdit('msa') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
                新增量具
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchGauges}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder="搜索编号 / 名称"
            allowClear
            style={{ width: 220 }}
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            onPressEnter={() => setPage(1)}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 140 }}
            value={filterStatus}
            onChange={(v) => {
              setFilterStatus(v || undefined);
              setPage(1);
            }}
          >
            <Option value="active">在用</Option>
            <Option value="inactive">闲置</Option>
            <Option value="calibrating">校准中</Option>
            <Option value="scrapped">报废</Option>
          </Select>
          <Select
            placeholder="部门"
            allowClear
            style={{ width: 140 }}
            value={filterDepartment}
            onChange={(v) => {
              setFilterDepartment(v || undefined);
              setPage(1);
            }}
          >
            <Option value="IQC">IQC</Option>
            <Option value="PQC">PQC</Option>
            <Option value="OQC">OQC</Option>
            <Option value="实验室">实验室</Option>
          </Select>
          <Button type="primary" onClick={() => setPage(1)}>
            查询
          </Button>
        </Space>

        <Table
          className="qf-table"
          rowKey="gauge_id"
          columns={columns}
          dataSource={gauges}
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
      </DataCard>

      <Drawer
        title="量具校准到期提醒（30天内）"
        open={expiryDrawerOpen}
        onClose={() => setExpiryDrawerOpen(false)}
        width={640}
      >
        <Table
          className="qf-table"
          rowKey="gauge_id"
          dataSource={expiryGauges}
          loading={expiryLoading}
          pagination={false}
          columns={[
            { title: "编号", dataIndex: "gauge_no", width: 140, render: (v: string) => <span className="qf-mono">{v}</span> },
            { title: "名称", dataIndex: "name" },
            {
              title: "到期日",
              dataIndex: "next_calibration_date",
              render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
            },
            {
              title: "剩余天数",
              render: (_: unknown, record: Gauge) => {
                const days = dayjs(record.next_calibration_date).diff(dayjs(), "day");
                return (
                  <span style={{ color: days <= 7 ? "var(--qf-red)" : undefined, fontWeight: days <= 7 ? 600 : undefined }}>
                    {days}天
                  </span>
                );
              },
            },
          ]}
        />
      </Drawer>

      <Modal
        title="新增量具"
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          modalForm.resetFields();
        }}
        onOk={handleCreate}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
        okButtonProps={{ className: "qf-btn-primary" }}
      >
        <Form form={modalForm} layout="vertical">
          <Form.Item label="量具编号" name="gauge_no" rules={[{ required: true, message: "请输入编号" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="名称" name="name" rules={[{ required: true, message: "请输入名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item label="型号" name="model">
            <Input />
          </Form.Item>
          <Form.Item label="制造商" name="manufacturer">
            <Input />
          </Form.Item>
          <Form.Item label="分辨力" name="resolution">
            <Input type="number" />
          </Form.Item>
          <Form.Item label="测量范围" name="measuring_range">
            <Input placeholder="如: 0-150mm" />
          </Form.Item>
          <Form.Item label="部门" name="department">
            <Select allowClear placeholder="选择部门">
              <Option value="IQC">IQC</Option>
              <Option value="PQC">PQC</Option>
              <Option value="OQC">OQC</Option>
              <Option value="实验室">实验室</Option>
            </Select>
          </Form.Item>
          <Form.Item label="存放位置" name="location">
            <Input />
          </Form.Item>
          <Form.Item label="校准周期（天）" name="calibration_cycle_days">
            <Input type="number" />
          </Form.Item>
          <Form.Item label="下次校准日期" name="next_calibration_date">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
