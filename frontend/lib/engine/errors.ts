/**
 * Domain rule violations.
 *
 * Thrown by the workflow layer and surfaced by the UI as the message the rule carries.
 * The rule lives here so it holds however the caller reached it -- a component, a test,
 * or a future API adapter.
 */

export class DomainError extends Error {
  /** The status the productionised API answers with, kept so the contract survives. */
  readonly status: number;
  readonly rule: string;

  constructor(message: string, rule = "DomainError", status = 400) {
    super(message);
    this.name = rule;
    this.rule = rule;
    this.status = status;
  }
}

/** A decision that must carry a rationale was attempted without one. */
export class RationaleRequired extends DomainError {
  constructor(message: string) {
    super(message, "RationaleRequired", 400);
  }
}

/** Returning a review at sign-off requires a comment. */
export class CommentRequired extends DomainError {
  constructor(message: string) {
    super(message, "CommentRequired", 400);
  }
}

/** Factor scores are facts from the scoring engine and are never user-editable. */
export class ReadOnlyField extends DomainError {
  constructor(message: string) {
    super(message, "ReadOnlyField", 422);
  }
}

/** Origin and the mandated flag must agree. */
export class OriginConflict extends DomainError {
  constructor(message: string) {
    super(message, "OriginConflict", 400);
  }
}

/** Optimistic concurrency: the row moved under the caller. */
export class StaleWrite extends DomainError {
  constructor(message: string) {
    super(message, "StaleWrite", 409);
  }
}

/** The caller's roles do not permit this action. */
export class Forbidden extends DomainError {
  constructor(message: string) {
    super(message, "Forbidden", 403);
  }
}

export function isDomainError(error: unknown): error is DomainError {
  return error instanceof DomainError;
}

export function errorMessage(error: unknown): string {
  if (isDomainError(error)) return error.message;
  if (error instanceof Error) return error.message;
  return "That change was rejected.";
}
