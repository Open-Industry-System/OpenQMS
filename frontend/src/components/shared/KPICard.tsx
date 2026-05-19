import { Card, Statistic } from "antd";

interface KPICardProps {
  title: string;
  value: number;
  suffix?: string;
  color?: string;
}

export default function KPICard({ title, value, suffix, color }: KPICardProps) {
  return (
    <Card>
      <Statistic
        title={title}
        value={value}
        suffix={suffix}
        valueStyle={{ color: color || "#1677FF", fontSize: 28 }}
      />
    </Card>
  );
}
