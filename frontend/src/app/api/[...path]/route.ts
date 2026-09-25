import { proxy } from "@/lib/proxy";

// Deployments: forward to the private backend (see src/lib/proxy.ts). Locally the browser calls the backend directly.
export const dynamic = "force-dynamic";
export { proxy as GET, proxy as HEAD, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
