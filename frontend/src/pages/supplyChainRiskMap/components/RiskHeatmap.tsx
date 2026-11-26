import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import type { HeatmapResponse, HeatmapColumn, HeatmapCell } from "../../../types";
import "./RiskHeatmap.css";

interface RiskHeatmapProps {
  data: HeatmapResponse;
  selectedSupplierIds?: readonly string[];
  onSupplierClick?: (supplierId: string) => void;
}

const RISK_LEVELS = ["low", "medium", "high", "critical"] as const;

function getCellTone(cell: HeatmapCell | undefined, column: HeatmapColumn) {
  if (cell?.value == null) return "missing";
  if (column.polarity === "neutral_exposure") return "neutral";
  const level = RISK_LEVELS.find((risk) => risk === cell.level);
  if (column.key === "risk_score" && level) return level;
  if (cell.risk_index == null) return "neutral";
  if (cell.risk_index <= 30) return "low";
  if (cell.risk_index <= 60) return "medium";
  if (column.polarity !== "lower_is_risk" && cell.risk_index <= 80) return "high";
  return "critical";
}

export default function RiskHeatmap({ data, selectedSupplierIds = [], onSupplierClick }: RiskHeatmapProps) {
  const { t, i18n } = useTranslation("supplyChainRiskMap");
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumFractionDigits: 2 });
  const columns = data.columns.map((column) => ({
    ...column,
    title: t(`heatmap.columns.${column.key}`, { defaultValue: column.label }),
  }));

  return (
    <div className="risk-heatmap">
      <ul className="risk-heatmap__legend" aria-label={t("heatmap.legend")}>
        {[...RISK_LEVELS, "missing"].map((tone) => (
          <li key={tone}>
            <span className="risk-heatmap__swatch" data-tone={tone} aria-hidden="true" />
            {t(`heatmap.tones.${tone}`)}
          </li>
        ))}
      </ul>
      <div className="risk-heatmap__scroll" role="region" aria-label={t("heatmap.title")} tabIndex={0}>
        <table
          className="risk-heatmap__table"
          aria-label={t("heatmap.title")}
          style={{ "--risk-column-count": columns.length } as CSSProperties}
        >
          <colgroup>
            <col className="risk-heatmap__supplier-width" />
            {columns.map((column) => <col key={column.key} />)}
          </colgroup>
          <thead>
            <tr>
              <th className="risk-heatmap__supplier" scope="col">{t("heatmap.supplier")}</th>
              {columns.map((column) => <th key={column.key} scope="col">{column.title}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => {
              const selected = selectedSupplierIds.includes(row.supplier_id);
              const cells = new Map(row.cells.map((cell) => [cell.key, cell]));
              const select = onSupplierClick && (() => onSupplierClick(row.supplier_id));
              return (
                <tr key={row.supplier_id} data-selected={selected}>
                  <th className="risk-heatmap__supplier" scope="row">
                    {select ? (
                      <button className="risk-heatmap__name" type="button" aria-pressed={selected} onClick={select}>
                        {row.supplier_name}
                      </button>
                    ) : row.supplier_name}
                  </th>
                  {columns.map((column) => {
                    const cell = cells.get(column.key);
                    const unit = column.type === "percent" ? "%" : "";
                    const value = cell?.value == null ? "—" : `${number.format(cell.value)}${unit}`;
                    const tone = getCellTone(cell, column);
                    const details = [
                      `${row.supplier_name} · ${column.title}`,
                      tone === "missing" ? t("heatmap.tones.missing") : value,
                    ];
                    if (tone !== "neutral" && tone !== "missing") details.push(t(`heatmap.tones.${tone}`));
                    if (cell?.diff != null) {
                      const change = `${cell.diff > 0 ? "+" : ""}${number.format(cell.diff)}${unit}`;
                      details.push(t("heatmap.change", { value: change }));
                    }
                    if (cell) {
                      const source = t(`dataSource.${cell.source}`, { defaultValue: cell.source });
                      details.push(t("heatmap.tooltipSource", { source }));
                    }
                    const label = details.join("\n");
                    return (
                      <td key={column.key}>
                        {select ? (
                          <button
                            className="risk-heatmap__value"
                            data-tone={tone}
                            type="button"
                            tabIndex={-1}
                            aria-pressed={selected}
                            aria-label={label}
                            title={label}
                            onClick={select}
                          >
                            {value}
                          </button>
                        ) : (
                          <span className="risk-heatmap__value" data-tone={tone} title={label}>{value}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
