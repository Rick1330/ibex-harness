import Link from "next/link";

type RoadmapReferenceCardProps = Readonly<{
  href: string;
  title: string;
  description: string;
}>;

export function RoadmapReferenceCard({
  href,
  title,
  description,
}: RoadmapReferenceCardProps) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-xl border border-border bg-card p-4 transition-colors hover:bg-muted/20"
    >
      <h3 className="mb-1 text-sm font-semibold text-foreground group-hover:underline">
        {title}
      </h3>
      <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
    </Link>
  );
}
