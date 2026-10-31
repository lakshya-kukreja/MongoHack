"""Application configuration and settings."""

from typing import Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = Field(default="development", description="Environment: development, test, production")
    HOST: str = Field(default="127.0.0.1", description="Host to bind application")
    PORT: int = Field(default=8000, description="Port to bind application")

    # Database
    MONGODB_URI: str = Field(
        default="",
        description="MongoDB Atlas connection URI. If empty, falls back to in-memory store for local testing.",
    )
    MONGODB_DB_NAME: str = Field(default="incident_investigator", description="MongoDB database name")

    # Embedding provider (Gemini defaults; OpenAI remains supported)
    EMBEDDING_PROVIDER: str = Field(default="gemini")
    EMBEDDING_API_KEY: str = Field(default="")
    EMBEDDING_MODEL_NAME: str = Field(default="gemini-embedding-2")
    EMBEDDING_DIMENSIONS: int = Field(
        default=1536,
        gt=0,
        description="Requested embedding dimension; must match backend/atlas_vector_index.json.",
    )

    # LLM provider (Gemini defaults; OpenAI remains supported)
    LLM_PROVIDER: str = Field(default="gemini")
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL_NAME: str = Field(default="gemini-3.8-flash")

    # CORS
    CORS_ORIGINS: Union[list[str], str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        description="Allowed CORS origins",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, list[str]]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
