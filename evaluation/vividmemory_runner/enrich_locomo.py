"""Enrich a runner search_checkpoint.jsonl into the LoCoMo pipeline's
input format (answer + evaluate).

Reads:
- The raw LoCoMo dataset (for speaker_a/speaker_b names, keyed by sample_id).
- runs/<run_id>/locomo/search_checkpoint.jsonl produced by the runner.

Writes a JSONL where each row has the fields the official
evaluation/agent-memory-leaderboard/locomo-refined/pipeline.py expects:
    id, question, gold_answer,
    speaker_1_name, speaker_1_memories,
    speaker_2_name, speaker_2_memories

Both speakers are ingested into a single bank by our LoCoMo loader, so all
retrieved memories are placed under `speaker_1_memories`; speaker_2 slots
remain empty. The pipeline template still renders cleanly because both slots
are labelled by name.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_speakers(locomo_path: Path) -> dict[str, tuple[str, str]]:
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


def format_memories(results: list[dict]) -> str:
    """Format /search results into a bullet block for the prompt.

    Preserves ordering and any temporal markers already present in the
    engine's fact content (e.g. '| When: July 2026').
    """
    lines: list[str] = []
    for r in results or []:
        content = str(r.get("content") or "").strip()
        if not content:
            continue
        created = r.get("created_at")
        if created:
            lines.append(f"- [{created}] {content}")
        else:
            lines.append(f"- {content}")
    return "\n".join(lines) if lines else "(no memories retrieved)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locomo-path", required=True, help="raw locomo10.json")
    ap.add_argument("--search-jsonl", required=True, help="runner search_checkpoint.jsonl")
    ap.add_argument("--output", required=True, help="pipeline-ready JSONL")
    args = ap.parse_args()

    speakers = load_speakers(Path(args.locomo_path))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with open(args.search_jsonl, encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") != "ok":
                continue
            conv_id = rec.get("conversation_id") or ""
            speaker_a, speaker_b = speakers.get(conv_id, ("speaker_a", "speaker_b"))
            row = {
                "id": rec["query_id"],
                "question": rec["query"],
                "gold_answer": rec.get("gold_answer") or "",
                "speaker_1_name": speaker_a,
                "speaker_1_memories": format_memories(rec.get("results") or []),
                "speaker_2_name": speaker_b,
                "speaker_2_memories": "",
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += 1

    print(f"wrote {total} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
