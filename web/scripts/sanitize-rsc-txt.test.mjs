import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { sanitizeRscTxtFiles } from "../scripts/sanitize-rsc-txt.mjs";

describe("sanitizeRscTxtFiles", () => {
  let tmpDir = "";

  afterEach(async () => {
    if (tmpDir) {
      await import("node:fs/promises").then(({ rm }) =>
        rm(tmpDir, { recursive: true, force: true }),
      );
      tmpDir = "";
    }
  });

  it("truncates route RSC txt files but preserves llms.txt and ai.txt", async () => {
    tmpDir = await mkdtemp(path.join(os.tmpdir(), "rsc-txt-"));
    await writeFile(path.join(tmpDir, "llms.txt"), "llm context", "utf8");
    await writeFile(path.join(tmpDir, "ai.txt"), "ai policy", "utf8");
    await mkdir(path.join(tmpDir, "benchmarks"), { recursive: true });
    await writeFile(
      path.join(tmpDir, "benchmarks", "latency.txt"),
      '1:"$Sreact.fragment"',
      "utf8",
    );

    const { sanitized } = await sanitizeRscTxtFiles(tmpDir);
    expect(sanitized).toBe(1);

    const latency = await readFile(path.join(tmpDir, "benchmarks", "latency.txt"));
    expect(latency.byteLength).toBe(0);

    const llms = await readFile(path.join(tmpDir, "llms.txt"), "utf8");
    expect(llms).toBe("llm context");

    const ai = await readFile(path.join(tmpDir, "ai.txt"), "utf8");
    expect(ai).toBe("ai policy");
  });
});
