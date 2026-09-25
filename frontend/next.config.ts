import type { NextConfig } from "next";

// In deployments the browser only talks to this app; /api/* and /withings/* are forwarded to the private
// backend by route handlers (src/lib/proxy.ts) that read BACKEND_INTERNAL_URL at runtime.
// Locally the frontend calls NEXT_PUBLIC_API_URL (default http://localhost:8000) directly.
const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
};

export default nextConfig;
