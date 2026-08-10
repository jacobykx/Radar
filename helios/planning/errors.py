"""Refusals the methodology requires.

Each one exists because a rule says the plan may not enter that state. They carry a
message written for the planner, not the developer, because it is shown verbatim.
"""

from __future__ import annotations


class PlanningError(Exception):
    """Base for every refusal. The server turns these into a 422 with the message."""


class RationaleRequired(PlanningError):
    """Rules 3 and 6: overriding a priority, or descoping, needs a reason on record."""


class CommentRequired(PlanningError):
    """Rule 10: returning a review at its gate needs a reason on record."""


class OriginConflict(PlanningError):
    """Rule 4: the mandated flag and the origin have to agree."""


class NotFound(PlanningError):
    """A ref that is not in the plan."""


class PlanFileError(PlanningError):
    """The plan file exists but cannot be read — corrupt, or not a plan file at all."""
