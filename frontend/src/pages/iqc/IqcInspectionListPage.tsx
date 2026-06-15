import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Card,
  Table,
  Button,
  Tag,
  Space,
  Input,
  Select,
  App,
  Row,
  Col,
  Statistic,
} from "antd";
import {
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { usePermission } from "../../hooks/usePermission";
import type { IqcInspection, IqcStats } from "../../types";
import { listInspections, getIqcStats } from "../../api/iqc";

const { Option } = Select;

export default function IqcInspectionListPage() {
  const { t } = useTranslation("iqc");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const { canEdit } = usePermission();

  const [inspections, setInspections] = useState<IqcInspection[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [stats, setStats] = useState<IqcStats>({
    total_inspections: 0,
    accepted_count: 0,
    rejected_count: 0,
    concession_count: 0,
    acceptance_rate: 0,
    rejection_rate: 0,
  });

  const [filterStatus, setFilterStatus] = useState<string | undefined>();
  const [filterResult, setFilterResult] = useState<string | undefined>();
  const [keyword, setKeyword] = useState("");

  const statusMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t("status.inspection.pending"), color: "orange" },
      inspecting: { label: t("status.inspection.inspecting"), color: "blue" },
      judged: { label: t("status.inspection.judged"), color: "cyan" },
      closed: { label: t("status.inspection.closed"), color: "default" },
    }),
    [t]
  );

  const resultMap = useMemo<Record<string, { label: string; color: string }>>(
    () => ({
      pending: { label: t("status.result.pending"), color: "default" },
      accepted: { label: t("status.result.accepted"), color: "green" },
      rejected: { label: t("status.result.rejected"), color: "red" },
      concession: { label: t("status.result.concession"), color: "gold" },
    }),
    [t]
  );

  const fetchStats = useCallback(async () => {
    try {
      const s = await getIqcStats();
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  const fetchInspections = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (filterStatus) params.status = filterStatus;
      if (filterResult) params.inspection_result = filterResult;
      if (keyword) params.keyword = keyword;
      const resp = await listInspections(params);
      setInspections(resp.items);
      setTotal(resp.total);
    } catch {
      message.error(t("messages.loadInspectionListFailed"));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, filterStatus, filterResult, keyword]);

  useEffect(() => {
    Promise.all([fetchInspections(), fetchStats()]);
  }, [fetchInspections, fetchStats]);

  const handleRefresh = () => {
    fetchInspections();
    fetchStats();
  };

  const handleQuery = () => {
    setPage(1);
    fetchInspections();
  };

  const columns = useMemo(
    () => [
      {
        title: t("table.inspectionNo"),
        dataIndex: "inspection_no",
        width: 160,
        render: (no: string) => <span style={{ fontFamily: "monospace" }}>{no}</span>,
      },
      {
        title: t("table.partNo"),
        dataIndex: "part_no",
        width: 140,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.partName"),
        dataIndex: "part_name",
        ellipsis: true,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.lotNo"),
        dataIndex: "lot_no",
        width: 120,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.lotQty"),
        dataIndex: "lot_qty",
        width: 80,
        render: (v: number | null) => v || "—",
      },
      {
        title: t("table.inspectionMode"),
        dataIndex: "inspection_mode",
        width: 100,
        render: (mode: string) =>
          mode === "quick" ? t("inspectionMode.quick") : t("inspectionMode.detailed"),
      },
      {
        title: t("table.status"),
        dataIndex: "status",
        width: 100,
        render: (status: string) => {
          const cfg = statusMap[status];
          return <Tag color={cfg?.color}>{cfg?.label || status}</Tag>;
        },
      },
      {
        title: t("table.inspectionResult"),
        dataIndex: "inspection_result",
        width: 100,
        render: (result: string) => {
          const cfg = resultMap[result];
          return <Tag color={cfg?.color}>{cfg?.label || result}</Tag>;
        },
      },
      {
        title: t("table.inspectionDate"),
        dataIndex: "inspection_date",
        width: 120,
        render: (v: string | null) => v || "—",
      },
      {
        title: t("table.operations"),
        width: 100,
        render: (_: unknown, record: IqcInspection) => (
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/iqc/inspections/${record.inspection_id}`)}
          >
            {tc("actions.view")}
          </Button>
        ),
      },
    ],
    [t, tc, statusMap, resultMap, navigate]
  );

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title={t("stats.totalInspections")} value={stats.total_inspections} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("stats.acceptedCount")}
              value={stats.accepted_count}
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("stats.rejectedCount")}
              value={stats.rejected_count}
              valueStyle={{ color: "#ff4d4f" }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={t("stats.acceptanceRate")}
              value={stats.acceptance_rate}
              suffix="%"
              precision={1}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={t("pageTitle.inspectionList")}
        extra={
          <Space>
            {canEdit('iqc') && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => navigate("/iqc/inspections/new")}
              >
                {t("actions.newInspection")}
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              {tc("actions.refresh")}
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder={t("placeholder.inspectionSearch")}
            allowClear
            style={{ width: 240 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Select
            placeholder={t("placeholder.selectStatus")}
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => setFilterStatus(v || undefined)}
          >
            <Option value="pending">{t("status.inspection.pending")}</Option>
            <Option value="inspecting">{t("status.inspection.inspecting")}</Option>
            <Option value="judged">{t("status.inspection.judged")}</Option>
            <Option value="closed">{t("status.inspection.closed")}</Option>
          </Select>
          <Select
            placeholder={t("placeholder.selectResult")}
            allowClear
            style={{ width: 120 }}
            value={filterResult}
            onChange={(v) => setFilterResult(v || undefined)}
          >
            <Option value="accepted">{t("status.result.accepted")}</Option>
            <Option value="rejected">{t("status.result.rejected")}</Option>
            <Option value="concession">{t("status.result.concession")}</Option>
          </Select>
          <Button type="primary" onClick={handleQuery}>
            {tc("actions.search")}
          </Button>
        </Space>

        <Table
          rowKey="inspection_id"
          columns={columns}
          dataSource={inspections}
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
    </div>
  );
}
