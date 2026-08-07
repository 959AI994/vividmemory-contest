"""Enrich a runner search_checkpoint.jsonl into the LoCoMo-refined pipeline's
input format (used by the leaderboard's answer + evaluate stages).

The `speaker_1_memories` / `speaker_2_memories` slot layout is the SHARED
contract across four of the six agent-memory-leaderboard benchmarks
(locomo-refined, longmemeval-s, beam, scriptmem). Routing memories by
speaker-attribution therefore benefits any of those datasets, not just LoCoMo.

Design choices (each is a general memory-framework improvement, not a
LoCoMo-specific hack):

1. Parse `| When: <event_date>` out of the extracted-fact content and use it
   as the visible timestamp prefix. The bank's `created_at` is the ingest
   time — identical across all memories of one conversation and therefore
   uninformative for temporal reasoning. Retain-produced event dates carry
   the real signal.
2. Strip trailing rationale segments (`| Involving:`, `| Why:`, etc.). These
   are retain metadata, not user-visible facts.
3. Split the top-K memories into speaker-1 / speaker-2 slots by whole-word
   name mention. Memories mentioning both speakers land in both slots
   (small duplication cost — the answer LLM handles repeats fine). Memories
   mentioning neither name fall through to the speaker-1 slot as a safe
   default so nothing is silently dropped.

`--conv-filter` is a general debug/experimentation aid: enrich only a
comma-separated whitelist of conversation_ids (e.g. `--conv-filter conv-30`).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Extracts `| When: X` from a retain-produced fact. X is captured up to the
# next `|` or end of string.
_WHEN_RE = re.compile(r"\|\s*When\s*:\s*(.+?)(?=\s*\||$)", re.IGNORECASE)


def load_speakers(locomo_path: Path) -> dict[str, tuple[str, str]]:
    """Return {sample_id: (speaker_a_name, speaker_b_name)}."""
    raw = json.loads(locomo_path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for item in raw:
        sample_id = item.get("sample_id") or ""
        conv = item.get("conversation") or {}
        out[sample_id] = (
            conv.get("speaker_a") or "speaker_a",
            conv.get("speaker_b") or "speaker_b",
        )
    return out


def clean_content(content: str) -> tuple[str, str | None]:
    """Return (core_fact, event_time_or_None).

    Splits on the first `|` to drop retain-side rationale suffixes, and
    separately extracts `| When: X` as the event timestamp.
    """
    if not content:
        return "", None
    when_match = _WHEN_RE.search(content)
    event_time = when_match.group(1).strip() if when_match else None
    core = content.split("|", 1)[0].strip()
    return core, event_time


def mentions_name(text: str, name: str) -> bool:
    """Case-insensitive whole-word check for a speaker's first name."""
    if not name:
        return False
    return re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE) is not None


def format_memory_line(core: str, event_time: str | None, created_at: str | None) -> str:
    """Format one memory as `- (<time>) <fact>`.

    Prefers the retain-produced event time. Falls back to a truncated
    `created_at` (date only) when no event time is available. When neither
    is present, emits just the core fact.
    """
    if event_time:
        prefix = f"({event_time}) "
    elif isinstance(created_at, str) and "T" in created_at:
        prefix = f"({created_at.split('T', 1)[0]}) "
    elif created_at:
        prefix = f"({created_at}) "
    else:
        prefix = ""
    return f"- {prefix}{core}".strip()


def format_split(
    results: list[dict], speaker_a: str, speaker_b: str
) -> tuple[str, str]:
    """Return (speaker_1_block, speaker_2_block) with memories routed by
    speaker-attribution.

    Memories that mention both speakers go into both blocks. Memories that
    mention neither fall through to speaker_1 to avoid silently dropping
    anonymous facts.
    """
    lines_a: list[str] = []
    lines_b: list[str] = []
    a_first = (speaker_a or "").split()[0] if speaker_a else ""
    b_first = (speaker_b or "").split()[0] if speaker_b else ""
    for r in results or []:
        content = str(r.get("content") or "").strip()
        if not content:
            continue
        core, event_time = clean_content(content)
        if not core:
            continue
        line = format_memory_line(core, event_time, r.get("created_at"))
        in_a = mentions_name(core, a_first)
        in_b = mentions_name(core, b_first)
        if in_a and in_b:
            lines_a.append(line)
            lines_b.append(line)
        elif in_a:
            lines_a.append(line)
        elif in_b:
            lines_b.append(line)
        else:
            lines_a.append(line)
    block_a = "\n".join(lines_a) if lines_a else "(no memories retrieved)"
    block_b = "\n".join(lines_b) if lines_b else "(no memories retrieved)"
    return block_a, block_b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locomo-path", required=True, help="raw locomo10.json")
    ap.add_argument("--search-jsonl", required=True, help="runner search_checkpoint.jsonl")
    ap.add_argument("--output", required=True, help="pipeline-ready JSONL")
    ap.add_argument(
        "--conv-filter",
        default="",
        help="Comma-separated conversation_id whitelist (e.g., 'conv-30,conv-42'). "
             "Empty = include all conversations.",
    )
    args = ap.parse_args()

    speakers = load_speakers(Path(args.locomo_path))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conv_filter = {c.strip() for c in args.conv_filter.split(",") if c.strip()}
    total = 0
    skipped = 0
    with open(args.search_jsonl, encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            conv_id = rec.get("conversation_id") or ""
            if conv_filter and conv_id not in conv_filter:
                skipped += 1
                continue
            speaker_a, speaker_b = speakers.get(conv_id, ("speaker_a", "speaker_b"))
            block_a, block_b = format_split(rec.get("results") or [], speaker_a, speaker_b)
            row = {
                "id": rec["query_id"],
                "question": rec["query"],
                "gold_answer": rec.get("gold_answer") or "",
                "speaker_1_name": speaker_a,
                "speaker_1_memories": block_a,
                "speaker_2_name": speaker_b,
                "speaker_2_memories": block_b,
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += 1

    print(f"wrote {total} rows to {out_path} (skipped {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
