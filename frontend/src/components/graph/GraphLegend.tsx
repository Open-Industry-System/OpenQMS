import { Card, Space, Tag, Divider, Typography } from "antd";
import { useTranslation } from "react-i18next";
import {
  GRAPH_EDGE_LEGEND,
  GRAPH_NODE_TYPES,
  DFMEA_LEGEND_NODE_TYPES,
  NODE_PRESENTATION,
  getEdgeStyle,
} from "../../utils/graphPresentation";

const LEGEND_TEXT_COLOR = "#f0f2f5";

interface GraphLegendProps {
  fmeaType?: string;
}

export default function GraphLegend({ fmeaType }: GraphLegendProps) {
  const { t } = useTranslation("graph");
  const types = fmeaType === "DFMEA" ? DFMEA_LEGEND_NODE_TYPES : GRAPH_NODE_TYPES;

  return (
    <Card size="small" title={t("legend.title")} style={{ width: 220 }}>
      <Space direction="vertical" size="small">
        {types.map((type) => {
          const presentation = NODE_PRESENTATION[type];
          if (!presentation) return null;
          return (
            <Tag
              key={type}
              style={{
                backgroundColor: presentation.style.fill,
                borderColor: presentation.style.stroke,
                borderStyle: "solid",
                borderWidth: 1,
                color: LEGEND_TEXT_COLOR,
              }}
            >
              {t(presentation.translationKey, { defaultValue: type })}
            </Tag>
          );
        })}
        <Divider style={{ margin: "8px 0" }} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t("edgeLegend.title")}
        </Typography.Text>
        {GRAPH_EDGE_LEGEND.map((entry) => {
          const style = getEdgeStyle(entry.type);
          return (
            <Tag
              key={entry.type}
              style={{
                backgroundColor: "transparent",
                borderColor: style.stroke,
                borderStyle: "solid",
                borderWidth: 2,
                color: LEGEND_TEXT_COLOR,
              }}
            >
              {t(entry.translationKey, { defaultValue: entry.type })}
            </Tag>
          );
        })}
      </Space>
    </Card>
  );
}
