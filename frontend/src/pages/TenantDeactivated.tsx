import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function TenantDeactivated() {
  const { t } = useTranslation("tenant");
  const navigate = useNavigate();
  return (
    <Result
      status="error"
      title={t("deactivated.title")}
      subTitle={t("deactivated.subtitle")}
      extra={<Button type="primary" onClick={() => navigate("/login")}>{t("deactivated.backToLogin")}</Button>}
    />
  );
}
