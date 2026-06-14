import {
  Activity,
  AlertCircle,
  AlertTriangle,
  BookMarked,
  BookOpen,
  Boxes,
  CheckCircle2,
  Circle,
  CircleHelp,
  Container,
  Database,
  FileCode,
  FileText,
  Flag,
  Gauge,
  GitBranch,
  History,
  Key,
  Layers,
  LayoutDashboard,
  Lightbulb,
  Lock,
  Map,
  Plug,
  Rocket,
  Scale,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Target,
  Terminal,
  Users,
  Waypoints,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { createElement, type ReactElement } from "react";

import { cn } from "@/lib/cn";

/** Lucide export name → component */
const LUCIDE_BY_NAME: Record<string, LucideIcon> = {
  Activity,
  AlertCircle,
  AlertTriangle,
  BookMarked,
  BookOpen,
  Boxes,
  CheckCircle2,
  Circle,
  CircleHelp,
  Container,
  Database,
  FileCode,
  FileText,
  Flag,
  Gauge,
  GitBranch,
  History,
  Key,
  Layers,
  LayoutDashboard,
  Lightbulb,
  Lock,
  Map,
  Plug,
  Rocket,
  Scale,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Target,
  Terminal,
  Users,
  Waypoints,
  Zap,
};

/** Docs section folders in meta.json */
const SECTION_ICONS: Record<string, LucideIcon> = {
  "getting-started": Rocket,
  architecture: Boxes,
  proxy: Waypoints,
  auth: Shield,
  security: ShieldCheck,
  deployment: Container,
  operations: Activity,
  "api-reference": Terminal,
  adr: ScrollText,
  changelog: History,
  glossary: BookMarked,
};

/** Full doc paths (without /docs/) */
const PAGE_ICONS: Record<string, LucideIcon> = {
  "getting-started/introduction": BookOpen,
  "getting-started/quickstart": Zap,
  "getting-started/concepts": Lightbulb,
  "getting-started/faq": CircleHelp,
  "architecture/overview": LayoutDashboard,
  "architecture/services": Boxes,
  "architecture/data-model": Database,
  "architecture/request-lifecycle": GitBranch,
  "proxy/overview": LayoutDashboard,
  "proxy/configuration": Settings,
  "proxy/authentication": Lock,
  "proxy/rate-limiting": Gauge,
  "proxy/request-routing": GitBranch,
  "proxy/provider-adapters": Plug,
  "auth/overview": Shield,
  "auth/issuing-api-keys": Key,
  "auth/org-project-model": Users,
  "auth/multi-tenant-rls": Database,
  "security/overview": ShieldCheck,
  "security/authentication": Lock,
  "security/tenant-isolation": Database,
  "security/secrets-and-keys": Key,
  "deployment/docker-compose": Container,
  "deployment/kubernetes": Boxes,
  "deployment/environment-variables": FileCode,
  "operations/observability": Activity,
  "operations/troubleshooting": CircleHelp,
  "operations/health-checks": Gauge,
  "operations/incident-response": AlertCircle,
  "api-reference/auth-grpc": Terminal,
  "api-reference/proxy-health": Activity,
  "api-reference/chat-completions": Plug,
  "api-reference/errors": AlertCircle,
  "adr/index": ScrollText,
  glossary: BookMarked,
  changelog: ScrollText,
};

/** Leaf slug fallbacks when path is ambiguous */
const SLUG_ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  configuration: Settings,
  authentication: Lock,
  introduction: BookOpen,
  quickstart: Zap,
  concepts: Lightbulb,
  faq: CircleHelp,
  services: Boxes,
  "data-model": Database,
  "request-lifecycle": GitBranch,
  "tenant-isolation": Database,
  "secrets-and-keys": Key,
  observability: Activity,
  troubleshooting: CircleHelp,
  "health-checks": Gauge,
  "incident-response": AlertCircle,
  "auth-grpc": Terminal,
  "proxy-health": Activity,
  "chat-completions": Plug,
  errors: AlertCircle,
  goals: Target,
  decisions: Scale,
  risks: AlertTriangle,
  milestones: Flag,
  "current-state": Activity,
  findings: AlertCircle,
  "content-sources": FileText,
  "master-brief": ScrollText,
};

/** Roadmap top-level phase folders */
const ROADMAP_PHASE_ICONS: Record<string, LucideIcon> = {
  "phase-0-foundation": Map,
  "phase-1-core-platform": Layers,
  "phase-1-5-docs-site": BookOpen,
  "phase-2-single-provider": Plug,
  "phase-3-memory-engine": Lightbulb,
  "phase-4-multi-provider": Waypoints,
  "phase-5-production-hardening": ShieldCheck,
  reference: BookMarked,
};

/** Roadmap nested section folders */
const ROADMAP_SECTION_ICONS: Record<string, LucideIcon> = {
  milestones: Flag,
  reference: BookOpen,
  goals: Target,
  decisions: Scale,
  risks: AlertTriangle,
};

