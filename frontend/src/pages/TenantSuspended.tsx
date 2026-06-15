import { Result, Button } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageShell } from "../components/design";

export default function TenantSuspended() {
  const navigate = useNavigate();
  const { t } = useTranslation("tenant");
  return (
    <PageShell
      title={t("suspended.title")}
      actions={
        <Button type="primary" onClick={() => navigate("/login")}>
          {t("suspended.backToLogin")}
        </Button>
      }
    >
      <Result
        status="warning"
        subTitle={t("suspended.subtitle")}
      />
    </PageShell>
  );
}
