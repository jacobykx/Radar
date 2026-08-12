/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next 16 blocks cross-origin dev-resource requests by default, which breaks
  // hydration when the app is opened on 127.0.0.1 rather than localhost.
  // Development only — it has no effect on a production build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Where the instance document is served from. Defaults to the copy in `public/`,
  // so the POC runs with no other process; point it at any URL returning the same
  // shape — an object store, a CDN, or the planning API when that lands.
  env: {
    NEXT_PUBLIC_INSTANCE_URL: process.env.NEXT_PUBLIC_INSTANCE_URL ?? "/instances/2027-iap.json",
  },
};

export default nextConfig;
