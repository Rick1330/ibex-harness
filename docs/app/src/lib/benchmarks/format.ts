export function formatMs(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${value.toFixed(2)} ms`;
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
