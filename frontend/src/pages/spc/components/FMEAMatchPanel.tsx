// frontend/src/pages/spc/components/FMEAMatchPanel.tsx
import { useState, useEffect } from "react";
import {
  Modal, Card, Button, Tag, Space, Typography, Spin, Empty, Alert,
} from "antd";
import {
  LinkOutlined, SearchOutlined, CheckCircleOutlined,
} from "@ant-design/icons";
import { getFMEAMatchRecommendations, confirmFMEAAssociation } from "../../../api/spc";
import type { FMEAMatch, FMEAMatchResponse } from "../../../types";

const { Text, Title } = Typography;

interface Props {
  alarmId: string;
  visible: boolean;
  onClose: () => void;
  onCreateCAPA: () => void;
}

const MATCH_SOURCE_LABELS: Record<string, { text: string; icon: React.ReactNode; color: string }> = {
  control_plan: { text: "控制计划关联", icon: <LinkOutlined />, color: "blue" },
  process_name: { text: "工序名称匹配", icon: <SearchOutlined />, color: "orange" },
  characteristic_name: { text: "特性名称匹配", icon: <SearchOutlined />, color: "orange" },
};

export default function FMEAMatchPanel({ alarmId, visible, onClose, onCreateCAPA }: Props) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<FMEAMatchResponse | null>(null);
  // 选中键使用 `${fmea_id}:${node_id}` 组合，避免跨 FMEA 节点 ID 冲突
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible && alarmId) {
      fetchRecommendations();
    }
  }, [visible, alarmId]);

  const fetchRecommendations = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getFMEAMatchRecommendations(alarmId, force);
      setData(res);
      if (res.confirmed_fmea_id && res.confirmed_fmea_node_id) {
        setSelectedKey(`${res.confirmed_fmea_id}:${res.confirmed_fmea_node_id}`);
      }
    } catch (e) {
      setError("获取推荐失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (rec: FMEAMatch) => {
    setConfirming(true);
    try {
      await confirmFMEAAssociation(alarmId, rec.fmea_id, rec.node_id);
      setSelectedKey(`${rec.fmea_id}:${rec.node_id}`);
    } catch (e) {
      setError("确认关联失败");
    } finally {
      setConfirming(false);
    }
  };

  const selectedRec = data?.recommendations.find(
    r => `${r.fmea_id}:${r.node_id}` === selectedKey
  );

  return (
    <Modal
      title="FMEA 关联推荐"
      open={visible}
      onCancel={onClose}
      width={720}
      footer={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            onClick={onCreateCAPA}
            disabled={!selectedKey}
          >
            创建 CAPA 8D
          </Button>
        </Space>
      }
    >
      {data && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            SPC告警: {data.ic_code} | 工序: {data.process_name} | 特性: {data.characteristic_name}
          </Text>
        </div>
      )}

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {loading ? (
        <Spin tip="加载推荐中..." />
      ) : data?.recommendations.length === 0 ? (
        <Empty description="未找到关联的 FMEA 失效模式">
          <Button onClick={() => fetchRecommendations(true)}>刷新</Button>
        </Empty>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {data?.recommendations.map(rec => {
            const source = MATCH_SOURCE_LABELS[rec.match_source];
            const isSelected = `${rec.fmea_id}:${rec.node_id}` === selectedKey;
            return (
              <Card
                key={`${rec.fmea_id}:${rec.node_id}`}
                size="small"
                style={{
                  borderColor: isSelected ? "#1890ff" : undefined,
                  background: isSelected ? "#e6f7ff" : undefined,
                }}
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Space>
                    <Tag icon={source?.icon} color={source?.color}>
                      {source?.text}
                    </Tag>
                    <Tag>匹配度 {Math.round(rec.match_score * 100)}%</Tag>
                  </Space>

                  <Title level={5} style={{ margin: 0 }}>
                    {rec.name}
                  </Title>

                  <Text type="secondary">路径: {rec.path}</Text>

                  <Space>
                    <Text>RPN: {rec.rpn || "-"}</Text>
                    <Text>AP: {rec.ap || "-"}</Text>
                    <Text>S:{rec.severity || "-"} O:{rec.occurrence || "-"} D:{rec.detection || "-"}</Text>
                  </Space>

                  {rec.cause_preview.length > 0 && (
                    <Text type="secondary">
                      失效原因: {rec.cause_preview.join("、")}
                    </Text>
                  )}

                  <Text type="secondary">控制措施: {rec.control_count}项</Text>

                  <Space>
                    <Button
                      type={isSelected ? "default" : "primary"}
                      size="small"
                      loading={confirming}
                      onClick={() => handleSelect(rec)}
                    >
                      {isSelected ? <><CheckCircleOutlined /> 已选择</> : "选择此关联"}
                    </Button>
                  </Space>
                </Space>
              </Card>
            );
          })}
        </Space>
      )}

      {selectedRec && (
        <div style={{ marginTop: 16, textAlign: "right" }}>
          <Text type="success">已选择: {selectedRec.name}</Text>
        </div>
      )}
    </Modal>
  );
}
