"""Application settings.

The hosting environment supplies the database and the authentication gateway; nothing
here invents either. Connection details come from the environment and are never
committed.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IAP_", env_file=".env", extra="ignore")

    app_name: str = "IAP Planning Module"
    plan_year: int = 2027

    #: Postgres in every deployed environment. SQLite is a local-development fallback
    #: only, for machines with no database server installed.
    database_url: str = "sqlite+pysqlite:///./iap_local.db"

    #: The authentication gateway decodes the sign-on token and forwards user context.
    #: In local development there is no gateway in front of the API, so a synthetic
    #: identity can stand in -- but only when this is switched on deliberately.
    #:
    #: Defaults to false so the failure mode is a 401, not an unauthenticated caller
    #: silently granted every role. Local development opts in through .env; no deployed
    #: environment ever should.
    auth_dev_mode: bool = False
    dev_username: str = "local.developer"
    dev_ad_groups: str = "IAP_PLANNER,IAP_APPROVER,IAP_ADMIN"

    #: Local development origins only. Deployed, the frontend and backend are served
    #: from the same site, so this is set per environment and never widened to "*".
    cors_origins: str = (
        "http://localhost:3010,http://127.0.0.1:3010,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
