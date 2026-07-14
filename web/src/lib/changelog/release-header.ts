import { ChangelogLine } from "./changelog-line";
import type { ChangeItem, ReleaseType } from "./types";

export type MutableReleaseHeader = {
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: { title: string; items: ChangeItem[] }[];
};

function readSemverTriple(
  version: string,
): readonly [major: number, minor: number, patch: number] | null {
  const parts = version.split(".");
  if (parts.length !== 3) return null;
  const majorStr = parts.at(0) ?? "";
  const minorStr = parts.at(1) ?? "";
  const patchStr = parts.at(2) ?? "";
  if (!new ChangelogLine(majorStr).isDecimalDigits()) return null;
  if (!new ChangelogLine(minorStr).isDecimalDigits()) return null;
  if (!new ChangelogLine(patchStr).isDecimalDigits()) return null;
  return [Number(majorStr), Number(minorStr), Number(patchStr)];
}

export function parseReleaseType(version: string): ReleaseType {
  const triple = readSemverTriple(version);
  if (!triple) return "patch";
  const [major, minor, patch] = triple;
  if (patch > 0) return "patch";
  if (minor > 0) return "minor";
  if (major > 0) return "major";
  return "patch";
}

function extractSemver(line: ChangelogLine): string | null {
  const start = line.findFirstDigitIndex();
  if (start === -1) return null;
  let end = start;
  while (end < line.text.length) {
    const ch = line.text.charAt(end);
    if (!new ChangelogLine(ch).isDecimalDigits() && ch !== ".") break;
    end += 1;
  }
  const candidate = line.text.slice(start, end);
  const parts = candidate.split(".");
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && new ChangelogLine(part).isDecimalDigits())) {
    return null;
  }
  return candidate;
}

function normalizeDate(raw: string | null): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed || trimmed === "YYYY-MM-DD") return null;
  return trimmed;
}

function extractReleaseDate(line: ChangelogLine): string | null {
  const open = line.text.lastIndexOf("(");
  const close = line.text.lastIndexOf(")");
  if (open !== -1 && close > open) {
    return normalizeDate(line.text.slice(open + 1, close));
  }
  const emDash = line.text.indexOf("— ");
  const dash = emDash === -1 ? line.text.indexOf("- ") : emDash;
  if (dash === -1) return null;
  return normalizeDate(line.text.slice(dash + 1).trim());
}

export function releaseHeaderFromLine(line: ChangelogLine): MutableReleaseHeader | null {
  if (!line.startsWith("## ") || line.includes("[Unreleased]")) return null;
  const version = extractSemver(line);
  if (!version) return null;
  return {
    version,
    date: extractReleaseDate(line),
    type: parseReleaseType(version),
    summary: null,
    sections: [],
  };
}
