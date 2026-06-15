import { Badge, type BadgeVariant } from "@/components/mdx/badge";

type VersionBadgeProps = Readonly<{
  version: string;
  type?: BadgeVariant;
}>;

function versionSuffix(type: BadgeVariant): string | undefined {
  switch (type) {
    case "beta":
      return "Beta";
    case "deprecated":
      return "Deprecated";
    case "new":
      return "New";
    case "default":
      return undefined;
  }
}

export function VersionBadge({ version, type = "default" }: VersionBadgeProps) {
  const suffix = versionSuffix(type);

  return (
    <Badge variant={type === "default" ? "default" : type}>
      v{version}
      {suffix ? ` ${suffix}` : ""}
    </Badge>
  );
}
