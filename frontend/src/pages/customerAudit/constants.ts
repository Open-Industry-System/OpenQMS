import type { TFunction } from "i18next";

// Backend stores the literal Chinese value for the "other" customer type.
// Use getCustomerTypeMap(t) for display labels.
export const getCustomerTypeMap = (t: TFunction) => ({
  OEM: t("customerType.OEM", "OEM"),
  "Tier 1": t("customerType.Tier 1", "Tier 1"),
  "Tier 2": t("customerType.Tier 2", "Tier 2"),
  other: t("customerType.other", "其他"),
});