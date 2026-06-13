import { useState, useEffect, useCallback } from "react";
import {
  Table,
  Button,
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
import { usePermission } from "../../hooks/usePermission";
import type { IqcInspection, IqcStats } from "../../types";
import { listInspections, getIqcStats } from "../../api/iqc";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const { Option } = Select;

const STATUS_MAP: Record<string, { label: string; status: string }> = {
  pending: { label: "待检验", status: "warning" },
  inspecting: { label: "检验中", status: "info" },
  judged: { label: "已判定", status: "normal" },
  closed: { label: "已关闭", status: "closed" },
};

const RESULT_MAP: Record<string, { label: string; status: string }> = {
  pending: { label: "待定", status: "draft" },
  accepted: { label: "合格", status: "success" },
  rejected: { label: "拒收", status: "error" },
  concession: { label: "让步接收", status: "warning" },
};

export default function IqcInspectionListPage() {
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
      message.error("加载检验单列表失败");
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

  const columns = [
    {
      title: "检验单号",
      dataIndex: "inspection_no",
      width: 160,
      render: (no: string) => <span className="qf-mono">{no}</span>,
    },
    {
      title: "物料号",
      dataIndex: "part_no",
      width: 140,
      render: (v: string | null) => v || "—",
    },
    {
      title: "物料名称",
      dataIndex: "part_name",
      ellipsis: true,
      render: (v: string | null) => v || "—",
    },
    {
      title: "批号",
      dataIndex: "lot_no",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "批量",
      dataIndex: "lot_qty",
      width: 80,
      render: (v: number | null) => v || "—",
    },
    {
      title: "检验模式",
      dataIndex: "inspection_mode",
      width: 100,
      render: (mode: string) => (mode === "quick" ? "快速检验" : "详细检验"),
    },
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
      title: "检验结果",
      dataIndex: "inspection_result",
      width: 100,
      render: (result: string) => {
        const cfg = RESULT_MAP[result];
        return <StatusBadge status={cfg?.status || "draft"}>{cfg?.label || result}</StatusBadge>;
      },
    },
    {
      title: "检验日期",
      dataIndex: "inspection_date",
      width: 120,
      render: (v: string | null) => v || "—",
    },
    {
      title: "操作",
      width: 100,
      render: (_: unknown, record: IqcInspection) => (
        <Button
          size="small"
          icon={<EyeOutlined />}
          onClick={() => navigate(`/iqc/inspections/${record.inspection_id}`)}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <PageShell title="来料检验" subtitle="IQC 检验单管理 · 合格 / 拒收 / 让步接收">
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <DataCard title="检验单总数" noPadding>
            <Statistic
              value={stats.total_inspections}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-text-primary)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="合格数" noPadding>
            <Statistic
              value={stats.accepted_count}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-green)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="拒收数" noPadding>
            <Statistic
              value={stats.rejected_count}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-red)" }}
            />
          </DataCard>
        </Col>
        <Col span={6}>
          <DataCard title="合格率" noPadding>
            <Statistic
              value={stats.acceptance_rate}
              suffix="%"
              precision={1}
              valueStyle={{ fontFamily: "var(--qf-font-mono)", color: "var(--qf-cyan)" }}
            />
          </DataCard>
        </Col>
      </Row>

      <DataCard
        title="检验单列表"
        extra={
          <Space>
            {canEdit('iqc') && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => navigate("/iqc/inspections/new")}
              >
                新建检验单
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <Input
            placeholder="检验单号 / 物料号 / 批号"
            allowClear
            style={{ width: 240 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={handleQuery}
          />
          <Select
            placeholder="状态"
            allowClear
            style={{ width: 120 }}
            value={filterStatus}
            onChange={(v) => setFilterStatus(v || undefined)}
          >
            <Option value="pending">待检验</Option>
            <Option value="inspecting">检验中</Option>
            <Option value="judged">已判定</Option>
            <Option value="closed">已关闭</Option>
          </Select>
          <Select
            placeholder="检验结果"
            allowClear
            style={{ width: 120 }}
            value={filterResult}
            onChange={(v) => setFilterResult(v || undefined)}
          >
            <Option value="accepted">合格</Option>
            <Option value="rejected">拒收</Option>
            <Option value="concession">让步接收</Option>
          </Select>
          <Button type="primary" onClick={handleQuery}>
            查询
          </Button>
        </Space>

        <Table
          className="qf-table"
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
      </DataCard>
    </PageShell>
  );
}
