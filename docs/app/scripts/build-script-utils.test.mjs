import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { isEnoent, loadEnvFile } from "./build-script-utils.mjs";

const originalEnv = { ...process.env };

afterEach(() => {
  for (const key of Object.keys(process.env)) {
    if (!(key in originalEnv)) {
      delete process.env[key];
    }
  }
  Object.assign(process.env, originalEnv);
});

describe("build-script-utils", () => {
  it("detects ENOENT fs errors", () => {
    expect(isEnoent({ code: "ENOENT" })).toBe(true);
    expect(isEnoent({ code: "EEXIST" })).toBe(false);
    expect(isEnoent(null)).toBe(false);
  });

  it("loads quoted and CRLF env values", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "ibex-env-"));
    const envPath = path.join(dir, ".env");
    writeFileSync(
      envPath,
      'FOO=bar\r\nQUOTED="value"\r\nSINGLE=\'one\'\r\n',
      "utf8",
    );

    loadEnvFile(envPath);

    expect(process.env.FOO).toBe("bar");
    expect(process.env.QUOTED).toBe("value");
    expect(process.env.SINGLE).toBe("one");
  });
});
