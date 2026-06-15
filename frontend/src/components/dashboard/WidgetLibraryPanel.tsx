import { useState, useMemo } from "react";
import { Input, Collapse, Button, theme } from "antd";
import { SearchOutlined, PlusOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { usePermission } from "../../hooks/usePermission";
import { getAllWidgets, getWidgetNameKey } from "./widgets/registry";
import type { WidgetMeta } from "./widgets/types";

interface WidgetLibraryPanelProps {
  onAddWidget: (type: string) => void;
}

export default function WidgetLibraryPanel({ onAddWidget }: WidgetLibraryPanelProps) {
  const { t } = useTranslation("dashboard");
  const { token } = theme.useToken();
  const { canView } = usePermission();
  const [search, setSearch] = useState("");

  const categoryLabels: Record<string, string> = useMemo(
    () => ({
      kpi: t("widgetLibrary.category.kpi"),
      alert: t("widgetLibrary.category.alert"),
      chart: t("widgetLibrary.category.chart"),
      list: t("widgetLibrary.category.list"),
      ai: t("widgetLibrary.category.ai"),
    }),
    [t]
  );

  const allWidgets = useMemo(
    () => getAllWidgets().filter((w) => canView(w.module)),
    [canView]
  );

  const filtered = search
    ? allWidgets.filter((w) => t(getWidgetNameKey(w.type)).toLowerCase().includes(search.toLowerCase()))
    : allWidgets;

  const byCategory: Record<string, WidgetMeta[]> = {};
  filtered.forEach((w) => {
    byCategory[w.category] = byCategory[w.category] || [];
    byCategory[w.category].push(w);
  });

  const items = Object.entries(byCategory).map(([cat, widgets]) => ({
    key: cat,
    label: `${categoryLabels[cat] || cat} (${widgets.length})`,
    children: (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {widgets.map((w) => (
          <Button
            key={w.type}
            type="dashed"
            block
            icon={<PlusOutlined />}
            onClick={() => onAddWidget(w.type)}
            style={{ textAlign: "left" }}
          >
            {t(getWidgetNameKey(w.type))}
          </Button>
        ))}
      </div>
    ),
  }));

  return (
    <div
      style={{
        width: 240,
        height: "100%",
        borderRight: `1px solid ${token.colorBorderSecondary}`,
        padding: 16,
        overflowY: "auto",
        background: token.colorBgContainer,
      }}
    >
      <h4 style={{ marginBottom: 12 }}>{t("widgetLibrary.title")}</h4>
      <Input
        placeholder={t("widgetLibrary.searchPlaceholder")}
        prefix={<SearchOutlined />}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Collapse items={items} defaultActiveKey={["kpi", "alert", "ai"]} ghost />
    </div>
  );
}