/** Full roadmap paths (without /roadmap/) */
const ROADMAP_PAGE_ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  "current-state": Activity,
  findings: AlertCircle,
  "reference/index": BookMarked,
  "phase-0-foundation/index": Map,
  "phase-1-core-platform/index": Layers,
  "phase-1-5-docs-site/index": BookOpen,
  "phase-2-single-provider/index": Plug,
  "phase-3-memory-engine/index": Lightbulb,
  "phase-4-multi-provider/index": Waypoints,
  "phase-5-production-hardening/index": ShieldCheck,
  "phase-1-5-docs-site/goals": Target,
  "phase-1-5-docs-site/decisions": Scale,
  "phase-1-5-docs-site/risks": AlertTriangle,
  "phase-1-5-docs-site/content-sources": FileText,
  "phase-1-5-docs-site/master-brief": ScrollText,
  "phase-1-5-docs-site/phase-1-5-docs-site-milestones": Flag,
};

export type ContentBaseUrl = "/docs" | "/roadmap";

export function contentPathFromUrl(
  url: string,
  baseUrl: ContentBaseUrl = "/docs",
): string {
  const prefix = baseUrl === "/docs" ? /^\/docs\/?/ : /^\/roadmap\/?/;
  return url.replace(prefix, "").replace(/\/$/, "");
}

/** @deprecated Use contentPathFromUrl(url, "/docs") */
export function docPathFromUrl(url: string): string {
  return contentPathFromUrl(url, "/docs");
}

function iconFromLucideName(name: string): LucideIcon | undefined {
  const trimmed = name.trim();
  if (!trimmed) return undefined;

  if (trimmed in LUCIDE_BY_NAME) {
    return LUCIDE_BY_NAME[trimmed];
  }

  const pascal = trimmed
    .split(/[-_\s]+/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");

  return LUCIDE_BY_NAME[pascal];
}

function resolveRoadmapMilestoneIcon(path: string): LucideIcon | undefined {
  if (!path.includes("/milestones/")) return undefined;

  const slug = path.split("/").pop() ?? "";
  if (slug.startsWith("d") || /^\d/.test(slug)) {
    return Circle;
  }

  return FileText;
}

export function resolveRoadmapNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;

  if (!url) return FileText;

  const path = contentPathFromUrl(url, "/roadmap");
  if (ROADMAP_PAGE_ICONS[path]) return ROADMAP_PAGE_ICONS[path];

  const segments = path.split("/");
  const topLevel = segments[0];
  if (topLevel && ROADMAP_PHASE_ICONS[topLevel] && segments.length === 1) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  const section = segments.find((s) => ROADMAP_SECTION_ICONS[s]);
  if (section) return ROADMAP_SECTION_ICONS[section];

  const milestoneIcon = resolveRoadmapMilestoneIcon(path);
  if (milestoneIcon) return milestoneIcon;

  const leaf = segments.pop() ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (topLevel && ROADMAP_PHASE_ICONS[topLevel]) {
    return ROADMAP_PHASE_ICONS[topLevel];
  }

  return FileText;
}

export function resolveNavIcon(
  iconName?: string,
  url?: string,
): LucideIcon | undefined {
  if (url?.startsWith("/roadmap")) {
    return resolveRoadmapNavIcon(iconName, url);
  }

  const named = iconName ? iconFromLucideName(iconName) : undefined;
  if (named) return named;

  if (!url) return FileCode;

  const path = contentPathFromUrl(url, "/docs");
  if (PAGE_ICONS[path]) return PAGE_ICONS[path];

  const section = path.split("/")[0];
  if (section && SECTION_ICONS[section] && !path.includes("/")) {
    return SECTION_ICONS[section];
  }

  const leaf = path.split("/").pop() ?? path;
  if (SLUG_ICONS[leaf]) return SLUG_ICONS[leaf];
  if (SECTION_ICONS[section]) return SECTION_ICONS[section];

  return FileCode;
}

type SidebarIconProps = {
  icon: LucideIcon;
  className?: string;
};

export function SidebarIcon({ icon: Icon, className }: SidebarIconProps) {
  return (
    <Icon
      aria-hidden
      className={cn("size-4 shrink-0 text-text-primary", className)}
      strokeWidth={2}
    />
  );
}

export function navIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveNavIcon(iconName, url);
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function roadmapNavIconElement(
  iconName?: string,
  url?: string,
): ReactElement | undefined {
  const Icon = resolveRoadmapNavIcon(iconName, url);
  if (!Icon) return undefined;
  return createElement(SidebarIcon, { icon: Icon });
}

export function getNavIconForUrl(url: string): LucideIcon {
  return resolveNavIcon(undefined, url) ?? FileCode;
}

export function getRoadmapIconForUrl(url: string): LucideIcon {
  return resolveRoadmapNavIcon(undefined, url) ?? FileText;
}

export function getSectionIconForSlug(
  sectionSlug: string,
  baseUrl: ContentBaseUrl = "/docs",
): LucideIcon {
  if (baseUrl === "/roadmap") {
    return (
      ROADMAP_PHASE_ICONS[sectionSlug] ??
      ROADMAP_SECTION_ICONS[sectionSlug] ??
      FileText
    );
  }

  return resolveNavIcon(undefined, `/docs/${sectionSlug}`) ?? FileCode;
}

export function baseUrlFromPathname(pathname: string): ContentBaseUrl {
  return pathname.startsWith("/roadmap") ? "/roadmap" : "/docs";
}

export function folderSectionSlugFromUrl(url: string): string {
  const baseUrl = url.startsWith("/roadmap") ? "/roadmap" : "/docs";
  return contentPathFromUrl(url, baseUrl).split("/")[0] || "section";
}
