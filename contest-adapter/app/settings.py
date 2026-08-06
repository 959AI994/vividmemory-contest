from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the contest adapter."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    vividmemory_base_url: str = Field(
        default="http://vividmemory:8888",
        validation_alias=AliasChoices("VIVIDMEMORY_BASE_URL", "vividmemory_base_url"),
        description="Internal base URL of vividmemory-api-slim",
    )
    http_timeout_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("ADAPTER_HTTP_TIMEOUT_SECONDS", "http_timeout_seconds"),
    )
    include_options_in_query: bool = Field(
        default=True,
        validation_alias=AliasChoices("ADAPTER_INCLUDE_OPTIONS_IN_QUERY", "include_options_in_query"),
        description="Append candidate options as supplemental context under the original query",
    )
    recall_budget: str = Field(
        default="high",
        validation_alias=AliasChoices("ADAPTER_RECALL_BUDGET", "recall_budget"),
    )
    recall_max_tokens: int = Field(
        default=8192,
        validation_alias=AliasChoices("ADAPTER_RECALL_MAX_TOKENS", "recall_max_tokens"),
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("ADAPTER_HOST", "host"),
    )
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("ADAPTER_PORT", "port"),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
