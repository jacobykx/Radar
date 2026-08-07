/**
 * The API client.
 *
 * Types come from `generated/schema.d.ts`, produced from the backend's OpenAPI schema
 * by `npm run generate:api`. Nothing in this file describes a request or response shape
 * by hand -- if the backend contract changes, regenerating is what surfaces the break,
 * at compile time rather than in production.
 */
import createClient from "openapi-fetch";

import type { paths } from "./generated/schema";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8010";

export const api = createClient<paths>({ baseUrl });

/** Everything the API can hand back for one review. */
export type Review =
  paths["/reviews"]["get"]["responses"]["200"]["content"]["application/json"][number];

export type Quarter = "Q1" | "Q2" | "Q3" | "Q4";
export const QUARTERS: Quarter[] = ["Q1", "Q2", "Q3", "Q4"];

/**
 * Surface a domain rejection as its message.
 *
 * The backend answers a methodology violation with `{detail, rule}` and a 4xx. The UI
 * shows that message rather than pre-empting the rule -- the API decides, the UI hints.
 */
export function errorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      return first.msg ?? "That change was rejected.";
    }
  }
  return "That change was rejected.";
}
