import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the dev indicator off the sidebar footer (health dot / settings live bottom-left).
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
