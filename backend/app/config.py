from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Runtime / deployment
    app_env: str = "development"
    app_version: str = "0.4.4-h"
    public_app_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1"
    enable_api_docs: bool = True
    seed_demo_data: bool = True
    log_level: str = "INFO"

    database_url: str = "sqlite:///./ai_data_steward.db"
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    # Authentication: demo or oidc.
    # Real authentication is Stage 4.4b. A production deployment must not
    # remain in demo mode once 4.4b is installed.
    auth_mode: str = "demo"
    auth_secret_key: str | None = None
    auth_token_hours: int = 8
    auth_password_min_length: int = 12
    auth_login_max_failures: int = 5
    auth_login_window_minutes: int = 15
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    @model_validator(mode="after")
    def validate_runtime(self):
        env = self.app_env.lower().strip()
        if env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV must be development, test, or production")

        if env == "production":
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS cannot contain * in production")
            if "*" in self.trusted_host_list:
                raise ValueError("TRUSTED_HOSTS cannot contain * in production")
            if self.seed_demo_data:
                raise ValueError("SEED_DEMO_DATA must be false in production")
            if self.enable_api_docs:
                raise ValueError("ENABLE_API_DOCS must be false in production")
            if self.auth_mode.lower() == "demo":
                raise ValueError("AUTH_MODE cannot be demo in production")
            if self.auth_mode.lower() == "local" and (not self.auth_secret_key or len(self.auth_secret_key) < 32):
                raise ValueError("AUTH_SECRET_KEY must be at least 32 characters for local production authentication")
            if self.auth_secret_key and "CHANGE_ME" in self.auth_secret_key.upper():
                raise ValueError("AUTH_SECRET_KEY still contains a placeholder value")
            if self.database_url and "CHANGE_ME" in self.database_url.upper():
                raise ValueError("DATABASE_URL still contains a placeholder value")
            if self.db_host:
                if not self.db_name or not self.db_user or not self.db_password:
                    raise ValueError("DB_NAME, DB_USER, and DB_PASSWORD are required when DB_HOST is set")
                if "CHANGE_ME" in self.db_password.upper():
                    raise ValueError("DB_PASSWORD still contains a placeholder value")
            if self.catalog_publisher.lower() == "ckan":
                if not self.ckan_base_url or not self.ckan_api_key:
                    raise ValueError("CKAN_BASE_URL and CKAN_API_KEY are required when CATALOG_PUBLISHER=ckan")
            if self.testgen_mode.lower() == "real":
                if not self.testgen_base_url:
                    raise ValueError("TESTGEN_BASE_URL is required when TESTGEN_MODE=real")
                auth_mode = self.testgen_auth_mode.lower()
                if auth_mode == "bearer" and not self.testgen_token:
                    raise ValueError("TESTGEN_TOKEN is required for bearer TestGen authentication")
                if auth_mode == "oauth_refresh" and (
                    not self.testgen_oauth_client_id
                    or not self.testgen_oauth_client_secret
                    or not self.testgen_oauth_refresh_token
                ):
                    raise ValueError(
                        "TestGen OAuth client ID, client secret, and refresh token are required "
                        "when TESTGEN_AUTH_MODE=oauth_refresh"
                    )

        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
