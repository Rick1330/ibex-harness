import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cn } from "@/lib/cn";

type HeadingTag = "h2" | "h3" | "h4";

type BlogHeadingProps = Readonly<
  ComponentPropsWithoutRef<"h2"> & {
    as: HeadingTag;
    children?: ReactNode;
  }
>;

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (Array.isArray(children)) {
    return children.map(textFromChildren).join("");
  }
  return "";
}

function slugifyHeading(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

function BlogHeading({
  as: Tag,
  className,
  children,
  id,
  ...props
}: BlogHeadingProps) {
  const fromChildren = textFromChildren(children);
  const resolvedId =
    id ?? (fromChildren ? slugifyHeading(fromChildren) : undefined);

  return (
    <Tag
      id={resolvedId}
      className={cn(`blog-heading blog-heading-${Tag}`, className)}
      {...props}
    >
      {children}
    </Tag>
  );
}

function BlogTable(props: ComponentPropsWithoutRef<"table">) {
  return (
    <section className="blog-table-wrap" aria-label="Data table">
      <table className="blog-table" {...props} />
    </section>
  );
}

function BlogBlockquote(props: ComponentPropsWithoutRef<"blockquote">) {
  return <blockquote className="blog-blockquote" {...props} />;
}

function BlogParagraph(props: ComponentPropsWithoutRef<"p">) {
  return <p className="blog-p" {...props} />;
}

function BlogAnchor(props: ComponentPropsWithoutRef<"a">) {
  return <a className="blog-a" {...props} />;
}

/** Editorial MDX overrides for blog posts (DESIGN_GUIDE §13.3 / §14.2). */
export function getBlogMdxOverrides() {
  return {
    h2: (props: ComponentPropsWithoutRef<"h2">) => (
      <BlogHeading as="h2" {...props} />
    ),
    h3: (props: ComponentPropsWithoutRef<"h3">) => (
      <BlogHeading as="h3" {...props} />
    ),
    h4: (props: ComponentPropsWithoutRef<"h4">) => (
      <BlogHeading as="h4" {...props} />
    ),
    p: BlogParagraph,
    a: BlogAnchor,
    table: BlogTable,
    blockquote: BlogBlockquote,
  };
}
