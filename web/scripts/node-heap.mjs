/**
 * Validate IBEX_NODE_HEAP_MB for Next main-process --max-old-space-size.
 * @param {string | undefined} raw
 * @param {string} [fallback="8192"]
 * @returns {string}
 */
export function resolveNodeHeapMb(raw, fallback = "8192") {
  const value = (raw ?? "").trim() || fallback;
  if (!/^\d+$/.test(value)) {
    throw new Error(
      `IBEX_NODE_HEAP_MB must be a positive integer (got "${raw ?? ""}")`,
    );
  }
  const n = Number(value);
  // 512 MiB floor / 32 GiB ceiling — keeps workers from OOM while rejecting typos.
  if (n < 512 || n > 32768) {
    throw new Error(
      `IBEX_NODE_HEAP_MB must be between 512 and 32768 (got ${n})`,
    );
  }
  return String(n);
}
