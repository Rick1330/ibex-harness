import type { Metadata } from "next";

import { LandingBenchmarks } from "@/components/landing/landing-benchmarks";
import { LandingCta } from "@/components/landing/landing-cta";
import { LandingFeatures } from "@/components/landing/landing-features";
import { LandingFlow } from "@/components/landing/landing-flow";
import { LandingFooter } from "@/components/landing/landing-footer";
import { LandingFrame } from "@/components/landing/landing-frame";
import { LandingHero } from "@/components/landing/landing-hero";
import { LandingMarquee } from "@/components/landing/landing-marquee";
import { LandingTerminal } from "@/components/landing/landing-terminal";
import { SITE_DESCRIPTION, SITE_URL } from "@/lib/site-seo";

const SOFTWARE_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "IBEX Harness",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Cross-platform",
  description: SITE_DESCRIPTION,
  url: SITE_URL,
  license: "https://github.com/Rick1330/ibex-harness/blob/main/LICENSE",
  isAccessibleForFree: true,
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
};

export const metadata: Metadata = {
  title: "IBEX Harness — Agent memory at the proxy",
  description: SITE_DESCRIPTION,
  openGraph: {
    title: "IBEX Harness — Agent memory at the proxy",
    description: SITE_DESCRIPTION,
    type: "website",
    url: SITE_URL,
    images: [
      {
        url: "/brand/android-chrome-512x512.png",
        width: 512,
        height: 512,
        alt: "IBEX Harness",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "IBEX Harness",
    description: SITE_DESCRIPTION,
    images: ["/brand/android-chrome-512x512.png"],
  },
};

/** Landing per the-whole.md — Lovable order, soft terminals, light CTA. */
export default function HomePage() {
  return (
    <LandingFrame>
      <a
        href="#overview"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-[calc(var(--site-nav-height)+0.5rem)] focus:z-50 focus:rounded-sm focus:bg-foreground focus:px-3 focus:py-2 focus:text-background"
      >
        Skip to content
      </a>
      <script type="application/ld+json">{JSON.stringify(SOFTWARE_JSON_LD)}</script>
      <LandingHero />
      <LandingMarquee />
      <LandingFeatures />
      <LandingFlow />
      <LandingTerminal />
      <LandingBenchmarks />
      <LandingCta />
      <LandingFooter />
    </LandingFrame>
  );
}
