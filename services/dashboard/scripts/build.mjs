#!/usr/bin/env node
/**
 * Copy static operator shell into dist/ for Cloudflare Pages.
 * No bundler — keeps 4.P.0 minimal and secret-free in deep links.
 */
import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
cpSync(join(root, "public"), dist, { recursive: true });

writeFileSync(
  join(dist, "_headers"),
  `/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  Permissions-Policy: geolocation=(), microphone=(), camera=()
`,
);

writeFileSync(
  join(dist, "_redirects"),
  `/*    /index.html   200
`,
);

console.log("dashboard: built static shell → dist/");
