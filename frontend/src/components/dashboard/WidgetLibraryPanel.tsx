import { useState } from "react";
import { Input, Collapse, Button, theme } from "antd";
import { SearchOutlined, PlusOutlined } from "@ant-design/icons";
import { usePermission } from "../../hooks/usePermission";
import { getAllWidgets } from "./widgets/registry";
import type { WidgetMeta } from "./widgets/types";

interface WidgetLibraryPanelProps {
  onAddWidget: (type: string) => void;
}

const categoryLabels: Record<string, string> = {
  kpi: "KPI 指标",
  alert: "预警提醒",
  chart: "图表分析",
  list: "列表",
};

export default function WidgetLibraryPanel({ onAddWidget }: WidgetLibraryPanelProps) {
  const { token } = theme.useToken();
  const { canView } = usePermission();
  const [search, setSearch] = useState("");

  const allWidgets = getAllWidgets().filter((w) => canView(w.module));

  const filtered = search
    ? allWidgets.filter((w) => w.name.toLowerCase().includes(search.toLowerCase()))
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
            {w.name}
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
      <h4 style={{ marginBottom: 12 }}>组件库</h4>
      <Input
        placeholder="搜索组件..."
        prefix={<SearchOutlined />}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Collapse items={items} defaultActiveKey={["kpi", "alert"]} ghost />
    </div>
  );
}
