import path from "node:path";
import { fileURLToPath } from "node:url";

import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();
const appRoot = path.dirname(fileURLToPath(import.meta.url));

const isStaticExport = process.env.NEXT_STATIC_EXPORT === "1";

/** @type {import('next').NextConfig} */
const config = {
  ...(isStaticExport
    ? {
        output: "export",
      }
    : {}),
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "fumadocs-ui"],
    webpackMemoryOptimizations: true,
    // Custom webpack config disables the build worker by default; re-enable so
    // compilation heap stays isolated from the main Next process.
    webpackBuildWorker: true,
  },
  webpack: (webpackConfig, { dev }) => {
    webpackConfig.resolve.alias = {
      ...webpackConfig.resolve.alias,
      "@": path.join(appRoot, "src"),
    };
    // Serial compile modules on Windows — parallel jest-workers OOMs on
    // /roadmap/[...slug] and other MDX-heavy routes.
    if (dev && process.platform === "win32") {
      webpackConfig.parallelism = 1;
    }
    return webpackConfig;
  },
  outputFileTracingExcludes: {
    "*": [
      "./node_modules/mermaid/**",
      "./node_modules/@esbuild/**",
    ],
  },
  serverExternalPackages: ["mermaid"],
  // Redirects apply in `next dev` only; production uses public/_redirects on Pages.
  redirects: async () => [
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
};

export default withMDX(config);
