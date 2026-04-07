from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="BuildWealth Orchestrator", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_currency: str = Field(default="USD", alias="APP_CURRENCY")
    app_state: str = Field(default="MN", alias="APP_STATE")

    snapshot_dir: Path = Field(default=Path("data/snapshots"), alias="SNAPSHOT_DIR")
    ignidash_export_dir: Path = Field(default=Path("data/ignidash"), alias="IGNIDASH_EXPORT_DIR")
    import_inbox_dir: Path = Field(default=Path("data/imports/inbox"), alias="IMPORT_INBOX_DIR")
    import_archive_dir: Path = Field(default=Path("data/imports/archive"), alias="IMPORT_ARCHIVE_DIR")

    ghostfolio_api_base: str = Field(default="http://ghostfolio:3333/api", alias="GHOSTFOLIO_API_BASE")
    ghostfolio_security_token: str = Field(default="", alias="GHOSTFOLIO_SECURITY_TOKEN")
    ghostfolio_timeout_seconds: float = Field(default=20.0, alias="GHOSTFOLIO_TIMEOUT_SECONDS")
    ghostfolio_default_data_source: str = Field(default="YAHOO", alias="GHOSTFOLIO_DEFAULT_DATA_SOURCE")
    ghostfolio_default_currency: str = Field(default="USD", alias="GHOSTFOLIO_DEFAULT_CURRENCY")

    ignidash_app_base_url: str = Field(default="http://ignidash:3000", alias="IGNIDASH_APP_BASE_URL")
    ignidash_convex_url: str = Field(default="http://ignidash-convex-backend:3211", alias="IGNIDASH_CONVEX_URL")
    ignidash_convex_api_secret: str = Field(default="", alias="IGNIDASH_CONVEX_API_SECRET")
    ignidash_default_user_id: str = Field(default="buildwealth-local-user", alias="IGNIDASH_DEFAULT_USER_ID")
    ignidash_default_user_name: str = Field(default="BuildWealth", alias="IGNIDASH_DEFAULT_USER_NAME")

    planner_years_to_retirement: int = Field(default=30, alias="PLANNER_YEARS_TO_RETIREMENT")
    planner_annual_contribution_usd: float = Field(default=18000.0, alias="PLANNER_ANNUAL_CONTRIBUTION_USD")
    planner_expected_return_baseline: float = Field(default=0.065, alias="PLANNER_EXPECTED_RETURN_BASELINE")
    planner_expected_return_optimistic: float = Field(default=0.085, alias="PLANNER_EXPECTED_RETURN_OPTIMISTIC")
    planner_expected_return_conservative: float = Field(default=0.045, alias="PLANNER_EXPECTED_RETURN_CONSERVATIVE")
    planner_return_volatility: float = Field(default=0.14, alias="PLANNER_RETURN_VOLATILITY")
    planner_inflation: float = Field(default=0.025, alias="PLANNER_INFLATION")
    planner_monte_carlo_runs: int = Field(default=2000, alias="PLANNER_MONTE_CARLO_RUNS")
    planner_hsa_delta_default: float = Field(default=1000.0, alias="PLANNER_HSA_DELTA_DEFAULT")
    planner_marginal_tax_rate: float = Field(default=0.28, alias="PLANNER_MARGINAL_TAX_RATE")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")

    openbb_provider: str = Field(default="yfinance", alias="OPENBB_PROVIDER")

    sync_interval_minutes: float = Field(default=0.0, alias="SYNC_INTERVAL_MINUTES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
