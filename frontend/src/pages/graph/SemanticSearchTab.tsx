import { useState, useCallback, useRef } from "react";
import { Input, Button, Select, Card, Tag, Space, Spin, Empty, Typography, Tooltip } from "antd";
import { SearchOutlined, RobotOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { semanticSearch, askQuestion } from "../../api/search";
import type { SearchResultItem, QAResponse } from "../../api/search";
import QAAnswer from "../../components/search/QAAnswer";
import { useProductLineStore } from "../../store/productLineStore";

const { Text } = Typography;

const ENTITY_TYPE_OPTIONS = [
  { label: "FMEA 节点", value: "fmea_node" },
  { label: "CAPA", value: "capa" },
  { label: "审核发现", value: "audit_finding" },
  { label: "客诉", value: "complaint" },
  { label: "SCAR", value: "scar" },
  { label: "RMA", value: "rma" },
];

const ENTITY_COLORS: Record<string, string> = {
  fmea_node: "blue",
  capa: "orange",
  audit_finding: "purple",
  complaint: "red",
  scar: "cyan",
  rma: "magenta",
};

export default function SemanticSearchTab() {
  const [query, setQuery] = useState("");
  const [entityTypes, setEntityTypes] = useState<string[]>([]);
  const [mode, setMode] = useState<"search" | "qa">("search");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [qaData, setQaData] = useState<QAResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [queryTime, setQueryTime] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  const productLineCode = useProductLineStore((s) => s.selected);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    setResults([]);
    setQaData(null);

    try {
      if (mode === "search") {
        const res = await semanticSearch(
          {
            q: query,
            entity_types: entityTypes.length ? entityTypes.join(",") : undefined,
            product_line_code: productLineCode || undefined,
            limit: 20,
          },
          abortRef.current.signal,
        );
        setResults(res.results);
        setQueryTime(res.query_time_ms);
      } else {
        const res = await askQuestion(
          {
            question: query,
            product_line_code: productLineCode || undefined,
            max_context_chunks: 10,
          },
          abortRef.current.signal,
        );
        setQaData(res);
        setQueryTime(res.query_time_ms);
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") {
        console.error("Search error:", e);
      }
    } finally {
      setLoading(false);
    }
  }, [query, entityTypes, mode, productLineCode]);

  const handleResultClick = (item: SearchResultItem) => {
    if (item.entity_type === "fmea_node") {
      navigate(`/fmea/${item.entity_id}?tab=graph&highlightNode=${item.node_id}`);
    } else if (item.entity_type === "capa") {
      navigate(`/capa/${item.entity_id}`);
    }
  };

  return (
    <div style={{ padding: "16px 0" }}>
      <Space.Compact style={{ width: "100%", marginBottom: 16 }}>
        <Input
          placeholder="输入自然语言问题，搜索历史质量记录..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={handleSearch}
          style={{ flex: 1 }}
          size="large"
        />
        <Button
          icon={<SearchOutlined />}
          onClick={handleSearch}
          type={mode === "search" ? "primary" : "default"}
          size="large"
        >
          搜索
        </Button>
        <Tooltip title={mode === "qa" ? "切换到搜索模式" : "切换到问答模式"}>
          <Button
            icon={<RobotOutlined />}
            onClick={() => setMode(mode === "search" ? "qa" : "search")}
            type={mode === "qa" ? "primary" : "default"}
            size="large"
          >
            问答
          </Button>
        </Tooltip>
      </Space.Compact>

      <Space style={{ marginBottom: 16 }}>
        <Select
          mode="multiple"
          placeholder="筛选类型"
          options={ENTITY_TYPE_OPTIONS}
          value={entityTypes}
          onChange={setEntityTypes}
          style={{ minWidth: 300 }}
          allowClear
        />
      </Space>

      {loading && <Spin style={{ display: "block", margin: "40px auto" }} />}

      {!loading && mode === "search" && results.length > 0 && (
        <>
          <Text type="secondary" style={{ marginBottom: 8, display: "block" }}>
            找到 {results.length} 条结果，耗时 {queryTime}ms
          </Text>
          {results.map((item) => (
            <Card
              key={item.entity_id + item.entity_field + (item.node_id || "")}
              hoverable
              style={{ marginBottom: 8 }}
              onClick={() => handleResultClick(item)}
              size="small"
            >
              <Space>
                <Tag color={ENTITY_COLORS[item.entity_type] || "default"}>
                  {item.entity_type}
                </Tag>
                {typeof item.metadata?.document_no === "string" && (
                  <Text strong>{item.metadata.document_no}</Text>
                )}
                {typeof item.metadata?.node_type === "string" && (
                  <Tag>{item.metadata.node_type}</Tag>
                )}
              </Space>
              <div style={{ marginTop: 4 }}>
                <Text>
                  {item.chunk_text.length > 200
                    ? item.chunk_text.slice(0, 200) + "..."
                    : item.chunk_text}
                </Text>
              </div>
              <div style={{ marginTop: 4 }}>
                <Text type="secondary">
                  相似度: {(item.score * 100).toFixed(0)}% | 来源: {item.source}
                </Text>
              </div>
            </Card>
          ))}
        </>
      )}

      {!loading && mode === "qa" && qaData && <QAAnswer data={qaData} />}

      {!loading && !results.length && !qaData && (
        <Empty description="输入问题开始搜索" style={{ marginTop: 60 }} />
      )}
    </div>
  );
}
