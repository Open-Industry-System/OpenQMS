import React from "react";
import { Button, Dropdown, message } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { riskMapApi } from "../../../api/supplyChainRiskMap";

interface ExportButtonProps {
  period: string;
  productLineCode: string | null;
}

const ExportButton: React.FC<ExportButtonProps> = ({ period, productLineCode }) => {
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

  const menuItems = [
    { key: "csv", label: "CSV", onClick: () => handleExport("csv") },
    { key: "excel", label: "Excel", onClick: () => handleExport("excel") },
  ];

  return (
    <Dropdown menu={{ items: menuItems }}>
      <Button icon={<DownloadOutlined />}>导出</Button>
    </Dropdown>
  );
};

export default ExportButton;
