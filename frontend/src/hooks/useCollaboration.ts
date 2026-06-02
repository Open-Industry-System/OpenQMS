import { useCallback, useEffect, useRef, useState } from "react";
import { heartbeat, getActiveUsers, leaveSession } from "../api/collaboration";
import type { ActiveUser, EditingArea, CollaborationState } from "../types/collaboration";

const HEARTBEAT_INTERVAL = 15000;      // 15s normal
const EDITING_INTERVAL = 8000;         // 8s when editing
const BLURRED_INTERVAL = 30000;        // 30s when tab not focused

export function useCollaboration(
  documentType: string,
  documentId: string
): CollaborationState {
  const [activeUsers, setActiveUsers] = useState<ActiveUser[]>([]);
  const [isSyncing, setIsSyncing] = useState(true);
  const [currentUserEditing, setCurrentUserEditing] = useState(false);
  const editingAreaRef = useRef<EditingArea | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastHeartbeatRef = useRef<number>(0);

  const sendHeartbeat = useCallback(async () => {
    if (!documentId) return;
    try {
      await heartbeat(
        documentType,
        documentId,
        editingAreaRef.current ? "editing" : "viewing",
        editingAreaRef.current || undefined
      );
      lastHeartbeatRef.current = Date.now();
      setIsSyncing(true);
    } catch {
      setIsSyncing(false);
    }
  }, [documentType, documentId]);

  const fetchActiveUsers = useCallback(async () => {
    if (!documentId) return;
    try {
      const resp = await getActiveUsers(documentType, documentId);
      setActiveUsers(resp.users);
      setIsSyncing(true);
    } catch {
      setIsSyncing(false);
    }
  }, [documentType, documentId]);

  const schedule = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    const interval = document.hidden
      ? BLURRED_INTERVAL
      : editingAreaRef.current
      ? EDITING_INTERVAL
      : HEARTBEAT_INTERVAL;
    intervalRef.current = setInterval(() => {
      sendHeartbeat();
      fetchActiveUsers();
    }, interval);
  }, [sendHeartbeat, fetchActiveUsers]);

  const startEditing = useCallback((area: EditingArea) => {
    editingAreaRef.current = area;
    setCurrentUserEditing(true);
    sendHeartbeat();
    schedule();  // 立即切换到 editing 间隔（8s）
  }, [sendHeartbeat, schedule]);

  const stopEditing = useCallback(() => {
    editingAreaRef.current = null;
    setCurrentUserEditing(false);
    sendHeartbeat();
    schedule();  // 切回 viewing 间隔（15s）
  }, [sendHeartbeat, schedule]);

  // Setup intervals
  useEffect(() => {
    if (!documentId) return;

    schedule();

    // Immediate first fetch
    fetchActiveUsers();

    const handleVisibility = () => {
      schedule();
      if (!document.hidden) {
        fetchActiveUsers();
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [documentId, schedule, fetchActiveUsers]);

  // Page unload: send fetch with keepalive + auth header to clean up session
  useEffect(() => {
    if (!documentId) return;

    const token = localStorage.getItem("access_token");

    const handleUnload = () => {
      const url = `/api/collaboration/leave/${documentType}/${documentId}`;
      fetch(url, {
        method: "DELETE",
        keepalive: true,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).catch(() => {});
    };

    window.addEventListener("beforeunload", handleUnload);
    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      // Normal unmount: use axios client (has auth interceptor)
      leaveSession(documentType, documentId).catch(() => {});
    };
  }, [documentType, documentId]);

  return {
    activeUsers,
    currentUserEditing,
    isSyncing,
    startEditing,
    stopEditing,
  };
}
