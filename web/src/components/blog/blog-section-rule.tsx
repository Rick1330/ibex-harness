type BlogSectionRuleProps = Readonly<{
  children: string;
  id?: string;
}>;

/** Mono label + extending hairline — editorial section divider. */
export function BlogSectionRule({ children, id }: BlogSectionRuleProps) {
  return (
    <div className="blog-section-rule" id={id}>
      <span className="blog-section-label">{children}</span>
      <span className="blog-section-rule-line" aria-hidden />
    </div>
  );
}
