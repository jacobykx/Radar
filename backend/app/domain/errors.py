"""Domain rule violations.

Raised by the services layer, mapped to HTTP 4xx by an exception handler in the API
layer. The rule lives here so it holds however the caller reached it.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base for every methodology violation."""

    status_code = 400


class RationaleRequired(DomainError):
    """A decision that must carry a rationale was attempted without one."""


class CommentRequired(DomainError):
    """Returning a review at sign-off requires a comment."""


class ReadOnlyField(DomainError):
    """Factor scores are facts from the scoring engine and are never user-editable."""

    status_code = 422


class OriginConflict(DomainError):
    """Origin and the mandated flag must agree."""


class StaleWrite(DomainError):
    """Optimistic concurrency: someone else changed this row first."""

    status_code = 409
