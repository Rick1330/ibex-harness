import { Badge, type BadgeVariant } from "@/components/mdx/badge";

type VersionBadgeProps = {
  version: string;
  type?: BadgeVariant;
};

const VERSION_LABELS: Partial<Record<BadgeVariant, string>> = {
  beta: "Beta",
  deprecated: "Deprecated",
  new: "New",
};

export function VersionBadge({ version, type = "default" }: VersionBadgeProps) {
  const suffix = VERSION_LABELS[type];

  return (
    <Badge variant={type === "default" ? "default" : type}>
      v{version}
      {suffix ? ` ${suffix}` : ""}
    </Badge>
  );
}
