import { cn } from "@/lib/cn";

type DiagramProps = Readonly<{
  src: string;
  alt: string;
  caption?: string;
  className?: string;
}>;

export function Diagram({ src, alt, caption, className }: DiagramProps) {
  return (
    <figure className={cn("docs-diagram my-8", className)}>
      <div className="overflow-hidden rounded-[4px] border border-border bg-panel p-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          alt={alt}
          className="h-auto w-full"
          loading="lazy"
          src={src}
        />
      </div>
      {caption ? (
        <figcaption className="mt-3 text-center text-sm text-text-secondary">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
