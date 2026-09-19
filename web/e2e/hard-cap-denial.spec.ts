import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * TESTING_STRATEGY journey #8: Cost alert → hard-cap denial on proxy path.
 * Spawns a fixture that mounts the real Go BudgetMiddleware with an exhausted
 * hard-cap loader, then asserts HTTP 402 + BUDGET_EXCEEDED.
 *
 * Playwright cwd is web/; repo root is one level up.
 */
const repoRoot = path.resolve(process.cwd(), "..");

async function startHardCapFixture(): Promise<{
  baseURL: string;
  child: ChildProcess;
}> {
  const child = spawn(
    "go",
    ["run", "./services/proxy/cmd/hardcap-deny-fixture"],
    { cwd: repoRoot, stdio: ["ignore", "pipe", "pipe"] },
  );
  const addr = await new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error("fixture startup timeout"));
    }, 60_000);
    let buf = "";
    const onData = (chunk: Buffer) => {
      buf += chunk.toString("utf8");
      const line = buf.split("\n").find((l) => l.includes("127.0.0.1:"));
      if (line) {
        clearTimeout(timer);
        child.stdout?.off("data", onData);
        resolve(line.trim());
      }
    };
    child.stdout?.on("data", onData);
    child.stderr?.on("data", (chunk: Buffer) => {
      process.stderr.write(chunk);
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`fixture exited early code=${code}`));
    });
  });
  return { baseURL: `http://${addr}`, child };
}

test.describe("journey 8: hard-cap denial", () => {
  test("exhausted hard-cap returns 402 BUDGET_EXCEEDED via BudgetMiddleware", async ({
    request,
  }) => {
    const { baseURL, child } = await startHardCapFixture();
    try {
      const res = await request.post(`${baseURL}/v1/chat/completions`, {
        data: { model: "gpt-4o", messages: [{ role: "user", content: "hi" }] },
        headers: { "content-type": "application/json" },
      });
      expect(res.status()).toBe(402);
      const body = await res.json();
      expect(body.error.code).toBe("BUDGET_EXCEEDED");
      expect(String(body.error.message)).toMatch(/budget/i);
    } finally {
      child.kill("SIGTERM");
    }
  });
});
