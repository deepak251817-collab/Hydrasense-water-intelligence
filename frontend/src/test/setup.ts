import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// React 19 + testing-library: auto-unmount between tests.
afterEach(() => {
  cleanup();
});

// sessionStorage is used by lib/auth; jsdom provides it, but tests may want isolation.
afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});
