import { useState, useEffect } from "react";
import { Modal, Card, Button, Spin, Empty, Collapse, Tag, Typography } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { LessonsLearnedResponse, LessonCard } from "../../types";

const { Text } = Typography;

interface Props {
  open: boolean;
  loading: boolean;
  data: LessonsLearnedResponse | null;
  onClose: () => void;
  onViewDetail: (card: LessonCard) => void;
}

export default function LessonsLearnedModal({ open, loading, data, onClose, onViewDetail }: Props) {
  const [activeKeys, setActiveKeys] = useState<string[]>(["highlights"]);

  useEffect(() => {
    if (data && !loading) {
      const firstNonEmpty: string[] = [];
      if (data.highlights.length > 0) firstNonEmpty.push("highlights");
      if (data.categories.fmea.length > 0) firstNonEmpty.push("fmea");
      setActiveKeys(firstNonEmpty);
    }
  }, [data, loading]);

  const handleCollapseChange = (keys: string | string[]) => {
    setActiveKeys(Array.isArray(keys) ? keys : [keys]);
  };

  const renderCard = (card: LessonCard, _index: number) => (
    <Card
      key={card.id}
      size="small"
      className="lesson-card"
      style={{ marginBottom: 8, borderLeft: `3px solid ${card.same_product_line ? '#ff4d4f' : '#faad14'}` }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ flex: 1 }}>
          <Text strong style={{ fontSize: 14 }}>{card.title}</Text>
          <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>
            {card.source_document_no} · {card.source_product_line}
            {card.severity && <Tag style={{ marginLeft: 8 }}>{card.severity}</Tag>}
            <Tag color={card.same_product_line ? "red" : "orange"} style={{ marginLeft: 8 }}>
              置信度 {Math.round(card.confidence * 100)}%
            </Tag>
          </div>
          {(card.root_cause || card.action) && (
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
              {card.root_cause && <div>根因: {card.root_cause}</div>}
              {card.action && <div>措施: {card.action}</div>}
            </div>
          )}
          <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>
            推荐依据: {card.match_reason}
          </div>
        </div>
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => onViewDetail(card)}
        >
          查看详情
        </Button>
      </div>
    </Card>
  );

  const collapseItems = [
    {
      key: "highlights",
      label: `⚠️ 推荐关注 (${data?.highlights.length || 0})`,
      children: data?.highlights.map((c, i) => renderCard(c, i)) || <Empty description="无高匹配项" />,
    },
    {
      key: "fmea",
      label: `📋 FMEA 相关经验 (${data?.categories.fmea.length || 0})`,
      children: data?.categories.fmea.map((c, i) => renderCard(c, i)) || <Empty description="无" />,
    },
    {
      key: "capa",
      label: `🔧 8D 整改经验 (${data?.categories.capa.length || 0})`,
      children: data?.categories.capa.map((c, i) => renderCard(c, i)) || <Empty description="无" />,
    },
    {
      key: "audit",
      label: `✅ 审核发现 (${data?.categories.audit.length || 0})`,
      children: data?.categories.audit.map((c, i) => renderCard(c, i)) || <Empty description="无" />,
    },
  ].filter(item => {
    if (item.key === "highlights") return true;
    const count = parseInt(item.label.match(/\d+/)?.[0] || "0");
    return count > 0;
  });

  const hasAnyResults = data && (
    data.highlights.length > 0 ||
    data.categories.fmea.length > 0 ||
    data.categories.capa.length > 0 ||
    data.categories.audit.length > 0
  );

  return (
    <Modal
      open={open}
      title={
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>💡 历史经验教训</span>
          <span style={{ fontSize: 12, color: "#888" }}>
            {data?.cached ? "(来自缓存)" : ""}
          </span>
        </div>
      }
      width={720}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button type="primary" onClick={onClose}>
            跳过，直接编辑
          </Button>
        </div>
      }
      onCancel={onClose}
      closable={!loading}
      maskClosable={!loading}
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: 40 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16, color: "#888" }}>
            正在检索相关经验教训...
          </div>
        </div>
      ) : !hasAnyResults ? (
        <Empty
          description="未找到相关经验教训，开始创建吧！"
          style={{ padding: 40 }}
        />
      ) : (
        <>
          <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            基于当前文档，我们找到了以下相关经验，供您参考
          </Text>
          <Collapse
            activeKey={activeKeys}
            onChange={handleCollapseChange}
            items={collapseItems}
          />
        </>
      )}
    </Modal>
  );
}
