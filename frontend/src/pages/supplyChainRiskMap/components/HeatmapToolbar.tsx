import React from "react";
import { Select, Button, Space, Dropdown, message } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { riskMapApi } from "../../../api/supplyChainRiskMap";

interface HeatmapToolbarProps {
  period: string;
  productLineCode: string | null;
  onPeriodChange: (period: string) => void;
  onProductLineChange: (code: string | null) => void;
  onRefresh: () => void;
  refreshing: boolean;
  periods: string[];
  productLines: Array<{ code: string; name: string }>;
}

const HeatmapToolbar: React.FC<HeatmapToolbarProps> = ({
  period,
  productLineCode,
  onPeriodChange,
  onProductLineChange,
  onRefresh,
  refreshing,
  periods,
  productLines,
}) => {
  const handleGenerateSnapshot = async () => {
    try {
      const params = productLineCode ? { product_line_code: productLineCode } : undefined;
      const res = await riskMapApi.generateSnapshot(params);
      message.success(`已生成 ${res.data.snapshot_count} 个快照`);
      onRefresh();
    } catch {
      message.error("快照生成失败");
    }
  };

  const handleExport = async (format: "csv" | "excel") => {
    try {
      const params = {
        product_line_code: productLineCode || undefined,
        period,
        format,
      };
      const res = format === "csv"
        ? await riskMapApi.exportCsv(params)
        : await riskMapApi.exportExcel(params);
      const url = window.URL.createObjectURL(res.data as unknown as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `risk_map_${period}.${format === "csv" ? "csv" : "xlsx"}`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      message.error("导出失败");
    }
  };

  const exportMenu = {
    items: [
      { key: "csv", label: "CSV", onClick: () => handleExport("csv") },
      { key: "excel", label: "Excel", onClick: () => handleExport("excel") },
    ],
  };

  return (
    <Space style={{ marginBottom: 16 }}>
      <Select
        value={productLineCode ?? undefined}
        placeholder="全部产品线"
        allowClear
        style={{ width: 180 }}
        onChange={(val) => onProductLineChange(val ?? null)}
        options={productLines.map((pl) => ({ value: pl.code, label: pl.name }))}
      />
      <Select
        value={period}
        style={{ width: 140 }}
        onChange={onPeriodChange}
        options={periods.map((p) => ({ value: p, label: p }))}
      />
      <Button
        icon={<ReloadOutlined />}
        onClick={handleGenerateSnapshot}
        loading={refreshing}
      >
        刷新数据
      </Button>
      <Dropdown menu={exportMenu}>
        <Button icon={<DownloadOutlined />}>导出</Button>
      </Dropdown>
    </Space>
  );
};

export default HeatmapToolbar;