import React, { useEffect, useState, useCallback } from "react";
import { Card, Row, Col, Spin, Empty } from "antd";
import { riskMapApi } from "../../api/supplyChainRiskMap";
import type { HeatmapResponse, TimelineResponse } from "../../types";
import { useProductLineStore } from "../../store/productLineStore";
import HeatmapToolbar from "./components/HeatmapToolbar";
import TimelineSlider from "./components/TimelineSlider";
import RiskHeatmap from "./components/RiskHeatmap";
import DetailPanel from "./components/DetailPanel";

const SupplyChainRiskMapPage: React.FC = () => {
  const { productLines, selected: selectedProductLine, setSelected: setSelectedProductLine } = useProductLineStore();
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [period, setPeriod] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [selectedSupplierIds, setSelectedSupplierIds] = useState<string[]>([]);

  const fetchHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const res = await riskMapApi.heatmap({
        product_line_code: selectedProductLine ?? undefined,
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
  }, [selectedProductLine, period]);

  const fetchTimeline = useCallback(async () => {
    try {
      const res = await riskMapApi.timeline({
        product_line_code: selectedProductLine ?? undefined,
      });
      setTimeline(res.data);
      if (!period && res.data.current_period) {
        setPeriod(res.data.current_period);
      }
    } catch {
      // ignore
    }
  }, [selectedProductLine, period]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  useEffect(() => {
    if (period) {
      fetchHeatmap();
    }
  }, [period, selectedProductLine, fetchHeatmap]);

  const handleSupplierClick = (supplierId: string) => {
    setSelectedSupplierIds((prev) => {
      const idx = prev.indexOf(supplierId);
      if (idx >= 0) {
        return prev.filter((id) => id !== supplierId);
      }
      if (prev.length >= 5) return prev;
      return [...prev, supplierId];
    });
  };

  const showDetail = selectedSupplierIds.length > 0;

  return (
    <div style={{ padding: 24 }}>
      <h2>供应链风险地图</h2>
      <HeatmapToolbar
        period={period}
        productLineCode={selectedProductLine}
        onPeriodChange={setPeriod}
        onProductLineChange={setSelectedProductLine}
        onRefresh={fetchHeatmap}
        refreshing={loading}
        periods={timeline?.periods ?? []}
        productLines={productLines}
      />
      {timeline && timeline.periods.length > 1 && (
        <TimelineSlider
          periods={timeline.periods}
          currentPeriod={period}
          onChange={setPeriod}
        />
      )}
      <Row gutter={16}>
        <Col span={showDetail ? 16 : 24}>
          <Card>
            {loading ? (
              <Spin />
            ) : heatmap && heatmap.rows.length > 0 ? (
              <RiskHeatmap data={heatmap} onSupplierClick={handleSupplierClick} />
            ) : (
              <Empty description="暂无数据，请先生成快照" />
            )}
          </Card>
        </Col>
        {showDetail && (
          <Col span={8}>
            <DetailPanel
              selectedSupplierIds={selectedSupplierIds}
              productLineCode={selectedProductLine}
              period={period}
            />
          </Col>
        )}
      </Row>
    </div>
  );
};

export default SupplyChainRiskMapPage;