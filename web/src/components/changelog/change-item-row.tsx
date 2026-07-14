import Link from "next/link";

import { Badge } from "@/components/mdx/badge";
import type { ChangeItem } from "@/lib/changelog";

type ChangeItemRowProps = Readonly<{
  item: ChangeItem;
  showCommit?: boolean;
}>;

export function ChangeItemRow({ item, showCommit = false }: ChangeItemRowProps) {
  return (
    <li className="flex flex-col gap-1.5 text-sm leading-relaxed text-text-secondary sm:flex-row sm:flex-wrap sm:items-baseline sm:gap-x-2 sm:gap-y-1">
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-1">
        {item.scope ? <Badge variant="default">{item.scope}</Badge> : null}
        <span className="min-w-0 text-text-primary [overflow-wrap:anywhere]">
          {item.description}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3 ps-0 sm:ps-0">
        {item.issueNumber !== null && item.issueUrl ? (
          <Link
            href={item.issueUrl}
            className="font-mono text-xs text-text-tertiary hover:text-text-primary hover:underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            #{item.issueNumber}
          </Link>
        ) : null}
        {showCommit && item.commitSha && item.commitUrl ? (
          <Link
            href={item.commitUrl}
            className="font-mono text-xs text-text-tertiary hover:text-text-primary hover:underline"
            target="_blank"
            rel="noopener noreferrer"
            title="View commit"
          >
            {item.commitSha}
          </Link>
        ) : null}
      </div>
    </li>
  );
}
