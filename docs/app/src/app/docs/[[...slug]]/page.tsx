import { getBreadcrumbItems } from "fumadocs-core/breadcrumb";
import { DocsBody, DocsPage } from "fumadocs-ui/page";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DocsBreadcrumb } from "@/components/layout/breadcrumb";
import { DocsFooterNav } from "@/components/layout/docs-footer-nav";
import { FeedbackWidget } from "@/components/layout/feedback";
import { PageIntro } from "@/components/layout/page-intro";
import { OnThisPage } from "@/components/layout/toc";
import {
  GITHUB_BRANCH,
  GITHUB_OWNER,
  GITHUB_REPO,
  getContentFilePath,
} from "@/lib/github";
import { getPageLastModified } from "@/lib/page-meta";
import { source } from "@/lib/source";
import { getMDXComponents } from "@/mdx-components";

/** Computed once at module load — shared by all doc pages. */
const pageTree = source.getPageTree();

type PageProps = Readonly<{
  params: Promise<{ slug?: string[] }>;
}>;

export const dynamic = "force-static";

export default async function Page(props: PageProps) {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const MdxContent = page.data.body;
  const toc = page.data.toc ?? [];
  const breadcrumbs = getBreadcrumbItems(page.url, pageTree, {
    includePage: false,
  });
  const section =
    breadcrumbs.length > 0 ? String(breadcrumbs[0].name) : undefined;

  return (
    <DocsPage
      toc={toc}
      full={page.data.full}
      breadcrumb={{ component: <DocsBreadcrumb tree={pageTree} /> }}
      tableOfContent={{
        component: <OnThisPage items={toc} />,
      }}
      editOnGithub={{
        owner: GITHUB_OWNER,
        repo: GITHUB_REPO,
        sha: GITHUB_BRANCH,
        path: getContentFilePath(page.file.path),
        className:
          "inline-flex h-9 items-center gap-1.5 rounded-[4px] border border-border px-3 text-sm text-text-secondary hover:bg-panel-raised hover:text-text-primary",
      }}
      lastUpdate={getPageLastModified(page)}
      footer={{ component: <DocsFooterNav /> }}
    >
      <PageIntro
        description={page.data.description}
        section={section}
        title={page.data.title}
      />
      <DocsBody className="docs-prose max-w-none">
        <MdxContent components={getMDXComponents()} />
        <FeedbackWidget pageId={page.file.path} />
      </DocsBody>
    </DocsPage>
  );
}

export async function generateStaticParams() {
  return source.generateParams();
}

export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const slugPath = params.slug?.length ? params.slug.join("/") : "";
  const ogPath = slugPath
    ? `/docs/${slugPath}/opengraph-image.png`
    : "/docs/opengraph-image.png";

  return {
    title: page.data.title,
    description: page.data.description,
    openGraph: {
      title: page.data.title,
      description: page.data.description,
      type: "article",
      siteName: "IBEX Harness Docs",
      images: [
        {
          url: ogPath,
          width: 1200,
          height: 630,
          alt: page.data.title,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: page.data.title,
      description: page.data.description,
      images: [ogPath],
    },
  };
}
