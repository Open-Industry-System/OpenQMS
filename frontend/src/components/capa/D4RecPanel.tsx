import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App } from "antd";import { CheckOutlined, CloseOutlined, SearchOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getD4Recommendations, adoptRecommendation } from "../../api/capa";
import RecommendationDAG from "./RecommendationDAG";
import type { D4Recommendation, StageRun } from "../../types";

const { Text } = Typography;

interface D4RecPanelProps {
  capaId: string;
  canAdopt?: boolean;
  beforeAdopt?: () => Promise<void>;
  onAdopted?: () => void;
}

export default function D4RecPanel({ capaId, canAdopt = true, beforeAdopt, onAdopted }: D4RecPanelProps) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const [recommendations, setRecommendations] = useState<D4Recommendation[]>([]);
  const [stages, setStages] = useState<StageRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD4Recommendations(capaId)
      .then((res) => {
        setRecommendations(res.items);
        setStages(res.stages ?? []);
      })
      .catch(() => message.error(t("d4.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capaId]);

  if (loading) return <Spin size="small" />;

  const knownSources = [
    "linked",
    "fmea_graph",
    "semantic_search",
    "keyword",
    "historical_capa",
    "llm",
    "rule",
    "same_type_product_kb",
    "lessons_learned",
    "spc_anomaly",
    "mes",
    "iqc",
    "supplier_history",
  ];

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
    same_type_product_kb: recommendations.filter((r) => r.match_source === "same_type_product_kb"),
    lessons_learned: recommendations.filter((r) => r.match_source === "lessons_learned"),
    spc_anomaly: recommendations.filter((r) => r.match_source === "spc_anomaly"),
    mes: recommendations.filter((r) => r.match_source === "mes"),
    iqc: recommendations.filter((r) => r.match_source === "iqc"),
    supplier_history: recommendations.filter((r) => r.match_source === "supplier_history"),
    other: recommendations.filter((r) => !knownSources.includes(r.match_source)),
  };

  const hasRecommendations = recommendations.length > 0;

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
                    data-e2e="d4-adopt"
                    disabled={!canAdopt}
                    title={!canAdopt ? t("d4.readonlyTooltip") : undefined}
                    onClick={async () => {
                      try {
                        await beforeAdopt?.();
                        await adoptRecommendation(capaId, {
                          d_step: "d4",
                          adopted_text: item.failure_cause_name,
                          source: item.match_source,
                          stage_index: item.stage_index,
                          item_ref: {
                            failure_cause_node_id: item.failure_cause_node_id,
                            fmea_id: item.fmea_id,
                            failure_mode_node_id: item.failure_mode_node_id,
                            // historical_capa 来源的节点 ID 为 null，靠 source_capa_id/document_no 区分，
                            // 否则两条同根因文本的历史推荐会被后端 dedupe 误并
                            source_capa_id: item.source_capa_id,
                            source_capa_document_no: item.source_capa_document_no,
                          },
                        });
                        message.success(t("d4.adopted"));
                        onAdopted?.();
                      } catch {
                        message.error(t("d4.adoptFailed"));
                      }
                    }}
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
                      <Tag data-e2e={`rec-source-${item.match_source}`}>
                        {t(`d4.sources.${item.match_source}`, { defaultValue: item.match_source })}
                      </Tag>
                      {item.stage_index != null && (
                        <Tag data-e2e={`rec-item-stage-${item.stage_index}`}>
                          {t("d4.stageLabel", { n: item.stage_index })}
                        </Tag>
                      )}
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
      {stages.length > 0 && <RecommendationDAG stages={stages} />}
      {!hasRecommendations && (
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
      )}
      {hasRecommendations && (
        <>
          {renderGroup(t("d4.groups.linked"), groups.linked)}
          {renderGroup(t("d4.groups.semantic"), groups.semantic)}
          {renderGroup(t("d4.groups.historical"), groups.historical)}
          {renderGroup(t("d4.groups.llm"), groups.llm)}
          {renderGroup(t("d4.groups.rule"), groups.rule)}
          {renderGroup(t("d4.groups.same_type_product_kb"), groups.same_type_product_kb)}
          {renderGroup(t("d4.groups.lessons_learned"), groups.lessons_learned)}
          {renderGroup(t("d4.groups.spc_anomaly"), groups.spc_anomaly)}
          {renderGroup(t("d4.groups.mes"), groups.mes)}
          {renderGroup(t("d4.groups.iqc"), groups.iqc)}
          {renderGroup(t("d4.groups.supplier_history"), groups.supplier_history)}
          {renderGroup(t("d4.groups.other"), groups.other)}
        </>
      )}
    </Card>
  );
}
