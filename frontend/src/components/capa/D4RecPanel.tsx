import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App } from "antd";import { CheckOutlined, CloseOutlined, SearchOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getD4Recommendations } from "../../api/capa";
import type { D4Recommendation } from "../../types";

const { Text } = Typography;

interface D4RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D4RecPanel({ capaId, onAdopt, canAdopt = true }: D4RecPanelProps) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const [recommendations, setRecommendations] = useState<D4Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD4Recommendations(capaId)
      .then((res) => setRecommendations(res.items))
      .catch(() => message.error(t("d4.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capaId]);

  if (loading) return <Spin size="small" />;
  if (recommendations.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            {t("d4.empty")}
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("d4.hint")}
            </Text>
          </span>
        }
      />
    );
  }

  const groups = {
    linked: recommendations.filter(
      (r) => r.match_source === "linked" || r.match_source === "fmea_graph"
    ),
    semantic: recommendations.filter(
      (r) => r.match_source === "semantic_search" || r.match_source === "keyword"
    ),
    historical: recommendations.filter((r) => r.match_source === "historical_capa"),
    llm: recommendations.filter((r) => r.match_source === "llm"),
    rule: recommendations.filter((r) => r.match_source === "rule"),
  };

  const renderGroup = (title: string, items: D4Recommendation[]) => {
    if (items.length === 0) return null;
    return (
      <>
        <Text strong style={{ fontSize: 12, color: "#888" }}>{title}</Text>
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => {
            const key = item.failure_cause_node_id || item.failure_cause_name;
            const isSkipped = skipped.has(key);
            return (
              <List.Item
                style={isSkipped ? { opacity: 0.4, textDecoration: "line-through" } : {}}
                actions={[
                  <Button
                    key="adopt"
                    type="link"
                    size="small"
                    icon={<CheckOutlined />}
                    disabled={!canAdopt}
                    title={!canAdopt ? t("d4.readonlyTooltip") : undefined}
                    onClick={() => onAdopt(item.failure_cause_name)}
                  >
                    {t("d4.adopt")}
                  </Button>,
                  !isSkipped && (
                    <Button
                      key="skip"
                      type="link"
                      size="small"
                      icon={<CloseOutlined />}
                      onClick={() => setSkipped(new Set(skipped).add(key))}
                    >
                      {t("d4.skip")}
                    </Button>
                  ),
                ]}
              >
                <List.Item.Meta
                  title={item.failure_cause_name}
                  description={
                    <Space size={4} wrap>
                      {item.failure_mode_name && <Tag>{item.failure_mode_name}</Tag>}
                      {item.fmea_document_no && <Tag color="blue">{item.fmea_document_no}</Tag>}
                      {item.match_reason && <Tag color="default">{item.match_reason}</Tag>}
                      {item.related_d2_keywords?.map((kw) => (
                        <Tag key={kw} color="green">{kw}</Tag>
                      ))}
                    </Space>
                  }
                />
              </List.Item>
            );
          }}
        />
      </>
    );
  };

  return (
    <Card
      size="small"
      title={<Space><SearchOutlined />{t("d4.title")}</Space>}
      style={{ marginBottom: 16 }}
      extra={<Text type="secondary" style={{ fontSize: 12 }}>{t("d4.subtitle")}</Text>}
    >
      {renderGroup(t("d4.groups.linked"), groups.linked)}
      {renderGroup(t("d4.groups.semantic"), groups.semantic)}
      {renderGroup(t("d4.groups.historical"), groups.historical)}
      {renderGroup(t("d4.groups.llm"), groups.llm)}
      {renderGroup(t("d4.groups.rule"), groups.rule)}
    </Card>
  );
}
