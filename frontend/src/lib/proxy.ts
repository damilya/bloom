import type { NextRequest } from "next/server";

/**
 * Forwards a request to the private backend (deployments only). BACKEND_INTERNAL_URL is read per request,
 * at runtime, so changing it needs a restart rather than a rebuild. Bodies are streamed both ways, which
 * keeps large uploads out of memory and lets the chat's SSE stream through unbuffered.
 */
const HOP_BY_HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "host", "authorization",
  "content-length", "content-encoding"];

export async function proxy(req: NextRequest): Promise<Response> {
  const backend = process.env.BACKEND_INTERNAL_URL;
  if (!backend) {
    return Response.json({ detail: "BACKEND_INTERNAL_URL is not set on the frontend service" }, { status: 503 });
  }
  const target = `${backend.replace(/\/$/, "")}${req.nextUrl.pathname}${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  HOP_BY_HOP.forEach((h) => headers.delete(h));
  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      redirect: "manual", // pass redirects (e.g. Withings OAuth) through to the browser
      cache: "no-store",
      // @ts-expect-error: Node's fetch needs this to stream a request body
      duplex: "half",
    });
  } catch (e) {
    console.error(`proxy: ${req.method} ${target} failed`, e);
    return Response.json({ detail: `backend unreachable at ${backend}` }, { status: 502 });
  }
  const out = new Headers(upstream.headers);
  HOP_BY_HOP.forEach((h) => out.delete(h));
  return new Response(upstream.body, { status: upstream.status, statusText: upstream.statusText, headers: out });
}
