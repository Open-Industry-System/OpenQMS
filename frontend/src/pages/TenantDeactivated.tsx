import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/design";

export default function TenantDeactivated() {
  const navigate = useNavigate();
  const { t } = useTranslation("tenant");
  return (
    <PageShell
      title={t("deactivated.title")}
      actions={
        <Button type="primary" onClick={() => navigate("/login")}>
          {t("deactivated.backToLogin")}
        </Button>
      }
    >
      <Result
        status="error"
        subTitle={t("deactivated.subtitle")}
      />
    </PageShell>
  );
}
