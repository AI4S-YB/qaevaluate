import type { NextConfig } from "next";

const distDir = process.env.NODE_ENV === "production" ? ".next-prod" : ".next-dev";

const nextConfig: NextConfig = {
  distDir,
  typedRoutes: true
};

export default nextConfig;
