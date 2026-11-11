import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api/* is proxied to the backend so the session
// cookie can be httpOnly + SameSite=Strict (see docs/ARCHITECTURE.md).
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
