import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 静态导出：npm run build 后生成 out/ 目录，直接上传 Nginx 即可
  ...(process.env.STATIC_EXPORT === "true"
    ? { output: "export" }
    : {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8008"}/api/:path*`,
            },
          ];
        },
      }),
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
