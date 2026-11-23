import { useEffect, useRef, useState } from "react";
import { getTaskActivity, parseActivityPage } from "../../api/agentTasks";
import { useAuthStore } from "../../store/authStore";
import type { ActivityPage } from "../../types/agentTask";
export function readAgentIdentity(): string {
  const { user, token } = useAuthStore.getState();
  return user?.user_id && (token || localStorage.getItem("access_token")) ? JSON.stringify([user.user_id, localStorage.getItem("tenant_slug") ?? ""]) : "";
}
export const readAgentCredential = () => localStorage.getItem("access_token") ?? useAuthStore.getState().token ?? "";
export function readAgentScope(): string {
  const { user, currentFactoryId, factoryScope } = useAuthStore.getState();
  return JSON.stringify([
    localStorage.getItem("current_factory_id"), currentFactoryId, factoryScope,
    user?.role_key, user?.permissions, user?.product_lines, user?.bypass_row_level_security, user?.is_active,
  ]);
}
const MAX_CONSECUTIVE_FAILURES = 3;
type StoppedStatus = "offline" | "denied";
export type ActivityStatus = "loading" | "ready" | "interrupted" | StoppedStatus;
interface Options {
  taskId: string | null;
  identity: string;
  credential: string;
  open: boolean;
  scope?: string;
  requestEpoch: number;
  selectionEpoch?: number;
}
interface Snapshot {
  key: string;
  page: ActivityPage | null;
  status: ActivityStatus;
}
interface PollingState {
  key: string;
  requestEpoch: number;
  failures: number;
  stopped?: StoppedStatus;
}
export function useAgentTaskActivity({ taskId, identity, credential, open, requestEpoch, selectionEpoch = 0, scope = readAgentScope() }: Options) {
  const [visible, setVisible] = useState(!document.hidden);
  const [visibilityEpoch, setVisibilityEpoch] = useState(0);
  const connectionKey = JSON.stringify([taskId, identity, credential, scope, open, selectionEpoch]);
  const key = JSON.stringify([connectionKey, visible, visibilityEpoch]);
  const [snapshot, setSnapshot] = useState<Snapshot>({ key, page: null, status: "loading" });
  const polling = useRef<PollingState | null>(null);
  const generation = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const latestKey = useRef(key);
  latestKey.current = key;
  useEffect(() => {
    const change = () => {
      ++generation.current;
      activeController.current?.abort();
      setVisible(!document.hidden);
      setVisibilityEpoch(n => n + 1);
    };
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => {
    const epoch = ++generation.current;
    const controller = new AbortController();
    activeController.current = controller;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const live = () => generation.current === epoch && latestKey.current === key && !controller.signal.aborted && open && !document.hidden && identity === readAgentIdentity() && credential === readAgentCredential() && scope === readAgentScope();
    // A tab visibility change pauses polling, without clearing an outage or a denial.
    const state: PollingState = polling.current?.key === connectionKey && polling.current.requestEpoch === requestEpoch
      ? polling.current : { key: connectionKey, requestEpoch, failures: 0 };
    polling.current = state;
    if (state.stopped) {
      setSnapshot({ key, page: null, status: state.stopped });
      return () => controller.abort();
    }
    setSnapshot(previous => previous.key === key && previous.status === "ready"
      ? previous : { key, page: null, status: "loading" });
    if (!taskId || !identity || !open || !visible)
      return () => controller.abort();
    async function cycle() {
      let delay = 2000;
      try {
        const latest = parseActivityPage(await getTaskActivity(taskId!, { page_size: 50 }, controller.signal));
        if (!live()) {
          if (generation.current === epoch)
            setSnapshot({ key, page: null, status: "loading" });
          return;
        }
        if (latest.task_id !== taskId)
          throw new Error("Wrong task activity");
        if (latest.next_before_sequence !== null && latest.next_before_sequence !== latest.items[0]?.sequence)
          throw new Error("Invalid latest activity cursor");
        let history: ActivityPage | null = null;
        if (latest.next_before_sequence !== null) {
          history = parseActivityPage(await getTaskActivity(taskId!, { page_size: 50, before_sequence: latest.next_before_sequence, window_end_sequence: latest.window_end_sequence }, controller.signal));
          if (history.task_id !== taskId || history.window_end_sequence !== latest.window_end_sequence || history.items.some(i => i.sequence >= latest.next_before_sequence!))
            throw new Error("Invalid adjacent activity window");
        }
        if (!live()) {
          if (generation.current === epoch)
            setSnapshot({ key, page: null, status: "loading" });
          return;
        }
        const rows = new Map([...history?.items ?? [], ...latest.items].map(item => [item.sequence, item]));
        state.failures = 0;
        setSnapshot({
          key, status: "ready", page: {
            ...latest,
            task_status: history?.task_status ?? latest.task_status,
            run_id: history ? history.run_id : latest.run_id,
            run_status: history ? history.run_status : latest.run_status,
            lease_epoch: history ? history.lease_epoch : latest.lease_epoch,
            items: [...rows.values()].sort((a, b) => a.sequence - b.sequence).slice(-100)
          }
        });
      } catch (error) {
        if (!live()) {
          if (generation.current === epoch)
            setSnapshot({ key, page: null, status: "loading" });
          return;
        }
        const status = (error as {
          response?: {
            status?: number;
          };
        })?.response?.status;
        if (status === 401 || status === 403 || status === 404)
          state.stopped = "denied";
        else if (++state.failures >= MAX_CONSECUTIVE_FAILURES)
          state.stopped = "offline";
        setSnapshot({ key, page: null, status: state.stopped ?? "interrupted" });
        if (state.stopped)
          return;
        delay = 5000;
      }
      if (live())
        timer = setTimeout(cycle, delay);
    }
    void cycle();
    return () => {
      ++generation.current;
      controller.abort();
      if (timer)
        clearTimeout(timer);
    };
  }, [taskId, identity, credential, scope, open, visible, requestEpoch, connectionKey, key]);
  // Gate presentation synchronously as well as at promise completion. No effect
  // can flash one user's retained body during another user's render.
  const current = snapshot.key === key && identity === readAgentIdentity() && credential === readAgentCredential() && scope === readAgentScope() && open && visible && !document.hidden;
  return { page: current ? snapshot.page : null, status: current ? snapshot.status : "loading" as ActivityStatus };
}
