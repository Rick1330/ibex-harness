import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  redirects: async () => [
    {
      source: "/",
      destination: "/docs/getting-started/introduction",
      permanent: false,
    },
  ],
};

export default withMDX(config);
