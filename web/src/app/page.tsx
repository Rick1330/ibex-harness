import type { Metadata } from "next";

import { AsciiBackground } from "@/components/landing/ascii-background";
import { LandingCta } from "@/components/landing/landing-cta";
import { LandingFeatures } from "@/components/landing/landing-features";
import { LandingFlow } from "@/components/landing/landing-flow";
import { LandingFooter } from "@/components/landing/landing-footer";
import { LandingHero } from "@/components/landing/landing-hero";
import { LandingMarquee } from "@/components/landing/landing-marquee";
import { LandingMetrics } from "@/components/landing/landing-metrics";
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

export default function HomePage() {
  return (
    <div className="ibex-landing relative min-h-screen text-foreground pt-[var(--site-nav-height)]">
      <script type="application/ld+json">{JSON.stringify(SOFTWARE_JSON_LD)}</script>
      <AsciiBackground />
      <LandingHero />
      <LandingMarquee />
      <LandingFeatures />
      <LandingFlow />
      <LandingTerminal />
      <LandingMetrics />
      <LandingCta />
      <LandingFooter />
    </div>
  );
}
