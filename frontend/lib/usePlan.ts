"use client";

/**
 * The plan, bound to React.
 *
 * One instance document is the single source of truth for every stage. This hook owns
 * it: it loads the hosted JSON, resumes the working copy if there is one, runs workflow
 * commands against it and persists the result. Screens read through `lib/engine/select`
 * and write through `run` -- they never mutate the document themselves.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_INSTANCE_URL,
  errorMessage,
  fetchInstance,
  select,
  storage,
  type InstanceDoc,
} from "./engine";
import type { CommandResult } from "./engine/workflow";

export type { Weights, Identity } from "./engine";

export interface RunOutcome<R> {
  ok: boolean;
  result: R | null;
}

export function usePlan(url: string = DEFAULT_INSTANCE_URL) {
  const [doc, setDoc] = useState<InstanceDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * Load the instance.
   *
   * The hosted document is the baseline; a working copy in local storage wins unless
   * `fresh` is set, which is what "Reset to the hosted instance" does.
   */
  const load = useCallback(
    async (fresh = false) => {
      setLoading(true);
      try {
        const hosted = await fetchInstance(url);
        if (fresh) {
          storage.clearWorkingCopy(hosted.id);
          setDoc(hosted);
        } else {
          setDoc(storage.loadWorkingCopy(hosted.id) ?? hosted);
        }
        setError(null);
      } catch (cause) {
        setError(
          `${errorMessage(cause)} The UI reads its plan from ${url} — check that the instance ` +
            "document is being served there.",
        );
      } finally {
        setLoading(false);
      }
    },
    [url],
  );

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Run one workflow command.
   *
   * A rule violation throws a `DomainError`, which is shown to the user and leaves the
   * document exactly as it was -- the same contract the API answered a 4xx with.
   */
  const run = useCallback(
    <R,>(command: (current: InstanceDoc) => CommandResult<R>): RunOutcome<R> => {
      if (!doc) return { ok: false, result: null };
      try {
        const { doc: next, result } = command(doc);
        setDoc(next);
        storage.saveWorkingCopy(next);
        setError(null);
        return { ok: true, result };
      } catch (cause) {
        setError(errorMessage(cause));
        return { ok: false, result: null };
      }
    },
    [doc],
  );

  const reviews = useMemo(() => (doc ? select.reviews(doc) : []), [doc]);
  const summary = useMemo(() => (doc ? select.planSummary(doc) : null), [doc]);

  return {
    doc,
    url,
    loading,
    error,
    setError,
    identity: doc?.identity ?? null,
    weights: doc?.weights ?? null,
    reviews,
    summary,
    run,
    /** Re-read the hosted document, keeping the working copy. */
    reload: () => load(false),
    /** Throw the working copy away and start again from the hosted instance. */
    reset: () => load(true),
  };
}

export type PlanState = ReturnType<typeof usePlan>;
