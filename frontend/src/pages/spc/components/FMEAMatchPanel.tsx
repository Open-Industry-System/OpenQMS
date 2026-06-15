// frontend/src/pages/spc/components/FMEAMatchPanel.tsx
import { useState, useEffect, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Modal, Button, Space, Typography, Spin, Empty, Alert,
} from "antd";
import {
  LinkOutlined, SearchOutlined, CheckCircleOutlined,
} from "@ant-design/icons";
import DataCard from "../../../components/design/DataCard";
import StatusBadge from "../../../components/design/StatusBadge";
import { getFMEAMatchRecommendations, confirmFMEAAssociation } from "../../../api/spc";
import type { FMEAMatch, FMEAMatchResponse } from "../../../types";

const { Text, Title } = Typography;

interface Props {
  alarmId: string;
  visible: boolean;
  onClose: () => void;
  onCreateCAPA: () => void;
  onConfirmed?: () => void; // 确认成功后回调，父组件可刷新列表
}

export default function FMEAMatchPanel({ alarmId, visible, onClose, onCreateCAPA, onConfirmed }: Props) {
  const { t } = useTranslation("spc");
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
    } catch (_e) {
      setError(t("fmeaMatch.loadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (rec: FMEAMatch) => {
    setConfirming(true);
    try {
      await confirmFMEAAssociation(alarmId, rec.fmea_id, rec.node_id);
      setSelectedKey(`${rec.fmea_id}:${rec.node_id}`);
      onConfirmed?.();
    } catch (_e) {
      setError(t("fmeaMatch.confirmFailed"));
    } finally {
      setConfirming(false);
    }
  };

  const selectedRec = data?.recommendations.find(
    r => `${r.fmea_id}:${r.node_id}` === selectedKey
  );

  const sourceInfo = (source: string): { text: string; icon: ReactNode; status: string } => {
    switch (source) {
      case "control_plan":
        return { text: t("fmeaMatch.source.control_plan"), icon: <LinkOutlined />, status: "info" };
      case "process_name":
        return { text: t("fmeaMatch.source.process_name"), icon: <SearchOutlined />, status: "warning" };
      case "characteristic_name":
        return { text: t("fmeaMatch.source.characteristic_name"), icon: <SearchOutlined />, status: "warning" };
      default:
        return { text: source, icon: <SearchOutlined />, status: "info" };
    }
  };

  return (
    <Modal
      title={t("fmeaMatch.title")}
      open={visible}
      onCancel={onClose}
      width={720}
      footer={
        <Space>
          <Button onClick={onClose}>{t("fmeaMatch.cancel")}</Button>
          <Button
            type="primary"
            onClick={onCreateCAPA}
            disabled={!selectedKey}
          >
            {t("fmeaMatch.createCapa")}
          </Button>
        </Space>
      }
    >
      {data && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            {t("fmeaMatch.summary", { icCode: data.ic_code, processName: data.process_name, characteristicName: data.characteristic_name })}
          </Text>
        </div>
      )}

      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}

      {loading ? (
        <Spin tip={t("fmeaMatch.loading")} />
      ) : data?.recommendations.length === 0 ? (
        <Empty description={t("fmeaMatch.empty")}>
          <Button onClick={() => fetchRecommendations(true)}>{t("fmeaMatch.refresh")}</Button>
        </Empty>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {data?.recommendations.map(rec => {
            const source = sourceInfo(rec.match_source);
            const isSelected = `${rec.fmea_id}:${rec.node_id}` === selectedKey;
            return (
              <DataCard
                key={`${rec.fmea_id}:${rec.node_id}`}
                title={null}
                style={{
                  borderColor: isSelected ? "#1890ff" : undefined,
                  background: isSelected ? "#e6f7ff" : undefined,
                }}
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Space>
                    <StatusBadge status={source?.status || "info"}>
                      {source?.icon} {source?.text}
                    </StatusBadge>
                    <StatusBadge status="info">{t("fmeaMatch.matchScore", { score: Math.round(rec.match_score * 100) })}</StatusBadge>
                  </Space>

                  <Title level={5} style={{ margin: 0 }}>
                    {rec.name}
                  </Title>

                  <Text type="secondary">{t("fmeaMatch.path", { path: rec.path })}</Text>

                  <Space>
                    <Text>RPN: {rec.rpn || "-"}</Text>
                    <Text>AP: {rec.ap || "-"}</Text>
                    <Text>S:{rec.severity || "-"} O:{rec.occurrence || "-"} D:{rec.detection || "-"}</Text>
                  </Space>

                  {rec.cause_preview.length > 0 && (
                    <Text type="secondary">
                      {t("fmeaMatch.failureCauses", { causes: rec.cause_preview.join("、") })}
                    </Text>
                  )}

                  <Text type="secondary">{t("fmeaMatch.controls", { count: rec.control_count })}</Text>

                  <Space>
                    <Button
                      type={isSelected ? "default" : "primary"}
                      size="small"
                      loading={confirming}
                      onClick={() => handleSelect(rec)}
                    >
                      {isSelected ? <><CheckCircleOutlined /> {t("fmeaMatch.source.selected")}</> : t("fmeaMatch.source.select")}
                    </Button>
                  </Space>
                </Space>
              </DataCard>
            );
          })}
        </Space>
      )}

      {selectedRec && (
        <div style={{ marginTop: 16, textAlign: "right" }}>
          <Text type="success">{t("fmeaMatch.selected", { name: selectedRec.name })}</Text>
        </div>
      )}
    </Modal>
  );
}
