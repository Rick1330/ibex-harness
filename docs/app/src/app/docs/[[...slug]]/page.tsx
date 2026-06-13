import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
} from "fumadocs-ui/page";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { DocsBreadcrumb } from "@/components/layout/breadcrumb";
import { OnThisPage } from "@/components/layout/toc";
import {
  GITHUB_BRANCH,
  GITHUB_OWNER,
  GITHUB_REPO,
  getContentFilePath,
} from "@/lib/github";
import { getPageLastModified } from "@/lib/page-meta";
import { source } from "@/lib/source";
import { useMDXComponents } from "@/mdx-components";

type PageProps = {
  params: Promise<{ slug?: string[] }>;
};

export default async function Page(props: PageProps) {
  const params = await props.params;
  const page = source.getPage(params.slug);
  if (!page) notFound();

  const MDX = page.data.body;
  const toc = page.data.toc ?? [];
  const tree = source.getPageTree();

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
        path: getContentFilePath(page.file.path),
        className:
          "inline-flex h-9 items-center gap-1.5 rounded-[4px] border border-border px-3 text-sm text-text-secondary hover:bg-panel-raised hover:text-text-primary",
      }}
      lastUpdate={getPageLastModified(page)}
    >
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody>
        <MDX components={useMDXComponents()} />
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
  const ogPath = `/docs/${slugPath}/opengraph-image`;

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
