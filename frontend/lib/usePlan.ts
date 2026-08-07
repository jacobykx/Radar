"use client";

/** Shared plan state. One fetch, one refresh path, so every stage sees the same truth. */
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage, type Review } from "./api/client";

export interface Weights {
  risk: number;
  urgency: number;
  coverage_gap: number;
  change: number;
}

export interface Identity {
  username: string;
  ad_groups: string[];
  roles: string[];
}

export function usePlan() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [weights, setWeights] = useState<Weights | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [list, w, s] = await Promise.all([
      api.GET("/reviews", { params: { query: {} } }),
      api.GET("/plan/weights", {}),
      api.GET("/plan/summary", {}),
    ]);
    if (list.data) setReviews(list.data as Review[]);
    if (w.data) setWeights(w.data as Weights);
    if (s.data) setSummary(s.data as Record<string, unknown>);
    setLoading(false);
  }, []);

  useEffect(() => {
    api
      .GET("/permission", {})
      .then((r) => {
        if (r.data) setIdentity(r.data as unknown as Identity);
      })
      // An unreachable backend must not raise an unhandled rejection. The refresh below
      // owns the user-facing message; identity simply stays null and the UI hides the
      // role-gated controls.
      .catch(() => setIdentity(null));
    refresh().catch(() => {
      setError("Cannot reach the backend. Is it running on " + process.env.NEXT_PUBLIC_API_BASE + "?");
      setLoading(false);
    });
  }, [refresh]);

  /** Run a mutation, surface the API's rejection message, then resync. */
  const act = useCallback(
    async (fn: () => Promise<{ error?: unknown }>) => {
      setError(null);
      const result = await fn();
      if (result.error) {
        setError(errorMessage(result.error));
        return false;
      }
      await refresh();
      return true;
    },
    [refresh],
  );

  return { reviews, weights, identity, summary, error, setError, loading, refresh, act };
}

export type PlanState = ReturnType<typeof usePlan>;
