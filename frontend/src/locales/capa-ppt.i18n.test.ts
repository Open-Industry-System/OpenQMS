import { describe, expect, it } from 'vitest';
import zh from './zh-CN/capa.json';
import en from './en-US/capa.json';

const locales = [
  ['zh-CN', zh],
  ['en-US', en],
] as const;
const singleBracePlaceholder = /(?<!\{)\{rounds\}(?!\})/;

describe('capa PPT review-round i18n', () => {
  for (const [language, locale] of locales) {
    it(`${language} uses i18next interpolation for PPT review rounds`, () => {
      for (const key of ['generated', 'needsReview'] as const) {
        const value = locale.ppt[key];

        expect(value).toContain('{{rounds}}');
        expect(value).not.toMatch(singleBracePlaceholder);
      }
    });
  }
});


describe('capa outcome review locale contract', () => {
  const keys = (value: Record<string, unknown>, prefix = ''): string[] => Object.entries(value).flatMap(([key, child]) =>
    typeof child === 'object' && child !== null ? keys(child as Record<string, unknown>, `${prefix}${key}.`) : [`${prefix}${key}`]);
  it('has matching nonempty Chinese and English review labels', () => {
    expect(keys(en.outcome).sort()).toEqual(keys(zh.outcome).sort());
    for (const locale of [zh, en]) {
      for (const value of Object.values(locale.outcome.binding)) expect(value.trim()).not.toBe('');
      expect(locale.outcome.conclusion.pending).not.toBe(locale.outcome.conclusion.passed);
      expect(locale.outcome.actionStatus.pending).not.toBe(locale.outcome.actionStatus.verified);
    }
  });
});
