import { notFound } from "next/navigation";

import { createOgImageResponse } from "@/lib/og/template";
import { source } from "@/lib/source";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ slug: string[] }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { slug } = await context.params;
  const page = source.getPage(slug);
  if (!page) notFound();

  return createOgImageResponse({
    title: page.data.title,
    description: page.data.description ?? "",
  });
}

export function generateStaticParams() {
  return source.generateParams();
}
