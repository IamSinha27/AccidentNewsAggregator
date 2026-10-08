import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server in .next/standalone, which the Docker image runs.
  output: "standalone",
};

export default nextConfig;
