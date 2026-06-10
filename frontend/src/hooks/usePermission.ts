import { useMemo } from "react";
import { useAuthStore } from "../store/authStore";

export type ModuleKey =
  | "fmea" | "capa" | "dashboard" | "audit" | "customer_quality"
  | "customer_audit" | "supplier" | "iqc" | "ppap" | "spc"
  | "msa" | "planning" | "management_review" | "user_mgmt"
  | "permission_mgmt" | "special_characteristic" | "quality_goal" | "scar"
  | "knowledge_graph" | "plm" | "mes";

export enum PermissionLevel {
  NONE = 0, VIEW = 1, CREATE = 2, EDIT = 3, APPROVE = 4, ADMIN = 5,
}

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const permissions = user?.permissions ?? {};
  const getLevel = useMemo(() => {
    return (module: ModuleKey): PermissionLevel => {
      return (permissions[module] ?? 0) as PermissionLevel;
    };
  }, [permissions]);
  return {
    getLevel,
    canView: (module: ModuleKey) => getLevel(module) >= PermissionLevel.VIEW,
    canCreate: (module: ModuleKey) => getLevel(module) >= PermissionLevel.CREATE,
    canEdit: (module: ModuleKey) => getLevel(module) >= PermissionLevel.EDIT,
    canApprove: (module: ModuleKey) => getLevel(module) >= PermissionLevel.APPROVE,
    canAdmin: (module: ModuleKey) => getLevel(module) >= PermissionLevel.ADMIN,
    isAdmin: user?.role_key === "admin",
    roleKey: user?.role_key ?? "viewer",
  };
}
