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
    auth_mode: str = Field(default="dev", alias="AUTH_MODE")
    auth_session_cookie_name: str = Field(default="buildwealth_session", alias="AUTH_SESSION_COOKIE_NAME")
    auth_session_days: int = Field(default=14, alias="AUTH_SESSION_DAYS")
    auth_dev_email: str = Field(default="owner@buildwealth.local", alias="AUTH_DEV_EMAIL")
    # In secure mode, registration closes once the first account exists — a
    # private instance must not accept strangers. Flip on deliberately for a
    # multi-user household.
    auth_allow_open_registration: bool = Field(default=False, alias="AUTH_ALLOW_OPEN_REGISTRATION")
    auth_oidc_provider_name: str = Field(default="Hosted Identity", alias="AUTH_OIDC_PROVIDER_NAME")
    auth_oidc_issuer_url: str = Field(default="", alias="AUTH_OIDC_ISSUER_URL")
    auth_oidc_client_id: str = Field(default="", alias="AUTH_OIDC_CLIENT_ID")
    auth_oidc_client_secret: str = Field(default="", alias="AUTH_OIDC_CLIENT_SECRET")
    auth_oidc_token_auth_method: str = Field(
        default="client_secret_basic",
        alias="AUTH_OIDC_TOKEN_AUTH_METHOD",
    )
    auth_oidc_redirect_uri: str = Field(default="", alias="AUTH_OIDC_REDIRECT_URI")
    auth_oidc_scopes: str = Field(default="openid email profile", alias="AUTH_OIDC_SCOPES")
    auth_oidc_jwks_uri: str = Field(default="", alias="AUTH_OIDC_JWKS_URI")
    auth_oidc_allowed_id_token_algs: str = Field(
        default="RS256 ES256",
        alias="AUTH_OIDC_ALLOWED_ID_TOKEN_ALGS",
    )
    auth_oidc_require_id_token: bool = Field(default=True, alias="AUTH_OIDC_REQUIRE_ID_TOKEN")
    auth_oidc_require_mfa: bool = Field(default=False, alias="AUTH_OIDC_REQUIRE_MFA")
    auth_oidc_authorization_endpoint: str = Field(
        default="",
        alias="AUTH_OIDC_AUTHORIZATION_ENDPOINT",
    )
    auth_oidc_token_endpoint: str = Field(default="", alias="AUTH_OIDC_TOKEN_ENDPOINT")
    auth_oidc_userinfo_endpoint: str = Field(default="", alias="AUTH_OIDC_USERINFO_ENDPOINT")
    auth_oidc_logout_url: str = Field(default="", alias="AUTH_OIDC_LOGOUT_URL")
    auth_post_login_redirect_path: str = Field(default="/v2", alias="AUTH_POST_LOGIN_REDIRECT_PATH")
    auth_post_logout_redirect_uri: str = Field(default="", alias="AUTH_POST_LOGOUT_REDIRECT_URI")
    auth_account_management_url: str = Field(default="", alias="AUTH_ACCOUNT_MANAGEMENT_URL")
    auth_password_reset_url: str = Field(default="", alias="AUTH_PASSWORD_RESET_URL")
    auth_mfa_enrollment_url: str = Field(default="", alias="AUTH_MFA_ENROLLMENT_URL")
    auth_passkey_enrollment_url: str = Field(default="", alias="AUTH_PASSKEY_ENROLLMENT_URL")
    control_db_path: Path = Field(default=Path("data/control/control.db"), alias="CONTROL_DB_PATH")
    workspace_root_dir: Path = Field(default=Path("data/workspaces"), alias="WORKSPACE_ROOT_DIR")
    secret_key_path: Path = Field(default=Path("data/control/local_secret.key"), alias="SECRET_KEY_PATH")

    snapshot_dir: Path = Field(default=Path("data/snapshots"), alias="SNAPSHOT_DIR")
    durable_storage_dir: Path = Field(default=Path("data/storage"), alias="DURABLE_STORAGE_DIR")
    backup_archive_dir: Path = Field(default=Path("data/backups"), alias="BACKUP_ARCHIVE_DIR")
    protection_policy_path: Path = Field(
        default=Path("data/security/protection_policy.json"),
        alias="PROTECTION_POLICY_PATH",
    )
    portfolio_review_packet_dir: Path = Field(
        default=Path("data/reports/portfolio_review_packets"),
        alias="PORTFOLIO_REVIEW_PACKET_DIR",
    )
    import_inbox_dir: Path = Field(default=Path("data/imports/inbox"), alias="IMPORT_INBOX_DIR")
    import_archive_dir: Path = Field(default=Path("data/imports/archive"), alias="IMPORT_ARCHIVE_DIR")
    import_workbench_dir: Path = Field(default=Path("data/imports/workbench"), alias="IMPORT_WORKBENCH_DIR")
    import_reports_dir: Path = Field(default=Path("data/imports/reports"), alias="IMPORT_REPORTS_DIR")
    conversation_dir: Path = Field(default=Path("data/conversations"), alias="CONVERSATION_DIR")
    plans_dir: Path = Field(default=Path("data/plans"), alias="PLANS_DIR")
    versioned_workspace_dir: Path = Field(default=Path("data/versioned"), alias="VERSIONED_WORKSPACE_DIR")
    git_integration_settings_path: Path = Field(
        default=Path("data/settings/git_integration.json"),
        alias="GIT_INTEGRATION_SETTINGS_PATH",
    )
    financial_profile_path: Path = Field(
        default=Path("data/profile/financial_profile.json"),
        alias="FINANCIAL_PROFILE_PATH",
    )
    recommendations_path: Path = Field(
        default=Path("data/recommendations/inbox.json"),
        alias="RECOMMENDATIONS_PATH",
    )
    today_review_checkpoint_path: Path = Field(
        default=Path("data/today/review_checkpoint.json"),
        alias="TODAY_REVIEW_CHECKPOINT_PATH",
    )

    portfolio_benchmark_default_symbols: str = Field(
        default="SPY",
        alias="PORTFOLIO_BENCHMARK_DEFAULT_SYMBOLS",
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
    openai_model: str = Field(default="gpt-5.5", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")
    llm_parallel_tool_calls: bool = Field(default=True, alias="LLM_PARALLEL_TOOL_CALLS")
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
    copilot_retrieval_focus_boost: bool = Field(
        default=True,
        alias="COPILOT_RETRIEVAL_FOCUS_BOOST",
    )
    copilot_context_snapshot_stale_after_seconds: float = Field(
        default=86400.0,
        alias="COPILOT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS",
    )
    context_embeddings_enabled: bool = Field(default=False, alias="CONTEXT_EMBEDDINGS_ENABLED")
    context_embedding_provider: str = Field(default="disabled", alias="CONTEXT_EMBEDDING_PROVIDER")
    context_embedding_model: str = Field(default="nomic-embed-text", alias="CONTEXT_EMBEDDING_MODEL")
    context_embedding_base_url: str = Field(
        default="http://localhost:11434",
        alias="CONTEXT_EMBEDDING_BASE_URL",
    )
    context_embedding_timeout_seconds: float = Field(default=5.0, alias="CONTEXT_EMBEDDING_TIMEOUT_SECONDS")

    openbb_provider: str = Field(default="yfinance", alias="OPENBB_PROVIDER")

    # Heartbeat cadence for scheduled price/snapshot sync. Daily by default so
    # freshness does not depend on the user clicking refresh; 0 disables.
    sync_interval_minutes: float = Field(default=1440.0, alias="SYNC_INTERVAL_MINUTES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
