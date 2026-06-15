import { useState, useEffect } from "react";
import { Card, Tabs, Input, Select, Table, Tag, Spin, Empty, Space, Statistic, Row, Col, Button } from "antd";
import { SearchOutlined, BarChartOutlined, FireOutlined, LinkOutlined, RobotOutlined } from "@ant-design/icons";
import SemanticSearchTab from "./SemanticSearchTab";
import { useNavigate } from "react-router-dom";
import { useProductLineStore } from "../../store/productLineStore";
import { useTranslation } from "react-i18next";
import { searchSimilarNodes, getCrossFmeaStats } from "../../api/graph";
import type { SimilarNode, CrossFmeaStats } from "../../api/graph";

export default function KnowledgeGraphPage() {
  const { t } = useTranslation("graph");
  const navigate = useNavigate();
  const { selected: productLineCode } = useProductLineStore();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState<CrossFmeaStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchType, setSearchType] = useState("FailureMode");
  const [searchResults, setSearchResults] = useState<SimilarNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

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

  const riskColumns = [
    { title: t("search.columns.name"), dataIndex: "name", key: "name" },
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
      title: t("search.columns.action"),
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
  ];

  const searchColumns = [
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
      title: t("search.columns.action"),
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
  ];

  if (!productLineCode) {
    return (
      <Card>
        <Empty description={t("search.selectProductLine")} />
      </Card>
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
              <Card><Statistic title={t("overview.totalFmeas")} value={stats.total_fmeas} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title={t("overview.totalNodes")} value={stats.total_nodes} /></Card>
            </Col>
            <Col span={6}>
              <Card>
                <Statistic
                  title={t("overview.highApNodes")}
                  value={stats.high_ap_nodes?.length || 0}
                  prefix={<FireOutlined style={{ color: "#ff4d4f" }} />}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title={t("overview.avgRpn")} value={stats.avg_rpn || 0} precision={1} /></Card>
            </Col>
          </Row>
          <Card title={t("overview.apDistribution")}>
            <Space size="large">
              <Tag color="red">{t("overview.apHighCount", { count: stats.ap_distribution?.H || 0 })}</Tag>
              <Tag color="orange">{t("overview.apMediumCount", { count: stats.ap_distribution?.M || 0 })}</Tag>
              <Tag color="green">{t("overview.apLowCount", { count: stats.ap_distribution?.L || 0 })}</Tag>
            </Space>
          </Card>
          <Card title={t("overview.topHighAp")} extra={<Tag color="red">{t("overview.topHighApExtra")}</Tag>}>
            <Table
              dataSource={stats.high_ap_nodes || []}
              columns={riskColumns}
              rowKey={(r) => `${r.fmea_id}-${r.node_id}`}
              pagination={false}
              size="small"
            />
          </Card>
          <Card title={t("overview.nodeTypeDistribution")}>
            <Space wrap>
              {Object.entries(stats.node_type_distribution || {}).map(([type, count]) => (
                <Tag key={type}>{type}: {count}</Tag>
              ))}
            </Space>
          </Card>
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
            <Select value={searchType} onChange={setSearchType} style={{ width: 140 }}>
              <Select.Option value="FailureMode">{t("search.failureMode")}</Select.Option>
              <Select.Option value="FailureCause">{t("search.failureCause")}</Select.Option>
              <Select.Option value="FailureEffect">{t("search.failureEffect")}</Select.Option>
              <Select.Option value="Function">{t("search.function")}</Select.Option>
            </Select>
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
    <div>
      <h2>{t("page.title")}</h2>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </div>
  );
}
