import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// Serve the prebuilt index as a static asset; avoid running Orama on Workers.
export function middleware(request: NextRequest) {
  if (process.env.NODE_ENV === "development" || process.env.SEARCH_EXTRACT === "1") {
    return NextResponse.next();
  }
  if (request.nextUrl.pathname === "/api/search") {
    return NextResponse.redirect(
      new URL("/search-index.json", request.url),
      308,
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/api/search",
};
