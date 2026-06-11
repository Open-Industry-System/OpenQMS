import { useState, useEffect, useCallback } from "react";
import { Card, Button, Spin, Empty, Alert, Badge, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
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
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

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
    } catch (e) {
      setError("加载校验结果失败");
      return null;
    }
  }, [cpId]);

  const handleTrigger = async () => {
    setLoading(true);
    setError(null);
    try {
      await triggerValidation(cpId);
      setPolling(true);
      setPollCount(0);
    } catch (e) {
      setError("触发校验失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!polling) return;

    const timer = setInterval(async () => {
      const status = await fetchData();
      setPollCount((c) => c + 1);

      if (status === "completed" || status === "failed" || pollCount >= MAX_POLLS) {
        setPolling(false);
      }
    }, POLL_INTERVAL);

    return () => clearInterval(timer);
  }, [polling, cpId, pollCount, fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAction = async (action: (id: string) => Promise<unknown>, id: string) => {
    setLoading(true);
    try {
      await action(id);
      await fetchData();
    } catch (e) {
      setError("操作失败");
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
            智能校验
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
            {polling ? "校验中..." : "重新校验"}
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
          <Text type="secondary" style={{ display: "block", marginTop: 8 }}>正在执行校验...</Text>
        </div>
      )}

      {!polling && results.length === 0 && !error && (
        <Empty description="暂无校验结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
            共 {summary.total} 项:{" "}
            <span style={{ color: "#ff4d4f" }}>{summary.error_count} 错误</span>,{" "}
            <span style={{ color: "#faad14" }}>{summary.warning_count} 警告</span>,{" "}
            <span style={{ color: "#1890ff" }}>{summary.info_count} 提示</span>
            {" | "}
            {summary.open_count} 待处理, {summary.resolved_count} 已解决, {summary.rejected_count} 已忽略
          </Text>
        </div>
      )}
    </Card>
  );
}
