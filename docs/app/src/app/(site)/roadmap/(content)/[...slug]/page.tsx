import { getBreadcrumbItems } from "fumadocs-core/breadcrumb";
import { DocsBody, DocsPage } from "fumadocs-ui/page";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DocsBreadcrumb } from "@/components/layout/breadcrumb";
import { DocsFooterNav } from "@/components/layout/docs-footer-nav";
import { PageIntro } from "@/components/layout/page-intro";
import { OnThisPage } from "@/components/layout/toc";
import { GITHUB_BRANCH, GITHUB_OWNER, GITHUB_REPO } from "@/lib/github";
import { getPageLastModified } from "@/lib/page-meta";
import { getRoadmapContentFilePath } from "@/lib/roadmap-layout.config";
import { isMilestonePage } from "@/lib/roadmap-types";
import { roadmapSource } from "@/lib/source";
import { getMDXComponents } from "@/mdx-components";

type PageProps = Readonly<{
  params: Promise<{ slug: string[] }>;
}>;

export const dynamic = "force-static";

export default async function RoadmapDetailPage(props: PageProps) {
  const params = await props.params;
  const page = roadmapSource.getPage(params.slug);
  if (!page) notFound();

  const MdxContent = page.data.body;
  const toc = page.data.toc ?? [];
  const tree = roadmapSource.getPageTree();
  const breadcrumbs = getBreadcrumbItems(page.url, tree, {
    includePage: false,
  });
  const section =
    breadcrumbs.length > 0 ? String(breadcrumbs[0].name) : undefined;
  const isMilestone = isMilestonePage(params.slug);
  const hideIntroTitle = isMilestone;

  const rawDescription = page.data.description as string | undefined;
  const cleanDescription =
    rawDescription && !rawDescription.includes("**") ? rawDescription : undefined;

  const displayTitle =
    (page.data.fullTitle as string | undefined) ?? page.data.title;

  return (
    <DocsPage
      toc={toc}
      full={page.data.full}
      breadcrumb={{ component: <DocsBreadcrumb tree={tree} /> }}
      tableOfContent={{
        component: <OnThisPage items={toc} />,
      }}
      editOnGithub={{
        owner: GITHUB_OWNER,
        repo: GITHUB_REPO,
        sha: GITHUB_BRANCH,
        path: getRoadmapContentFilePath(page.file.path),
        className:
          "inline-flex h-9 items-center gap-1.5 rounded-[4px] border border-border px-3 text-sm text-text-secondary hover:bg-panel-raised hover:text-text-primary",
      }}
      lastUpdate={getPageLastModified(page, "content/roadmap")}
      footer={{ component: <DocsFooterNav /> }}
    >
      <PageIntro
        description={cleanDescription}
        hideTitle={hideIntroTitle}
        section={section}
        title={displayTitle}
      />

      <DocsBody className="docs-prose max-w-none">
        <MdxContent components={getMDXComponents()} />
      </DocsBody>

      <div className="mt-10 border-t border-border pt-6">
        <Link
          href="/roadmap"
          className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to roadmap overview
        </Link>
      </div>
    </DocsPage>
  );
}

export async function generateStaticParams() {
  return roadmapSource.generateParams();
}

export async function generateMetadata(props: PageProps): Promise<Metadata> {
  const params = await props.params;
  const page = roadmapSource.getPage(params.slug);
  if (!page) notFound();

  return {
    title: (page.data.fullTitle as string | undefined) ?? page.data.title,
    description: page.data.description,
  };
}
