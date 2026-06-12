import React, { useEffect, useState, useCallback } from "react";
import { Card, Spin, Empty } from "antd";
import { riskMapApi } from "../../api/supplyChainRiskMap";
import type { HeatmapResponse, TimelineResponse } from "../../types";
import HeatmapToolbar from "./components/HeatmapToolbar";
import TimelineSlider from "./components/TimelineSlider";
import RiskHeatmap from "./components/RiskHeatmap";

const PRODUCT_LINES = [
  { code: "DC-DC-100", name: "DC-DC-100" },
];

const SupplyChainRiskMapPage: React.FC = () => {
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [period, setPeriod] = useState<string>("");
  const [productLineCode, setProductLineCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const res = await riskMapApi.heatmap({
        product_line_code: productLineCode ?? undefined,
        period: period || undefined,
      });
      setHeatmap(res.data);
      if (res.data.period && !period) {
        setPeriod(res.data.period);
      }
    } catch {
      // 404 or no data — show empty
    } finally {
      setLoading(false);
    }
  }, [productLineCode, period]);

  const fetchTimeline = useCallback(async () => {
    try {
      const res = await riskMapApi.timeline({
        product_line_code: productLineCode ?? undefined,
      });
      setTimeline(res.data);
      if (!period && res.data.current_period) {
        setPeriod(res.data.current_period);
      }
    } catch {
      // ignore
    }
  }, [productLineCode, period]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  useEffect(() => {
    if (period) {
      fetchHeatmap();
    }
  }, [period, productLineCode, fetchHeatmap]);

  const handleSupplierClick = (supplierId: string) => {
    // Navigate to detail panel (Task 9 will implement this)
    console.log("Supplier clicked:", supplierId);
  };

  return (
    <div style={{ padding: 24 }}>
      <h2>供应链风险地图</h2>
      <HeatmapToolbar
        period={period}
        productLineCode={productLineCode}
        onPeriodChange={setPeriod}
        onProductLineChange={setProductLineCode}
        onRefresh={fetchHeatmap}
        refreshing={loading}
        periods={timeline?.periods ?? []}
        productLines={PRODUCT_LINES}
      />
      {timeline && timeline.periods.length > 1 && (
        <TimelineSlider
          periods={timeline.periods}
          currentPeriod={period}
          onChange={setPeriod}
        />
      )}
      <Card>
        {loading ? (
          <Spin />
        ) : heatmap && heatmap.rows.length > 0 ? (
          <RiskHeatmap data={heatmap} onSupplierClick={handleSupplierClick} />
        ) : (
          <Empty description="暂无数据，请先生成快照" />
        )}
      </Card>
    </div>
  );
};

export default SupplyChainRiskMapPage;