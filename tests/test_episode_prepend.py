"""Phase 3 — dual retrieval: observations + episode prepend."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.schemas import SearchRequest  # noqa: E402


def test_search_request_session_id_optional():
    """session_id remains optional (backwards compatible)."""
    r = SearchRequest(query="q", user_id="u")
    assert r.session_id is None
    r2 = SearchRequest(query="q", user_id="u", session_id="sess-1")
    assert r2.session_id == "sess-1"


def test_search_request_rejects_invalid_top_k_even_with_session_id():
    with pytest.raises(ValidationError):
        SearchRequest(query="q", user_id="u", session_id="sess-1", top_k=0)


class _FakeVM:
    """Records recall() calls to verify the adapter wires flags correctly."""

    def __init__(self, primary: list[dict], secondary: list[dict] | None = None):
        self.primary = primary
        self.secondary = secondary
        self.calls: list[dict] = []

    async def recall(
        self,
        *,
        bank_id: str,
        query: str,
        top_k: int,
        types=None,
        prefer_observations: bool = False,
        tags=None,
        tags_match: str = "any",
    ):
        self.calls.append(
            {
                "bank_id": bank_id,
                "query": query,
                "top_k": top_k,
                "types": types,
                "prefer_observations": prefer_observations,
                "tags": tags,
                "tags_match": tags_match,
            }
        )
        # First call = primary; subsequent calls = secondary/episodes.
        if len(self.calls) == 1:
            return self.primary
        return self.secondary or []


def _make_app_and_client(monkeypatch, settings_overrides: dict):
    """Build a TestClient with an overridden Settings + fake VM injected."""
    from fastapi.testclient import TestClient

    import importlib
    from app import main as main_module
    from app.settings import Settings

    # Reset settings singleton
    monkeypatch.setattr(main_module, "get_settings", lambda: Settings(_env_file=None, **settings_overrides))

    # Rebuild app + inject fake vm
    fake_vm = _FakeVM(
        primary=[
            {"id": "1", "text": "world fact", "scores": {"final": 0.9}},
        ],
        secondary=[
            {"id": "e1", "text": "raw episode text", "scores": {"final": 0.5}},
        ],
    )

    # Bypass lifespan — put state directly on app.
    app = main_module.app
    app.state.settings = main_module.get_settings()
    app.state.vm = fake_vm
    return TestClient(app), fake_vm


def test_recall_include_observations_flag_sets_types_and_prefer(monkeypatch):
    client, fake_vm = _make_app_and_client(
        monkeypatch,
        {"recall_include_observations": True},
    )
    resp = client.post(
        "/search",
        json={"query": "what happened", "user_id": "u1", "top_k": 5},
    )
    assert resp.status_code == 200
    call = fake_vm.calls[0]
    assert call["types"] == ["world", "experience", "observation"]
    assert call["prefer_observations"] is True


def test_recall_include_observations_can_be_disabled(monkeypatch):
    """The 2026-08-07 ship flipped the default to True (see FINAL_REPORT.md);
    this test verifies the flag still honours an explicit False override so
    users on the old profile can opt out."""
    client, fake_vm = _make_app_and_client(
        monkeypatch,
        {"recall_include_observations": False},
    )
    resp = client.post(
        "/search",
        json={"query": "what happened", "user_id": "u1", "top_k": 5},
    )
    assert resp.status_code == 200
    call = fake_vm.calls[0]
    assert call["types"] is None
    assert call["prefer_observations"] is False


def test_episode_prepend_flag_makes_secondary_recall(monkeypatch):
    client, fake_vm = _make_app_and_client(
        monkeypatch,
        {"episode_prepend": True, "episode_prepend_count": 2},
    )
    resp = client.post(
        "/search",
        json={
            "query": "what happened",
            "user_id": "u1",
            "session_id": "sess-abc",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    assert len(fake_vm.calls) == 2, "episode prepend should trigger a secondary recall"
    secondary = fake_vm.calls[1]
    assert secondary["types"] == ["observation"]
    assert secondary["tags"] == ["session:sess-abc"]
    # Prepended results appear first.
    data = resp.json()["data"]
    assert data[0]["id"] == "e1"


def test_episode_prepend_requires_session_id(monkeypatch):
    """Without session_id, secondary recall must be skipped."""
    client, fake_vm = _make_app_and_client(
        monkeypatch,
        {"episode_prepend": True, "episode_prepend_count": 2},
    )
    resp = client.post(
        "/search",
        json={"query": "what happened", "user_id": "u1", "top_k": 5},
    )
    assert resp.status_code == 200
    assert len(fake_vm.calls) == 1


def test_episode_prepend_disabled_by_default(monkeypatch):
    client, fake_vm = _make_app_and_client(monkeypatch, {})
    resp = client.post(
        "/search",
        json={
            "query": "what happened",
            "user_id": "u1",
            "session_id": "sess-abc",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    assert len(fake_vm.calls) == 1
