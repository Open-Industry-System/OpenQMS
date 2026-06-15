import { useState, useEffect, useCallback, useRef } from "react";
import { Card, Button, Spin, Empty, Alert, Badge, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import ValidationCard from "./ValidationCard";
import {
  getValidationResults,
  getValidationSummary,
  triggerValidation,
  rejectValidationResult,
  resolveValidationResult,
  reopenValidationResult,
} from "../../api/cpValidation";
import type { ValidationResult, ValidationSummary } from "../../types/cpValidation";

const { Text } = Typography;

interface Props {
  cpId: string;
}

const POLL_INTERVAL = 2000;
const MAX_POLLS = 30;

export default function ValidationPanel({ cpId }: Props) {
  const { t } = useTranslation("controlPlan");
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollCountRef = useRef(0);
  const pollingRef = useRef(false);

  const fetchData = useCallback(async () => {
    try {
      const [resList, sum] = await Promise.all([
        getValidationResults(cpId),
        getValidationSummary(cpId),
      ]);
      setResults(resList.items);
      setSummary(sum);
      setError(null);
      return sum.status;
    } catch (_e) {
      setError(t("validation.loadFailed"));
      return null;
    }
  }, [cpId, t]);

  const handleTrigger = async () => {
    setLoading(true);
    setError(null);
    try {
      await triggerValidation(cpId);
      pollCountRef.current = 0;
      pollingRef.current = true;
      setPolling(true);
    } catch (_e) {
      setError(t("validation.triggerFailed"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    pollingRef.current = polling;
  }, [polling]);

  useEffect(() => {
    if (!polling) return;

    const tick = async () => {
      const status = await fetchData();
      pollCountRef.current += 1;

      if (
        status === "completed" ||
        status === "failed" ||
        pollCountRef.current >= MAX_POLLS
      ) {
        pollingRef.current = false;
        setPolling(false);
      }

      if (pollingRef.current) {
        timeoutRef.current = setTimeout(tick, POLL_INTERVAL);
      }
    };

    const timeoutRef = { current: setTimeout(tick, POLL_INTERVAL) } as { current: ReturnType<typeof setTimeout> };

    return () => {
      clearTimeout(timeoutRef.current);
    };
  }, [polling, cpId, fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAction = async (action: (id: string) => Promise<unknown>, id: string) => {
    setLoading(true);
    try {
      await action(id);
      await fetchData();
    } catch (_e) {
      setError(t("validation.operationFailed"));
    } finally {
      setLoading(false);
    }
  };

  const errorCount = summary?.error_count || 0;
  const warningCount = summary?.warning_count || 0;

  return (
    <Card
      title={
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>
            {t("validation.title")}
            {errorCount > 0 && <Badge count={errorCount} style={{ backgroundColor: "#ff4d4f", marginLeft: 8 }} />}
            {errorCount === 0 && warningCount > 0 && <Badge count={warningCount} style={{ backgroundColor: "#faad14", marginLeft: 8 }} />}
          </span>
          <Button
            size="small"
            icon={<ReloadOutlined spin={polling} />}
            onClick={handleTrigger}
            loading={loading}
            disabled={polling}
          >
            {polling ? t("validation.validating") : t("validation.revalidate")}
          </Button>
        </div>
      }
      size="small"
      style={{ width: 360 }}
    >
      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 12 }} />}

      {polling && results.length === 0 && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin />
          <Text type="secondary" style={{ display: "block", marginTop: 8 }}>{t("validation.validating")}</Text>
        </div>
      )}

      {!polling && results.length === 0 && !error && (
        <Empty description={t("validation.noResults")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}

      {results.length > 0 && (
        <div style={{ maxHeight: "calc(100vh - 300px)", overflowY: "auto" }}>
          {results.map((r) => (
            <ValidationCard
              key={r.occurrence_id}
              result={r}
              onReject={(id) => handleAction(rejectValidationResult, id)}
              onResolve={(id) => handleAction(resolveValidationResult, id)}
              onReopen={(id) => handleAction(reopenValidationResult, id)}
              loading={loading}
            />
          ))}
        </div>
      )}

      {summary && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f0f0f0", fontSize: 12 }}>
          <Text type="secondary">
            {t("validation.total", { total: summary.total })}:{" "}
            <span style={{ color: "#ff4d4f" }}>{t("validation.errors", { count: summary.error_count })}</span>,{" "}
            <span style={{ color: "#faad14" }}>{t("validation.warnings", { count: summary.warning_count })}</span>,{" "}
            <span style={{ color: "#1890ff" }}>{t("validation.infos", { count: summary.info_count })}</span>
            {" | "}
            {t("validation.pending", { count: summary.open_count })}, {t("validation.resolved", { count: summary.resolved_count })}, {t("validation.rejected", { count: summary.rejected_count })}
          </Text>
        </div>
      )}
    </Card>
  );
}
