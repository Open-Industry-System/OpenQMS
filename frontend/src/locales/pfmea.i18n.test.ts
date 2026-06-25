import { describe, it, expect } from 'vitest';
import zh from './zh-CN/pfmea.json';
import en from './en-US/pfmea.json';

describe('pfmea i18n parity', () => {
  const zhSteps = (zh as any).wizard.steps;
  const enSteps = (en as any).wizard.steps;
  it('has 7 steps in both languages', () => {
    expect(zhSteps.length).toBe(7);
    expect(enSteps.length).toBe(7);
  });
  it('has guidance for all 7 steps in both', () => {
    for (const lang of [zh, en]) {
      for (let i = 0; i < 7; i++) {
        expect((lang as any).wizard.guidance[`step${i}`].title).toBeTruthy();
      }
    }
  });
});
