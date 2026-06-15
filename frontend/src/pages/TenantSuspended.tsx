import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function TenantSuspended() {
  const { t } = useTranslation("tenant");
  const navigate = useNavigate();
  return (
    <Result
      status="warning"
      title={t("suspended.title")}
      subTitle={t("suspended.subtitle")}
      extra={<Button type="primary" onClick={() => navigate("/login")}>{t("suspended.backToLogin")}</Button>}
    />
  );
}
