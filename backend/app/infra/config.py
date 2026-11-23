from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    openai_api_key: str | None = None

    @field_validator("database_url")
    @classmethod
    def _name_the_psycopg_driver(cls, value: str) -> str:
        """Neon and hosting dashboards hand out plain postgresql:// (or the
        older postgres://) addresses. SQLAlchemy reads those as the psycopg2
        driver, which this app does not install, so the app would crash on
        start. Naming psycopg here, once, means a pasted address works as
        given instead of depending on everyone remembering to edit it."""
        value = value.strip().strip("\"'")
        for plain in ("postgresql://", "postgres://"):
            if value.startswith(plain):
                return "postgresql+psycopg://" + value[len(plain):]
        return value

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

    # Permanent storage for uploaded files (optional). Unset, uploads/ on
    # local disk is the only copy, exactly as before. Set all five, and
    # every upload is also written to this S3-compatible bucket (Neon
    # Object Storage), with the local folders acting as a cache. Needed
    # wherever the disk is wiped on restart, such as Render's free tier.
    # The AWS_* names are the ones Neon writes into .env.local, so they
    # can be copied across unchanged.
    upload_bucket: str | None = None
    aws_endpoint_url_s3: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None

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
