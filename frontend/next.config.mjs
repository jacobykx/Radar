/**
 * Build configuration.
 *
 * Two hosting shapes are supported from one codebase:
 *   - `npm run build` + `npm start` — Node serves it (Windows service, container, PaaS)
 *   - `npm run build:static` — a folder of files to drop on IIS or any static host
 *
 * The POC has no server-side work in it, so the static export is the whole app.
 */

/** Sub-path the app is served under, e.g. "/iap" for an IIS application. */
const basePath = process.env.NEXT_BASE_PATH ?? "";

/** "export" for a static site; unset for the Node server. */
const output = process.env.NEXT_OUTPUT;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next 16 blocks cross-origin dev-resource requests by default, which breaks
  // hydration when the app is opened on 127.0.0.1 rather than localhost.
  // Development only — it has no effect on a production build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  ...(output ? { output } : {}),
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
  // IIS serves a directory by looking for its default document, so exported pages are
  // written as `<route>/index.html` rather than `<route>.html`.
  trailingSlash: output === "export",
  env: {
    // Where the instance document is served from. Defaults to the copy shipped in
    // `public/`, so the app runs with no other process; point it at any URL returning
    // the same shape — a file share over HTTP, an intranet site, or the planning API
    // when that lands.
    NEXT_PUBLIC_INSTANCE_URL:
      process.env.NEXT_PUBLIC_INSTANCE_URL ?? `${basePath}/instances/2027-iap.json`,
  },
};

export default nextConfig;
