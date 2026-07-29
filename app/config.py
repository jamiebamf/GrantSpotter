from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    admin_api_key: str = "change-me"
    crawler_user_agent: str = "GrantSpotterBot/1.0"
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""
    companies_house_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    website_import_url: str = ""
    website_import_secret: str = ""
    auto_publish_min_score: int = 92
    max_pages_per_run: int = 150
    request_delay_seconds: float = 1.5
    schedule_hour_utc: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def settings() -> Settings:
    return Settings()
