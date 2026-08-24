from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=True)


class Settings(BaseSettings):
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    llm_provider: str = Field(default="auto", alias="LLM_PROVIDER")
    model_name: str = Field(default="llama-3.1-8b-instant", alias="MODEL_NAME")
    gemini_model_name: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL_NAME")
    database_url: str = Field(default="sqlite:///./thread_ai.db", alias="DATABASE_URL")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    backend_url: str = Field(default="http://127.0.0.1:8020", alias="BACKEND_URL")
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    auth_secret: str = Field(default="change-this-before-deployment", alias="AUTH_SECRET")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")
    session_days: int = Field(default=14, alias="SESSION_DAYS")
    allow_dev_auth: bool = Field(default=False, alias="ALLOW_DEV_AUTH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
