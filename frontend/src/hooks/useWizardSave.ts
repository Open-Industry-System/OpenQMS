import { useRef, useState, useCallback } from 'react';
import { message } from 'antd';
import { updateFMEA } from '../api/fmea';
import type { GraphData } from '../types';

interface UseWizardSaveOptions {
  fmeaId: string;
}

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function useWizardSave({ fmeaId }: UseWizardSaveOptions) {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const lockVersionRef = useRef<number>(0);
  const queueTailRef = useRef<Promise<boolean>>(Promise.resolve(false));
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Hash of the last payload that was successfully saved — never reads live page state. */
  const lastSavedHashRef = useRef<string>('');

  const setLockVersion = useCallback((v: number) => {
    lockVersionRef.current = v;
  }, []);

  /** Serial save: enqueues after any in-flight save, returns true on success.
   *  `dataHash` is the hash of the payload snapshot AT enqueue time. On success,
   *  the hook writes `dataHash` into `lastSavedHashRef` — NOT the current page state. */
  const enqueueSave = useCallback(async (
    graphData: GraphData,
    title?: string,
    dataHash?: string,
  ): Promise<boolean> => {
    const doSave = async (): Promise<boolean> => {
      try {
        setSaveStatus('saving');
        const resp = await updateFMEA(fmeaId, {
          ...(title ? { title } : {}),
          graph_data: graphData,
          lock_version: lockVersionRef.current,
        });
        lockVersionRef.current = resp.lock_version ?? resp.version;
        if (dataHash) lastSavedHashRef.current = dataHash;
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 2000);
        return true;
      } catch (err: any) {
        setSaveStatus('error');
        if (err?.response?.status === 409 || String(err?.response?.data?.detail).includes('lock_version')) {
          message.error('数据已被其他会话修改，请刷新页面后重试');
        } else {
          message.error('保存失败，请重试');
        }
        return false;
      }
    };

    // Chain this save onto the tail of the queue
    const prevTail = queueTailRef.current;
    const newTail = prevTail.then(() => doSave());
    queueTailRef.current = newTail;
    return newTail;
  }, [fmeaId]);

  /** Debounced save: 500ms delay, cancels previous timer. Returns void (fire-and-forget). */
  const debouncedSave = useCallback((graphData: GraphData, title?: string, dataHash?: string) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
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
    debouncedSave,
    immediateSave,
    lastSavedHashRef,
  };
}