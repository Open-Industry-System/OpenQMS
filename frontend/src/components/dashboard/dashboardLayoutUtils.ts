import type { ModuleKey } from "../../hooks/usePermission";
import { getWidgetMeta } from "./widgets/registry";
import type { WidgetLayoutItem } from "./widgets/types";

export function createWidgetLayoutItem(type: string, id: string): WidgetLayoutItem {
  const meta = getWidgetMeta(type);
  const size = meta?.defaultSize ?? { w: 3, h: 2 };

  return {
    i: `${type}-${id}`,
    type,
    x: 0,
    y: 100,
    w: size.w,
    h: size.h,
  };
}

export function filterLayoutByPermission(
  layout: WidgetLayoutItem[],
  canView: (module: ModuleKey) => boolean,
): WidgetLayoutItem[] {
  return layout
    .filter((item) => {
      const meta = getWidgetMeta(item.type);
      return !meta || canView(meta.module);
    })
    .map((item) => ({ ...item }));
}

export function getWidgetErrorKey(type: string): string {
  if (type.startsWith("kpi_")) return "kpi";
  if (type.startsWith("alert_")) return "alerts";
  if (type === "recent_actions") return "recent_actions";
  if (type.startsWith("spc_")) return "spc";
  if (type.startsWith("msa_")) return "msa";
  if (type.startsWith("iqc_")) return "iqc";
  if (type.startsWith("mes_")) return "mes";
  if (type.startsWith("supplier_")) return "supplier";
  return type;
}
