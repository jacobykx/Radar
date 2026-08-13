/**
 * Serve the built app with nothing but Node.
 *
 *     node serve.js            # serves ./frontend/out on http://127.0.0.1:3010
 *     node serve.js out 8080   # or any folder and port
 *
 * `npm run build:static` produces the folder; this serves it. No dependencies, so it
 * works when `npm install` will not -- a locked-down laptop, a broken npm cache, an
 * offline machine. It is a development and demo server: it listens on the loopback
 * address only and is not a substitute for IIS in a deployed environment.
 *
 * The app fetches its instance document over HTTP, which is why opening index.html
 * directly from the file system does not work and this exists.
 */
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

/** In the repository the build lands in frontend/out; unzipped on its own it sits alongside. */
const DEFAULTS = [path.join(__dirname, "frontend", "out"), path.join(__dirname, "out")];
const root = path.resolve(
  process.argv[2] || DEFAULTS.find((candidate) => fs.existsSync(candidate)) || DEFAULTS[0],
);
const port = Number(process.argv[3] || 3010);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".map": "application/json; charset=utf-8",
};

if (!fs.existsSync(root)) {
  console.error(`Nothing to serve: ${root} does not exist.`);
  console.error("Build it first with `npm run build:static`, or pass a folder:");
  console.error("    node serve.js <folder> [port]");
  process.exit(1);
}

const server = http.createServer((req, res) => {
  const url = decodeURIComponent((req.url || "/").split("?")[0]);
  let file = path.join(root, path.normalize(url).replace(/^(\.\.[/\\])+/, ""));

  // Never serve outside the folder, whatever the request asks for.
  if (!file.startsWith(root)) {
    res.writeHead(403).end("Forbidden");
    return;
  }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) {
    file = path.join(file, "index.html");
  }
  if (!fs.existsSync(file)) {
    res.writeHead(404, { "content-type": "text/plain" }).end(`Not found: ${url}`);
    return;
  }

  const type = TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream";
  // The instance is meant to be swapped without restarting, so it is never cached.
  const cache = url.startsWith("/instances/") ? "no-store" : "no-cache";
  res.writeHead(200, { "content-type": type, "cache-control": cache });
  fs.createReadStream(file).pipe(res);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving ${root}`);
  console.log(`Open http://127.0.0.1:${port}  —  Ctrl+C to stop`);
});

server.on("error", (error) => {
  if (error.code === "EADDRINUSE") {
    console.error(`Port ${port} is already in use. Try: node serve.js "${root}" ${port + 1}`);
    process.exit(1);
  }
  throw error;
});
