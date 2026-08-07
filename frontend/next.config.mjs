/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next 16 blocks cross-origin dev-resource requests by default, which breaks
  // hydration when the app is opened on 127.0.0.1 rather than localhost.
  // Development only — it has no effect on a production build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // The backend URL is environment configuration, never a committed constant.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8010",
  },
};

export default nextConfig;
