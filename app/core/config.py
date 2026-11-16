from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting comes from environment variables and is validated at startup."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(pattern=r"^postgresql\+asyncpg://")
    api_key: str = Field(min_length=32)

    # Storage (uploaded files)
    storage_provider: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./data/uploads"
    s3_bucket: str | None = None
    aws_region: str | None = None

    # LLM
    llm_provider: Literal["fake", "anthropic", "bedrock"] = "fake"
    anthropic_model: str = "claude-opus-5-5"
    bedrock_llm_model: str = "anthropic.claude-opus-5-5"
    bedrock_fallback_model: str = "anthropic.claude-opus-4-8"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tokens: int = Field(default=16_000, gt=0)

    # Documents
    max_upload_bytes: int = Field(default=5_000_000, gt=0)
    max_document_chars: int = Field(default=50_000, gt=0)

    @model_validator(mode="after")
    def check_provider_settings(self) -> Self:
        problems = []
        if self.storage_provider == "s3" and not (self.s3_bucket and self.aws_region):
            problems.append("STORAGE_PROVIDER=s3 needs S3_BUCKET and AWS_REGION")
        if self.llm_provider == "bedrock" and not self.aws_region:
            problems.append("LLM_PROVIDER=bedrock needs AWS_REGION")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """Singleton: settings are parsed and validated once, then shared."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment
