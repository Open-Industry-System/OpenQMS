import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App } from "antd";
import { CheckOutlined, CloseOutlined, SearchOutlined } from "@ant-design/icons";
import { getD4Recommendations } from "../../api/capa";
import type { D4Recommendation } from "../../types";

const { Text } = Typography;

interface D4RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D4RecPanel({ capaId, onAdopt, canAdopt = true }: D4RecPanelProps) {
  const { message } = App.useApp();
  const [recommendations, setRecommendations] = useState<D4Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD4Recommendations(capaId)
      .then((res) => setRecommendations(res.items))
      .catch(() => message.error("加载 D4 推荐失败"))
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
            暂无推荐
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              提示：完善 D2 问题描述可提升语义匹配效果
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
                    title={!canAdopt ? "只读用户无法采纳" : undefined}
                    onClick={() => onAdopt(item.failure_cause_name)}
                  >
                    采纳
                  </Button>,
                  !isSkipped && (
                    <Button
                      key="skip"
                      type="link"
                      size="small"
                      icon={<CloseOutlined />}
                      onClick={() => setSkipped(new Set(skipped).add(key))}
                    >
                      跳过
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
      title={<Space><SearchOutlined />D4 根因推荐</Space>}
      style={{ marginBottom: 16 }}
      extra={<Text type="secondary" style={{ fontSize: 12 }}>基于 D2 问题描述和关联 FMEA 分析</Text>}
    >
      {renderGroup("关联 FMEA", groups.linked)}
      {renderGroup("语义匹配", groups.semantic)}
      {renderGroup("历史 CAPA", groups.historical)}
      {renderGroup("智能建议", groups.llm)}
      {renderGroup("规则引擎建议", groups.rule)}
    </Card>
  );
}
