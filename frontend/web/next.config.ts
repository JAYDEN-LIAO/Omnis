import type { NextConfig } from 'next';

// 非静态模式（npm run dev）的 API 代理目标必须显式配置，禁止硬编码回退地址。
// 静态导出只产出静态文件，不发服务端请求，也不需要 rewrites。
const apiProxyTarget = process.env.NEXT_PUBLIC_API_BASE;

const nextConfig: NextConfig = {
  // 静态导出：npm run build 后生成 out/ 目录，直接上传 Nginx 即可
  ...(process.env.STATIC_EXPORT === 'true'
    ? { output: 'export' }
    : apiProxyTarget
      ? {
          async rewrites() {
            return [
              {
                source: '/api/:path*',
                destination: `${apiProxyTarget}/api/:path*`,
              },
            ];
          },
        }
      : {}),
};

export default nextConfig;
