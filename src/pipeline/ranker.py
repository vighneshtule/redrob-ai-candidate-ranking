"""
src/pipeline/ranker.py
=======================
Ranking Engine for the Redrob candidate ranking system.

Takes a stream of raw candidate dicts, extracts features, applies the
weighted ranking formula with stuffing penalty and veto logic, and
returns the top-K ranked candidates using a min-heap for O(N log K)
memory efficiency.

Ranking formula
---------------
    base_score =
        0.35 × career_score
      + 0.25 × skill_score
      + 0.20 × behavior_score
      + 0.10 × integrity_score
      + 0.10 × profile_integrity_score

Stuffing penalty (soft multiplier)
-----------------------------------
    if stuffing_score > STUFFING_PENALTY_THRESHOLD:
        final_score = base_score × (1 - 0.5 × stuffing_score)

Veto logic
----------
    if veto_candidate:
        final_score = 0.0
        candidate is excluded from top-K entirely.

Tie-breaking
------------
    Primary : final_score descending
    Secondary: career_score descending (ML depth first)
    Tertiary : candidate_id ascending (deterministic lexicographic)

Public API
----------
    rank_candidates(
        candidates, title_taxonomy, industry_taxonomy,
        tier_a, tier_b, tier_c,
        top_k=100, debug=False, today=None,
    ) -> list[RankedCandidate]

    compute_final_score(features: CandidateFeatures) -> float

    RankedCandidate   — frozen dataclass
"""

from __future__ import annotations

import heapq
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import Iterator, List, Optional, Any

from src.config import STUFFING_PENALTY_THRESHOLD
from src.pipeline.feature_extractor import CandidateFeatures, extract_features
from src.pipeline.reasoning_generator import generate_explanation


# ---------------------------------------------------------------------------
# Ranking weights (must sum to 1.0)
# ---------------------------------------------------------------------------

_RANK_WEIGHTS: dict[str, float] = {
    "career":              0.30,
    "skill":               0.20,
    "behavior":            0.15,
    "integrity":           0.10,
    "profile_integrity":   0.10,
    "semantic":            0.15,
}
assert abs(sum(_RANK_WEIGHTS.values()) - 1.0) < 1e-9, "Rank weights must sum to 1.0"

# Stuffing penalty: final_score *= (1 - 0.5 * stuffing_score)
# Only applied when stuffing_score > STUFFING_PENALTY_THRESHOLD
_STUFFING_PENALTY_FACTOR: float = 0.5


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RankedCandidate:
    """
    Output of rank_candidates().  Frozen → hashable, thread-safe.

    Attributes
    ----------
    candidate_id : str
    final_score : float [0, 1]
        Weighted aggregate after stuffing penalty.  0.0 for vetoed candidates.
    rank : int
        1-indexed rank position (1 = best).
    feature_breakdown : dict
        All sub-scores for debug/export.  Same keys as CandidateFeatures.final_feature_vector.
    explanation : str
        Human-readable recruiter-facing reasoning string.
    """
    candidate_id: str
    final_score: float
    rank: int
    feature_breakdown: dict
    explanation: str


# ---------------------------------------------------------------------------
# Scoring function (public for unit testing)
# ---------------------------------------------------------------------------

def compute_final_score(features: CandidateFeatures) -> float:
    """
    Apply the ranking formula to a CandidateFeatures record.

    Returns 0.0 for vetoed candidates (before penalty calculation).
    Returns the stuffing-penalised weighted score for non-vetoed candidates.

    Parameters
    ----------
    features : CandidateFeatures

    Returns
    -------
    float in [0.0, 1.0]

    Complexity: O(1)
    """
    if features.veto_candidate:
        return 0.0

    # Weighted base score
    base = (
        _RANK_WEIGHTS["career"]            * features.career_score
        + _RANK_WEIGHTS["skill"]           * features.skill_score
        + _RANK_WEIGHTS["behavior"]        * features.behavior_score
        + _RANK_WEIGHTS["integrity"]       * features.integrity_score
        + _RANK_WEIGHTS["profile_integrity"] * features.profile_integrity_score
        + _RANK_WEIGHTS["semantic"]        * features.semantic_score
    )

    # Soft stuffing penalty
    if features.stuffing_score > STUFFING_PENALTY_THRESHOLD:
        penalty_multiplier = 1.0 - _STUFFING_PENALTY_FACTOR * features.stuffing_score
        base = base * max(penalty_multiplier, 0.0)

    return round(min(max(base, 0.0), 1.0), 6)


# ---------------------------------------------------------------------------
# Heap entry helpers (for tie-breaking)
# ---------------------------------------------------------------------------

