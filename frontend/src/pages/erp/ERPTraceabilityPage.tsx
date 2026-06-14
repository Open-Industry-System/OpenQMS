import { useState } from "react";
import { Input, Button, Radio, Tag, Alert, App } from "antd";
import { queryERPTraceability } from "../../api/erp";
import type { TraceabilityResponse, TraceabilityNode } from "../../types/erp";
import { PageShell, DataCard, StatusBadge } from "../../components/design";

const nodeVariant: Record<string, string> = {
  erp_lot: "info",
  po: "success",
  supplier: "info",
  shipment: "warning",
  customer: "info",
};

export default function ERPTraceabilityPage() {
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
      message.error("追溯查询失败");
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
    <PageShell title="批次追溯">
      <DataCard title="追溯查询">
        <div style={{ display: "flex", gap: 16, marginBottom: 16, alignItems: "center" }}>
          <Input
            placeholder="输入批次号"
            value={lotNo}
            onChange={(e) => setLotNo(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 300 }}
          />
          <Radio.Group
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          >
            <Radio.Button value="forward">正向（原料 → 客户）</Radio.Button>
            <Radio.Button value="backward">反向（客户 → 原料）</Radio.Button>
          </Radio.Group>
          <Button type="primary" onClick={handleSearch} loading={loading}>
            查询
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
            <h3 style={{ marginBottom: 16 }}>追溯节点</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
              {result.nodes.map((node) => (
                <DataCard
                  key={node.id}
                  title={node.label}
                  style={{ width: 200 }}
                >
                  <StatusBadge status={nodeVariant[node.type] || "info"}>
                    {node.type}
                  </StatusBadge>
                </DataCard>
              ))}
            </div>

            {result.edges.length > 0 && (
              <>
                <h3 style={{ marginBottom: 16 }}>追溯关系</h3>
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
              <Alert type="info" message="未找到追溯数据" />
            )}
          </>
        )}
      </DataCard>
    </PageShell>
  );
}
