import { createMDX } from "fumadocs-mdx/next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Wrangler platform proxy is for `next dev` only; during `next build` it can hang workers.
if (process.env.NODE_ENV === "development") {
  initOpenNextCloudflareForDev();
}

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "fumadocs-ui"],
    webpackMemoryOptimizations: true,
  },
  outputFileTracingExcludes: {
    "*": [
      "./node_modules/mermaid/**",
      "./node_modules/@esbuild/**",
    ],
  },
  serverExternalPackages: ["mermaid"],
  redirects: async () => [
    {
      source: "/",
      destination: "/docs/getting-started/introduction",
      permanent: false,
    },
    {
      source: "/docs",
      destination: "/docs/getting-started/introduction",
      permanent: false,
    },
    {
      source: "/roadmap/phase-3-context-system/:path*",
      destination: "/roadmap/phase-3-memory-engine/:path*",
      permanent: true,
    },
    {
      source: "/roadmap/phase-3-context-system",
      destination: "/roadmap/phase-3-memory-engine",
      permanent: true,
    },
    {
      source: "/milestones",
      destination: "/roadmap",
      permanent: false,
    },
    {
      source: "/status",
      destination: "/roadmap/current-state",
      permanent: true,
    },
  ],
  rewrites: async () => [
    {
      source: "/docs/:slug*/opengraph-image",
      destination: "/api/og/:slug*",
    },
  ],
};

export default withMDX(config);
