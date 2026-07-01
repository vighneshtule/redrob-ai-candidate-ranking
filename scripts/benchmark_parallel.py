"""
Benchmark: serial vs parallel candidate ranking.
Verifies output fidelity (identical Top-K IDs and scores) and measures speedup.
"""
from __future__ import annotations

import sys
import time
import tracemalloc
from pathlib import Path

# -- project root on sys.path -------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline.loader import load_candidates
from src.pipeline.ranker import rank_candidates, rank_candidates_parallel
from src.features.career_scorer import load_taxonomies
from src.features.skill_scorer import load_skill_taxonomy
from src.config import CANDIDATES_JSONL

TOP_K   = 100
LIMIT   = 5_000

def _load_resources():
    title_tax, industry_tax = load_taxonomies()
    tier_a, tier_b, tier_c, _ = load_skill_taxonomy()
    return title_tax, industry_tax, tier_a, tier_b, tier_c

def _load_candidates(limit):
    return list(load_candidates(CANDIDATES_JSONL, limit=limit, validate=False))

def run_serial(candidates, title_tax, industry_tax, tier_a, tier_b, tier_c):
    tracemalloc.start()
    t0 = time.perf_counter()
    results = rank_candidates(
        iter(candidates),
        title_taxonomy=title_tax,
        industry_taxonomy=industry_tax,
        tier_a=tier_a, tier_b=tier_b, tier_c=tier_c,
        top_k=TOP_K,
    )
    elapsed = time.perf_counter() - t0
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return results, elapsed, peak_mem / (1024 * 1024)

def run_parallel(candidates, title_tax, industry_tax, tier_a, tier_b, tier_c):
    tracemalloc.start()
    t0 = time.perf_counter()
    results = rank_candidates_parallel(
        candidates,
        title_taxonomy=title_tax,
        industry_taxonomy=industry_tax,
        tier_a=tier_a, tier_b=tier_b, tier_c=tier_c,
        top_k=TOP_K,
    )
    elapsed = time.perf_counter() - t0
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return results, elapsed, peak_mem / (1024 * 1024)

def verify_fidelity(serial_results, parallel_results):
    s_ids    = [r.candidate_id for r in serial_results]
    p_ids    = [r.candidate_id for r in parallel_results]
    s_scores = [r.final_score  for r in serial_results]
    p_scores = [r.final_score  for r in parallel_results]

    ids_match    = (s_ids    == p_ids)
    scores_match = (s_scores == p_scores)

    print("\n-- Fidelity Verification ----------------------------------------")
    print("  Top-K IDs match    : " + ("PASS" if ids_match    else "FAIL"))
    print("  Final scores match : " + ("PASS" if scores_match else "FAIL"))

    if not ids_match:
        for i, (si, pi) in enumerate(zip(s_ids, p_ids)):
            if si != pi:
                print(f"  First mismatch at rank {i+1}: serial={si!r}  parallel={pi!r}")
                break
    if not scores_match:
        for i, (ss, ps) in enumerate(zip(s_scores, p_scores)):
            if ss != ps:
                print(f"  First score mismatch at rank {i+1}: serial={ss}  parallel={ps}")
                break
    return ids_match and scores_match

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    print(f"Loading {LIMIT:,} candidates ...")
    title_tax, industry_tax, tier_a, tier_b, tier_c = _load_resources()
    candidates = _load_candidates(LIMIT)
    print(f"Loaded {len(candidates):,} candidates.\n")

    print("Running SERIAL ranking ...")
    serial_res,   s_time, s_mem = run_serial(
        candidates, title_tax, industry_tax, tier_a, tier_b, tier_c)

    print("Running PARALLEL ranking ...")
    parallel_res, p_time, p_mem = run_parallel(
        candidates, title_tax, industry_tax, tier_a, tier_b, tier_c)

    fidelity_ok = verify_fidelity(serial_res, parallel_res)

    speedup            = s_time / max(p_time, 1e-9)
    projected_serial   = (s_time / LIMIT) * 100_000 / 60
    projected_parallel = (p_time / LIMIT) * 100_000 / 60

    print("\n-- Benchmark Results --------------------------------------------")
    print(f"  Candidates tested : {LIMIT:,}")
    print(f"  Serial   runtime  : {s_time:.2f}s  |  peak memory: {s_mem:.1f} MB")
    print(f"  Parallel runtime  : {p_time:.2f}s  |  peak memory: {p_mem:.1f} MB")
    print(f"  Speedup           : {speedup:.2f}x")
    print(f"  Projected @ 100K  : serial ~{projected_serial:.0f} min -> parallel ~{projected_parallel:.0f} min")
    print("  Fidelity          : " + ("PASS" if fidelity_ok else "FAIL"))
    print("-" * 65)
    sys.exit(0 if fidelity_ok else 1)