def _heap_key(score: float, features: CandidateFeatures) -> tuple:
    """
    Build a min-heap comparison key for a bounded top-K heap.

    The heap retains the top-K candidates.  heapq is a min-heap, so the
    *root* (heap[0]) must always hold the *worst* entry currently in the
    top-K, so that it can be evicted when a better candidate arrives.

    To achieve this we store the key as (score, ...) — the candidate with
    the *lowest* score floats to the root and gets evicted first.

    Tie-breaking order (all ascending = ascending heap order):
      1. score asc          → worst score evicted first
      2. career_score desc  → -career_score asc (higher career ranks higher)
      3. candidate_id asc   → deterministic lexicographic tiebreak
    """
    return (score, -features.career_score, features.candidate_id)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def rank_candidates(
    candidates: Iterator[dict],
    title_taxonomy: dict,
    industry_taxonomy: dict,
    tier_a: dict,
    tier_b: dict,
    tier_c: dict,
    top_k: int = 100,
    debug: bool = False,
    today: Optional[date] = None,
    semantic_cache: Optional[dict] = None,
    jd_embedding: Optional[Any] = None,
) -> list[RankedCandidate]:
    """
    Stream candidates, extract features, rank them, and return top-K.

    Algorithm
    ---------
    1. For each candidate: extract_features() → compute_final_score().
    2. Skip vetoed candidates (final_score == 0.0) entirely.
    3. Maintain a min-heap of size top_k.
    4. After exhausting the iterator, sort heap descending.
    5. Assign ranks 1..K, generate explanations, return list[RankedCandidate].

    Parameters
    ----------
    candidates : Iterator[dict]
        Streaming candidate records (e.g. from load_candidates()).
    title_taxonomy, industry_taxonomy : dict
        Taxonomy dicts for career scorer.
    tier_a, tier_b, tier_c : dict
        Skill taxonomy tiers for skill scorer.
    top_k : int
        Number of top candidates to return (default 100).
    debug : bool
        Passed through to extract_features().  If True, vetoed candidates
        still have all scorers run (for full breakdown visibility).
    today : date, optional
        Reference date for recency calculations.

    Returns
    -------
    list[RankedCandidate]
        Sorted descending by final_score, length = min(top_k, non_vetoed_count).
        Ranks are 1-indexed.

    Complexity
    ----------
    Time  : O(N log K) — N candidates, heap size K.
    Memory: O(K) heap + O(1) per candidate processed.
    """
    # Min-heap entries: (sort_key_tuple, features, final_score)
    heap: list[tuple] = []

    for raw_candidate in candidates:
        # Extract features (integrity-first, veto short-circuit).
        # semantic_cache and jd_embedding are forwarded to extract_features(),
        # which performs the per-candidate embedding lookup internally.
        features = extract_features(
            raw_candidate,
            title_taxonomy,
            industry_taxonomy,
            tier_a, tier_b, tier_c,
            debug=debug,
            today=today,
            semantic_cache=semantic_cache,
            jd_embedding=jd_embedding,
        )

        # Skip vetoed candidates
        if features.veto_candidate:
            continue

        score = compute_final_score(features)
        key = _heap_key(score, features)

        if top_k > 0 and len(heap) < top_k:
            heapq.heappush(heap, (key, features, score))
        elif top_k > 0:
            # heap[0] is the *worst* candidate currently in the top-K.
            # Replace it only if the current candidate scores better
            # (i.e. its key is strictly greater than the root's key).
            if key > heap[0][0]:
                heapq.heapreplace(heap, (key, features, score))

    # Sort heap entries by key descending → highest score first.
    # Key is (score, -career, cid): larger key = better candidate.
    sorted_entries = sorted(heap, key=lambda entry: entry[0], reverse=True)

    # Assign ranks and build output
    results: list[RankedCandidate] = []
    for rank_idx, (_, features, score) in enumerate(sorted_entries, start=1):
        explanation = generate_explanation(features, score)
        breakdown = dict(features.final_feature_vector)
        breakdown["final_score"] = score

        results.append(
            RankedCandidate(
                candidate_id=features.candidate_id,
                final_score=round(score, 6),
                rank=rank_idx,
                feature_breakdown=breakdown,
                explanation=explanation,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Parallel public function
# ---------------------------------------------------------------------------

def rank_candidates_parallel(
    candidates: List[dict],
    title_taxonomy: dict,
    industry_taxonomy: dict,
    tier_a: dict,
    tier_b: dict,
    tier_c: dict,
    top_k: int = 100,
    today: Optional[date] = None,
    semantic_cache: Optional[dict] = None,
    jd_embedding: Optional[Any] = None,
    n_workers: Optional[int] = None,
) -> list[RankedCandidate]:
    """
    Parallelized drop-in replacement for rank_candidates().

    Architecture
    ------------
    1. Partition *candidates* into ``n_workers`` contiguous batches.
    2. Spawn ``n_workers`` worker processes via ProcessPoolExecutor.
       Each worker calls ``_worker_init()`` once — taxonomies and the
       semantic cache are pickled *once per worker* at startup, not once
       per batch, so IPC overhead scales with N_WORKERS not N_CANDIDATES.
    3. Dispatch one ``score_batch()`` call per worker; collect futures.
    4. Merge all ``(sort_key, features, score)`` tuples from all workers
       in the main process.
    5. Run the existing Top-K min-heap exactly once over the merged list.
    6. Generate explanations for the Top-K candidates in the main process.

    Parameters
    ----------
    candidates : list[dict]
        The full loaded candidate list (NOT a generator — must be sliceable).
    title_taxonomy, industry_taxonomy : dict
        Career-scorer taxonomy dicts.
    tier_a, tier_b, tier_c : dict
        Skill-taxonomy tier dicts.
    top_k : int
        Number of top candidates to return (default 100).
    today : date, optional
        Reference date for recency calculations.
    semantic_cache : dict, optional
        Maps candidate_id -> embedding array.
    jd_embedding : array-like, optional
        Precomputed JD embedding.
    n_workers : int, optional
        Number of worker processes.  Defaults to ``os.cpu_count()`` capped at 8.

    Returns
    -------
    list[RankedCandidate]
        Identical ordering and scores to the serial ``rank_candidates()``.

    Notes
    -----
    * The function requires *candidates* to be a list (not a generator) so it
      can be sliced into batches.  Call ``list(load_candidates(...))`` first.
    * On Windows the ``spawn`` start-method is used automatically by
      ``ProcessPoolExecutor`` — all objects passed to the initializer must
      be picklable.  Numpy arrays and standard dicts satisfy this.
    * If ``n_workers == 1`` the function falls back to the serial path to
      avoid spawn overhead on small datasets or single-core machines.
    """
    # Import here to avoid circular imports at module load time.
    from src.pipeline.worker import _worker_init, score_batch

    effective_workers = min(
        n_workers or (os.cpu_count() or 1),
        8,                   # cap — diminishing returns beyond ~8 for this workload
        max(len(candidates), 1),  # never more workers than candidates
    )

    # Fall back to serial path for trivially small inputs or single-core machines.
    if effective_workers <= 1 or len(candidates) < 2:
        return rank_candidates(
            iter(candidates),
            title_taxonomy=title_taxonomy,
            industry_taxonomy=industry_taxonomy,
            tier_a=tier_a,
            tier_b=tier_b,
            tier_c=tier_c,
            top_k=top_k,
            today=today,
            semantic_cache=semantic_cache,
            jd_embedding=jd_embedding,
        )

    # Partition candidates into contiguous batches (one per worker).
    batch_size = math.ceil(len(candidates) / effective_workers)
    batches: list[list[dict]] = [
        candidates[i : i + batch_size]
        for i in range(0, len(candidates), batch_size)
    ]

    # --- Parallel scoring ---
    all_scored: list[tuple] = []   # (sort_key, features, score) from all workers

    with ProcessPoolExecutor(
        max_workers=effective_workers,
        initializer=_worker_init,
        initargs=(
            title_taxonomy,
            industry_taxonomy,
            tier_a,
            tier_b,
            tier_c,
            semantic_cache,
            jd_embedding,
            today,
        ),
    ) as executor:
        futures = {executor.submit(score_batch, batch): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            batch_results = future.result()   # list of (key, features, score)
            all_scored.extend(batch_results)

    # --- Top-K heap (main process, identical to serial implementation) ---
    heap: list[tuple] = []

    for key, features, score in all_scored:
        if top_k > 0 and len(heap) < top_k:
            heapq.heappush(heap, (key, features, score))
        elif top_k > 0 and key > heap[0][0]:
            heapq.heapreplace(heap, (key, features, score))

    # Sort descending — highest score first.
    sorted_entries = sorted(heap, key=lambda entry: entry[0], reverse=True)

    # --- Explanation generation + result assembly (main process only) ---
    results: list[RankedCandidate] = []
    for rank_idx, (_, features, score) in enumerate(sorted_entries, start=1):
        explanation = generate_explanation(features, score)
        breakdown = dict(features.final_feature_vector)
        breakdown["final_score"] = score

        results.append(
            RankedCandidate(
                candidate_id=features.candidate_id,
                final_score=round(score, 6),
                rank=rank_idx,
                feature_breakdown=breakdown,
                explanation=explanation,
            )
        )

    return results
