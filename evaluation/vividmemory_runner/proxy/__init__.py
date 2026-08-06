"""Cheap proxy metric: substring recall@k against evidence texts."""

from __future__ import annotations

import re
from typing import Iterable


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _norm_tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def substring_hit(evidence_text: str, retrieved_contents: Iterable[str]) -> bool:
    """Return True if any retrieved content contains evidence_text as a
    case-insensitive substring, or if their token sets have Jaccard >= 0.5
    (fallback for lightly-paraphrased extraction).
    """
    ev_norm = evidence_text.strip()
    if not ev_norm:
        return False
    ev_lower = ev_norm.lower()
    ev_tokens = _norm_tokens(ev_norm)

    for content in retrieved_contents:
        c_lower = content.lower()
        if ev_lower in c_lower:
            return True
        # Loose fallback: high token overlap.
        c_tokens = _norm_tokens(content)
        if ev_tokens and c_tokens:
            inter = len(ev_tokens & c_tokens)
            if inter == 0:
                continue
            jac = inter / len(ev_tokens | c_tokens)
            if jac >= 0.5:
                return True
    return False


def recall_at_k(evidence_texts: list[str], retrieved_contents: list[str]) -> float:
    """Fraction of evidence texts that a retrieved item covers."""
    if not evidence_texts:
        return 0.0
    hits = sum(1 for e in evidence_texts if substring_hit(e, retrieved_contents))
    return hits / len(evidence_texts)
