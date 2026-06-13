import { appendFileSync } from "node:fs";
import { join } from "node:path";

const LOG_PATH = join(process.cwd(), "..", "..", "..", "debug-9aa172.log");
const ENDPOINT =
  "http://127.0.0.1:7702/ingest/4cd47e38-3a6f-4d7f-9681-abcd867b52ac";

export function debugLog(
  hypothesisId: string,
  location: string,
  message: string,
  data: Record<string, unknown> = {},
) {
  const mem = process.memoryUsage();
  const payload = {
    sessionId: "9aa172",
    hypothesisId,
    location,
    message,
    data: {
      ...data,
      heapUsedMB: Math.round(mem.heapUsed / 1024 / 1024),
      heapTotalMB: Math.round(mem.heapTotal / 1024 / 1024),
      rssMB: Math.round(mem.rss / 1024 / 1024),
      externalMB: Math.round(mem.external / 1024 / 1024),
    },
    timestamp: Date.now(),
    runId: process.env.DEBUG_RUN_ID ?? "pre-fix",
  };

  // #region agent log
  try {
    appendFileSync(LOG_PATH, `${JSON.stringify(payload)}\n`);
  } catch {
    /* ignore */
  }
  fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Debug-Session-Id": "9aa172",
    },
    body: JSON.stringify(payload),
  }).catch(() => {});
  // #endregion
}
