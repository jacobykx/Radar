"""FastAPI application.

An authentication gateway fronts this service: it terminates auth and routes users
through the frontend. Nothing here implements login, sessions or tokens.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import governance, plan, reviews
from app.auth.gateway import CurrentUser, get_current_user
from app.core.config import settings
from app.domain.errors import DomainError

logging.basicConfig(level=logging.INFO)


def warn_on_unsafe_configuration() -> None:
    """Make an insecure local configuration impossible to miss in the logs."""
    log = logging.getLogger(__name__)
    if settings.auth_dev_mode:
        log.warning(
            "AUTH DEV MODE IS ON — requests without gateway user context are accepted as "
            "%r with groups %s. Never enable this outside local development.",
            settings.dev_username,
            settings.dev_ad_groups,
        )
    if settings.is_sqlite:
        log.warning(
            "Using the SQLite development fallback (%s). Deployed environments run "
            "Postgres; set IAP_DATABASE_URL.",
            settings.database_url,
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    warn_on_unsafe_configuration()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version="0.1.0",
    description=(
        "2LOD assurance planning: turns risk-scoring output and externally-mandated "
        "obligations into a shaped, capacity-feasible, signed-off annual plan."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    """A methodology violation is a client error, reported with the rule that failed."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "rule": exc.__class__.__name__},
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "plan_year": settings.plan_year}


@app.get("/permission", tags=["meta"])
def permission(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Who the gateway says the caller is, and what that entitles them to do."""
    return {
        "username": user.username,
        "ad_groups": list(user.ad_groups),
        "roles": sorted(r.value for r in user.roles),
    }


app.include_router(reviews.router)
app.include_router(plan.router)
app.include_router(governance.router)
