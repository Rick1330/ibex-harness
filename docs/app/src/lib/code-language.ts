import {
  Braces,
  FileCode,
  FileJson,
  FileText,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import { Children, isValidElement, type ReactNode } from "react";

export const LANG_DISPLAY: Record<string, string> = {
  ts: "TypeScript",
  typescript: "TypeScript",
  js: "JavaScript",
  javascript: "JavaScript",
  jsx: "JSX",
  tsx: "TSX",
  bash: "bash",
  sh: "shell",
  shell: "shell",
  shellscript: "shell",
  zsh: "zsh",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  go: "Go",
  python: "Python",
  py: "Python",
  rust: "Rust",
  rs: "Rust",
  sql: "SQL",
  css: "CSS",
  html: "HTML",
  mdx: "MDX",
  md: "Markdown",
  env: ".env",
  toml: "TOML",
  dockerfile: "Dockerfile",
  graphql: "GraphQL",
  proto: "Protobuf",
  prisma: "Prisma",
  terraform: "Terraform",
  curl: "cURL",
};

export type CodeLanguageMeta = {
  id: string;
  label: string;
  icon: LucideIcon;
};

const LANGUAGE_ICONS: Record<string, LucideIcon> = {
  bash: Terminal,
  sh: Terminal,
  shell: Terminal,
  shellscript: Terminal,
  zsh: Terminal,
  dockerfile: Terminal,
  curl: Terminal,
  json: FileJson,
  yaml: FileText,
  yml: FileText,
  mdx: FileText,
  md: FileText,
};

export function parseCodeLanguage(className?: string): string | undefined {
  if (!className) return undefined;
  const match = className.match(/(?:^|\s)language-([\w+#.-]+)/);
  return match?.[1];
}

export function languageFromChildren(children: ReactNode): string | undefined {
  let found: string | undefined;

  Children.forEach(children, (child) => {
    if (found) return;
    if (!isValidElement(child)) return;

    const props = child.props as {
      className?: string;
      children?: ReactNode;
      "data-language"?: string;
    };

    if (props["data-language"]) {
      found = props["data-language"];
      return;
    }

    const fromClass = parseCodeLanguage(props.className);
    if (fromClass) {
      found = fromClass;
      return;
    }

    const nested = languageFromChildren(props.children);
    if (nested) found = nested;
  });

  return found;
}

export function getLanguageDisplayLabel(
  lang?: string,
  title?: string,
): string | undefined {
  if (title?.trim()) return title.trim();
  if (!lang || lang === "plaintext" || lang === "text") return undefined;

  const key = lang.toLowerCase();
  return LANG_DISPLAY[key] ?? key;
}

export function resolveCodeLanguage(
  lang?: string,
  title?: string,
): CodeLanguageMeta | undefined {
  const label = getLanguageDisplayLabel(lang, title);
  if (!label) return undefined;

  const id = (lang ?? title ?? "code").toLowerCase();
  const icon =
    LANGUAGE_ICONS[id] ??
    (["bash", "sh", "shell", "zsh", "shellscript"].includes(id)
      ? Terminal
      : FileCode);

  return { id, label, icon };
}
