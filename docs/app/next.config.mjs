import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "fumadocs-ui"],
  },
  redirects: async () => [
    {
      source: "/",
      destination: "/docs/getting-started/introduction",
      permanent: false,
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
