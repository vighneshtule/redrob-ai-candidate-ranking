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
from dataclasses import dataclass
from datetime import date
from typing import Iterator, Optional, Any

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
        candidate_embedding = None
        if semantic_cache:
            cid = str(raw_candidate.get("candidate_id", ""))
            candidate_embedding = semantic_cache.get(cid)

        # Extract features (integrity-first, veto short-circuit)
        features = extract_features(
            raw_candidate,
            title_taxonomy,
            industry_taxonomy,
            tier_a, tier_b, tier_c,
            debug=debug,
            today=today,
            candidate_embedding=candidate_embedding,
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
