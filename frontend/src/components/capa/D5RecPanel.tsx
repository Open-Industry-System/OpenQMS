import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App, Collapse } from "antd";
import { CheckOutlined, CloseOutlined, SafetyOutlined } from "@ant-design/icons";
import { getD5Recommendations } from "../../api/capa";
import type { D5ExistingControl, D5GeneralSuggestion } from "../../types";

const { Text } = Typography;

interface D5RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D5RecPanel({ capaId, onAdopt, canAdopt = true }: D5RecPanelProps) {
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
      .catch(() => message.error("加载 D5 推荐失败"))
      .finally(() => setLoading(false));
  }, [capaId]);

  if (loading) return <Spin size="small" />;
  if (controls.length === 0 && suggestions.length === 0) {
    return <Empty description="暂无推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
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
            title={!canAdopt ? "只读用户无法采纳" : undefined}
            onClick={() => onAdopt(item.control_name)}
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
          title={
            <Space>
              {item.control_name}
              <Tag color={item.control_type === "prevention" ? "green" : "orange"}>
                {item.control_type === "prevention" ? "预防" : "探测"}
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
            onClick={() => onAdopt(item.content)}
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
          title={item.content}
          description={
            <Space size={4}>
              <Tag color={item.category === "预防措施" ? "green" : "orange"}>{item.category}</Tag>
              <Tag color="default">{item.basis}</Tag>
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
      label: `FMEA 已有控制措施 (${controls.length})`,
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
      label: `通用建议 (${suggestions.length})`,
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
      title={<Space><SafetyOutlined />D5 纠正措施推荐</Space>}
      style={{ marginBottom: 16 }}
    >
      <Collapse defaultActiveKey={["controls", "suggestions"]} items={collapseItems} />
    </Card>
  );
}
