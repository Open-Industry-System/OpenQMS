import React from "react";
import { Select, Button, Space, Dropdown, message } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import { usePermission } from "../../../hooks/usePermission";

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
  const { t } = useTranslation("supplyChainRiskMap");
  const { t: tc } = useTranslation("common");
  const { canEdit } = usePermission();
  const canGenerate = canEdit("supply_chain_risk_map");

  const handleGenerateSnapshot = async () => {
    try {
      const params = productLineCode ? { product_line_code: productLineCode } : undefined;
      const res = await riskMapApi.generateSnapshot(params);
      message.success(t("toolbar.snapshotSuccess", { count: res.data.snapshot_count }));
      onRefresh();
    } catch {
      message.error(t("toolbar.snapshotFailed"));
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
      message.error(t("toolbar.exportFailed"));
    }
  };

  const exportMenu = {
    items: [
      { key: "csv", label: t("export.csv"), onClick: () => handleExport("csv") },
      { key: "excel", label: t("export.excel"), onClick: () => handleExport("excel") },
    ],
  };

  return (
    <Space style={{ marginBottom: 16 }}>
      <Select
        value={productLineCode ?? undefined}
        placeholder={t("toolbar.allProductLines")}
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
      {canGenerate && (
        <Button
          icon={<ReloadOutlined />}
          onClick={handleGenerateSnapshot}
          loading={refreshing}
        >
          {t("toolbar.refresh")}
        </Button>
      )}
      <Dropdown menu={exportMenu}>
        <Button icon={<DownloadOutlined />}>{tc("actions.export")}</Button>
      </Dropdown>
    </Space>
  );
};

export default HeatmapToolbar;
