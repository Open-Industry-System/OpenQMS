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
