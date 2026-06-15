import { useEffect, useState, useMemo } from "react";
import {
  Card, List, Tag, Button, Space, Typography, Tooltip, Badge, App, Empty, Spin,
} from "antd";
import {
  LinkOutlined, CheckOutlined, CloseOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getD7Recommendations } from "../../api/capa";
import { getFMEA, updateFMEA } from "../../api/fmea";
import type { D7Recommendation } from "../../types";

const { Text } = Typography;

export interface D7UnconfirmedItem {
  fmea_id: string;
  failure_mode_node_id: string;
  failure_mode_name: string;
  failure_cause_node_id: string | null;
}

interface D7RecPanelProps {
  capaId: string;
  d5Correction: string | null;
  onConfirmationChange: (allConfirmed: boolean, unconfirmedItems: D7UnconfirmedItem[]) => void;
}

export default function D7RecPanel({
  capaId,
  d5Correction,
  onConfirmationChange,
}: D7RecPanelProps) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState<D7Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmedNodes, setConfirmedNodes] = useState<Map<string, "updated" | "skipped">>(new Map());
  const [fillingNode, setFillingNode] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getD7Recommendations(capaId)
      .then((res) => setRecommendations(res.recommendations))
      .catch(() => message.error(t("d7.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capaId]);

  useEffect(() => {
    if (recommendations.length === 0) {
      onConfirmationChange(true, []);
      return;
    }
    const unconfirmed: D7UnconfirmedItem[] = recommendations
      .filter((r) => !confirmedNodes.has(r.failure_mode_node_id + (r.failure_cause_node_id || "")))
      .map((r) => ({
        fmea_id: String(r.fmea_id),
        failure_mode_node_id: r.failure_mode_node_id,
        failure_mode_name: r.failure_mode_name,
        failure_cause_node_id: r.failure_cause_node_id,
      }));
    onConfirmationChange(unconfirmed.length === 0, unconfirmed);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmedNodes, recommendations]);

  const linked = useMemo(
    () => recommendations.filter((r) => r.match_source === "linked"),
    [recommendations]
  );
  const keyword = useMemo(
    () => recommendations.filter((r) => r.match_source === "keyword"),
    [recommendations]
  );

  const confirmedCount = useMemo(() => {
    return recommendations.filter((r) =>
      confirmedNodes.has(r.failure_mode_node_id + (r.failure_cause_node_id || ""))
    ).length;
  }, [confirmedNodes, recommendations]);

  const handleConfirm = (rec: D7Recommendation, status: "updated" | "skipped") => {
    const key = rec.failure_mode_node_id + (rec.failure_cause_node_id || "");
    setConfirmedNodes((prev) => new Map(prev).set(key, status));
  };

  const handleAutoFill = async (rec: D7Recommendation) => {
    if (!d5Correction || !rec.failure_cause_node_id) return;
    setFillingNode(rec.failure_cause_node_id);
    try {
      const fmea = await getFMEA(rec.fmea_id);
      const graph = fmea.graph_data;

      const existingControl = graph.nodes.find(
        (n: any) =>
          n.type === "PreventionControl" &&
          graph.edges.some(
            (e: any) =>
              e.source === rec.failure_cause_node_id &&
              e.target === n.id &&
              e.type === "PREVENTED_BY"
          )
      );

      if (existingControl) {
        existingControl.name = d5Correction;
      } else {
        const newControlId = crypto.randomUUID();
        graph.nodes.push({
          id: newControlId,
          type: "PreventionControl",
          name: d5Correction,
          severity: 1,
          occurrence: 1,
          detection: 1,
        });
        graph.edges.push({
          source: rec.failure_cause_node_id,
          target: newControlId,
          type: "PREVENTED_BY",
        });
      }

      await updateFMEA(rec.fmea_id, { graph_data: graph });
      message.success(t("d7.autoFillSuccess"));

      handleConfirm(rec, "updated");

      const refreshed = await getD7Recommendations(capaId);
      setRecommendations(refreshed.recommendations);
    } catch {
      message.error(t("d7.autoFillFailed"));
    } finally {
      setFillingNode(null);
    }
  };

  const handleJump = (rec: D7Recommendation) => {
    navigate(`/fmea/${rec.fmea_id}?node=${rec.failure_mode_node_id}`);
  };

  if (loading) return <Spin size="small" />;

  if (recommendations.length === 0) {
    return (
      <Card title={t("d7.title")} size="small">
        <Empty description={t("d7.empty")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const renderRecItem = (rec: D7Recommendation) => {
    const key = rec.failure_mode_node_id + (rec.failure_cause_node_id || "");
    const confirmed = confirmedNodes.get(key);

    return (
      <List.Item
        key={key}
        actions={[
          <Button
            key="jump"
            size="small"
            icon={<LinkOutlined />}
            onClick={() => handleJump(rec)}
          >
            {t("d7.jump")}
          </Button>,
          rec.failure_cause_node_id && d5Correction ? (
            <Tooltip
              key="fill"
              title={
                rec.prevention_control_node_id
                  ? t("d7.autoFillTooltipUpdate")
                  : t("d7.autoFillTooltipNew")
              }
            >
              <Button
                size="small"
                type="primary"
                ghost
                icon={<ThunderboltOutlined />}
                loading={fillingNode === rec.failure_cause_node_id}
                onClick={() => handleAutoFill(rec)}
              >
                {t("d7.autoFill")}
              </Button>
            </Tooltip>
          ) : (
            <Tooltip
              key="fill-disabled"
              title={!rec.failure_cause_node_id ? t("d7.autoFillDisabledNoCause") : t("d7.autoFillDisabledNoD5")}
            >
              <Button size="small" icon={<ThunderboltOutlined />} disabled>
                {t("d7.autoFill")}
              </Button>
            </Tooltip>
          ),
          <Button
            key="confirm"
            size="small"
            type={confirmed === "updated" ? "primary" : "default"}
            icon={<CheckOutlined />}
            onClick={() => handleConfirm(rec, "updated")}
          >
            {t("d7.updated")}
          </Button>,
          <Button
            key="skip"
            size="small"
            danger={confirmed === "skipped"}
            icon={<CloseOutlined />}
            onClick={() => handleConfirm(rec, "skipped")}
          >
            {t("d7.skipped")}
          </Button>,
        ]}
      >
        <List.Item.Meta
          title={
            <Space>
              <Text strong>{rec.failure_mode_name}</Text>
              {rec.failure_cause_name && (
                <Text type="secondary">→ {rec.failure_cause_name}</Text>
              )}
              {rec.prevention_control_name && (
                <Tag color="green">{t("d7.existing", { name: rec.prevention_control_name })}</Tag>
              )}
              {!rec.prevention_control_name && rec.failure_cause_node_id && (
                <Tag color="orange">{t("d7.needsNew")}</Tag>
              )}
            </Space>
          }
          description={
            <Space>
              <Tag color="blue">{rec.fmea_document_no}</Tag>
              <Tag>{t(`d7.matchSource.${rec.match_source === "linked" ? "linked" : "similar"}`)}</Tag>
              {rec.match_reason && <Text type="secondary">{rec.match_reason}</Text>}
              {confirmed && (
                <Tag color={confirmed === "updated" ? "green" : "default"}>
                  {confirmed === "updated" ? `✓ ${t("d7.updated")}` : `✗ ${t("d7.skipped")}`}
                </Tag>
              )}
            </Space>
          }
        />
      </List.Item>
    );
  };

  return (
    <Card
      title={
        <Space>
          {t("d7.title")}
          <Badge count={confirmedCount} overflowCount={99} style={{ backgroundColor: "#52c41a" }} />
          <Text type="secondary">/ {recommendations.length}</Text>
        </Space>
      }
      size="small"
    >
      {linked.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>{t("d7.linkedNodes")}</Text>
          <List
            size="small"
            dataSource={linked}
            renderItem={renderRecItem}
            style={{ marginBottom: 16 }}
          />
        </>
      )}
      {keyword.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>
            {t("d7.similarNodes")}
          </Text>
          <List size="small" dataSource={keyword} renderItem={renderRecItem} />
        </>
      )}
    </Card>
  );
}
