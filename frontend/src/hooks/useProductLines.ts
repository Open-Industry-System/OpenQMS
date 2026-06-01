import { useMemo } from "react";
import { useAuthStore } from "../store/authStore";
import { useProductLineStore } from "../store/productLineStore";

export function useProductLines() {
  const user = useAuthStore((s) => s.user);
  const productLines = user?.product_lines ?? [];
  const bypass = user?.bypass_row_level_security ?? false;
  const currentProductLine = useProductLineStore((s) => s.selected);
  const setCurrentProductLine = useProductLineStore((s) => s.setSelected);
  const hasProductLines = productLines.length > 0;
  const queryParam = useMemo(() => {
    if (bypass) return currentProductLine ?? undefined;
    if (!hasProductLines) return undefined;
    if (productLines.length === 1) return productLines[0].product_line_code;
    return currentProductLine ?? undefined;
  }, [bypass, hasProductLines, productLines, currentProductLine]);
  return { productLines, currentProductLine, setCurrentProductLine, hasProductLines, queryParam, bypass };
}
