"""VividMemory contest benchmark runner (skeleton).

Minimal, dependency-light runner that:
- Ingests conversation datasets into the contest adapter via /add
- Runs /search per question with configured top_k
- Computes a cheap proxy metric (recall@k against evidence substrings)
- Writes checkpointed JSONL under runs/{run_id}/{dataset}/

Answer + judge stages are stubs (see plan Phase 0.3); the runner
scaffolding is the priority for Phase 0.2.
"""
