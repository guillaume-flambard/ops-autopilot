"""Application configuration loaded from environment variables.

Only reads environment / .env; no secrets are ever logged.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Groq Configuration (live LLM paths)
    groq_api_key: str = Field(default="", description="Groq API key for live LLM calls")
    groq_model: str = Field(default="llama-3.3-70b-versatile", description="Groq model id")

    # Ollama Configuration (local LLM, no quota)
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(default="qwen2.5:3b", description="Ollama model id")

    # Jina Reader Configuration (optional; lifts the r.jina.ai rate limit)
    jina_api_key: str = Field(default="", description="Optional Jina Reader API key for website analysis")

    # App Configuration
    app_secret: str = Field(default="", description="Secret for session / password pepper (optional in dev)")
    database_url: str = Field(default="sqlite:///./ops_autopilot.db", description="Database connection URL")
    default_locale: str = Field(default="fr", description="Default locale (fr or en)")

    # LLM Provider Selection (mock works offline)
    llm_provider: str = Field(default="mock", description="LLM provider: mock, ollama or groq")

    @field_validator("default_locale")
    @classmethod
    def validate_locale(cls, v):
        if v not in ("fr", "en"):
            raise ValueError('locale must be either "fr" or "en"')
        return v

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v):
        if v not in ("mock", "ollama", "groq"):
            raise ValueError('llm_provider must be one of "mock", "ollama" or "groq"')
        return v


# Global settings instance
settings = Settings()
