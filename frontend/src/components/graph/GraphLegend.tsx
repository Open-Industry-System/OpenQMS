import { Card, Space, Tag } from "antd";
import { useTranslation } from "react-i18next";
import { GRAPH_NODE_TYPES, DFMEA_LEGEND_NODE_TYPES, NODE_PRESENTATION } from "../../utils/graphPresentation";

// Light text that stays readable on the translucent colored tag fills over the
// dark UI background (the previous #1f2937 was near-invisible on dark).
const LEGEND_TEXT_COLOR = "#f0f2f5";

interface GraphLegendProps {
  /** FMEA family — when DFMEA, only DFMEA-relevant node types are listed. */
  fmeaType?: string;
}

export default function GraphLegend({ fmeaType }: GraphLegendProps) {
  const { t } = useTranslation("graph");
  const types =
    fmeaType === "DFMEA" ? DFMEA_LEGEND_NODE_TYPES : GRAPH_NODE_TYPES;

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
      </Space>
    </Card>
  );
}
