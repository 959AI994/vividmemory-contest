"""User isolation helpers."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.client import user_to_bank_id  # noqa: E402


def test_different_users_map_to_different_banks():
    banks = {user_to_bank_id(f"eval:run:user-{i}") for i in range(20)}
    assert len(banks) == 20


def test_bank_id_is_stable_hex_digest():
    bank = user_to_bank_id("eval:run_xxx:user-0")
    assert bank.startswith("contest-")
    digest = bank.removeprefix("contest-")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
