"""Application settings.

FRAME supplies the database and auth; nothing here invents either. Connection details
come from the environment and are never committed.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IAP_", env_file=".env", extra="ignore")

    app_name: str = "IAP Planning Module"
    plan_year: int = 2027

    #: Postgres in every deployed environment. SQLite is a local-development fallback
    #: only, for machines without the FRAME toolchain.
    database_url: str = "sqlite+pysqlite:///./iap_local.db"

    #: FRAME Auth Service decodes the AM Token and forwards user context. In local
    #: development there is no FRAME in front of the API, so a synthetic identity can
    #: stand in -- but only when this is switched on deliberately.
    #:
    #: Defaults to false so the failure mode is a 401, not an unauthenticated caller
    #: silently granted every role. Local development opts in through .env; no deployed
    #: environment ever should.
    auth_dev_mode: bool = False
    dev_username: str = "local.developer"
    dev_ad_groups: str = "IAP_PLANNER,IAP_APPROVER,IAP_ADMIN"

    #: Local development origins only. In FRAME the frontend and backend are served
    #: behind the platform, so this is set per environment and never widened to "*".
    cors_origins: str = (
        "http://localhost:3010,http://127.0.0.1:3010,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
