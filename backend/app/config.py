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

    # Publication profile
    catalog_profile_name: str = "Florida Enterprise Catalog Profile"
    minimum_submission_score: int = 70

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
