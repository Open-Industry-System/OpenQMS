import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

// Strict format parsing (dayjs(str, format, true)) requires this plugin.
// The repo does not enable it globally (only locale in main.tsx), so extend it here.
dayjs.extend(customParseFormat);

/** Range → readable string; null or either side null returns ''. */
export function rangeToTimeframe(range: [Dayjs | null, Dayjs | null] | null): string {
  if (!range || !range[0] || !range[1]) return '';
  return `${range[0].format('YYYY-MM-DD')} ~ ${range[1].format('YYYY-MM-DD')}`;
}

/** Readable string → range; unparseable or invalid dates (incl. legacy free-text) return null. */
export function timeframeToRange(timeframe: string): [Dayjs, Dayjs] | null {
  const m = timeframe.match(/^(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})$/);
  if (!m) return null;
  const start = dayjs(m[1], 'YYYY-MM-DD', true);
  const end = dayjs(m[2], 'YYYY-MM-DD', true);
  // Reject invalid dates and reversed ranges (start after end). The picker never
  // produces a reversed range, but legacy/hand-edited JSON can contain one.
  if (!start.isValid() || !end.isValid() || start.isAfter(end, 'day')) return null;
  return [start, end];
}
