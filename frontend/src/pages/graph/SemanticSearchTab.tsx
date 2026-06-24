import { useState, useCallback, useRef, useEffect } from "react";
import { Input, Button, Select, Tag, Space, Spin, Empty, Typography, Tooltip } from "antd";
import { SearchOutlined, RobotOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { semanticSearch, askQuestion } from "../../api/search";
import type { SearchResultItem, QAResponse } from "../../api/search";
import QAAnswer from "../../components/search/QAAnswer";
import { useProductLineStore } from "../../store/productLineStore";
import DataCard from "../../components/design/DataCard";
import { listProductTypes } from "../../api/productType";
import { listProductLines } from "../../api/productLine";
import type { ProductType, ProductLine } from "../../types";

const { Text } = Typography;

export default function SemanticSearchTab() {
  const { t } = useTranslation("search");
  const [query, setQuery] = useState("");
  const [entityTypes, setEntityTypes] = useState<string[]>([]);
  const [productTypeCode, setProductTypeCode] = useState<string | undefined>(undefined);
  const [productTypes, setProductTypes] = useState<ProductType[]>([]);
  const [productLines, setProductLines] = useState<ProductLine[]>([]);
  const [mode, setMode] = useState<"search" | "qa">("search");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [qaData, setQaData] = useState<QAResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [queryTime, setQueryTime] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const navigate = useNavigate();
  const productLineCode = useProductLineStore((s) => s.selected);

  const entityTypeOptions = [
    { label: t("qa.entityTypes.fmeaNode"), value: "fmea_node" },
    { label: t("qa.entityTypes.capa"), value: "capa" },
    { label: t("qa.entityTypes.auditFinding"), value: "audit_finding" },
    { label: t("qa.entityTypes.complaint"), value: "complaint" },
    { label: t("qa.entityTypes.scar"), value: "scar" },
    { label: t("qa.entityTypes.rma"), value: "rma" },
  ];

  useEffect(() => {
    listProductTypes(true)
      .then((types) => setProductTypes(types))
      .catch(() => setProductTypes([]));
  }, []);

  useEffect(() => {
    listProductLines(true)
      .then((lines) => setProductLines(lines))
      .catch(() => setProductLines([]));
  }, []);

  const productTypeOptions = productTypes.map((pt) => ({
    label: `${pt.name} (${pt.code})`,
    value: pt.code,
  }));

  const productLineOptions = productLines
    .filter((pl) => (productTypeCode ? pl.product_type_code === productTypeCode : true))
    .map((pl) => ({
      label: `${pl.name} (${pl.code})`,
      value: pl.code,
    }));

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
            product_type_code: productTypeCode,
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
            product_type_code: productTypeCode,
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
  }, [query, entityTypes, mode, productLineCode, productTypeCode]);

  const getEntityRoute = (item: SearchResultItem): string | null => {
    switch (item.entity_type) {
      case "fmea_node":
        return `/fmea/${item.entity_id}?tab=graph&highlightNode=${item.node_id}`;
      case "capa":
        return `/capa/${item.entity_id}`;
      default:
        return null;
    }
  };

  const handleResultClick = (item: SearchResultItem) => {
    const route = getEntityRoute(item);
    if (route) navigate(route);
  };

  return (
    <div style={{ padding: "16px 0" }}>
      <Space.Compact style={{ width: "100%", marginBottom: 16 }}>
        <Input
          placeholder={t("qa.placeholder")}
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
          {t("qa.search")}
        </Button>
        <Tooltip title={mode === "qa" ? t("qa.switchToSearch") : t("qa.switchToQa")}>
          <Button
            icon={<RobotOutlined />}
            onClick={() => setMode(mode === "search" ? "qa" : "search")}
            type={mode === "qa" ? "primary" : "default"}
            size="large"
          >
            {t("qa.qa")}
          </Button>
        </Tooltip>
      </Space.Compact>

      <Space style={{ marginBottom: 16 }}>
        <Select
          mode="multiple"
          placeholder={t("qa.filterType")}
          options={entityTypeOptions}
          value={entityTypes}
          onChange={setEntityTypes}
          style={{ minWidth: 300 }}
          allowClear
        />
        <Select
          placeholder={t("qa.productType")}
          options={productTypeOptions}
          value={productTypeCode}
          onChange={(value) => {
            setProductTypeCode(value);
            // Clear a stale global product-line selection that doesn't belong to the
            // newly-chosen type; otherwise the backend type filter is silently ignored
            // (product_line_code takes precedence). productLineOptions already hides
            // non-matching PLs, so the store value can otherwise linger invisibly.
            if (value && productLineCode) {
              const stillMatches = productLines.some(
                (pl) => pl.code === productLineCode && pl.product_type_code === value,
              );
              if (!stillMatches) {
                useProductLineStore.getState().setSelected(null);
              }
            }
          }}
          style={{ minWidth: 200 }}
          allowClear
        />
        <Select
          placeholder={t("qa.productLine")}
          options={productLineOptions}
          value={productLineCode}
          onChange={(value) => useProductLineStore.getState().setSelected(value)}
          style={{ minWidth: 220 }}
          allowClear
        />
      </Space>

      {loading && <Spin style={{ display: "block", margin: "40px auto" }} />}

      {!loading && mode === "search" && results.length > 0 && (
        <>
          <Text type="secondary" style={{ marginBottom: 8, display: "block" }}>
            {t("qa.resultsFound", { count: results.length, ms: queryTime })}
          </Text>
          {results.map((item) => (
            <DataCard
              key={item.entity_id + item.entity_field + (item.node_id || "")}
              title={null}
              style={{ marginBottom: 8, cursor: getEntityRoute(item) ? "pointer" : "default" }}
              onClick={() => handleResultClick(item)}
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
                  {t("qa.similarity", { score: (item.score * 100).toFixed(0), source: item.source })}
                </Text>
              </div>
            </DataCard>
          ))}
        </>
      )}

      {!loading && mode === "qa" && qaData && <QAAnswer data={qaData} />}

      {!loading && !results.length && !qaData && (
        <Empty description={t("qa.startSearch")} style={{ marginTop: 60 }} />
      )}
    </div>
  );
}

const ENTITY_COLORS: Record<string, string> = {
  fmea_node: "blue",
  capa: "orange",
  audit_finding: "purple",
  complaint: "red",
  scar: "cyan",
  rma: "magenta",
};
