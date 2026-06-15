import { useState, useEffect } from "react";
import { Modal, Card, Button, Spin, Empty, Collapse, Tag, Typography } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");
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
              {t("lessons.card.confidence", { value: Math.round(card.confidence * 100) })}
            </Tag>
          </div>
          {(card.root_cause || card.action) && (
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
              {card.root_cause && <div>{t("lessons.card.rootCause")}{card.root_cause}</div>}
              {card.action && <div>{t("lessons.card.action")}{card.action}</div>}
            </div>
          )}
          <div style={{ fontSize: 11, color: "#999", marginTop: 4 }}>
            {t("lessons.card.basis")}{card.match_reason}
          </div>
        </div>
        <Button
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => onViewDetail(card)}
        >
          {t("actions.viewDetail")}
        </Button>
      </div>
    </Card>
  );

  const collapseItems = [
    {
      key: "highlights",
      label: t("lessons.sections.highlights", { count: data?.highlights.length || 0 }),
      children: data?.highlights.map((c, i) => renderCard(c, i)) || <Empty description={tc("empty.data")} />,
    },
    {
      key: "fmea",
      label: t("lessons.sections.fmea", { count: data?.categories.fmea.length || 0 }),
      children: data?.categories.fmea.map((c, i) => renderCard(c, i)) || <Empty description={tc("empty.data")} />,
    },
    {
      key: "capa",
      label: t("lessons.sections.capa", { count: data?.categories.capa.length || 0 }),
      children: data?.categories.capa.map((c, i) => renderCard(c, i)) || <Empty description={tc("empty.data")} />,
    },
    {
      key: "audit",
      label: t("lessons.sections.audit", { count: data?.categories.audit.length || 0 }),
      children: data?.categories.audit.map((c, i) => renderCard(c, i)) || <Empty description={tc("empty.data")} />,
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
          <span>{t("lessons.title")}</span>
          <span style={{ fontSize: 12, color: "#888" }}>
            {data?.cached ? t("lessons.fromCache") : ""}
          </span>
        </div>
      }
      width={720}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button type="primary" onClick={onClose}>
            {t("lessons.skipEdit")}
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
            {t("lessons.loading")}
          </div>
        </div>
      ) : !hasAnyResults ? (
        <Empty
          description={t("lessons.empty")}
          style={{ padding: 40 }}
        />
      ) : (
        <>
          <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
            {t("lessons.description")}
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
