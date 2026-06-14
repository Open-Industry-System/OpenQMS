import React from "react";

interface DiffIndicatorProps {
  diff: number | null;
  reverse?: boolean; // If true, positive diff = good (green), negative = bad (red)
}

const DiffIndicator: React.FC<DiffIndicatorProps> = ({ diff, reverse = false }) => {
  if (diff === null || diff === undefined) return null;
  const isGood = reverse ? diff < 0 : diff > 0;
  const isBad = reverse ? diff > 0 : diff < 0;
  const color = isGood ? "#52c41a" : isBad ? "#f5222d" : "#999";
  const arrow = diff > 0 ? "↑" : diff < 0 ? "↓" : "→";

  return (
    <span style={{ fontSize: 11, marginLeft: 4, color }}>
      {arrow}{Math.abs(diff).toFixed(1)}
    </span>
  );
};

export default DiffIndicator;
