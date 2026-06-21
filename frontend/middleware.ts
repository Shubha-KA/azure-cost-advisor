import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_ROUTES = new Set([
  "/",
  "/login",
  "/api/auth/login",
  "/api/auth/callback",
]);

const PROTECTED_PREFIXES = [
  "/dashboard",
  "/chat",
  "/assistant",
  "/costs",
  "/recommendations",
  "/resources",
  "/onboarding",
  "/admin",
];

function isProtectedRoute(pathname: string) {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function middleware(request: NextRequest) {
  // Kubernetes health probes follow redirects by default and will 404 if redirected to the gateway.
  // We intercept them here and return a 200 OK to keep the pod healthy.
  if (request.headers.get("user-agent")?.includes("kube-probe")) {
    return new NextResponse("OK", { status: 200 });
  }

  const { pathname } = request.nextUrl;

  if (PUBLIC_ROUTES.has(pathname)) {
    return NextResponse.next();
  }

  const session = request.cookies.get("finops_session");

  if (!session && isProtectedRoute(pathname)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/login",
    "/dashboard/:path*",
    "/chat/:path*",
    "/assistant/:path*",
    "/costs/:path*",
    "/recommendations/:path*",
    "/resources/:path*",
    "/onboarding/:path*",
    "/admin/:path*",
    "/api/auth/login",
    "/api/auth/callback",
  ],
};
