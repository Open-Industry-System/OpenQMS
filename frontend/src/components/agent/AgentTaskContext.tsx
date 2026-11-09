import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { getTaskAvailability } from "../../api/agentTasks";
import { useAuthStore } from "../../store/authStore";
import type { AgentTask } from "../../types/agentTask";
import { readAgentCredential, readAgentIdentity } from "./useAgentTaskActivity";
interface AgentTaskContextValue {
  available: boolean;
  identity: string;
  credential: string;
  selectedTask: AgentTask | null;
  creationReportId: string | null;
  open: boolean;
  requestEpoch: number;
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
const readSession = () => JSON.stringify([readAgentIdentity(), readAgentCredential()]);
export function AgentTaskProvider({ children }: {
  children: ReactNode;
}) {
  const snapshot = useSyncExternalStore(subscribeIdentity, readSession, readSession);
  const [identity, credential] = JSON.parse(snapshot) as [
    string,
    string
  ];
  // A new identity owns a new provider immediately. Credential refresh retains
  // selection while aborting/refetching protected bodies through the hook.
  return <IdentitySession key={identity} identity={identity} credential={credential}>{children}</IdentitySession>;
}
function IdentitySession({ children, identity, credential }: {
  children: ReactNode;
  identity: string;
  credential: string;
}) {
  const [available, setAvailable] = useState(false);
  const [selectedTask, setTask] = useState<AgentTask | null>(null);
  const [creationReportId, setReport] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [requestEpoch, setEpoch] = useState(0);
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
  }, [identity]);
  const value: AgentTaskContextValue = {
    available,
    identity,
    credential,
    selectedTask,
    creationReportId,
    open,
    requestEpoch,
    setOpen,
    beginCreate: reportId => {
      if (available && identity === readAgentIdentity()) {
        setReport(reportId);
        setOpen(true);
      }
    },
    selectTask: task => {
      if (available && identity === readAgentIdentity()) {
        setTask({ ...task });
        setReport(null);
        setOpen(true);
        setEpoch(n => n + 1);
      }
    },
    clearTask: () => {
      setTask(null);
      setReport(null);
      setEpoch(n => n + 1);
    },
    refresh: () => setEpoch(n => n + 1),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useAgentTaskContext = () => useContext(Context);
