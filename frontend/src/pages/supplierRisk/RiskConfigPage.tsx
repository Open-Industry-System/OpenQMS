import React from "react";
import { Tabs, Card } from "antd";
import RuleConfigTable from "./components/RuleConfigTable";
import ChannelConfigTable from "./components/ChannelConfigTable";

const RiskConfigPage: React.FC = () => (
  <Card style={{ margin: 24 }}>
    <Tabs
      items={[
        { key: "rules", label: "规则配置", children: <RuleConfigTable /> },
        { key: "channels", label: "通知渠道", children: <ChannelConfigTable /> },
      ]}
    />
  </Card>
);

export default RiskConfigPage;
