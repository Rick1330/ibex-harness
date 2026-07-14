import { ChangelogLine } from "./changelog-line";
import { classifyChangePriority } from "./highlight-ranking";
import type { ChangeItem } from "./types";

type IssueRef = Readonly<{ number: number; url: string }>;
type CommitRef = Readonly<{ sha: string; url: string }>;

function shouldIgnoreItem(body: ChangelogLine): boolean {
  const normalized = body.text.toLowerCase();
  return (
    normalized === "_tbd_" ||
    normalized === "(example)" ||
    normalized.startsWith("(example) ")
  );
}

function parseIssueLink(body: ChangelogLine): IssueRef | null {
  let remaining = body;
  while (!remaining.isEmpty()) {
    const link = remaining.takeWrappedMarkdownLink();
    if (!link) return null;
    const number = new ChangelogLine(link.label).issueNumberFromHashLabel();
    if (number !== null) return { number, url: link.url };
    remaining = new ChangelogLine(link.after);
  }
  return null;
}

function parseCommitLink(body: ChangelogLine): CommitRef | null {
  let found: CommitRef | null = null;
  let remaining = body;
  let link = remaining.takeWrappedMarkdownLink();
  while (link) {
    if (new ChangelogLine(link.label).isHexCommitLabel()) {
      found = { sha: link.label, url: link.url };
    }
    remaining = new ChangelogLine(link.after);
    link = remaining.takeWrappedMarkdownLink();
  }
  return found;
}

function parseScope(body: ChangelogLine): {
  scope: string | null;
  rest: ChangelogLine;
} {
  if (!body.startsWith("**")) {
    return { scope: null, rest: body };
  }
  const close = body.text.indexOf(":**", 2);
  if (close === -1) return { scope: null, rest: body };
  const scope = body.text.slice(2, close).trim();
  return {
    scope: scope || null,
    rest: new ChangelogLine(body.text.slice(close + 3).trim()),
  };
}

function buildChangeItem(body: ChangelogLine): ChangeItem | null {
  if (body.isEmpty() || shouldIgnoreItem(body)) return null;

  const issue = parseIssueLink(body);
  const commit = parseCommitLink(body);
  const scoped = parseScope(body);
  const description = scoped.rest.stripMarkdownLinks().stripMilestoneMarkers().text;
  if (!description) return null;

  return {
    scope: scoped.scope,
    description,
    issueNumber: issue?.number ?? null,
    issueUrl: issue?.url ?? null,
    commitSha: commit?.sha ?? null,
    commitUrl: commit?.url ?? null,
    priority: classifyChangePriority(scoped.scope),
  };
}

export function parseChangeItem(line: string): ChangeItem | null {
  const body = new ChangelogLine(line).trimmed().bulletBody();
  if (!body) return null;
  return buildChangeItem(body);
}
