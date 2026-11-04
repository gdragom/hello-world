import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ["@bitget-ai/bitget-agent-sdk"],
  experimental: {
    serverActions: {
      bodySizeLimit: "8mb",
    },
    proxyClientMaxBodySize: "8mb",
  },
};

export default nextConfig;
