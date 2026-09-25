import { NextResponse, type NextRequest } from "next/server";

/**
 * Shared-password gate for deployments (browser's built-in login prompt, HTTP Basic auth).
 * Active only when APP_PASSWORD is set; any username is accepted. Covers pages AND the proxied
 * /api/* calls, so the backend (and the OpenAI credits behind it) is unreachable without it.
 */
export function middleware(req: NextRequest) {
  const password = process.env.APP_PASSWORD;
  if (!password) return NextResponse.next();
  const header = req.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));
      const supplied = decoded.slice(decoded.indexOf(":") + 1);
      if (supplied === password) return NextResponse.next();
    } catch {}
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Bloom", charset="UTF-8"' },
  });
}

export const config = {
  // everything except Next's static assets
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
