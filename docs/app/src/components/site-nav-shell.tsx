import { SiteNav } from "@/components/site-nav";
import { getMobileNavData } from "@/lib/mobile-nav-data";

export function SiteNavShell() {
  const mobileNavData = getMobileNavData();

  return <SiteNav mobileNavData={mobileNavData} />;
}
