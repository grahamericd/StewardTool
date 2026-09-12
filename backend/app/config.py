from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./ai_data_steward.db"
    cors_origins: str = "http://localhost:5173"

    # Authentication: demo or oidc
    auth_mode: str = "demo"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_email_claim: str = "email"

    # Catalog publishing: mock or ckan
    catalog_publisher: str = "mock"
    ckan_base_url: str | None = None
    ckan_api_key: str | None = None
    ckan_owner_org: str | None = None

    # DataKitchen TestGen integration
    # mock = fully functional demo without a TestGen install
    # real = call an installed TestGen REST API
    testgen_mode: str = "mock"
    testgen_base_url: str | None = None
    testgen_auth_mode: str = "oauth_refresh"
    testgen_token: str | None = None
    testgen_oauth_client_id: str | None = None
    testgen_oauth_client_secret: str | None = None
    testgen_oauth_refresh_token: str | None = None
    testgen_project_code: str | None = None
    testgen_table_group_id: str | None = None
    testgen_test_suite_id: str | None = None
    testgen_timeout_seconds: int = 30
    testgen_poll_seconds: float = 1.0
    testgen_max_wait_seconds: int = 600

    # Publication profile
    catalog_profile_name: str = "Florida Enterprise Catalog Profile"
    minimum_submission_score: int = 70

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
