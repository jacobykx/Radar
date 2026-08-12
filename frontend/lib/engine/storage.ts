/**
 * Where the working copy lives.
 *
 * The hosted JSON is the starting point and is never written to. Everything a user
 * changes is kept in `localStorage` against the instance id, so a reload resumes the
 * session and "Reset" is simply dropping that key and re-reading the hosted document.
 * Export writes the working copy back out in the same shape (see `csv.downloadInstance`).
 */
import { normaliseInstance } from "./instance";
import type { InstanceDoc } from "./types";

export const STORAGE_PREFIX = "iap.instance.";

export function storageKey(instanceId: string): string {
  return `${STORAGE_PREFIX}${instanceId}`;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    // Private-mode browsers throw on access rather than returning null.
    return null;
  }
}

/** The working copy, or null when there is none or it cannot be read. */
export function loadWorkingCopy(instanceId: string): InstanceDoc | null {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(storageKey(instanceId));
    if (!raw) return null;
    return normaliseInstance(JSON.parse(raw) as Record<string, unknown>);
  } catch {
    // A corrupt or outdated working copy should not strand the user on a blank screen;
    // falling back to the hosted document is always safe.
    return null;
  }
}

export function saveWorkingCopy(doc: InstanceDoc): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(storageKey(doc.id), JSON.stringify(doc));
  } catch {
    // Quota exceeded: the session continues in memory rather than failing the edit.
  }
}

export function clearWorkingCopy(instanceId: string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(storageKey(instanceId));
  } catch {
    /* nothing to clear */
  }
}
