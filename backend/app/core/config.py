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
    VECTOR_INDEX_NAME: str = Field(
        default="vector_index",
        min_length=1,
        description=(
            "Atlas Vector Search index name. Must match the deployed index; "
            "the name is chosen when the index is created (see "
            "backend/atlas_vector_index.json)."
        ),
    )

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
    LLM_GEMINI_THINKING_LEVEL: str = Field(
        default="low",
        description=(
            "Gemini thinking level (minimal | low | medium | high). "
            "Use 'none' to omit thinkingConfig and accept the provider default. "
            "Ignored for OpenAI."
        ),
    )
    LLM_MAX_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Total generation attempts including the first (1 disables retries).",
    )
    LLM_RETRY_BASE_DELAY_SECONDS: float = Field(
        default=0.5,
        ge=0,
        le=5,
        description="Base delay for exponential backoff between retries.",
    )
    LLM_RETRY_MAX_DELAY_SECONDS: float = Field(
        default=4.0,
        ge=0,
        le=30,
        description="Upper bound for a single jittered backoff delay.",
    )
    LLM_REQUEST_DEADLINE_SECONDS: float = Field(
        default=30.0,
        gt=0,
        le=300,
        description=(
            "Hard wall-clock budget for one generation call including retries. "
            "Keeps the documented 30s LLM timeout from growing silently."
        ),
    )

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

    @field_validator("LLM_GEMINI_THINKING_LEVEL")
    @classmethod
    def normalize_gemini_thinking_level(cls, v: str) -> str:
        """Keep the setting case-insensitive and fail fast on typos."""
        normalized = str(v).strip().lower()
        if normalized in {"", "none", "off", "default"}:
            # Empty means "do not send thinkingConfig"; the provider decides.
            return ""
        allowed = {"minimal", "low", "medium", "high"}
        if normalized not in allowed:
            raise ValueError(
                f"LLM_GEMINI_THINKING_LEVEL must be one of {sorted(allowed)} "
                f"(or 'none'); got '{v}'"
            )
        return normalized


settings = Settings()
