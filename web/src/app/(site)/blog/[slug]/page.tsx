import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getBlogMdxOverrides } from "@/components/blog/blog-mdx";
import { BlogPostHeader } from "@/components/blog/blog-post-header";
import { ContinueReading } from "@/components/blog/continue-reading";
import { ReadingProgress } from "@/components/blog/reading-progress";
import { ArticleWithToc } from "@/components/layout/article-with-toc";
import { resolveBlogCategory } from "@/lib/blog";
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

  const index = allPosts.findIndex((p) => p.url === page.url);
  const newer = index > 0 ? allPosts[index - 1] : undefined;
  const older =
    index >= 0 && index < allPosts.length - 1
      ? allPosts[index + 1]
      : undefined;

  const authorUrl =
    typeof page.data.authorUrl === "string" ? page.data.authorUrl : undefined;
  const readingTime =
    typeof page.data.readingTime === "string"
      ? page.data.readingTime
      : undefined;
  const category = resolveBlogCategory(page.data.tags);
  const description = page.data.excerpt ?? page.data.description;

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: page.data.title,
    datePublished: String(page.data.date),
    author: page.data.author
      ? {
          "@type": "Person",
          name: page.data.author,
          url: authorUrl,
        }
      : undefined,
    description,
    mainEntityOfPage: page.url,
  };

  return (
    <>
      <ReadingProgress />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="blog-page blog-post-page">
        <article className="blog-article">
          <BlogPostHeader
            title={page.data.title}
            date={String(page.data.date)}
            category={category}
            author={page.data.author}
            authorUrl={authorUrl}
            readingTime={readingTime}
          />
          <ArticleWithToc toc={toc}>
            <div className="prose docs-prose blog-prose">
              <MdxContent
                components={getMDXComponents(getBlogMdxOverrides())}
              />
            </div>
          </ArticleWithToc>
          <ContinueReading
            prev={
              older
                ? {
                    url: older.url,
                    title: older.data.title,
                    date: String(older.data.date),
                    category: resolveBlogCategory(older.data.tags),
                  }
                : null
            }
            next={
              newer
                ? {
                    url: newer.url,
                    title: newer.data.title,
                    date: String(newer.data.date),
                    category: resolveBlogCategory(newer.data.tags),
                  }
                : null
            }
          />
        </article>
      </div>
    </>
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
    alternates: {
      types: {
        "application/rss+xml": "/blog/rss.xml",
      },
    },
  };
}
