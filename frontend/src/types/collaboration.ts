export type CollaborationAction = "viewing" | "editing" | "idle";

export interface EditingArea {
  row_key?: string;
  field?: string;
  node_id?: string;
  section?: string;
  column?: string;
}

export interface ActiveUser {
  user_id: string;
  user_name: string;
  action: CollaborationAction;
  editing_area: EditingArea | null;
}

export interface CollaborationState {
  activeUsers: ActiveUser[];
  currentUserEditing: boolean;
  isSyncing: boolean;
  startEditing: (area: EditingArea) => void;
  stopEditing: () => void;
}

export interface ConflictInfo {
  saved_by: string | null;
  saved_at: string | null;
  latest_lock_version: number;
}
