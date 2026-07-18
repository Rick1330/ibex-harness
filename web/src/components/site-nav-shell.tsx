import { BrandLockup } from "@/components/brand-lockup";
import { SiteNavClient } from "@/components/site-nav-client";
import { getMobileNavData } from "@/lib/mobile-nav-data";

export function SiteNavShell() {
  const mobileNavData = getMobileNavData();

  return (
    <SiteNavClient
      mobileNavData={mobileNavData}
      brand={<BrandLockup showWordmark="always" />}
    />
  );
}
