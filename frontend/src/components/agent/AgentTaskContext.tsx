import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { getTaskAvailability } from "../../api/agentTasks";
import { useAuthStore } from "../../store/authStore";
import type { AgentTask } from "../../types/agentTask";
import { readAgentCredential, readAgentIdentity, readAgentScope } from "./useAgentTaskActivity";
interface AgentTaskContextValue {
  available: boolean;
  identity: string;
  credential: string;
  scope: string;
  selectedTask: AgentTask | null;
  creationReportId: string | null;
  open: boolean;
  requestEpoch: number;
  selectionEpoch: number;
  setOpen: (open: boolean) => void;
  beginCreate: (reportId: string) => void;
  selectTask: (task: AgentTask) => void;
  clearTask: () => void;
  refresh: () => void;
}
const Context = createContext<AgentTaskContextValue | null>(null);
function subscribeIdentity(callback: () => void) {
  const unsubscribe = useAuthStore.subscribe(callback);
  window.addEventListener("storage", callback);
  const timer = setInterval(callback, 250);
  return () => {
    unsubscribe();
    window.removeEventListener("storage", callback);
    clearInterval(timer);
  };
}
const readSession = () => JSON.stringify([readAgentIdentity(), readAgentCredential(), readAgentScope()]);
export function AgentTaskProvider({ children }: {
  children: ReactNode;
}) {
  const snapshot = useSyncExternalStore(subscribeIdentity, readSession, readSession);
  const [identity, credential, scope] = JSON.parse(snapshot) as [
    string,
    string,
    string
  ];
  // A new identity owns a new provider immediately. Credential refresh retains
  // selection while aborting/refetching protected bodies through the hook.
  return <IdentitySession key={identity} identity={identity} credential={credential} scope={scope}>{children}</IdentitySession>;
}
function IdentitySession({ children, identity, credential, scope }: {
  children: ReactNode;
  identity: string;
  credential: string;
  scope: string;
}) {
  const [available, setAvailable] = useState(false);
  const [selectedTask, setTask] = useState<AgentTask | null>(null);
  const [creationReportId, setReport] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [requestEpoch, setEpoch] = useState(0);
  const [selectionEpoch, advanceSelection] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    if (identity)
      void getTaskAvailability(controller.signal).then(() => {
        if (!controller.signal.aborted && identity === readAgentIdentity())
          setAvailable(true);
      }).catch(() => {
        if (!controller.signal.aborted) {
          setAvailable(false);
          setTask(null);
          setReport(null);
          setOpen(false);
        }
      });
    return () => controller.abort();
  }, [identity, scope]);
  const value: AgentTaskContextValue = {
    available,
    identity,
    credential,
    scope,
    selectedTask,
    creationReportId,
    open,
    requestEpoch,
    selectionEpoch,
    setOpen: nextOpen => {
      if (nextOpen !== open) advanceSelection(n => n + 1);
      setOpen(nextOpen);
    },
    beginCreate: reportId => {
      if (available && identity === readAgentIdentity()) {
        setReport(reportId);
        if (!open) advanceSelection(n => n + 1);
        setOpen(true);
      }
    },
    selectTask: task => {
      if (available && identity === readAgentIdentity()) {
        setTask({ ...task });
        setReport(null);
        setOpen(true);
        advanceSelection(n => n + 1);
        setEpoch(n => n + 1);
      }
    },
    clearTask: () => {
      setTask(null);
      setReport(null);
      advanceSelection(n => n + 1);
      setEpoch(n => n + 1);
    },
    refresh: () => setEpoch(n => n + 1),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useAgentTaskContext = () => useContext(Context);
