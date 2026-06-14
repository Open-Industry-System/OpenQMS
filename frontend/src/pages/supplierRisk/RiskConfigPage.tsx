import React from "react";
import { Tabs } from "antd";
import RuleConfigTable from "./components/RuleConfigTable";
import ChannelConfigTable from "./components/ChannelConfigTable";
import { PageShell, DataCard } from "../../components/design";

const RiskConfigPage: React.FC = () => (
  <PageShell title="风险配置">
    <DataCard title={null}>
      <Tabs
        items={[
          { key: "rules", label: "规则配置", children: <RuleConfigTable /> },
          { key: "channels", label: "通知渠道", children: <ChannelConfigTable /> },
        ]}
      />
    </DataCard>
  </PageShell>
);

export default RiskConfigPage;
