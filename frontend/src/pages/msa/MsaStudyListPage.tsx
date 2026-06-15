import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
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
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { MsaStudyOverview } from "../../types";
import { listMsaStudies, deleteGrrStudy, deleteBiasStudy, deleteLinearityStudy, deleteStabilityStudy, deleteAttributeStudy } from "../../api/msa";
import dayjs from "dayjs";

const { Option } = Select;

interface TypeMapping {
  backend: string;
  route: string;
}

export default function MsaStudyListPage() {
  const { t } = useTranslation("msa");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const _user = useAuthStore((s) => s.user);
  const { canEdit } = usePermission();

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
  const [_creating, _setCreating] = useState(false);

  const typeMapping = t("study.typeMapping", { returnObjects: true }) as TypeMapping[];
  const routeOfType = (type: string) => typeMapping.find((m) => m.backend === type)?.route || "grr";
  const typeLabel = (type: string) => t(`study.type.${routeOfType(type)}`, { defaultValue: type });
  const statusLabel = (status: string) => t(`study.status.${status}`, { defaultValue: status });

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
      message.error(t("study.listLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterSearch, filterType, filterStatus, t]);

  useEffect(() => {
    fetchStudies();
  }, [fetchStudies]);

  const handleDelete = async (record: MsaStudyOverview) => {
    try {
      const typeMap: Record<string, (id: string) => Promise<void>> = {
        grr: deleteGrrStudy,
        bias: deleteBiasStudy,
        linearity: deleteLinearityStudy,
        stability: deleteStabilityStudy,
        attribute: deleteAttributeStudy,
      };
      const route = routeOfType(record.type);
      const fn = typeMap[route];
      if (!fn) return;
      await fn(record.study_id);
      message.success(t("study.deleteSuccess"));
      fetchStudies();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      message.error(err.response?.data?.detail || t("study.deleteFailed"));
    }
  };

  const typeToRoute = (type: string): string => {
    return routeOfType(type);
  };

  const columns = [
    {
      title: t("study.columns.studyNo"),
      dataIndex: "study_no",
      width: 160,
      render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
    },
    {
      title: t("study.columns.type"),
      dataIndex: "type",
      width: 90,
      render: (type: string) => {
        const route = routeOfType(type);
        const color = route === "grr" ? "blue" : route === "bias" ? "cyan" : route === "linearity" ? "purple" : route === "stability" ? "orange" : "green";
        return <Tag color={color}>{typeLabel(type)}</Tag>;
      },
    },
    { title: t("study.columns.title"), dataIndex: "title" },
    {
      title: t("study.columns.gauge"),
      dataIndex: "gauge_name",
      render: (v: string | null) => v || "—",
    },
    {
      title: t("study.columns.status"),
      dataIndex: "status",
      width: 100,
      render: (status: string) => {
        const color = status === "draft" ? "default" : status === "ongoing" ? "processing" : "success";
        return <Tag color={color}>{statusLabel(status)}</Tag>;
      },
    },
    {
      title: t("study.columns.studyDate"),
      dataIndex: "study_date",
      width: 120,
      render: (v: string | null) => (v ? dayjs(v).format("YYYY-MM-DD") : "—"),
    },
    {
      title: tc("table.operations"),
      width: 160,
      render: (_: unknown, record: MsaStudyOverview) => (
        <Space size="small">
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/msa/studies/${typeToRoute(record.type)}/${record.study_id}`)}
          >
            {tc("actions.view")}
          </Button>
          {canEdit('msa') && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            >
              {tc("actions.delete")}
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const counts = {
    grr: studies.filter((s) => s.type === "GRR").length,
    bias: studies.filter((s) => s.type === typeMapping.find((m) => m.route === "bias")?.backend).length,
    linearity: studies.filter((s) => s.type === typeMapping.find((m) => m.route === "linearity")?.backend).length,
    stability: studies.filter((s) => s.type === typeMapping.find((m) => m.route === "stability")?.backend).length,
    attribute: studies.filter((s) => s.type === typeMapping.find((m) => m.route === "attribute")?.backend).length,
  };

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card>
            <Statistic title={t("study.counts.grr")} value={counts.grr} valueStyle={{ color: "#1890ff" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title={t("study.counts.bias")} value={counts.bias} valueStyle={{ color: "#13c2c2" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title={t("study.counts.linearity")} value={counts.linearity} valueStyle={{ color: "#722ed1" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title={t("study.counts.stability")} value={counts.stability} valueStyle={{ color: "#fa8c16" }} />
          </Card>
        </Col>
        <Col span={5}>
          <Card>
            <Statistic title={t("study.counts.attribute")} value={counts.attribute} valueStyle={{ color: "#52c41a" }} />
          </Card>
        </Col>
      </Row>

      <Card
        title={t("study.title")}
        extra={
          <Space>
            {canEdit('msa') && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                {t("study.new")}
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={fetchStudies}>
              {tc("actions.refresh")}
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder={t("study.searchPlaceholder")}
            allowClear
            style={{ width: 220 }}
            value={filterSearch}
            onChange={(e) => setFilterSearch(e.target.value)}
            onPressEnter={() => setPage(1)}
          />
          <Select
            placeholder={t("study.columns.type")}
            allowClear
            style={{ width: 120 }}
            value={filterType}
            onChange={(v) => {
              setFilterType(v || undefined);
              setPage(1);
            }}
          >
                {typeMapping.map((m) => (
              <Option key={m.backend} value={m.backend}>{typeLabel(m.backend)}</Option>
            ))}
          </Select>
          <Select
            placeholder={t("study.columns.status")}
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => {
              setFilterStatus(v || undefined);
              setPage(1);
            }}
          >
            <Option value="draft">{t("study.status.draft")}</Option>
            <Option value="ongoing">{t("study.status.ongoing")}</Option>
            <Option value="completed">{t("study.status.completed")}</Option>
          </Select>
          <Button type="primary" onClick={() => setPage(1)}>
            {tc("actions.search")}
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
        title={t("study.new")}
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          createForm.resetFields();
        }}
        footer={null}
        destroyOnHidden
      >
        <Form form={createForm} layout="vertical">
          <Form.Item label={t("study.selectType")} name="study_type" rules={[{ required: true }]}>
            <Select placeholder={t("study.selectType")}>
              <Option value="grr">{t("study.type.grr")}（GRR）</Option>
              <Option value="bias">{t("study.type.bias")}</Option>
              <Option value="linearity">{t("study.type.linearity")}</Option>
              <Option value="stability">{t("study.type.stability")}</Option>
              <Option value="attribute">{t("study.type.attribute")}</Option>
            </Select>
          </Form.Item>
          <Button
            type="primary"
            block
            onClick={() => {
              const type = createForm.getFieldValue("study_type");
              if (!type) {
                message.error(t("study.selectTypeRequired"));
                return;
              }
              navigate(`/msa/studies/${type}/new`);
            }}
          >
            {t("study.next")}
          </Button>
        </Form>
      </Modal>
    </div>
  );
}
