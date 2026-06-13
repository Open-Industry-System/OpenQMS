import { useCallback, useMemo } from "react";
import { useAuthStore } from "../store/authStore";

export type ModuleKey =
  | "fmea" | "capa" | "dashboard" | "audit" | "customer_quality"
  | "customer_audit" | "supplier" | "iqc" | "ppap" | "spc"
  | "msa" | "planning" | "management_review" | "user_mgmt"
  | "permission_mgmt" | "special_characteristic" | "quality_goal" | "scar"
  | "knowledge_graph" | "plm" | "mes" | "erp" | "supplier_risk" | "supply_chain_risk_map" | "group";

export enum PermissionLevel {
  NONE = 0, VIEW = 1, CREATE = 2, EDIT = 3, APPROVE = 4, ADMIN = 5,
}

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const permissions = useMemo(() => user?.permissions ?? {}, [user]);
  const getLevel = useMemo(() => {
    return (module: ModuleKey): PermissionLevel => {
      return (permissions[module] ?? 0) as PermissionLevel;
    };
  }, [permissions]);
  const canView = useCallback((module: ModuleKey) => getLevel(module) >= PermissionLevel.VIEW, [getLevel]);
  const canCreate = useCallback((module: ModuleKey) => getLevel(module) >= PermissionLevel.CREATE, [getLevel]);
  const canEdit = useCallback((module: ModuleKey) => getLevel(module) >= PermissionLevel.EDIT, [getLevel]);
  const canApprove = useCallback((module: ModuleKey) => getLevel(module) >= PermissionLevel.APPROVE, [getLevel]);
  const canAdmin = useCallback((module: ModuleKey) => getLevel(module) >= PermissionLevel.ADMIN, [getLevel]);
  return {
    getLevel,
    canView,
    canCreate,
    canEdit,
    canApprove,
    canAdmin,
    isAdmin: user?.role_key === "admin",
    roleKey: user?.role_key ?? "viewer",
  };
}
