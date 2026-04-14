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
    conversation_dir: Path = Field(default=Path("data/conversations"), alias="CONVERSATION_DIR")
    plans_dir: Path = Field(default=Path("data/plans"), alias="PLANS_DIR")
    financial_profile_path: Path = Field(
        default=Path("data/profile/financial_profile.json"),
        alias="FINANCIAL_PROFILE_PATH",
    )
    recommendations_path: Path = Field(
        default=Path("data/recommendations/inbox.json"),
        alias="RECOMMENDATIONS_PATH",
    )

    ghostfolio_sidecar_base_url: str = Field(
        default="http://localhost:8411",
        alias="GHOSTFOLIO_SIDECAR_BASE_URL",
    )
    ghostfolio_benchmark_sidecar_path: str = Field(
        default="/v1/benchmark/compare",
        alias="GHOSTFOLIO_BENCHMARK_SIDECAR_PATH",
    )
    ghostfolio_attribution_sidecar_path: str = Field(
        default="/v1/attribution/compute",
        alias="GHOSTFOLIO_ATTRIBUTION_SIDECAR_PATH",
    )
    enable_ghostfolio_benchmark_sidecar: bool = Field(
        default=False,
        alias="ENABLE_GHOSTFOLIO_BENCHMARK_SIDECAR",
    )
    enable_ghostfolio_attribution_sidecar: bool = Field(
        default=False,
        alias="ENABLE_GHOSTFOLIO_ATTRIBUTION_SIDECAR",
    )
    engine_sidecar_timeout_seconds: float = Field(default=3.0, alias="ENGINE_SIDECAR_TIMEOUT_SECONDS")
    engine_sidecar_retry_count: int = Field(default=1, alias="ENGINE_SIDECAR_RETRY_COUNT")
    engine_health_probe_interval_seconds: float = Field(
        default=60.0,
        alias="ENGINE_HEALTH_PROBE_INTERVAL_SECONDS",
    )
    engine_sidecar_version_paths: str = Field(
        default="/version",
        alias="ENGINE_SIDECAR_VERSION_PATHS",
    )
    ghostfolio_sidecar_health_paths: str = Field(
        default="/health,/api/v1/health",
        alias="GHOSTFOLIO_SIDECAR_HEALTH_PATHS",
    )
    ignidash_sidecar_health_paths: str = Field(
        default="/health,/api/health",
        alias="IGNIDASH_SIDECAR_HEALTH_PATHS",
    )
    ghostfolio_sidecar_contract_version: int = Field(
        default=1,
        alias="GHOSTFOLIO_SIDECAR_CONTRACT_VERSION",
    )
    ignidash_sidecar_contract_version: int = Field(
        default=1,
        alias="IGNIDASH_SIDECAR_CONTRACT_VERSION",
    )
    portfolio_benchmark_default_symbols: str = Field(
        default="SPY",
        alias="PORTFOLIO_BENCHMARK_DEFAULT_SYMBOLS",
    )

    ignidash_sidecar_base_url: str = Field(
        default="http://localhost:8412",
        alias="IGNIDASH_SIDECAR_BASE_URL",
    )
    ignidash_scenario_sidecar_path: str = Field(
        default="/v1/scenario/simulate",
        alias="IGNIDASH_SCENARIO_SIDECAR_PATH",
    )
    enable_ignidash_scenario_sidecar: bool = Field(
        default=False,
        alias="ENABLE_IGNIDASH_SCENARIO_SIDECAR",
    )

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
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    copilot_max_history_messages: int = Field(default=24, alias="COPILOT_MAX_HISTORY_MESSAGES")
    copilot_max_tool_rounds: int = Field(default=6, alias="COPILOT_MAX_TOOL_ROUNDS")
    copilot_context_cache_enabled: bool = Field(default=True, alias="COPILOT_CONTEXT_CACHE_ENABLED")
    copilot_context_cache_max_entries: int = Field(default=128, alias="COPILOT_CONTEXT_CACHE_MAX_ENTRIES")
    copilot_context_research_cache_ttl_seconds: float = Field(
        default=180.0,
        alias="COPILOT_CONTEXT_RESEARCH_CACHE_TTL_SECONDS",
    )
    copilot_context_projection_cache_ttl_seconds: float = Field(
        default=120.0,
        alias="COPILOT_CONTEXT_PROJECTION_CACHE_TTL_SECONDS",
    )

    openbb_provider: str = Field(default="yfinance", alias="OPENBB_PROVIDER")

    sync_interval_minutes: float = Field(default=0.0, alias="SYNC_INTERVAL_MINUTES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
