// Vitest jsdom on Node 25 can leave globalThis.localStorage undefined;
// provide a minimal in-memory store so authStore and tests can use it.
if (!globalThis.localStorage) {
  const data = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => data.set(key, String(value)),
      removeItem: (key: string) => data.delete(key),
      clear: () => data.clear(),
      key: (index: number) => Array.from(data.keys())[index] ?? null,
      get length() { return data.size; },
    },
    writable: true,
  });
}

import "@testing-library/jest-dom/vitest";
import i18n from "./i18n";

// Run tests in English so component tests don't depend on Chinese UI strings.
i18n.changeLanguage("en-US");

// Ant Design requires matchMedia in jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
