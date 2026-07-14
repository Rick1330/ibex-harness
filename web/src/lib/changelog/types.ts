export type ReleaseType = "major" | "minor" | "patch";

export type ChangePriority = "highlight" | "standard" | "internal";

export type ChangeItem = Readonly<{
  scope: string | null;
  description: string;
  issueNumber: number | null;
  issueUrl: string | null;
  commitSha: string | null;
  commitUrl: string | null;
  priority: ChangePriority;
}>;

export type ReleaseSection = Readonly<{
  title: string;
  items: ChangeItem[];
  highlights: ChangeItem[];
}>;

export type ReleaseEntry = Readonly<{
  version: string;
  date: string | null;
  type: ReleaseType;
  summary: string | null;
  sections: ReleaseSection[];
}>;
