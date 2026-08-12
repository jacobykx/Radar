"""Identity and authorisation.

The API sits behind an authentication gateway -- an IIS site with Windows
Authentication, a reverse proxy, or any SSO front end -- which validates the sign-on
token and forwards a decoded username and AD groups on every request. This module reads
that context and maps AD groups to roles. It does not validate tokens, manage sessions
or issue credentials; doing any of that here would re-implement the gateway badly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings

#: Headers the gateway populates once the sign-on token is decoded. Configurable there,
#: fixed here -- both ends must agree, so the names live in one place.
USER_HEADER = "x-auth-user"
GROUPS_HEADER = "x-auth-groups"


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
    auth_user: str | None = Header(default=None, alias=USER_HEADER),
    auth_groups: str | None = Header(default=None, alias=GROUPS_HEADER),
) -> CurrentUser:
    """Resolve the caller from the context the gateway supplies.

    In local development there is no gateway in front of the API, so a synthetic
    identity stands in. `auth_dev_mode` must be false in every deployed environment.
    """
    username = auth_user
    raw_groups = auth_groups

    if not username:
        if not settings.auth_dev_mode:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No user context from the authentication gateway.",
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
