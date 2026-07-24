import { Tag, Space } from "antd";
import type { ReactNode } from "react";

const AP_COLORS: Record<string, string> = { H: "red", M: "orange", L: "green" };

interface RiskTagsProps {
  ap?: string | null;
  severity?: number | null;
  occurrence?: number | null;
  detection?: number | null;
}

/**
 * AP / S / O / D provenance tags shared by D4/D5 recommendation panels.
 * Only renders tags for values that are present (non-null). Rule-engine
 * fallback recommendations leave S/O/D null and only carry AP=M.
 */
export default function RiskTags({ ap, severity, occurrence, detection }: RiskTagsProps): ReactNode {
  const tags: ReactNode[] = [];
  if (ap) tags.push(<Tag key="ap" color={AP_COLORS[ap] ?? "default"}>AP={ap}</Tag>);
  if (severity != null) tags.push(<Tag key="s">S={severity}</Tag>);
  if (occurrence != null) tags.push(<Tag key="o">O={occurrence}</Tag>);
  if (detection != null) tags.push(<Tag key="d">D={detection}</Tag>);
  if (tags.length === 0) return null;
  return <Space size={4} wrap>{tags}</Space>;
}