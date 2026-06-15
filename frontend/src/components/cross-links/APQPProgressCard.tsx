import { Card, Steps } from "antd";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

interface SubModule {
  type: "fmea" | "control_plan" | "ppap";
  id: string;
  status: string;
  label: string;
}

export default function APQPProgressCard({
  subModules,
}: {
  subModules: SubModule[];
}) {
  const { t } = useTranslation("apqp");
  const navigate = useNavigate();

  const pathMap: Record<string, string> = {
    fmea: "/fmea",
    control_plan: "/control-plans",
    ppap: "/ppap",
  };

  return (
    <Card title={t("progress.subModules")} size="small">
      <Steps
        direction="vertical"
        size="small"
        current={subModules.filter((m) => m.status === "approved").length}
        items={subModules.map((m) => ({
          title: m.label,
          description: m.status,
          style: { cursor: "pointer" },
          onClick: () => navigate(`${pathMap[m.type]}/${m.id}`),
        }))}
      />
    </Card>
  );
}
