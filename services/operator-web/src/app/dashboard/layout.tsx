import { redirect } from "next/navigation"

import { isDashboardPreviewEnabled } from "@/lib/classification"

/**
 * The transplanted route tree is presentation-only until tenant-scoped APIs are
 * connected. Keep fixture imports out of production execution by gating the
 * entire dashboard subtree on the explicit, server-validated preview pair.
 */
export default function DashboardLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  if (!isDashboardPreviewEnabled()) {
    redirect("/login")
  }

  return children
}
