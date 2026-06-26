import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BlogPostHeader } from "@/components/blog/blog-post-header";
import { RelatedPosts } from "@/components/blog/related-posts";
import { ArticleWithToc } from "@/components/layout/article-with-toc";
import { blogSource } from "@/lib/source";
import { getMDXComponents } from "@/mdx-components";

type BlogPostPageProps = Readonly<{
  params: Promise<{ slug: string }>;
}>;

export default async function BlogPostPage(props: BlogPostPageProps) {
  const { slug } = await props.params;
  const page = blogSource.getPage([slug]);
  if (!page) notFound();

  const MdxContent = page.data.body;
  const toc = page.data.toc ?? [];
  const allPosts = blogSource.getPages().sort(
    (a, b) =>
      new Date(String(b.data.date)).getTime() -
      new Date(String(a.data.date)).getTime(),
  );

  const related = allPosts.filter((p) => {
    if (p.url === page.url) return false;
    const tags = page.data.tags ?? [];
    return tags.some((tag) => p.data.tags?.includes(tag));
  });

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <ArticleWithToc toc={toc}>
        <article className="min-w-0">
          <BlogPostHeader
            title={page.data.title}
            date={String(page.data.date)}
            author={page.data.author}
            authorUrl={page.data.authorUrl as string | undefined}
            tags={page.data.tags}
            readingTime={page.data.readingTime as string | undefined}
          />
          <div className="prose docs-prose max-w-none">
            <MdxContent components={getMDXComponents()} />
          </div>
          <RelatedPosts
            posts={related.length > 0 ? related : allPosts}
            currentUrl={page.url}
          />
        </article>
      </ArticleWithToc>
    </div>
  );
}

export function generateStaticParams() {
  return blogSource.getPages().map((page) => ({
    slug: page.slugs[0] ?? page.slugs.join("/"),
  }));
}

export async function generateMetadata(
  props: BlogPostPageProps,
): Promise<Metadata> {
  const { slug } = await props.params;
  const page = blogSource.getPage([slug]);
  if (!page) notFound();

  return {
    title: page.data.title,
    description: page.data.excerpt ?? page.data.description,
  };
}
