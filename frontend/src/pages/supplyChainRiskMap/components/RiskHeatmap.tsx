import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { HeatmapResponse, HeatmapColumn, HeatmapCell } from "../../../types";

interface RiskHeatmapProps {
  data: HeatmapResponse;
  onSupplierClick?: (supplierId: string) => void;
}

const RISK_COLORS: Record<string, string> = {
  low: "#52c41a",
  medium: "#faad14",
  high: "#fa8c16",
  critical: "#f5222d",
};

function getCellColor(cell: HeatmapCell, col: HeatmapColumn): string {
  if (col.key === "risk_score" && cell.level) {
    return RISK_COLORS[cell.level] || "#d9d9d9";
  }
  if (cell.risk_index == null) return "#f5f5f5";
  if (col.polarity === "lower_is_risk") {
    if (cell.risk_index <= 30) return "#52c41a";
    if (cell.risk_index <= 60) return "#faad14";
    return "#f5222d";
  }
  if (cell.risk_index <= 30) return "#52c41a";
  if (cell.risk_index <= 60) return "#faad14";
  if (cell.risk_index <= 80) return "#fa8c16";
  return "#f5222d";
}

const RiskHeatmap: React.FC<RiskHeatmapProps> = ({ data, onSupplierClick }) => {
  const option = useMemo(() => {
    const yData = data.rows.map((r) => r.supplier_name);
    const xData = data.columns.map((c) => c.label);

    const seriesData: Array<[number, number, number, string]> = [];
    data.rows.forEach((row, yIdx) => {
      row.cells.forEach((cell, xIdx) => {
        seriesData.push([xIdx, yIdx, cell.risk_index ?? 0, getCellColor(cell, data.columns[xIdx])]);
      });
    });

    return {
      tooltip: {
        formatter: (params: any) => {
          const row = data.rows[params.data[1]];
          const col = data.columns[params.data[0]];
          const cell = row?.cells[params.data[0]];
          if (!cell) return "";
          return `<strong>${row.supplier_name}</strong><br/>${col.label}: ${cell.value ?? "N/A"}${cell.diff != null ? ` (Δ${cell.diff > 0 ? "+" : ""}${cell.diff.toFixed(1)})` : ""}<br/>来源: ${cell.source}`;
        },
      },
      grid: { top: 40, right: 20, bottom: 60, left: 120 },
      xAxis: { type: "category", data: xData, axisLabel: { fontSize: 11 } },
      yAxis: { type: "category", data: yData, axisLabel: { fontSize: 11 } },
      series: [{
        type: "heatmap",
        data: seriesData,
        itemStyle: {
          color: (params: any) => params.data[3],
        },
        label: {
          show: true,
          formatter: (params: any) => {
            const row = data.rows[params.data[1]];
            const cell = row?.cells[params.data[0]];
            return cell?.value != null ? String(Math.round(cell.value * 10) / 10) : "-";
          },
          fontSize: 10,
        },
        emphasis: { itemStyle: { borderColor: "#1890ff", borderWidth: 2 } },
      }],
    };
  }, [data]);

  return (
    <ReactECharts
      option={option}
      style={{ height: "auto", minHeight: Math.max(300, data.rows.length * 45 + 80) }}
      onEvents={{ click: (params: any) => {
        if (onSupplierClick && params.data) {
          const row = data.rows[params.data[1]];
          if (row) onSupplierClick(row.supplier_id);
        }
      }}}
    />
  );
};

export default RiskHeatmap;
