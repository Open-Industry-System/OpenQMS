import { describe, it, expect } from 'vitest';
import dayjs from 'dayjs';
import { rangeToTimeframe, timeframeToRange } from './wizardTimeframe';

const d = (s: string) => dayjs(s);

describe('rangeToTimeframe', () => {
  it('formats a full range as "YYYY-MM-DD ~ YYYY-MM-DD"', () => {
    expect(rangeToTimeframe([d('2026-01-01'), d('2026-09-30')])).toBe('2026-01-01 ~ 2026-09-30');
  });
  it('returns empty string for null', () => {
    expect(rangeToTimeframe(null)).toBe('');
  });
  it('returns empty string when one side is null (half-selected)', () => {
    expect(rangeToTimeframe([d('2026-01-01'), null])).toBe('');
  });
});

describe('timeframeToRange', () => {
  it('round-trips a formatted range back to the same days', () => {
    const range = timeframeToRange('2026-01-01 ~ 2026-09-30')!;
    expect(range[0].isSame(d('2026-01-01'), 'day')).toBe(true);
    expect(range[1].isSame(d('2026-09-30'), 'day')).toBe(true);
  });
  it('returns null for empty string', () => {
    expect(timeframeToRange('')).toBeNull();
  });
  it('returns null for legacy free-text', () => {
    expect(timeframeToRange('2026年Q1-Q3')).toBeNull();
  });
  it('returns null for invalid calendar date (Feb 31)', () => {
    expect(timeframeToRange('2026-02-31 ~ 2026-09-30')).toBeNull();
  });
  it('returns null for invalid month (13)', () => {
    expect(timeframeToRange('2026-13-01 ~ 2026-09-30')).toBeNull();
  });
  it('returns null for reversed range (start after end)', () => {
    expect(timeframeToRange('2026-09-30 ~ 2026-01-01')).toBeNull();
  });
});
