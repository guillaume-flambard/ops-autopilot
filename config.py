from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(default="llama3.2:3b", description="Ollama model to use")
    
    # Groq Configuration (fallback)
    groq_api_key: str = Field(default="", description="Groq API key for fallback")
    
    # App Configuration
    app_secret: str = Field(default="", description="Secret for session and password hashing")
    database_url: str = Field(default="sqlite:///./ops_autopilot.db", description="Database connection URL")
    default_locale: str = Field(default="fr", description="Default locale (fr or en)")
    
    # LLM Provider Selection
    llm_provider: str = Field(default="ollama", description="LLM provider: ollama or groq")
    
    @validator('default_locale')
    def validate_locale(cls, v):
        if v not in ['fr', 'en']:
            raise ValueError('locale must be either "fr" or "en"')
        return v
    
    @validator('llm_provider')
    def validate_llm_provider(cls, v):
        if v not in ['ollama', 'groq']:
            raise ValueError('llm_provider must be either "ollama" or "groq"')
        return v
    
    @validator('app_secret')
    def validate_app_secret(cls, v):
        if not v:
            raise ValueError('app_secret must be set for security')
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
