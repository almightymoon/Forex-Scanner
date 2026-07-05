/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    const api = process.env.API_URL || "http://127.0.0.1:8001";
    return [
      { source: "/health", destination: `${api}/health` },
      { source: "/api/:path*", destination: `${api}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
