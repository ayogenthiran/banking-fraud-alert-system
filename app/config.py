from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "Banking Fraud Detection API"
    environment: str = "local"
    aws_region: str = "us-east-1"
    sqs_queue_url: str = ""
    dynamodb_table_name: str = ""
    local_fallback_enabled: bool = True
    enable_auth: bool = False
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
