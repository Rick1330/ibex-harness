"use client";

import { Download } from "lucide-react";

function needsCsvQuoting(value: string): boolean {
  return (
    value.includes(",") ||
    value.includes('"') ||
    value.includes("\n") ||
    value.includes("\r")
  );
}

function escapeCell(value: string | number): string {
  const text = String(value);
  if (!needsCsvQuoting(text)) {
    return text;
  }
  return `"${text.replaceAll('"', '""')}"`;
}

export function downloadCsv(
  filename: string,
  headers: readonly string[],
  rows: readonly (readonly (string | number)[])[],
): void {
  const headerLine = headers.map(escapeCell).join(",");
  const lines = rows.map((row) => row.map(escapeCell).join(","));
  const blob = new Blob([[headerLine, ...lines].join("\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

type ExportCsvButtonProps = Readonly<{
  filename: string;
  headers: readonly string[];
  rows: readonly (readonly (string | number)[])[];
  label?: string;
  disabled?: boolean;
}>;

export function SuiteExportCsvButton({
  filename,
  headers,
  rows,
  label = "Export CSV",
  disabled = false,
}: ExportCsvButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || rows.length === 0}
      onClick={() => {
        downloadCsv(filename, headers, rows);
      }}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 font-mono text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Download className="h-3.5 w-3.5" aria-hidden />
      {label}
    </button>
  );
}
