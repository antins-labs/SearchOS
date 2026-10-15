import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the installed production build separate from the development preview.
  distDir: process.env.SF_NEXT_DIST_DIR || ".next",
  // Do not cover mobile navigation or composer controls during local previews.
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.SF_API_PROXY || "http://127.0.0.1:8000"}/api/:path*` }];
  },
  // npm and web/start.sh run Next from this package directory. Pin Turbopack
  // here so an unrelated parent lockfile cannot become the project root.
  turbopack: { root: process.cwd() },
};

export default nextConfig;
