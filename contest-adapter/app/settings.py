from __future__ import annotations

from functools import lru_cache
from typing import Literal

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

    # Phase 1 — per-message retain
    per_message_retain: bool = Field(
        default=False,
        validation_alias=AliasChoices("ADAPTER_PER_MESSAGE_RETAIN", "per_message_retain"),
        description="Retain each contest message as its own document when true",
    )
    retain_concurrency: int = Field(
        default=4,
        ge=1,
        le=32,
        validation_alias=AliasChoices("ADAPTER_RETAIN_CONCURRENCY", "retain_concurrency"),
        description="Bounded parallel retain calls when per_message_retain is true",
    )

    # Phase 3 — dual retrieval
    recall_include_observations: bool = Field(
        default=False,
        validation_alias=AliasChoices("ADAPTER_RECALL_INCLUDE_OBSERVATIONS", "recall_include_observations"),
        description="Ask the engine to include observation-type units in recall",
    )
    episode_prepend: bool = Field(
        default=False,
        validation_alias=AliasChoices("ADAPTER_EPISODE_PREPEND", "episode_prepend"),
        description="Prepend a second-channel raw-episode recall to the primary results",
    )
    episode_prepend_count: int = Field(
        default=2,
        ge=0,
        le=20,
        validation_alias=AliasChoices("ADAPTER_EPISODE_PREPEND_COUNT", "episode_prepend_count"),
        description="Maximum episodes prepended when episode_prepend is true",
    )

    # Phase 4B — options query rewriting
    options_in_query_mode: Literal["append", "none", "rewrite"] = Field(
        default="append",
        validation_alias=AliasChoices("ADAPTER_OPTIONS_IN_QUERY_MODE", "options_in_query_mode"),
        description="How options are folded into the recall query: append | none | rewrite",
    )

    # Phase 4C — near-duplicate suppression
    near_dedup_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("ADAPTER_NEAR_DEDUP_THRESHOLD", "near_dedup_threshold"),
        description="Token-Jaccard threshold for near-duplicate collapse; 0.0 disables",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
