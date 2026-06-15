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
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { usePermission } from "../../hooks/usePermission";
import type { MsaStudyOverview } from "../../types";
import { listMsaStudies, deleteGrrStudy, deleteBiasStudy, deleteLinearityStudy, deleteStabilityStudy, deleteAttributeStudy } from "../../api/msa";
import dayjs from "dayjs";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const { Option } = Select;

export default function MsaStudyListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation("msa");
  const { t: tc } = useTranslation("common");
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

  const statusLabel = (status: string) => t(`study.status.${status}`, { defaultValue: status });
  const statusVariant = (status: string): string => {
    switch (status) {
      case "completed": return "success";
      case "ongoing": return "warning";
      case "draft": return "info";
      default: return "info";
    }
  };
  const typeLabel = (type: string) => t(`study.type.${type}`, { defaultValue: type });
  const typeVariant = (type: string): string => {
    switch (type) {
      case "GRR": return "info";
      case "偏倚": return "normal";
      case "线性": return "warning";
      case "稳定性": return "rework";
      case "计数型": return "success";
      default: return "draft";
    }
  };

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
        GRR: deleteGrrStudy,
        偏倚: deleteBiasStudy,
        线性: deleteLinearityStudy,
        稳定性: deleteStabilityStudy,
        计数型: deleteAttributeStudy,
      };
      const fn = typeMap[record.type];
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
      title: t("study.columns.studyNo"),
      dataIndex: "study_no",
      width: 160,
      render: (no: string) => <span className="qf-mono">{no}</span>,
    },
    {
      title: t("study.columns.type"),
      dataIndex: "type",
      width: 90,
      render: (type: string) => {
        return <StatusBadge status={typeVariant(type)}>{typeLabel(type)}</StatusBadge>;
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
        return <StatusBadge status={statusVariant(status)}>{statusLabel(status)}</StatusBadge>;
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
    bias: studies.filter((s) => s.type === "偏倚").length,
    linearity: studies.filter((s) => s.type === "线性").length,
    stability: studies.filter((s) => s.type === "稳定性").length,
    attribute: studies.filter((s) => s.type === "计数型").length,
  };

  return (
    <PageShell title={t("study.title")} subtitle={t("title")}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <DataCard title={t("study.counts.grr")} noPadding>
            <Statistic
              value={counts.grr}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-cyan)" }}
            />
          </DataCard>
        </Col>
        <Col span={5}>
          <DataCard title={t("study.counts.bias")} noPadding>
            <Statistic
              value={counts.bias}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-blue)" }}
            />
          </DataCard>
        </Col>
        <Col span={5}>
          <DataCard title={t("study.counts.linearity")} noPadding>
            <Statistic
              value={counts.linearity}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-purple)" }}
            />
          </DataCard>
        </Col>
        <Col span={5}>
          <DataCard title={t("study.counts.stability")} noPadding>
            <Statistic
              value={counts.stability}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-amber)" }}
            />
          </DataCard>
        </Col>
        <Col span={5}>
          <DataCard title={t("study.counts.attribute")} noPadding>
            <Statistic
              value={counts.attribute}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-green)" }}
            />
          </DataCard>
        </Col>
      </Row>

      <DataCard
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
            <Option value="GRR">{t("study.type.grr")}</Option>
            <Option value="偏倚">{t("study.type.bias")}</Option>
            <Option value="线性">{t("study.type.linearity")}</Option>
            <Option value="稳定性">{t("study.type.stability")}</Option>
            <Option value="计数型">{t("study.type.attribute")}</Option>
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
          className="qf-table"
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
      </DataCard>

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
            <Select placeholder={t("study.placeholders.selectType", { defaultValue: "选择研究类型" })}>
              <Option value="grr">{t("study.type.grr")}（{t("study.method.average_range")}）</Option>
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
    </PageShell>
  );
}
