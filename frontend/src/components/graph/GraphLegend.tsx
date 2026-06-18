import { Card, Space, Tag } from "antd";
import { useTranslation } from "react-i18next";
import { GRAPH_NODE_TYPES, NODE_PRESENTATION } from "../../utils/graphPresentation";

export default function GraphLegend() {
  const { t } = useTranslation("graph");

  return (
    <Card size="small" title={t("legend.title")} style={{ width: 220 }}>
      <Space direction="vertical" size="small">
        {GRAPH_NODE_TYPES.map((type) => {
          const presentation = NODE_PRESENTATION[type];
          return (
            <Tag
              key={type}
              style={{
                backgroundColor: presentation.style.fill,
                borderColor: presentation.style.stroke,
                borderStyle: "solid",
                borderWidth: 1,
                color: "#1f2937",
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
