"""Tests for adapter Settings feature flags and SearchRequest.session_id."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.schemas import SearchRequest  # noqa: E402
from app.settings import Settings  # noqa: E402


_NEW_ENV_VARS = (
    "ADAPTER_PER_MESSAGE_RETAIN",
    "ADAPTER_RETAIN_CONCURRENCY",
    "ADAPTER_RECALL_INCLUDE_OBSERVATIONS",
    "ADAPTER_EPISODE_PREPEND",
    "ADAPTER_EPISODE_PREPEND_COUNT",
    "ADAPTER_OPTIONS_IN_QUERY_MODE",
    "ADAPTER_NEAR_DEDUP_THRESHOLD",
    "ADAPTER_INCLUDE_OPTIONS_IN_QUERY",
)


def _clear_new_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _NEW_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_preserve_current_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.per_message_retain is False
    assert settings.retain_concurrency == 4
    assert settings.recall_include_observations is False
    assert settings.episode_prepend is False
    assert settings.episode_prepend_count == 2
    assert settings.options_in_query_mode == "append"
    assert settings.near_dedup_threshold == 0.0
    assert settings.include_options_in_query is True


def test_env_var_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    monkeypatch.setenv("ADAPTER_PER_MESSAGE_RETAIN", "true")
    monkeypatch.setenv("ADAPTER_RETAIN_CONCURRENCY", "8")
    monkeypatch.setenv("ADAPTER_RECALL_INCLUDE_OBSERVATIONS", "true")
    monkeypatch.setenv("ADAPTER_EPISODE_PREPEND", "true")
    monkeypatch.setenv("ADAPTER_EPISODE_PREPEND_COUNT", "5")
    monkeypatch.setenv("ADAPTER_OPTIONS_IN_QUERY_MODE", "rewrite")
    monkeypatch.setenv("ADAPTER_NEAR_DEDUP_THRESHOLD", "0.85")

    settings = Settings(_env_file=None)
    assert settings.per_message_retain is True
    assert settings.retain_concurrency == 8
    assert settings.recall_include_observations is True
    assert settings.episode_prepend is True
    assert settings.episode_prepend_count == 5
    assert settings.options_in_query_mode == "rewrite"
    assert settings.near_dedup_threshold == 0.85


def test_retain_concurrency_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    monkeypatch.setenv("ADAPTER_RETAIN_CONCURRENCY", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("ADAPTER_RETAIN_CONCURRENCY", "33")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_episode_prepend_count_negative_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    monkeypatch.setenv("ADAPTER_EPISODE_PREPEND_COUNT", "-1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_near_dedup_threshold_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    monkeypatch.setenv("ADAPTER_NEAR_DEDUP_THRESHOLD", "1.5")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_options_in_query_mode_accepts_valid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_new_env(monkeypatch)
    monkeypatch.setenv("ADAPTER_OPTIONS_IN_QUERY_MODE", "rewrite")
    assert Settings(_env_file=None).options_in_query_mode == "rewrite"

    monkeypatch.setenv("ADAPTER_OPTIONS_IN_QUERY_MODE", "none")
    assert Settings(_env_file=None).options_in_query_mode == "none"

    monkeypatch.setenv("ADAPTER_OPTIONS_IN_QUERY_MODE", "apend")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_search_request_session_id_optional() -> None:
    without = SearchRequest(query="q", user_id="u")
    assert without.session_id is None

    with_sid = SearchRequest(query="q", user_id="u", session_id="s1")
    assert with_sid.session_id == "s1"
