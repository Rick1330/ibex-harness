import { NextResponse, type NextRequest } from "next/server"

import { classifyPath } from "@/lib/classification"

export function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  if (
    pathname.startsWith("/dashboard/") &&
    classifyPath(pathname).status === "deferred"
  ) {
    const destination = request.nextUrl.clone()
    destination.pathname = "/deferred"
    destination.search = ""
    destination.searchParams.set("route", pathname)
    return NextResponse.rewrite(destination)
  }
  return NextResponse.next()
}

export const config = {
  matcher: ["/dashboard/:path*"],
}
