import React from "react";
import { Slider } from "antd";

interface TimelineSliderProps {
  periods: string[];
  currentPeriod: string;
  onChange: (period: string) => void;
}

const TimelineSlider: React.FC<TimelineSliderProps> = ({
  periods,
  currentPeriod,
  onChange,
}) => {
  if (periods.length === 0) return null;

  const currentIndex = periods.indexOf(currentPeriod);
  const marks: Record<number, string> = {};
  periods.forEach((p, i) => {
    marks[i] = p;
  });

  return (
    <div style={{ margin: "16px 0" }}>
      <Slider
        min={0}
        max={periods.length - 1}
        value={currentIndex >= 0 ? currentIndex : periods.length - 1}
        marks={marks}
        onChange={(val) => onChange(periods[val])}
        tooltip={{ formatter: (val) => periods[val ?? 0] }}
      />
    </div>
  );
};

export default TimelineSlider;