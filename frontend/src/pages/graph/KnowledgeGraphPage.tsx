import { useState, useEffect, useMemo } from "react";
import { Tabs, Input, Select, Table, Tag, Spin, Empty, Space, Statistic, Row, Col, Button } from "antd";
import { SearchOutlined, BarChartOutlined, FireOutlined, LinkOutlined, RobotOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import SemanticSearchTab from "./SemanticSearchTab";
import { useNavigate } from "react-router-dom";
import { useProductLineStore } from "../../store/productLineStore";
import { searchSimilarNodes, getCrossFmeaStats } from "../../api/graph";
import type { SimilarNode, CrossFmeaStats } from "../../api/graph";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";

export default function KnowledgeGraphPage() {
  const { t } = useTranslation("graph");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const { selected: productLineCode } = useProductLineStore();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState<CrossFmeaStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchType, setSearchType] = useState("FailureMode");
  const [searchResults, setSearchResults] = useState<SimilarNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const typeOptions = useMemo(() => [
    { value: "FailureMode", label: t("search.failureMode") },
    { value: "FailureCause", label: t("search.failureCause") },
    { value: "FailureEffect", label: t("search.failureEffect") },
    { value: "Function", label: t("search.function") },
  ], [t]);

  const riskColumns = useMemo(() => [
    { title: t("search.failureMode"), dataIndex: "name", key: "name" },
    { title: "RPN", dataIndex: "rpn", key: "rpn", width: 80 },
    {
      title: t("search.columns.sourceFmea"),
      dataIndex: "document_no",
      key: "document_no",
      render: (v: string, record: { node_id: string; fmea_id: string }) => (
        <Button
          type="link"
          icon={<LinkOutlined />}
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {v || record.fmea_id}
        </Button>
      ),
    },
    {
      title: tc("table.operations"),
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {t("search.viewGraph")}
        </Button>
      ),
    },
  ], [t, tc, navigate]);

  const searchColumns = useMemo(() => [
    { title: t("search.columns.name"), dataIndex: "name", key: "name" },
    { title: t("search.columns.type"), dataIndex: "type", key: "type", width: 120 },
    {
      title: t("search.columns.sourceFmea"),
      dataIndex: "document_no",
      key: "document_no",
      render: (v: string, record: { node_id: string; fmea_id: string }) => (
        <Button
          type="link"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {v || record.fmea_id}
        </Button>
      ),
    },
    {
      title: tc("table.operations"),
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {t("search.view")}
        </Button>
      ),
    },
  ], [t, tc, navigate]);

  useEffect(() => {
    if (!productLineCode) return;
    setStatsLoading(true);
    getCrossFmeaStats(productLineCode)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, [productLineCode]);

  const handleSearch = () => {
    if (!productLineCode || !searchKeyword.trim()) return;
    setSearchLoading(true);
    searchSimilarNodes({
      node_type: searchType,
      name_keyword: searchKeyword.trim(),
      product_line_code: productLineCode,
      limit: 20,
    })
      .then(setSearchResults)
      .catch(() => setSearchResults([]))
      .finally(() => setSearchLoading(false));
  };

  if (!productLineCode) {
    return (
      <DataCard title={null}>
        <Empty description={t("search.selectProductLine")} />
      </DataCard>
    );
  }

  const tabItems = [
    {
      key: "overview",
      label: <span><BarChartOutlined /> {t("page.overview")}</span>,
      children: statsLoading ? (
        <Spin size="large" style={{ display: "block", margin: "60px auto" }} />
      ) : stats ? (
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Row gutter={16}>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.totalFmeas")} value={stats.total_fmeas} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.totalNodes")} value={stats.total_nodes} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}>
                <Statistic
                  title={t("overview.highApNodes")}
                  value={stats.high_ap_nodes?.length || 0}
                  prefix={<FireOutlined style={{ color: "#ff4d4f" }} />}
                />
              </DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.avgRpn")} value={stats.avg_rpn || 0} precision={1} /></DataCard>
            </Col>
          </Row>
          <DataCard title={t("overview.apDistribution")}>
            <Space size="large">
              <StatusBadge status="error">{t("nodeDetail.apHigh")}: {stats.ap_distribution?.H || 0}</StatusBadge>
              <StatusBadge status="info">{t("nodeDetail.apMedium")}: {stats.ap_distribution?.M || 0}</StatusBadge>
              <StatusBadge status="success">{t("nodeDetail.apLow")}: {stats.ap_distribution?.L || 0}</StatusBadge>
            </Space>
          </DataCard>
          <DataCard
            title={t("overview.topHighAp")}
            extra={<StatusBadge status="error">{t("overview.topHighApExtra")}</StatusBadge>}
          >
            <Table
              className="qf-table"
              dataSource={stats.high_ap_nodes || []}
              columns={riskColumns}
              rowKey={(r) => `${r.fmea_id}-${r.node_id}`}
              pagination={false}
              size="small"
            />
          </DataCard>
          <DataCard title={t("overview.nodeTypeDistribution")}>
            <Space wrap>
              {Object.entries(stats.node_type_distribution || {}).map(([type, count]) => (
                <Tag key={type}>{type}: {count}</Tag>
              ))}
            </Space>
          </DataCard>
        </Space>
      ) : (
        <Empty description={t("search.noStats")} />
      ),
    },
    {
      key: "search",
      label: <span><SearchOutlined /> {t("page.keywordSearch")}</span>,
      children: (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Select value={searchType} onChange={setSearchType} options={typeOptions} style={{ width: 140 }} />
            <Input.Search
              placeholder={t("search.placeholder")}
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              onSearch={handleSearch}
              loading={searchLoading}
              style={{ width: 300 }}
            />
          </Space>
          {searchResults.length > 0 && (
            <Table
              className="qf-table"
              dataSource={searchResults}
              columns={searchColumns}
              rowKey={(r) => `${r.fmea_id}-${r.node_id}`}
              size="small"
            />
          )}
        </>
      ),
    },
    {
      key: "semantic",
      label: <span><RobotOutlined /> {t("page.semanticSearch")}</span>,
      children: <SemanticSearchTab />,
    },
  ];

  return (
    <PageShell title={t("page.title")}>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </PageShell>
  );
}