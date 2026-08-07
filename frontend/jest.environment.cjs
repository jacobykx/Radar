/**
 * jsdom with the Fetch API primitives restored.
 *
 * jsdom does not implement Request/Response/Headers, but openapi-fetch builds a real
 * Request before calling fetch -- so specs fail with "CustomRequest is not a constructor"
 * under the stock jsdom environment. Node 18+ provides these natively, and this
 * environment's constructor runs in the Node context, so they can be handed through to
 * the sandbox rather than pulling in a polyfill dependency.
 */
const JSDOMEnvironment = require("jest-environment-jsdom").default;

const WEB_GLOBALS = [
  "fetch",
  "Request",
  "Response",
  "Headers",
  "FormData",
  "Blob",
  "File",
  "ReadableStream",
  "TextEncoder",
  "TextDecoder",
  "AbortController",
  "AbortSignal",
  "structuredClone",
];

class WebApiEnvironment extends JSDOMEnvironment {
  constructor(config, context) {
    super(config, context);

    for (const name of WEB_GLOBALS) {
      if (this.global[name] === undefined && globalThis[name] !== undefined) {
        this.global[name] = globalThis[name];
      }
    }
  }
}

module.exports = WebApiEnvironment;
