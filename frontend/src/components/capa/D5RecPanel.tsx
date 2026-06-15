import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Empty, Spin, App, Collapse } from "antd";
import { CheckOutlined, CloseOutlined, SafetyOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { getD5Recommendations } from "../../api/capa";
import type { D5ExistingControl, D5GeneralSuggestion } from "../../types";

interface D5RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D5RecPanel({ capaId, onAdopt, canAdopt = true }: D5RecPanelProps) {
  const { t } = useTranslation("capa");
  const { t: tc } = useTranslation("common");
  const { message } = App.useApp();
  const [controls, setControls] = useState<D5ExistingControl[]>([]);
  const [suggestions, setSuggestions] = useState<D5GeneralSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD5Recommendations(capaId)
      .then((res) => {
        setControls(res.existing_controls);
        setSuggestions(res.general_suggestions);
      })
      .catch(() => message.error(t("d5.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capaId]);

  if (loading) return <Spin size="small" />;
  if (controls.length === 0 && suggestions.length === 0) {
    return <Empty description={tc("empty.data")} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const renderControl = (item: D5ExistingControl) => {
    const key = item.control_node_id;
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
            title={!canAdopt ? t("d5.readonlyTooltip") : undefined}
            onClick={() => onAdopt(item.control_name)}
          >
            {t("d5.adopt")}
          </Button>,
          !isSkipped && (
            <Button
              key="skip"
              type="link"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setSkipped(new Set(skipped).add(key))}
            >
              {t("d5.skip")}
            </Button>
          ),
        ]}
      >
        <List.Item.Meta
          title={
            <Space>
              {item.control_name}
              <Tag color={item.control_type === "prevention" ? "green" : "orange"}>
                {t(`d5.controlTypes.${item.control_type}`)}
              </Tag>
            </Space>
          }
          description={
            <Space size={4} wrap>
              {item.failure_cause_name && <Tag>{item.failure_cause_name}</Tag>}
              {item.failure_mode_name && <Tag>{item.failure_mode_name}</Tag>}
              {item.fmea_document_no && <Tag color="blue">{item.fmea_document_no}</Tag>}
            </Space>
          }
        />
      </List.Item>
    );
  };

  const renderSuggestion = (item: D5GeneralSuggestion, index: number) => {
    const key = `suggestion-${index}`;
    const isSkipped = skipped.has(key);
    const categoryLabel = t(`d5.categories.${item.category}`);
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
            title={!canAdopt ? t("d5.readonlyTooltip") : undefined}
            onClick={() => onAdopt(item.content)}
          >
            {t("d5.adopt")}
          </Button>,
          !isSkipped && (
            <Button
              key="skip"
              type="link"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setSkipped(new Set(skipped).add(key))}
            >
              {t("d5.skip")}
            </Button>
          ),
        ]}
      >
        <List.Item.Meta
          title={item.content}
          description={
            <Space size={4}>
              <Tag color="blue">
                {categoryLabel}
              </Tag>
              <Tag color="default">{item.match_reason || item.basis || t("d5.defaultBasis")}</Tag>
            </Space>
          }
        />
      </List.Item>
    );
  };

  const collapseItems = [];

  if (controls.length > 0) {
    collapseItems.push({
      key: "controls",
      label: t("d5.controls", { count: controls.length }),
      children: (
        <List
          size="small"
          dataSource={controls}
          renderItem={renderControl}
        />
      ),
    });
  }

  if (suggestions.length > 0) {
    collapseItems.push({
      key: "suggestions",
      label: t("d5.suggestions", { count: suggestions.length }),
      children: (
        <List
          size="small"
          dataSource={suggestions}
          renderItem={renderSuggestion}
        />
      ),
    });
  }

  return (
    <Card
      size="small"
      title={<Space><SafetyOutlined />{t("d5.title")}</Space>}
      style={{ marginBottom: 16 }}
    >
      <Collapse defaultActiveKey={["controls", "suggestions"]} items={collapseItems} />
    </Card>
  );
}
