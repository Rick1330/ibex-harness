import { afterEach, describe, expect, it, vi } from "vitest";

import {
  collectAncestorPids,
  getDocsAppRoot,
  isDocsAppNextProcess,
} from "./node-process-utils.mjs";

const originalPlatform = process.platform;

afterEach(() => {
  Object.defineProperty(process, "platform", { value: originalPlatform });
  vi.restoreAllMocks();
});

describe("node-process-utils", () => {
  it("resolves docs app root from the script location", () => {
    expect(getDocsAppRoot().replaceAll("\\", "/")).toMatch(/docs\/app$/);
  });

  it("matches docs app next commands by path marker", () => {
    const root = getDocsAppRoot();
    expect(
      isDocsAppNextProcess(`node ${root}/node_modules/next/dist/bin/next dev`),
    ).toBe(true);
    expect(isDocsAppNextProcess("node /tmp/other-app/node_modules/next dev")).toBe(
      false,
    );
  });

  it("walks ancestor pids on unix-like platforms", () => {
    Object.defineProperty(process, "platform", { value: "linux" });

    const ancestors = collectAncestorPids();
    expect(ancestors.has(process.pid)).toBe(true);
    expect(ancestors.has(process.ppid)).toBe(true);
  });
});
