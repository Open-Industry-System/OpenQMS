import { Badge, Tooltip } from "antd";
import { useTranslation } from "react-i18next";

interface Props {
  errorCount: number;
  warningCount: number;
  total: number;
  validated?: boolean;
}

export default function ValidationBadge({ errorCount, warningCount, total: _total, validated }: Props) {
  const { t } = useTranslation("controlPlan");

  if (!validated) {
    return <Tooltip title={t("validation.notValidated")}><Badge status="default" /></Tooltip>;
  }
  if (errorCount > 0) {
    return <Tooltip title={t("validation.errorsPending", { count: errorCount })}><Badge status="error" /></Tooltip>;
  }
  if (warningCount > 0) {
    return <Tooltip title={t("validation.warningsPending", { count: warningCount })}><Badge status="warning" /></Tooltip>;
  }
  return <Tooltip title={t("validation.allPassed")}><Badge status="success" /></Tooltip>;
}
