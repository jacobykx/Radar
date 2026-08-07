"""FRAME identity and authorisation.

FRAME Auth Service validates the AM Token the frontend sends and forwards a decoded
username and AD Group to the backend on every request. This module reads that context
and maps AD Groups to roles. It does not validate tokens, manage sessions or issue
credentials -- doing any of that here would be re-implementing the platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings

#: Headers populated by FRAME Auth Service once the AM Token is decoded.
USER_HEADER = "x-frame-user"
GROUPS_HEADER = "x-frame-ad-groups"


class Role(str, Enum):
    PLANNER = "planner"
    APPROVER = "approver"
    ADMIN = "admin"
    READER = "reader"


#: AD Group -> role. Group names are environment configuration, not secrets.
AD_GROUP_ROLES: dict[str, Role] = {
    "IAP_PLANNER": Role.PLANNER,
    "IAP_APPROVER": Role.APPROVER,
    "IAP_ADMIN": Role.ADMIN,
    "IAP_READER": Role.READER,
}


@dataclass(frozen=True)
class CurrentUser:
    username: str
    ad_groups: tuple[str, ...]
    roles: frozenset[Role]

    def has(self, *roles: Role) -> bool:
        return bool(self.roles & set(roles))


def _roles_for(groups: tuple[str, ...]) -> frozenset[Role]:
    roles = {AD_GROUP_ROLES[g] for g in groups if g in AD_GROUP_ROLES}
    return frozenset(roles or {Role.READER})


def get_current_user(
    x_frame_user: str | None = Header(default=None, alias=USER_HEADER),
    x_frame_ad_groups: str | None = Header(default=None, alias=GROUPS_HEADER),
) -> CurrentUser:
    """Resolve the caller from the context FRAME supplies.

    In local development there is no FRAME in front of the API, so a synthetic identity
    stands in. `auth_dev_mode` must be false in every deployed environment.
    """
    username = x_frame_user
    raw_groups = x_frame_ad_groups

    if not username:
        if not settings.auth_dev_mode:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No user context from FRAME Auth Service.",
            )
        username = settings.dev_username
        raw_groups = raw_groups or settings.dev_ad_groups

    groups = tuple(g.strip() for g in (raw_groups or "").split(",") if g.strip())
    return CurrentUser(username=username, ad_groups=groups, roles=_roles_for(groups))


def require(*roles: Role):
    """Dependency factory: refuse the request unless the caller holds one of `roles`."""

    def _guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has(*roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(r.value for r in roles)}.",
            )
        return user

    return _guard
