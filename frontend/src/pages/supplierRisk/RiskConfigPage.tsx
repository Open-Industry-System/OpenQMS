import React from "react";
import { Tabs } from "antd";
import { useTranslation } from "react-i18next";
import RuleConfigTable from "./components/RuleConfigTable";
import ChannelConfigTable from "./components/ChannelConfigTable";
import { PageShell, DataCard } from "../../components/design";

const RiskConfigPage: React.FC = () => {
  const { t } = useTranslation("supplierRisk");
  return (
    <PageShell title={t("config.title")}>
      <DataCard title={null}>
        <Tabs
          items={[
            { key: "rules", label: t("config.rules"), children: <RuleConfigTable /> },
            { key: "channels", label: t("config.channels"), children: <ChannelConfigTable /> },
          ]}
        />
      </DataCard>
    </PageShell>
  );
};

export default RiskConfigPage;
