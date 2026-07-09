export function formatMs(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${value.toFixed(2)} ms`;
}

/** Format sub-millisecond stage values without rounding to misleading 0.00 ms. */
export function formatLatencyMs(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  if (value === 0) {
    return "0 ms";
  }
  const abs = Math.abs(value);
  if (abs < 0.01) {
    const micros = value * 1000;
    if (Math.abs(micros) < 0.1) {
      return `${Math.round(value * 1_000_000)} ns`;
    }
    return `${micros.toFixed(2)} µs`;
  }
  return `${value.toFixed(2)} ms`;
}

export function formatNsPerOp(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return "—";
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)} ms/op`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} µs/op`;
  }
  return `${value.toFixed(1)} ns/op`;
}

export function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`;
}

export function formatReqPerSec(value: number): string {
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 0 })} req/s`;
}

export function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value.toFixed(0)} B/op`;
  }
  return `${(value / 1024).toFixed(1)} KB/op`;
}

export function formatDeltaPct(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

const TIMESTAMP_LOCALE = "en-US";
const TIMESTAMP_OPTIONS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  second: "numeric",
  hour12: false,
};

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(TIMESTAMP_LOCALE, TIMESTAMP_OPTIONS);
}
