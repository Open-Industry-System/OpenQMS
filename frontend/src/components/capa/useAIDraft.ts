import { useState, useRef, useCallback } from "react";
import { generateDraft } from "../../api/capaDraft";
import type { DraftResponse, DraftFormat } from "../../types";

export type ErrorLevel = "warning" | "error";

export interface UseAIDraftResult {
  loading: boolean;
  draft: DraftResponse | null;
  error: string | null;
  errorLevel: ErrorLevel;
  tempUnavailable: boolean;
  generate: (reportId: string, step: string, format: DraftFormat) => void;
  clear: () => void;
  undo: (step: string) => string | undefined;
  saveUndo: (step: string, snapshot: string) => void;
  canUndo: (step: string) => boolean;
}

export function useAIDraft(): UseAIDraftResult {
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<DraftResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorLevel, setErrorLevel] = useState<ErrorLevel>("error");
  const [tempUnavailable, setTempUnavailable] = useState(false);
  const requestIdRef = useRef<string>("");
  const undoStack = useRef<Record<string, string>>({});

  const generate = useCallback(
    async (reportId: string, step: string, format: DraftFormat) => {
      setLoading(true);
      setError(null);
      setTempUnavailable(false);
      setErrorLevel("error");

      const reqId = crypto.randomUUID();
      requestIdRef.current = reqId;

      try {
        const resp = await generateDraft(reportId, step, {
          format,
          request_id: reqId,
        });
        // 竞态保护：忽略过期响应
        if (requestIdRef.current !== reqId) return;
        setDraft(resp);
      } catch (e: unknown) {
        if (requestIdRef.current !== reqId) return;
        const err = e as { response?: { data?: { detail?: string }; status?: number } };
        const status = err.response?.status;
        const detail = err.response?.data?.detail;

        if (status === 400) {
          setError("请求 ID 格式错误");
          setErrorLevel("error");
        } else if (status === 409) {
          setError(detail || "请先完成前置步骤或检查报告状态");
          setErrorLevel("warning");
        } else if (status === 422) {
          setError("AI 输出格式异常，请重试");
          setErrorLevel("error");
        } else if (status === 429) {
          setError("AI 草拟调用过于频繁，请稍后再试");
          setErrorLevel("warning");
        } else if (status === 503) {
          setTempUnavailable(true);
          setError("AI 功能暂时不可用");
          setErrorLevel("error");
        } else if (status === 504) {
          setError("AI 响应超时，请重试");
          setErrorLevel("error");
        } else {
          setError(detail || "AI 服务异常，请稍后重试");
          setErrorLevel("error");
        }
      } finally {
        if (requestIdRef.current === reqId) {
          setLoading(false);
        }
      }
    },
    []
  );

  const clear = useCallback(() => {
    setDraft(null);
    setError(null);
    setTempUnavailable(false);
    requestIdRef.current = "";
  }, []);

  const saveUndo = useCallback((step: string, snapshot: string) => {
    undoStack.current[step] = snapshot;
  }, []);

  const undo = useCallback((step: string) => {
    const prev = undoStack.current[step];
    if (prev !== undefined) {
      delete undoStack.current[step];
      return prev;
    }
    return undefined;
  }, []);

  const canUndo = useCallback((step: string) => {
    return undoStack.current[step] !== undefined;
  }, []);

  return {
    loading,
    draft,
    error,
    errorLevel,
    tempUnavailable,
    generate,
    clear,
    undo,
    saveUndo,
    canUndo,
  };
}
