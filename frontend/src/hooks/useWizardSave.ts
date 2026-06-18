import { useEffect, useRef, useState, useCallback } from 'react';
import { message } from 'antd';
import { updateFMEA } from '../api/fmea';
import type { GraphData } from '../types';

interface UseWizardSaveOptions {
  fmeaId: string;
  /** Called once when a lock-version conflict (409) is detected. The page uses
   *  this to show a Reload / Discard modal and reset the hook on resolution. */
  onConflict?: (latestLockVersion: number | null) => void;
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error' | 'conflict';

export function useWizardSave({ fmeaId, onConflict }: UseWizardSaveOptions) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const lockVersionRef = useRef<number>(0);
  const queueTailRef = useRef<Promise<boolean>>(Promise.resolve(false));
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Hash of the last payload that was successfully saved — never reads live page state. */
  const lastSavedHashRef = useRef<string>('');
  /** Latched after a conflict: all further enqueues are rejected until resetConflict()
   *  is called (page reloaded / changes discarded). Prevents the debounced queue from
   *  thrashing a stale lock_version while the user keeps typing. */
  const conflictLatchedRef = useRef(false);
  const mountedRef = useRef(true);

  // Keep mountedRef in sync so post-unmount state updates can be suppressed.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      // Drain any pending debounce so it can't fire on an unmounted component.
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      if (statusTimerRef.current) {
        clearTimeout(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    };
  }, []);

  const setLockVersion = useCallback((v: number) => {
    lockVersionRef.current = v;
  }, []);

  /** Clear the latched conflict so saves can resume (called by the page after the
   *  user picks Reload or Discard in the conflict modal). */
  const resetConflict = useCallback((nextLockVersion?: number) => {
    conflictLatchedRef.current = false;
    if (nextLockVersion !== undefined) lockVersionRef.current = nextLockVersion;
    if (mountedRef.current) setSaveStatus('idle');
  }, []);

  const safeSetStatus = useCallback((s: SaveStatus) => {
    if (mountedRef.current) setSaveStatus(s);
  }, []);

  /** Serial save: enqueues after any in-flight save, returns true on success.
   *  `dataHash` is the hash of the payload snapshot AT enqueue time. On success,
   *  the hook writes `dataHash` into `lastSavedHashRef` — NOT the current page state. */
  const enqueueSave = useCallback(async (
    graphData: GraphData,
    title?: string,
    dataHash?: string,
  ): Promise<boolean> => {
    // Reject immediately once a conflict is latched — the page must resolve it
    // (reload / discard) before any further save is allowed.
    if (conflictLatchedRef.current) return false;

    const doSave = async (): Promise<boolean> => {
      if (conflictLatchedRef.current) return false;
      try {
        safeSetStatus('saving');
        const resp = await updateFMEA(fmeaId, {
          ...(title ? { title } : {}),
          graph_data: graphData,
          lock_version: lockVersionRef.current,
        });
        lockVersionRef.current = resp.lock_version ?? resp.version;
        if (dataHash) lastSavedHashRef.current = dataHash;
        safeSetStatus('saved');
        if (statusTimerRef.current) clearTimeout(statusTimerRef.current);
        statusTimerRef.current = setTimeout(() => safeSetStatus('idle'), 2000);
        return true;
      } catch (err: any) {
        const status = err?.response?.status;
        const conflictDetail = err?.response?.data?.detail;
        // 409 body: {detail: {detail: "...", conflict: {latest_lock_version: N}}}
        const latest = (typeof conflictDetail === 'object' && conflictDetail?.conflict?.latest_lock_version)
          ?? (typeof conflictDetail === 'object' ? conflictDetail?.latest_lock_version : null)
          ?? null;
        if (status === 409 || /lock_version/i.test(String(conflictDetail))) {
          // Latch the conflict so the queue stops thrashing the stale version,
          // and let the page show a recovery modal.
          conflictLatchedRef.current = true;
          safeSetStatus('conflict');
          // Clear any pending debounce so a queued keystroke doesn't re-fire.
          if (debounceTimerRef.current) {
            clearTimeout(debounceTimerRef.current);
            debounceTimerRef.current = null;
          }
          onConflict?.(latest);
        } else {
          safeSetStatus('error');
          if (mountedRef.current) message.error('保存失败，请重试');
        }
        return false;
      }
    };

    // Chain this save onto the tail of the queue
    const prevTail = queueTailRef.current;
    const newTail = prevTail.then(() => doSave());
    queueTailRef.current = newTail;
    return newTail;
  }, [fmeaId, onConflict, safeSetStatus]);

  /** Debounced save: 500ms delay, cancels previous timer. Returns void (fire-and-forget). */
  const debouncedSave = useCallback((graphData: GraphData, title?: string, dataHash?: string) => {
    if (conflictLatchedRef.current) return;
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      enqueueSave(graphData, title, dataHash);
    }, 500);
  }, [enqueueSave]);

  /** Immediate save: cancels debounce, saves right away. Returns true on success. */
  const immediateSave = useCallback(async (
    graphData: GraphData,
    title?: string,
    dataHash?: string,
  ): Promise<boolean> => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    return await enqueueSave(graphData, title, dataHash);
  }, [enqueueSave]);

  return {
    saveStatus,
    setLockVersion,
    resetConflict,
    debouncedSave,
    immediateSave,
    lastSavedHashRef,
  };
}
