import { useState } from "react";
import { Input, Button, Radio, Card, Tag, Alert, Typography, App } from "antd";
import { useTranslation } from "react-i18next";
import { queryERPTraceability } from "../../api/erp";
import type { TraceabilityResponse, TraceabilityNode } from "../../types/erp";

const { Title } = Typography;

const nodeTypeColors: Record<string, string> = {
  erp_lot: "purple",
  po: "green",
  supplier: "blue",
  shipment: "orange",
  customer: "cyan",
};

export default function ERPTraceabilityPage() {
  const { t } = useTranslation("erp");
  const { message } = App.useApp();
  const [lotNo, setLotNo] = useState("");
  const [direction, setDirection] = useState<"forward" | "backward">("forward");
  const [result, setResult] = useState<TraceabilityResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!lotNo.trim()) return;
    setLoading(true);
    try {
      const res = await queryERPTraceability(lotNo.trim(), direction);
      setResult(res);
    } catch {
      message.error(t("traceability.errors.queryFailed"));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  // Build a lookup for edge display labels
  const nodeLookup = result
    ? new Map(result.nodes.map((n: TraceabilityNode) => [n.id, n.label]))
    : new Map();

  return (
    <div>
      <Title level={4} style={{ marginBottom: 16 }}>
        {t("traceability.title")}
      </Title>

      <Card>
        <div style={{ display: "flex", gap: 16, marginBottom: 16, alignItems: "center" }}>
          <Input
            placeholder={t("traceability.lotPlaceholder")}
            value={lotNo}
            onChange={(e) => setLotNo(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 300 }}
          />
          <Radio.Group
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <Radio.Button value="forward">{t("traceability.direction.forward")}</Radio.Button>
            <Radio.Button value="backward">{t("traceability.direction.backward")}</Radio.Button>
          </Radio.Group>
          <Button type="primary" onClick={handleSearch} loading={loading}>
            {t("traceability.search")}
          </Button>
        </div>

        {result?.gaps && result.gaps.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            {result.gaps.map((gap, i) => (
              <Alert
                key={`${gap.type}-${i}`}
                type="warning"
                message={gap.message}
                style={{ marginBottom: 8 }}
                showIcon
              />
            ))}
          </div>
        )}

        {result && (
          <>
            <Title level={5}>{t("traceability.nodes")}</Title>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
              {result.nodes.map((node) => (
                <Card
                  key={node.id}
                  size="small"
                  style={{ width: 200, borderColor: nodeTypeColors[node.type] ? undefined : undefined }}
                >
                  <Tag color={nodeTypeColors[node.type] || "default"}>
                    {node.type}
                  </Tag>
                  <div style={{ marginTop: 4 }}>{node.label}</div>
                </Card>
              ))}
            </div>

            {result.edges.length > 0 && (
              <>
                <Title level={5}>{t("traceability.edges")}</Title>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {result.edges.map((edge, i) => (
                    <div key={i}>
                      <Tag>{nodeLookup.get(edge.from) || edge.from}</Tag>
                      <span style={{ margin: "0 8px" }}>&rarr;</span>
                      <Tag>{nodeLookup.get(edge.to) || edge.to}</Tag>
                      <span style={{ marginLeft: 8, color: "#999" }}>
                        ({edge.type})
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {result.nodes.length === 0 && (
              <Alert type="info" message={t("traceability.noData")} />
            )}
          </>
        )}
      </Card>
    </div>
  );
}
