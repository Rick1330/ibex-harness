import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Gauge,
  Sparkles,
  Wrench,
} from "lucide-react";

export function sectionIcon(title: string): LucideIcon {
  const normalized = title.toLowerCase();
  if (normalized.includes("breaking")) return AlertTriangle;
  if (normalized.includes("performance")) return Gauge;
  if (normalized.includes("bug") || normalized.includes("fix")) return Wrench;
  return Sparkles;
}

export function sectionAccentClass(title: string): string {
  const normalized = title.toLowerCase();
  if (normalized.includes("breaking")) return "text-danger";
  if (normalized.includes("performance")) return "text-info";
  if (normalized.includes("bug") || normalized.includes("fix")) return "text-warning";
  return "text-success";
}
