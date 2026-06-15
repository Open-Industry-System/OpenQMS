import React from "react";
import { Tabs, Card } from "antd";
import { useTranslation } from "react-i18next";
import RuleConfigTable from "./components/RuleConfigTable";
import ChannelConfigTable from "./components/ChannelConfigTable";

const RiskConfigPage: React.FC = () => {
  const { t } = useTranslation("supplierRisk");
  return (
    <Card style={{ margin: 24 }}>
      <Tabs
        items={[
          { key: "rules", label: t("config.rules"), children: <RuleConfigTable /> },
          { key: "channels", label: t("config.channels"), children: <ChannelConfigTable /> },
        ]}
      />
    </Card>
  );
};

export default RiskConfigPage;
