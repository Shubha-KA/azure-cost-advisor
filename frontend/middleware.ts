import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // Kubernetes health probes follow redirects by default and will 404 if redirected to the gateway.
  // We intercept them here and return a 200 OK to keep the pod healthy.
  if (request.headers.get("user-agent")?.includes("kube-probe")) {
    return new NextResponse("OK", { status: 200 });
  }

  // If user doesn't have the finops_session cookie, they are not authenticated
  const session = request.cookies.get("finops_session");

  if (!session) {
    // Save the requested URL so we could potentially redirect back after login
    // but for now we just send them to login which defaults to dashboard
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// See "Matching Paths" below to learn more
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - login (login page — must be accessible without session)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt (metadata files)
     */
    '/((?!api|login|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)',
  ],
};
