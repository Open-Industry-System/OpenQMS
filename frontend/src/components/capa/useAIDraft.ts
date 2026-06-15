import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("capa");
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
        // Race-condition guard: ignore stale responses
        if (requestIdRef.current !== reqId) return;
        setDraft(resp);
      } catch (e: unknown) {
        if (requestIdRef.current !== reqId) return;
        const err = e as { response?: { data?: { detail?: string }; status?: number } };
        const status = err.response?.status;

        if (status === 400) {
          setError(t("draft.errors.400"));
          setErrorLevel("error");
        } else if (status === 409) {
          setError(t("draft.errors.409"));
          setErrorLevel("warning");
        } else if (status === 422) {
          setError(t("draft.errors.422"));
          setErrorLevel("error");
        } else if (status === 429) {
          setError(t("draft.errors.429"));
          setErrorLevel("warning");
        } else if (status === 503) {
          setTempUnavailable(true);
          setError(t("draft.errors.503"));
          setErrorLevel("error");
        } else if (status === 504) {
          setError(t("draft.errors.504"));
          setErrorLevel("error");
        } else {
          setError(t("draft.errors.default"));
          setErrorLevel("error");
        }
      } finally {
        if (requestIdRef.current === reqId) {
          setLoading(false);
        }
      }
    },
    [t]
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
