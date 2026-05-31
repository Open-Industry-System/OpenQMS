import React, { useEffect, useState, useCallback } from "react";
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Input,
  Select,
  Space,
  Typography,
  Spin,
  Empty,
  Tag,
  Button,
  Alert,
  message,
} from "antd";
import {
  FileTextOutlined,
  NodeIndexOutlined,
  WarningOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getCrossFmeaStats,
  searchSimilarNodes,
  type CrossFmeaStats,
  type SimilarNode,
} from "../../api/graph";
import { useProductLineStore } from "../../store/productLineStore";

const { Title } = Typography;
const { Option } = Select;

const NODE_TYPE_OPTIONS = [
  "FailureMode",
  "FailureEffect",
  "FailureCause",
  "Function",
  "PreventionControl",
  "DetectionControl",
  "ProcessItem",
  "ProcessStep",
  "ProcessWorkElement",
  "System",
  "Subsystem",
  "Component",
];

const AP_COLOR_MAP: Record<string, string> = {
  H: "red",
  M: "orange",
  L: "green",
};

const KnowledgeGraphPage: React.FC = () => {
  const navigate = useNavigate();
  const currentProductLine = useProductLineStore((s) => s.selected);

  const [stats, setStats] = useState<CrossFmeaStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchType, setSearchType] = useState("FailureMode");
  const [searchResults, setSearchResults] = useState<SimilarNode[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const fetchStats = useCallback(async () => {
    if (!currentProductLine) return;
    setStatsLoading(true);
    try {
      const data = await getCrossFmeaStats(currentProductLine);
      setStats(data);
    } catch {
      message.error("加载统计失败，请稍后重试");
      setStats(null);
    } finally {
      setStatsLoading(false);
    }
  }, [currentProductLine]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // 抽取共用搜索函数，统一错误处理 + AbortController 防竞态
  const runSearch = useCallback(
    async (keyword: string, type: string, productLine: string, signal?: AbortSignal) => {
      setSearchLoading(true);
      try {
        const results = await searchSimilarNodes({
          node_type: type,
          name_keyword: keyword,
          product_line_code: productLine,
          limit: 20,
        });
        if (signal?.aborted) return;
        setSearchResults(results);
      } catch {
        if (signal?.aborted) return;
        message.error("搜索失败，请稍后重试");
        setSearchResults([]);
      } finally {
        if (!signal?.aborted) {
          setSearchLoading(false);
        }
      }
    },
    []
  );

  // 搜索防抖：监听 keyword/type/productLine 变化，300ms 后自动触发
  useEffect(() => {
    const trimmed = searchKeyword.trim();
    if (!trimmed || !currentProductLine) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    const abortCtrl = new AbortController();
    const timer = setTimeout(() => {
      runSearch(trimmed, searchType, currentProductLine, abortCtrl.signal);
    }, 300);
    return () => {
      clearTimeout(timer);
      abortCtrl.abort();
    };
  }, [searchKeyword, searchType, currentProductLine, runSearch]);

  const handleViewGraph = (fmeaId: string, nodeId?: string) => {
    if (nodeId) {
      navigate(`/fmea/${fmeaId}?node=${nodeId}`);
    } else {
      navigate(`/fmea/${fmeaId}`);
    }
  };

  const apDist = stats?.ap_distribution || { H: 0, M: 0, L: 0 };

  if (!currentProductLine) {
    return (
      <div style={{ padding: 24 }}>
        <Title level={3}>全局知识库</Title>
        <Alert
          message="请选择产品线"
          description="请在顶部导航栏选择产品线以查看知识库数据。"
          type="info"
          showIcon
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}>全局知识库</Title>
      <p style={{ color: "#888" }}>产品线: {currentProductLine}</p>

      <Spin spinning={statsLoading}>
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="FMEA 文档数"
                value={stats?.total_fmeas || 0}
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="节点总数"
                value={stats?.total_nodes || 0}
                prefix={<NodeIndexOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <Statistic
                title="平均 RPN"
                value={stats?.avg_rpn || 0}
                precision={1}
                prefix={<WarningOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card>
              <div style={{ fontSize: 14, color: "#00000073", marginBottom: 8 }}>
                AP 分布
              </div>
              <Space>
                <Tag color="red">H: {apDist.H}</Tag>
                <Tag color="orange">M: {apDist.M}</Tag>
                <Tag color="green">L: {apDist.L}</Tag>
              </Space>
            </Card>
          </Col>
        </Row>
      </Spin>

      <Card title="跨 FMEA 节点搜索" style={{ marginBottom: 24 }}>
        <Space.Compact style={{ width: "100%", maxWidth: 600 }}>
          <Select
            value={searchType}
            onChange={setSearchType}
            style={{ width: 160 }}
          >
            {NODE_TYPE_OPTIONS.map((t) => (
              <Option key={t} value={t}>
                {t}
              </Option>
            ))}
          </Select>
          <Input
            placeholder="输入节点名称关键词（自动搜索）"
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            allowClear
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => {
              const trimmed = searchKeyword.trim();
              if (trimmed && currentProductLine) {
                runSearch(trimmed, searchType, currentProductLine);
              }
            }}
          >
            搜索
          </Button>
        </Space.Compact>

        <div style={{ marginTop: 16 }}>
          {searchResults.length === 0 && !searchLoading && searchKeyword.trim() && (
            <Empty description="未找到匹配节点" />
          )}
          {searchResults.length > 0 && (
            <Table
              dataSource={searchResults}
              rowKey={(record) => `${record.fmea_id}-${record.node_id}`}
              loading={searchLoading}
              size="small"
              pagination={{ pageSize: 10 }}
              columns={[
                { title: "名称", dataIndex: "name", key: "name" },
                { title: "类型", dataIndex: "type", key: "type" },
                { title: "来源文档", dataIndex: "document_no", key: "document_no" },
                {
                  title: "操作",
                  key: "action",
                  render: (_, record) => (
                    <Button
                      type="link"
                      size="small"
                      onClick={() => handleViewGraph(record.fmea_id, record.node_id)}
                    >
                      查看图谱
                    </Button>
                  ),
                },
              ]}
            />
          )}
        </div>
      </Card>

      <Card title="高风险节点 (AP = H)" style={{ marginBottom: 24 }}>
        <Table
          dataSource={stats?.high_ap_nodes || []}
          rowKey={(record) => `${record.fmea_id}-${record.node_id}`}
          loading={statsLoading}
          size="small"
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "RPN",
              dataIndex: "rpn",
              key: "rpn",
              sorter: (a, b) => a.rpn - b.rpn,
            },
            {
              title: "AP",
              dataIndex: "ap",
              key: "ap",
              render: (ap: string) => <Tag color={AP_COLOR_MAP[ap] || "default"}>{ap}</Tag>,
            },
            { title: "来源文档", dataIndex: "document_no", key: "document_no" },
            {
              title: "操作",
              key: "action",
              render: (_, record) => (
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleViewGraph(record.fmea_id, record.node_id)}
                >
                  查看图谱
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="TOP10 失效模式">
        <Table
          dataSource={stats?.top_failure_modes || []}
          rowKey={(record) => `${record.fmea_id}-${record.name}`}
          loading={statsLoading}
          size="small"
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name", key: "name" },
            {
              title: "RPN",
              dataIndex: "rpn",
              key: "rpn",
            },
            { title: "来源文档", dataIndex: "document_no", key: "document_no" },
            {
              title: "操作",
              key: "action",
              render: (_, record) => (
                <Button
                  type="link"
                  size="small"
                  onClick={() => handleViewGraph(record.fmea_id)}
                >
                  查看图谱
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default KnowledgeGraphPage;
