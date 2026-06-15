import React from "react";
import { useTranslation } from "react-i18next";
import SupplierDetail from "./SupplierDetail";
import SupplierComparison from "./SupplierComparison";

interface DetailPanelProps {
  selectedSupplierIds: string[];
  productLineCode: string | null;
  period: string;
}

const DetailPanel: React.FC<DetailPanelProps> = ({ selectedSupplierIds, productLineCode, period }) => {
  const { t } = useTranslation("supplyChainRiskMap");

  if (selectedSupplierIds.length === 0) {
    return <div style={{ padding: 24, textAlign: "center", color: "#999" }}>{t("detailPanel.clickSupplier")}</div>;
  }

  if (selectedSupplierIds.length === 1) {
    return <SupplierDetail supplierId={selectedSupplierIds[0]} productLineCode={productLineCode} period={period} />;
  }

  return <SupplierComparison supplierIds={selectedSupplierIds} productLineCode={productLineCode} period={period} />;
};

export default DetailPanel;
