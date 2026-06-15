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
    { value: "FailureMode", label: t("search.failureMode", "失效模式") },
    { value: "FailureCause", label: t("search.failureCause", "失效原因") },
    { value: "FailureEffect", label: t("search.failureEffect", "失效影响") },
    { value: "Function", label: t("search.function", "功能") },
  ], [t]);

  const riskColumns = useMemo(() => [
    { title: t("search.failureMode", "失效模式"), dataIndex: "name", key: "name" },
    { title: "RPN", dataIndex: "rpn", key: "rpn", width: 80 },
    {
      title: t("search.columns.sourceFmea", "来源 FMEA"),
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
      title: tc("table.operations", "操作"),
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {t("search.viewGraph", "查看图谱")}
        </Button>
      ),
    },
  ], [t, tc, navigate]);

  const searchColumns = useMemo(() => [
    { title: t("search.columns.name", "名称"), dataIndex: "name", key: "name" },
    { title: t("search.columns.type", "类型"), dataIndex: "type", key: "type", width: 120 },
    {
      title: t("search.columns.sourceFmea", "来源 FMEA"),
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
      title: tc("table.operations", "操作"),
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          {t("search.view", "查看")}
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
        <Empty description={t("search.selectProductLine", "请先选择产品线")} />
      </DataCard>
    );
  }

  const tabItems = [
    {
      key: "overview",
      label: <span><BarChartOutlined /> {t("page.overview", "总览 / 风险地图")}</span>,
      children: statsLoading ? (
        <Spin size="large" style={{ display: "block", margin: "60px auto" }} />
      ) : stats ? (
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Row gutter={16}>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.totalFmeas", "FMEA 总数")} value={stats.total_fmeas} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.totalNodes", "节点总数")} value={stats.total_nodes} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}>
                <Statistic
                  title={t("overview.highApNodes", "高优先级失效模式 (AP=H)")}
                  value={stats.high_ap_nodes?.length || 0}
                  prefix={<FireOutlined style={{ color: "#ff4d4f" }} />}
                />
              </DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title={t("overview.avgRpn", "平均 RPN")} value={stats.avg_rpn || 0} precision={1} /></DataCard>
            </Col>
          </Row>
          <DataCard title={t("overview.apDistribution", "AP 分布")}>
            <Space size="large">
              <StatusBadge status="error">{t("nodeDetail.apHigh", "高 (H)")}: {stats.ap_distribution?.H || 0}</StatusBadge>
              <StatusBadge status="info">{t("nodeDetail.apMedium", "中 (M)")}: {stats.ap_distribution?.M || 0}</StatusBadge>
              <StatusBadge status="success">{t("nodeDetail.apLow", "低 (L)")}: {stats.ap_distribution?.L || 0}</StatusBadge>
            </Space>
          </DataCard>
          <DataCard
            title={t("overview.topHighAp", "高优先级失效模式 Top 10")}
            extra={<StatusBadge status="error">{t("overview.topHighApExtra", "AP = H (高优先级)")}</StatusBadge>}
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
          <DataCard title={t("overview.nodeTypeDistribution", "节点类型分布")}>
            <Space wrap>
              {Object.entries(stats.node_type_distribution || {}).map(([type, count]) => (
                <Tag key={type}>{type}: {count}</Tag>
              ))}
            </Space>
          </DataCard>
        </Space>
      ) : (
        <Empty description={t("search.noStats", "暂无统计数据")} />
      ),
    },
    {
      key: "search",
      label: <span><SearchOutlined /> {t("page.keywordSearch", "历史关键词搜索")}</span>,
      children: (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Select value={searchType} onChange={setSearchType} options={typeOptions} style={{ width: 140 }} />
            <Input.Search
              placeholder={t("search.placeholder", "输入关键词搜索...")}
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
      label: <span><RobotOutlined /> {t("page.semanticSearch", "语义搜索")}</span>,
      children: <SemanticSearchTab />,
    },
  ];

  return (
    <PageShell title={t("page.title", "知识图谱")}>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </PageShell>
  );
}