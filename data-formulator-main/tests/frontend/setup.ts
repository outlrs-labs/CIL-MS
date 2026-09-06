import '@testing-library/jest-dom/vitest';

// Node can expose an incomplete `localStorage` global when Vitest is launched
// without `--localstorage-file`.  jsdom normally supplies this API, but the
// Node global takes precedence in some releases and makes otherwise unrelated
// UI suites fail during module initialization.  Install a small standards-like
// in-memory store so the tests exercise the same persistence contract as the
// browser.
const values = new Map<string, string>();
const testStorage: Storage = {
  get length() {
    return values.size;
  },
  clear() {
    values.clear();
  },
  getItem(key: string) {
    return values.has(String(key)) ? values.get(String(key))! : null;
  },
  key(index: number) {
    return [...values.keys()][index] ?? null;
  },
  removeItem(key: string) {
    values.delete(String(key));
  },
  setItem(key: string, value: string) {
    values.set(String(key), String(value));
  },
};

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: testStorage,
});
Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: testStorage,
});
