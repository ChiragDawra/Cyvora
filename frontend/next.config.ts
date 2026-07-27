import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export - this app is a single client-side page (no API routes, no SSR),
  // deployed as static files to S3 + CloudFront (see infra/cloudfront.tf).
  output: "export",
};

export default nextConfig;
