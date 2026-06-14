import { useState, useEffect } from "react";
import { Tabs, Input, Select, Table, Tag, Spin, Empty, Space, Statistic, Row, Col, Button } from "antd";
import { SearchOutlined, BarChartOutlined, FireOutlined, LinkOutlined, RobotOutlined } from "@ant-design/icons";
import SemanticSearchTab from "./SemanticSearchTab";
import { useNavigate } from "react-router-dom";
import { useProductLineStore } from "../../store/productLineStore";
import { searchSimilarNodes, getCrossFmeaStats } from "../../api/graph";
import type { SimilarNode, CrossFmeaStats } from "../../api/graph";
import PageShell from "../../components/design/PageShell";
import DataCard from "../../components/design/DataCard";
import StatusBadge from "../../components/design/StatusBadge";

export default function KnowledgeGraphPage() {
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
    { title: "失效模式", dataIndex: "name", key: "name" },
    { title: "RPN", dataIndex: "rpn", key: "rpn", width: 80 },
    {
      title: "来源 FMEA",
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
      title: "操作",
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          查看图谱
        </Button>
      ),
    },
  ];

  const searchColumns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "类型", dataIndex: "type", key: "type", width: 120 },
    {
      title: "来源 FMEA",
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
      title: "操作",
      key: "action",
      render: (_: unknown, record: { node_id: string; fmea_id: string }) => (
        <Button
          size="small"
          onClick={() => navigate(`/fmea/${record.fmea_id}?tab=graph&highlightNode=${record.node_id}`)}
        >
          查看
        </Button>
      ),
    },
  ];

  if (!productLineCode) {
    return (
      <DataCard title={null}>
        <Empty description="请先选择产品线" />
      </DataCard>
    );
  }

  const tabItems = [
    {
      key: "overview",
      label: <span><BarChartOutlined /> 总览 / 风险地图</span>,
      children: statsLoading ? (
        <Spin size="large" style={{ display: "block", margin: "60px auto" }} />
      ) : stats ? (
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <Row gutter={16}>
            <Col span={6}>
              <DataCard title={null}><Statistic title="FMEA 总数" value={stats.total_fmeas} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title="节点总数" value={stats.total_nodes} /></DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}>
                <Statistic
                  title="高优先级失效模式 (AP=H)"
                  value={stats.high_ap_nodes?.length || 0}
                  prefix={<FireOutlined style={{ color: "#ff4d4f" }} />}
                />
              </DataCard>
            </Col>
            <Col span={6}>
              <DataCard title={null}><Statistic title="平均 RPN" value={stats.avg_rpn || 0} precision={1} /></DataCard>
            </Col>
          </Row>
          <DataCard title="AP 分布">
            <Space size="large">
              <StatusBadge status="error">高 (H): {stats.ap_distribution?.H || 0}</StatusBadge>
              <StatusBadge status="info">中 (M): {stats.ap_distribution?.M || 0}</StatusBadge>
              <StatusBadge status="success">低 (L): {stats.ap_distribution?.L || 0}</StatusBadge>
            </Space>
          </DataCard>
          <DataCard
            title="高优先级失效模式 Top 10"
            extra={<StatusBadge status="error">AP = H (高优先级)</StatusBadge>}
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
          <DataCard title="节点类型分布">
            <Space wrap>
              {Object.entries(stats.node_type_distribution || {}).map(([type, count]) => (
                <Tag key={type}>{type}: {count}</Tag>
              ))}
            </Space>
          </DataCard>
        </Space>
      ) : (
        <Empty description="暂无统计数据" />
      ),
    },
    {
      key: "search",
      label: <span><SearchOutlined /> 历史关键词搜索</span>,
      children: (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Select value={searchType} onChange={setSearchType} style={{ width: 140 }}>
              <Select.Option value="FailureMode">失效模式</Select.Option>
              <Select.Option value="FailureCause">失效原因</Select.Option>
              <Select.Option value="FailureEffect">失效影响</Select.Option>
              <Select.Option value="Function">功能</Select.Option>
            </Select>
            <Input.Search
              placeholder="输入关键词搜索..."
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
      label: <span><RobotOutlined /> 语义搜索</span>,
      children: <SemanticSearchTab />,
    },
  ];

  return (
    <PageShell title="知识图谱">
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
    </PageShell>
  );
}
