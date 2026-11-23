from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    openai_api_key: str | None = None

    # LLM-written retrieval probes (Context Router, Clarify). Off: an extra
    # model call while the applicant waits, with no measured gain
    # (scripts/eval/RESULTS.md). Re-measure before enabling.
    rag_query_expansion: bool = False

    # Real outbound email (app.services.email). Optional, same convention
    # as openai_api_key -- unset locally, every send just logs and no-ops
    # rather than crashing whatever triggered it.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    # Falls back to smtp_username if unset -- most providers require the
    # From address to match the authenticated account anyway.
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True

    # Browser origins allowed to call the API.
    # Comma-separated string, not list[str], on purpose -- pydantic-
    # settings JSON-decodes complex types from env vars, so a list[str]
    # field would demand ["http://a","http://b"] in .env and fail
    # confusingly on the plain comma-separated form people actually write
    cors_origins: str = "http://localhost:5173"

    # the frontend address that emailed links (reset, invitation) point
    # to; unset, the first CORS origin. Set it when the two differ
    app_base_url: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def frontend_base_url(self) -> str:
        if self.app_base_url:
            return self.app_base_url
        origins = self.cors_origin_list
        return origins[0] if origins else "http://localhost:5173"


settings = Settings()
