from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_env: str = "localhost"
    app_debug: bool = True
    app_secret_key: str = "change-me"
    app_domain: str = "localhost"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 2
    api_cors_origins: str = "http://localhost:3000,http://localhost:8000"

    mongo_uri: str = "mongodb://localhost:27017/email_platform"
    mongo_db: str = "email_platform"

    redis_uri: str = "redis://localhost:6379/0"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_concurrency: int = 4

    postal_api_url: str = "http://localhost:5000"
    postal_api_key: Optional[str] = None
    postal_mariadb_root_password: str = ""
    postal_mariadb_container: str = "ep-mariadb"
    postal_message_db: str = "postal-server-1"

    stream_optin_domain: str = "mail.localhost"
    stream_engaged_domain: str = "eng.localhost"
    stream_cold_domain: str = "out.localhost"

    warmup_enabled: bool = True
    warmup_optin_daily_cap: int = 500
    warmup_engaged_daily_cap: int = 200
    warmup_cold_daily_cap: int = 100
    warmup_ramp_percent: int = 20
    warmup_max_bounce_rate: float = 5.0
    warmup_max_complaint_rate: float = 0.3

    anthropic_api_key: Optional[str] = None
    claude_model: str = "claude-sonnet-4-6"

    s3_endpoint: Optional[str] = None
    s3_bucket: str = ""
    s3_public_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: str = "us-east-1"

    jwt_secret_key: str = "change-me-to-random-64-chars"
    jwt_expiry_hours: int = 24
    default_admin_email: str = "admin@localhost"

    log_level: str = "DEBUG"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
