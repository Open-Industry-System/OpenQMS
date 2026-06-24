// frontend/src/utils/pfmeaRules.test.ts
import { describe, it, expect } from 'vitest';
import { usePfmeaRules } from './pfmeaRules';

describe('usePfmeaRules', () => {
  const rules = usePfmeaRules();

  it('generateFailureModes returns process-verb-based modes', () => {
    const modes = rules.generateFailureModes('贴装电子元器件');
    expect(modes.length).toBeGreaterThan(0);
    expect(modes.some((m) => m.includes('偏移') || m.includes('漏件'))).toBe(true);
  });

  it('suggestFailureChain returns effects+causes for a known PFMEA mode', () => {
    const chain = rules.suggestFailureChain('贴装偏移');
    expect(chain.effects.length).toBeGreaterThan(0);
    expect(chain.causes.length).toBeGreaterThan(0);
  });

  it('suggest4MCauses returns Man/Machine/Material/Environment buckets', () => {
    const buckets = rules.suggest4MCauses();
    expect(buckets.Man.length).toBeGreaterThan(0);
    expect(buckets.Machine.length).toBeGreaterThan(0);
    expect(buckets.Material.length).toBeGreaterThan(0);
    expect(buckets.Environment.length).toBeGreaterThan(0);
  });
});
