import { useEffect, useState } from "react";
import {
  Card, List, Tag, Button, Space, Typography, Tooltip, Badge, App, Empty, Spin,
} from "antd";
import {
  LinkOutlined, CheckOutlined, CloseOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getD7Recommendations, recordD7Action, listD7Actions, autoFillD7 } from "../../api/capa";
import type { D7Recommendation, D7NodeAction } from "../../types";

const { Text } = Typography;

export interface D7UnconfirmedItem {
  fmea_id: string | null;
  failure_mode_node_id: string;
  failure_mode_name: string | null;
  failure_cause_node_id: string | null;
}

interface D7RecPanelProps {
  capaId: string;
  d5Correction: string | null;
  canAdopt?: boolean;
  canAutoFill?: boolean;
  onConfirmationChange: (allConfirmed: boolean, unconfirmedItems: D7UnconfirmedItem[]) => void;
}

export default function D7RecPanel({
  capaId,
  d5Correction,
  canAdopt = true,
  canAutoFill = true,
  onConfirmationChange,
}: D7RecPanelProps) {
  const { t } = useTranslation("capa");
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState<D7Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [actions, setActions] = useState<D7NodeAction[]>([]);
  const [fillingNode, setFillingNode] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getD7Recommendations(capaId)
      .then((res) => setRecommendations(res.recommendations))
      .catch(() => message.error(t("d7.loadFailed")))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capaId]);

  const reloadActions = async () => {
    try { setActions(await listD7Actions(capaId)); } catch { /* ignore */ }
  };

  useEffect(() => { reloadActions(); /* eslint-disable-line */ }, [capaId]);

  const actionFor = (rec: D7Recommendation): D7NodeAction | undefined =>
    actions.find(a => a.fmea_id === rec.fmea_id && a.failure_mode_node_id === rec.failure_mode_node_id
                      && (a.failure_cause_node_id || null) === (rec.failure_cause_node_id || null));

  const actionOf = (rec: D7Recommendation) => actionFor(rec);

  const handleConfirm = async (rec: D7Recommendation, action: "confirmed" | "skipped") => {
    try {
      await recordD7Action(capaId, {
        action, fmea_id: rec.fmea_id, failure_mode_node_id: rec.failure_mode_node_id,
        failure_cause_node_id: rec.failure_cause_node_id, match_source: rec.match_source,
      });
      await reloadActions();
      const refreshed = await getD7Recommendations(capaId);
      setRecommendations(refreshed.recommendations);
    } catch { message.error(t("d7.actionFailed")); }
  };

  const handleAutoFill = async (rec: D7Recommendation) => {
    if (!d5Correction || !rec.failure_cause_node_id) return;
    setFillingNode(rec.failure_cause_node_id);
    try {
      await autoFillD7(capaId, {
        fmea_id: rec.fmea_id, failure_mode_node_id: rec.failure_mode_node_id,
        failure_cause_node_id: rec.failure_cause_node_id, match_source: rec.match_source,
      });
      message.success(t("d7.autoFillSuccess"));
      await reloadActions();
      const refreshed = await getD7Recommendations(capaId);
      setRecommendations(refreshed.recommendations);
    } catch { message.error(t("d7.autoFillFailed")); }
    finally { setFillingNode(null); }
  };

  useEffect(() => {
    if (recommendations.length === 0) { onConfirmationChange(true, []); return; }
    const unconfirmed = recommendations
      .filter(r => !actionFor(r))
      .map(r => ({ fmea_id: r.fmea_id, failure_mode_node_id: r.failure_mode_node_id,
                   failure_mode_name: r.failure_mode_name, failure_cause_node_id: r.failure_cause_node_id }));
    onConfirmationChange(unconfirmed.length === 0, unconfirmed);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actions, recommendations]);

  const linked = recommendations.filter((r) => r.match_source === "linked");
  const keyword = recommendations.filter((r) => r.match_source === "keyword");
  const rule = recommendations.filter((r) => r.match_source === "rule");

  const confirmedCount = recommendations.filter((r) => actionFor(r)).length;

  const handleJump = (rec: D7Recommendation) => {
    if (!rec.fmea_id) return;
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

  const renderRecItem = (rec: D7Recommendation, index: number) => {
    const act = actionOf(rec);
    const locked = act?.action === "auto_filled";

    return (
      <List.Item
        key={`${rec.fmea_id}:${rec.failure_mode_node_id}:${rec.failure_cause_node_id ?? "none"}`}
        data-e2e={`d7-node-action-${index}`}
        actions={[
          <Button
            key="jump"
            size="small"
            icon={<LinkOutlined />}
            disabled={!rec.fmea_id}
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
                data-e2e="d7-auto-fill"
                disabled={locked || !canAdopt || !canAutoFill}
                loading={fillingNode !== null && fillingNode === rec.failure_cause_node_id}
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
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                data-e2e="d7-auto-fill"
                disabled={locked || !canAdopt || !canAutoFill || !d5Correction || !rec.failure_cause_node_id}
                loading={fillingNode !== null && fillingNode === rec.failure_cause_node_id}
              >
                {t("d7.autoFill")}
              </Button>
            </Tooltip>
          ),
          <Button
            key="confirm"
            size="small"
            type={act?.action === "confirmed" ? "primary" : "default"}
            icon={<CheckOutlined />}
            data-e2e="d7-confirm"
            disabled={locked || !canAdopt}
            onClick={() => handleConfirm(rec, "confirmed")}
          >
            {t("d7.updated")}
          </Button>,
          <Button
            key="skip"
            size="small"
            danger={act?.action === "skipped"}
            icon={<CloseOutlined />}
            data-e2e="d7-skip"
            disabled={locked || !canAdopt}
            onClick={() => handleConfirm(rec, "skipped")}
          >
            {t("d7.skipped")}
          </Button>,
        ]}
      >
        <List.Item.Meta
          title={
            <Space>
              <Text strong>{rec.failure_mode_name || rec.suggested_prevention}</Text>
              {rec.failure_cause_name && (
                <Text type="secondary">→ {rec.failure_cause_name}</Text>
              )}
              {rec.prevention_control_name && (
                <Tag color="green">{t("d7.existing", { name: rec.prevention_control_name })}</Tag>
              )}
              {!rec.prevention_control_name && rec.failure_cause_node_id && (
                <Tag color="orange">{t("d7.needsNew")}</Tag>
              )}
              {act && (
                <Tag data-e2e="d7-action-status" className={locked ? "locked" : undefined}>
                  {act.action === "confirmed" ? t("d7.updated")
                    : act.action === "skipped" ? t("d7.skipped")
                    : t("d7.autoFill")}
                </Tag>
              )}
            </Space>
          }
          description={
            <Space>
              {rec.fmea_document_no && <Tag color="blue">{rec.fmea_document_no}</Tag>}
              <Tag>{t(`d7.matchSource.${rec.match_source === "linked" ? "linked" : rec.match_source === "rule" ? "rule" : "similar"}`)}</Tag>
              {rec.match_reason && <Text type="secondary">{rec.match_reason}</Text>}
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
            renderItem={(rec, i) => renderRecItem(rec, i)}
            style={{ marginBottom: 16 }}
          />
        </>
      )}
      {keyword.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>
            {t("d7.similarNodes")}
          </Text>
          <List size="small" dataSource={keyword} renderItem={(rec, i) => renderRecItem(rec, i + linked.length)} />
        </>
      )}
      {rule.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>
            {t("d7.ruleSuggestions", { defaultValue: "规则引擎预防建议" })}
          </Text>
          <List
            size="small"
            dataSource={rule}
            renderItem={(rec, i) => renderRecItem(rec, i + linked.length + keyword.length)}
            style={{ marginTop: 8 }}
          />
        </>
      )}
    </Card>
  );
}
