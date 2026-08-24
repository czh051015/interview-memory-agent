import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 双部署形态：
  // ① 开发：next dev（3000）→ rewrites 把 /api/* 代理到 FastAPI（8000）
  // ② 生产：next build 静态导出到 out/，由 FastAPI 托管（单进程，8000 一个端口全通）
  output: "export",
  trailingSlash: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
