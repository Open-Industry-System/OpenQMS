import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
import { usePermission } from "../../hooks/usePermission";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;

export default function SPCListPage() {
  const { t } = useTranslation("spc");
  const { t: tc } = useTranslation("common");
  const { t: tv } = useTranslation("validation");
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

  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();
  const productLine = useProductLineStore((s) => s.selected);

  const chartTypeLabel = (type: string) => t(`chartType.${type}`, { defaultValue: type });

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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      message.success(t("list.createSuccess"));
      setModalOpen(false);
      form.resetFields();
      navigate(`/spc/${ic.ic_id}`);
    } catch {
      message.error(t("list.createFailed"));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteInspectionCharacteristic(id);
      message.success(t("list.deleteSuccess"));
      fetchData();
    } catch {
      message.error(t("list.deleteFailed"));
    }
  };

  const totalCount = data.length;
  const lockedCount = data.filter((d) => d.control_limits_locked).length;

  const columns = [
    {
      title: t("list.columns.characteristic_name"),
      dataIndex: "characteristic_name",
      key: "characteristic_name",
      ellipsis: true,
    },
    {
      title: t("list.columns.process_name"),
      dataIndex: "process_name",
      key: "process_name",
      width: 140,
    },
    {
      title: t("list.columns.chart_type"),
      dataIndex: "chart_type",
      key: "chart_type",
      width: 120,
      render: (t: string) => chartTypeLabel(t),
    },
    {
      title: t("list.columns.spec_upper"),
      dataIndex: "spec_upper",
      key: "spec_upper",
      width: 100,
    },
    {
      title: t("list.columns.spec_lower"),
      dataIndex: "spec_lower",
      key: "spec_lower",
      width: 100,
    },
    {
      title: t("list.columns.control_limits_locked"),
      dataIndex: "control_limits_locked",
      key: "control_limits_locked",
      width: 120,
      render: (locked: boolean) => (
        <Tag color={locked ? "green" : "orange"}>
          {locked ? t("list.limitStatus.locked") : t("list.limitStatus.auto")}
        </Tag>
      ),
    },
    {
      title: t("list.columns.updated_at"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 170,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: tc("table.operations"),
      key: "actions",
      width: 160,
      render: (_: unknown, record: InspectionCharacteristic) => (
        <>
          <Button
            type="link"
            icon={<FileTextOutlined />}
            onClick={() => navigate(`/spc/${record.ic_id}`)}
          >
            {t("list.view")}
          </Button>
          {canEdit('spc') && (
            <Popconfirm title={t("list.confirmDelete")} onConfirm={() => handleDelete(record.ic_id)}>
              <Button type="link" danger icon={<DeleteOutlined />}>
                {tc("actions.delete")}
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
              title={t("list.totalCharacteristics")}
              value={totalCount}
              prefix={<AreaChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("list.lockedLimits")}
              value={lockedCount}
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("list.unlockedLimits")}
              value={totalCount - lockedCount}
              prefix={<AlertOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("list.newBatchesThisWeek")}
              value="-"
              prefix={<BarChartOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>{t("list.title")}</Title>
          <Input.Search
            placeholder={t("list.searchPlaceholder")}
            allowClear
            onSearch={(v) => {
              setSearchProcess(v);
              setPage(1);
              fetchData(1);
            }}
            style={{ width: 240 }}
          />
        </Space>
        {canEdit('spc') && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            {t("list.newCharacteristic")}
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
        title={t("list.newCharacteristic")}
        open={modalOpen}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="process_name"
            label={t("list.form.process_name")}
            rules={[{ required: true, message: tv("required", { field: t("list.form.process_name") }) }]}
          >
            <Input placeholder={t("list.form.processPlaceholder")} />
          </Form.Item>
          <Form.Item
            name="characteristic_name"
            label={t("list.form.characteristic_name")}
            rules={[{ required: true, message: tv("required", { field: t("list.form.characteristic_name") }) }]}
          >
            <Input placeholder={t("list.form.characteristicPlaceholder")} />
          </Form.Item>
          <Form.Item
            name="chart_type"
            label={t("list.form.chart_type")}
            initialValue="xbar_r"
            rules={[{ required: true }]}
          >
            <Select onChange={(v) => setCreateChartType(v)}>
              <Select.Option value="xbar_r">{chartTypeLabel("xbar_r")}</Select.Option>
              <Select.Option value="imr">{chartTypeLabel("imr")}</Select.Option>
              <Select.Option value="p">{chartTypeLabel("p")}</Select.Option>
              <Select.Option value="np">{chartTypeLabel("np")}</Select.Option>
              <Select.Option value="c">{chartTypeLabel("c")}</Select.Option>
              <Select.Option value="u">{chartTypeLabel("u")}</Select.Option>
            </Select>
          </Form.Item>
          {!["p", "np", "c", "u"].includes(createChartType) && (
            <Form.Item name="subgroup_size" label={t("list.form.subgroup_size")} initialValue={5}>
              <Input type="number" min={1} />
            </Form.Item>
          )}
          {["np", "c"].includes(createChartType) && (
            <Form.Item>
              <Alert type="info" showIcon message={t("list.form.fixedSampleAlert")} />
            </Form.Item>
          )}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="spec_lower"
                label={t("list.form.spec_lower")}
                rules={[{ required: true, message: tv("required", { field: t("list.form.spec_lower") }) }]}
              >
                <Input type="number" step="0.01" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="spec_upper"
                label={t("list.form.spec_upper")}
                rules={[{ required: true, message: tv("required", { field: t("list.form.spec_upper") }) }]}
              >
                <Input type="number" step="0.01" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="target_value"
                label={t("list.form.target_value")}
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
