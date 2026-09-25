import type { NextConfig } from "next";

// In deployments the browser only talks to this app; /api/* is forwarded to the private backend
// (e.g. http://backend.railway.internal:8000). Locally the frontend calls NEXT_PUBLIC_API_URL directly.
const backend = process.env.BACKEND_INTERNAL_URL;

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
  async rewrites() {
    if (!backend) return [];
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/withings/:path*", destination: `${backend}/withings/:path*` },
    ];
  },
};

export default nextConfig;
