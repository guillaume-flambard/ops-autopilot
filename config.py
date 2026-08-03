"""Application configuration loaded from environment variables.

Only reads environment / .env; no secrets are ever logged.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Legacy Ollama config (kept for scripts/check_ollama.py)
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(default="llama3.2:3b", description="Ollama model to use")

    # Groq Configuration (live LLM paths)
    groq_api_key: str = Field(default="", description="Groq API key for live LLM calls")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model id")

    # App Configuration
    app_secret: str = Field(default="", description="Secret for session / password pepper (optional in dev)")
    database_url: str = Field(default="sqlite:///./ops_autopilot.db", description="Database connection URL")
    default_locale: str = Field(default="fr", description="Default locale (fr or en)")

    # LLM Provider Selection (mock works offline)
    llm_provider: str = Field(default="mock", description="LLM provider: mock, groq (ollama kept for legacy script)")

    @validator("default_locale")
    def validate_locale(cls, v):
        if v not in ("fr", "en"):
            raise ValueError('locale must be either "fr" or "en"')
        return v

    @validator("llm_provider")
    def validate_llm_provider(cls, v):
        if v not in ("mock", "groq", "ollama"):
            raise ValueError('llm_provider must be one of "mock", "groq", "ollama"')
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
